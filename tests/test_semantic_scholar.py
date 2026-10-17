import requests
import pytest

from core.models import ReferencePaper, SeedPaper
from providers.http import RateLimitedError
from providers.semantic_scholar import SemanticScholarProvider
from storage.cache import ApiCache


class TitleSeedHttp:
    def __init__(self, candidates=None, search_error=None):
        self.calls = []
        self.candidates = candidates if candidates is not None else [self.published_candidate()]
        self.search_error = search_error

    @staticmethod
    def published_candidate(**changes):
        return {
            "paperId": "published-seed", "title": "Language Models Predict Empathy Gaps",
            "authors": [{"name": "Yu Hou"}, {"name": "Rachel Rudinger"}], "year": 2025,
            "externalIds": {"DOI": "10.18653/v1/2025.naacl-long.611"},
            "publicationTypes": ["Conference"], "venue": "NAACL", **changes,
        }

    def post_json(self, _url, **kwargs):
        self.calls.append(("batch", kwargs))
        return [{"paperId": "reference", "embedding": {"vector": [1.0, 0.0]}} for _ in kwargs["json"]["ids"]]

    def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/search"):
            if self.search_error:
                raise self.search_error
            return {"data": self.candidates}
        if url.endswith("/references"):
            assert "/published-seed/" in url
            return {"data": [{"citedPaper": {"paperId": "reference"}, "isInfluential": True}]}
        assert url.endswith("/published-seed")
        return {"paperId": "published-seed", "embedding": {"vector": [1.0, 0.0]}}


