import pytest

from core.models import ReferencePaper
from resolvers.crossref import CrossrefResolver, _normalize, score_candidate
from storage.cache import ApiCache


def test_crossref_candidate_score_rewards_matching_metadata():
    paper = ReferencePaper(title="A Study of Local Citation Networks", year=2024, authors=["Ada Lovelace"], source_name="Research Systems")
    matching = {
        "title": ["A Study of Local Citation Networks"],
        "published": {"date-parts": [[2024]]},
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "container-title": ["Research Systems"],
    }
    wrong = {"title": ["Unrelated Work"], "published": {"date-parts": [[1999]]}}
    assert score_candidate(paper, matching) > 0.95
    assert score_candidate(paper, wrong) < 0.3


def citation_candidate(**overrides):
    candidate = {
        "DOI": "10.1109/CVPR.2016.90",
        "title": ["Deep Residual Learning for Image Recognition"],
        "published": {"date-parts": [[2016]]},
        "author": [{"given": "Kaiming", "family": "He"}],
        "container-title": ["2016 IEEE Conference on Computer Vision and Pattern Recognition"],
    }
    return dict(candidate, **overrides)


RAW_CITATION = "He, K., Zhang, X., Ren, S., and Sun, J. 2016. Deep residual learning for image recognition. CVPR, pp. 770–778."


def test_raw_only_citation_resolves_with_title_year_and_author(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    candidate = citation_candidate()
    resolver.http.get_json = lambda *args, **kwargs: {"message": {"items": [candidate]}}
    paper = resolver.resolve(ReferencePaper(raw_reference=RAW_CITATION))
    assert paper.doi == candidate["DOI"].lower()
    assert paper.resolution_status == "high_confidence"
    assert paper.title == candidate["title"][0]
    assert paper.year == 2016
    assert paper.authors == ["Kaiming He"]
    assert paper.raw_reference == RAW_CITATION


@pytest.mark.parametrize("candidate", [
    citation_candidate(title=["Deep Residual Learning for Video Recognition"]),
    citation_candidate(published={"date-parts": [[2015]]}),
    citation_candidate(author=[{"family": "She"}]),
    citation_candidate(title=["Image Recognition"]),
    citation_candidate(author=[]),
    citation_candidate(published={}),
])
def test_raw_only_citation_rejects_insufficient_or_conflicting_evidence(tmp_path, candidate):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.http.get_json = lambda *args, **kwargs: {"message": {"items": [candidate]}}
    paper = resolver.resolve(ReferencePaper(raw_reference=RAW_CITATION))
    assert paper.doi is None
    assert paper.resolution_status == "unresolved"


def test_raw_only_candidate_requires_distinguishable_doi(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.http.get_json = lambda *args, **kwargs: {"message": {"items": [
        citation_candidate(), citation_candidate(DOI="10.1000/reprint"),
    ]}}
    paper = resolver.resolve(ReferencePaper(raw_reference=RAW_CITATION))
    assert paper.doi is None
    assert paper.resolution_confidence >= 0.9


def test_duplicate_raw_candidates_with_same_doi_are_not_ambiguous(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.http.get_json = lambda *args, **kwargs: {"message": {"items": [
        citation_candidate(), citation_candidate(),
    ]}}
    assert resolver.resolve(ReferencePaper(raw_reference=RAW_CITATION)).doi == "10.1109/cvpr.2016.90"


def test_raw_only_citation_does_not_override_existing_year_or_author():
    candidate = citation_candidate()
    assert score_candidate(ReferencePaper(raw_reference=RAW_CITATION, year=2020), candidate) == 0
    assert score_candidate(ReferencePaper(raw_reference=RAW_CITATION, authors=["Another Author"]), candidate) == 0


def test_author_or_year_inside_title_is_not_independent_evidence():
    candidate = citation_candidate(title=["What He Did in 2016: A Research Study"])
    assert score_candidate(ReferencePaper(raw_reference="Other, A. What He Did in 2016: A Research Study. 2016. Journal."), candidate) == 0
    assert score_candidate(ReferencePaper(raw_reference="He, K. What He Did in 2016: A Research Study. Journal."), candidate) == 0


@pytest.mark.parametrize("text, expected", [
    ("中文標題：語言模型", "中文標題 語言模型"),
    ("中文 ＡＩ ２０２４", "中文 ai 2024"),
    ("Café", "café"),
    ("Cafe\u0301", "café"),
    ("Ελληνικά и русский", "ελληνικά и русский"),
    ("भाषा मॉडल", "भाषा मॉडल"),
])
def test_normalization_retains_non_latin_text_and_canonical_accents(text, expected):
    assert _normalize(text) == expected


def test_chinese_source_titles_do_not_share_cache_or_accept_unrelated_candidates(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    calls = []
    titles = {"語言模型與同理心": "10.1000/empathy", "機器視覺的資料集": "10.1000/vision"}
    # Legacy ASCII normalization collapsed both titles into an empty key.
    resolver.cache.set("crossref", "source-title:", {"message": {"items": [
        {"DOI": "10.1000/wrong", "title": ["完全無關的舊資料"]},
    ]}})
    def get_json(url, **kwargs):
        if url.endswith("/works"):
            title = kwargs["params"]["query.title"]
            calls.append(title)
            return {"message": {"items": [{"DOI": titles[title], "title": [title]}]}}
        doi = url.split("/works/")[1]
        title = next(title for title, value in titles.items() if value == doi)
        return {"message": {"title": [title]}}
    resolver.http.get_json = get_json
    assert resolver.source_work("語言模型與同理心")[0].doi == "10.1000/empathy"
    assert resolver.source_work("機器視覺的資料集")[0].doi == "10.1000/vision"
    assert resolver.source_work("語言模型與同理心")[0].doi == "10.1000/empathy"
    assert calls == list(titles)
    resolver.http.get_json = lambda *args, **kwargs: {"message": {"items": [
        {"DOI": "10.1000/unrelated", "title": ["機器視覺的資料集"]},
    ]}}
    with pytest.raises(ValueError, match="sufficiently close"):
        resolver.source_work("語言模型與同理心", force_refresh=True)


def test_bibliographic_queries_ignore_legacy_cache_and_keep_unicode_separate(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.cache.set("crossref", "", {"message": {"items": [citation_candidate()]}})
    queries = []
    def get_json(url, **kwargs):
        queries.append(kwargs["params"]["query.bibliographic"])
        return {"message": {"items": []}}
    resolver.http.get_json = get_json
    for raw in ["中文研究甲", "中文研究乙", "中文研究甲"]:
        assert resolver.resolve(ReferencePaper(raw_reference=raw)).doi is None
    assert queries == ["中文研究甲", "中文研究乙"]


def test_punctuation_only_title_is_not_searchable(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.http.get_json = lambda *args, **kwargs: pytest.fail("An empty normalized title must not be searched")
    with pytest.raises(ValueError, match="DOI or paper title"):
        resolver.source_work("！？...")