def test_doi_less_seed_uses_confirmed_published_identity_and_caches_metadata(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp()
    seed = SeedPaper(title="Language Models Predict Empathy Gaps", authors=["Yu Hou", "Rachel Rudinger"], year=2025)
    paper = ReferencePaper(doi="10.1000/reference")

    provider.enrich_with_seed(seed, [paper])

    assert paper.semantic_similarity == 1.0
    assert paper.is_influential_citation is True
    assert provider.seed_status == "resolved"
    assert provider.seed_match_method == "metadata"
    assert provider.seed_warning is None
    assert not provider.partial_errors
    assert seed.doi is None  # Search identity must not silently rewrite the original PDF metadata.
    assert len(provider.http.calls) == 4

    provider.enrich_with_seed(seed, [ReferencePaper(doi=paper.doi)])
    assert len(provider.http.calls) == 4

    provider.enrich_with_seed(seed, [ReferencePaper(doi=paper.doi)], force_refresh=True)
    assert len(provider.http.calls) == 8


@pytest.mark.parametrize("candidate_changes", [
    {"externalIds": {"ArXiv": "2503.01030"}, "venue": "arXiv", "publicationTypes": None},
    {"externalIds": {"DOI": "10.48550/arXiv.2503.01030"}, "venue": "arXiv"},
    {"authors": [{"name": "Another Author"}]},
    {"year": 2024},
    {"title": "Language Models Predict Empathy Gaps: Another Experiment"},
    {"externalIds": {"DOI": "10.1101/2025.03.01.123456"}, "venue": "bioRxiv"},
    {"publicationTypes": ["Dataset"]},
    {"publicationTypes": None, "venue": ""},
])
def test_title_fallback_rejects_preprints_or_conflicting_identity(tmp_path, candidate_changes):
    candidate = TitleSeedHttp.published_candidate(**candidate_changes)
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp([candidate])
    seed = SeedPaper(title="Language Models Predict Empathy Gaps", authors=["Yu Hou", "Rachel Rudinger"], year=2025)
    paper = ReferencePaper(doi="10.1000/reference")

    provider.enrich_with_seed(seed, [paper])

    assert paper.semantic_scholar_id == "reference"
    assert paper.semantic_similarity is None
    assert paper.is_influential_citation is None
    assert provider.seed_status == "unmatched"
    assert provider.seed_warning
    assert not provider.partial_errors
    assert len(provider.http.calls) == 2


def test_title_fallback_rejects_multiple_published_versions(tmp_path):
    first = TitleSeedHttp.published_candidate()
    second = TitleSeedHttp.published_candidate(paperId="another-version", externalIds={"DOI": "10.1000/other"})
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp([first, second])
    seed = SeedPaper(title=first["title"], authors=["Yu Hou", "Rachel Rudinger"])

    provider.enrich_with_seed(seed, [ReferencePaper(doi="10.1000/reference")])

    assert provider.seed_status == "unmatched"
    assert provider.seed_warning


def test_title_fallback_accepts_missing_year_but_ignores_preprint_candidate(tmp_path):
    published = TitleSeedHttp.published_candidate()
    preprint = TitleSeedHttp.published_candidate(paperId="preprint", externalIds={"ArXiv": "2503.01030"}, venue="arXiv")
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp([preprint, published])
    seed = SeedPaper(title=published["title"], authors=["Y. Hou", "Rachel Rudinger"])
    paper = ReferencePaper(doi="10.1000/reference")

    provider.enrich_with_seed(seed, [paper])

    assert provider.seed_status == "resolved"
    assert provider.seed_match_method == "metadata"
    assert paper.semantic_similarity == 1.0


def test_title_fallback_accepts_published_work_with_missing_optional_publication_type(tmp_path):
    # Live S2 metadata for 2025.wnu-1.12 supplies its publisher DOI and workshop venue, but no type.
    published = TitleSeedHttp.published_candidate(
        title="Tracking Evolving Relationship Between Characters in Books in the Era of Large Language Models",
        authors=[{"name": "Abhilasha Sancheti"}, {"name": "Rachel Rudinger"}],
        externalIds={"DOI": "10.18653/v1/2025.wnu-1.12"},
        venue="Proceedings of the The 7th Workshop on Narrative Understanding", publicationTypes=None,
    )
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp([published])
    seed = SeedPaper(title=published["title"], authors=["Abhilasha Sancheti", "Rachel Rudinger"])
    paper = ReferencePaper(doi="10.1000/reference")

    provider.enrich_with_seed(seed, [paper])

    assert provider.seed_status == "resolved"
    assert provider.seed_match_method == "metadata"
    assert paper.semantic_similarity == 1.0


def test_surname_only_pdf_author_is_not_sufficient_for_seed_identity(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp([TitleSeedHttp.published_candidate(authors=[{"name": "Hou"}])])
    seed = SeedPaper(title="Language Models Predict Empathy Gaps", authors=["Hou"])

    provider.enrich_with_seed(seed, [ReferencePaper(doi="10.1000/reference")])

    assert provider.seed_status == "unmatched"
    assert provider.seed_match_method is None


def test_known_seed_with_no_embedding_reports_missing_semantic_metric(tmp_path):
    class NoSeedEmbeddingHttp(SemanticScholarHttp):
        def post_json(self, *_args, **_kwargs):
            return [{"paperId": "seed"}, {"paperId": "influential", "embedding": {"vector": [1.0, 0.0]}}]

    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = NoSeedEmbeddingHttp()
    paper = ReferencePaper(doi="10.1000/influential")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [paper])

    assert provider.seed_status == "resolved"
    assert provider.seed_match_method == "doi"
    assert provider.seed_warning
    assert paper.semantic_similarity is None
    assert paper.is_influential_citation is True


def test_title_only_seed_without_authors_reports_missing_metadata_without_search(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp()

    provider.enrich_with_seed(SeedPaper(title="Language Models Predict Empathy Gaps"), [ReferencePaper(doi="10.1000/reference")])

    assert provider.seed_status == "insufficient_metadata"
    assert provider.seed_warning
    assert not provider.partial_errors
    assert len(provider.http.calls) == 1


def test_seed_search_rate_limit_does_not_discard_reference_metadata(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = TitleSeedHttp(search_error=RateLimitedError("Search rate limited"))
    seed = SeedPaper(title="Language Models Predict Empathy Gaps", authors=["Yu Hou", "Rachel Rudinger"])
    paper = ReferencePaper(doi="10.1000/reference")

    provider.enrich_with_seed(seed, [paper])

    assert paper.semantic_scholar_id == "reference"
    assert provider.seed_status == "api_error"
    assert provider.partial_errors == ["Search rate limited"]


def test_known_doi_missing_from_s2_does_not_switch_to_a_title_matched_preprint(tmp_path):
    class MissingKnownDoiHttp(TitleSeedHttp):
        def post_json(self, _url, **kwargs):
            self.calls.append(("batch", kwargs))
            return [None, {"paperId": "reference"}]

    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http = MissingKnownDoiHttp()
    seed = SeedPaper(title="Language Models Predict Empathy Gaps", doi="10.1000/seed", authors=["Yu Hou"])

    provider.enrich_with_seed(seed, [ReferencePaper(doi="10.1000/reference")])

    assert provider.seed_status == "unmatched"
    assert provider.seed_warning
    assert not provider.partial_errors
    assert len(provider.http.calls) == 1


class NoValidPaperIdsHttp:
    def post_json(self, *_args, **_kwargs):
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"error":"No valid paper ids given"}'
        raise requests.HTTPError(
            "400 Client Error: Bad Request",
            response=response,
        )


def test_batch_with_no_semantic_scholar_matches_is_not_a_provider_failure(tmp_path):
    cache = ApiCache(tmp_path / "cache.db")
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = NoValidPaperIdsHttp()
    paper = ReferencePaper(doi="10.1101/612218")

    provider.enrich([paper])

    assert paper.semantic_scholar_id is None
    assert cache.get("semantic_scholar", "doi:10.1101/612218") == {}


class SemanticScholarHttp:
    def post_json(self, *_args, **_kwargs):
        return [
            {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}},
            {"paperId": "influential", "embedding": {"vector": [1.0, 0.0]}},
            {"paperId": "incidental", "embedding": {"vector": [0.0, 1.0]}},
            {"paperId": "unclassified", "embedding": {"vector": [0.5, 0.5]}},
        ]

    def get_json(self, *_args, **_kwargs):
        return {
            "data": [
                {"citedPaper": {"paperId": "influential"}, "isInfluential": True},
                {"citedPaper": {"paperId": "incidental"}, "isInfluential": False},
            ]
        }


def test_influential_citation_uses_seed_to_reference_edge(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"), "test-key")
    provider.http = SemanticScholarHttp()
    seed = SeedPaper(doi="10.1000/seed")
    papers = [
        ReferencePaper(doi="10.1000/influential"),
        ReferencePaper(doi="10.1000/incidental"),
        ReferencePaper(doi="10.1000/unclassified"),
    ]

    provider.enrich_with_seed(seed, papers)

    assert papers[0].is_influential_citation is True
    assert papers[1].is_influential_citation is False
    assert papers[2].is_influential_citation is None


def test_public_semantic_scholar_requests_do_not_require_a_key(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    assert "x-api-key" not in provider.http.session.headers
    provider.http = SemanticScholarHttp()
    paper = ReferencePaper(doi="10.1000/influential")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [paper])

    assert paper.semantic_scholar_id == "influential"
    assert not provider.partial_errors


class FieldsSensitiveReferencesHttp:
    def __init__(self):
        self.calls = 0

    def get_json(self, *_args, **kwargs):
        self.calls += 1
        fields = kwargs["params"]["fields"]
        item = {"isInfluential": True}
        if "title" in fields:
            item["citedPaper"] = {"paperId": "reference", "title": "Reference"}
        return {"data": [item]}


def test_influential_edges_refresh_cached_responses_without_reference_ids(tmp_path):
    cache = ApiCache(tmp_path / "cache.db")
    cache.set(
        "semantic_scholar",
        "references:seed",
        {"data": [{"isInfluential": False}]},
    )
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = FieldsSensitiveReferencesHttp()

    edges = provider._influential_edges({"paperId": "seed"}, False)

    assert edges == {"reference": True}
    assert provider.http.calls == 1


def test_references_rate_limit_preserves_paper_metadata_and_similarity(tmp_path):
    class ReferencesRateLimitedHttp:
        def post_json(self, *_args, **_kwargs):
            return [
                {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}},
                {"paperId": "cited", "embedding": {"vector": [1.0, 0.0]}},
            ]

        def get_json(self, *_args, **_kwargs):
            raise RateLimitedError("Rate limited by references endpoint")

    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"), "test-key")
    provider.http = ReferencesRateLimitedHttp()
    paper = ReferencePaper(doi="10.1000/cited")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [paper])

    assert paper.semantic_scholar_id == "cited"
    assert paper.semantic_similarity == 1.0
    assert paper.is_influential_citation is None
    assert provider.partial_errors == ["Rate limited by references endpoint"]


def test_batch_rate_limit_preserves_cached_paper_metadata(tmp_path):
    class BatchRateLimitedHttp:
        def post_json(self, *_args, **_kwargs):
            raise RateLimitedError("Rate limited by batch endpoint")

        def get_json(self, *_args, **_kwargs):
            raise AssertionError("Do not send another request after a rate limit")

    cache = ApiCache(tmp_path / "cache.db")
    cache.set("semantic_scholar", "doi:10.1000/seed", {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}})
    cache.set("semantic_scholar", "doi:10.1000/cited", {"paperId": "cited", "embedding": {"vector": [1.0, 0.0]}})
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = BatchRateLimitedHttp()
    cited = ReferencePaper(doi="10.1000/cited")
    missing = ReferencePaper(doi="10.1000/missing")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [cited, missing])

    assert cited.semantic_scholar_id == "cited"
    assert cited.semantic_similarity == 1.0
    assert missing.semantic_scholar_id is None
    assert provider.partial_errors == ["Rate limited by batch endpoint"]


def test_windows_socket_refusal_is_reported_as_network_access_issue(tmp_path):
    def blocked(*_args, **_kwargs):
        raise requests.ConnectionError(
            "HTTPSConnectionPool(host='api.semanticscholar.org'): "
            "Failed to establish a new connection: [WinError 10013]"
        )

    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"))
    provider.http.session.post = blocked

    provider.enrich([ReferencePaper(doi="10.1000/test")])

    assert len(provider.partial_errors) == 1
    assert "Windows 拒絕 NextRead 連線到 Semantic Scholar" in provider.partial_errors[0]
    assert "check-nextread.cmd" in provider.partial_errors[0]
    assert "HTTPSConnectionPool" not in provider.partial_errors[0]
