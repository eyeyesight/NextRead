from core.config import Settings
from core.models import ReferencePaper, SeedPaper
from core.pipeline import AnalysisPipeline
from resolvers.crossref import CrossrefResolver
from storage.cache import ApiCache
import pytest
import requests
from providers.http import NetworkAccessError


ENABLED = {"crossref": False, "openalex": False, "semantic_scholar": False}


def test_doi_path_needs_neither_pdf_nor_grobid(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    def source_work(_identifier, _refresh):
        return SeedPaper(title="Source", doi="10.1000/source"), [ReferencePaper(doi="10.1000/ref", title="A reference")]
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: source_work(identifier, refresh))
    monkeypatch.setattr(pipeline.grobid, "is_available", lambda: (_ for _ in ()).throw(AssertionError("GROBID used")))
    result = pipeline.analyze_identifier("10.1000/source", ENABLED)
    assert result.stats["reference_source"] == "crossref"
    assert len(result.references) == 1
    assert "尚未與論文 PDF 完整核對" in result.warnings[0]


def test_missing_crossref_references_are_explicit(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (SeedPaper(title="Source"), []))
    result = pipeline.analyze_identifier("10.1000/source", ENABLED)
    assert result.references == []
    assert result.provider_states["crossref"] == "no_references"
    assert any("沒有參考文獻清單" in warning for warning in result.warnings)


def test_optional_pdf_extraction_failure_keeps_unverified_crossref_result(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (
        SeedPaper(title="Source"), [ReferencePaper(doi="10.1000/ref")]
    ))
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda path: (_ for _ in ()).throw(ValueError("unsupported PDF")))
    result = pipeline.analyze_identifier("10.1000/source", ENABLED, pdf_path=tmp_path / "source.pdf")
    assert len(result.references) == 1
    assert result.stats["pdf_comparison"]["status"] == "unavailable"
    assert "尚未與論文 PDF 完整核對" in result.warnings[0]


def test_pdf_comparison_reports_doi_overlap_without_claiming_parity(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (
        SeedPaper(title="Source"), [ReferencePaper(doi="10.1000/shared"), ReferencePaper(doi="10.1000/crossref")]
    ))
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda path: [
        ReferencePaper(doi="10.1000/shared"), ReferencePaper(doi="10.1000/pdf")
    ])
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda path, title: True)
    result = pipeline.analyze_identifier("10.1000/source", ENABLED, pdf_path=tmp_path / "source.pdf")
    assert result.stats["pdf_comparison"]["shared_dois"] == 1
    assert result.stats["pdf_comparison"]["status"] == "partial_comparison"
    assert any("無法證明兩份清單" in warning for warning in result.warnings)


def test_missing_crossref_list_uses_extractable_pdf(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (SeedPaper(title="Source"), []))
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda path: [ReferencePaper(doi="10.1000/ref")])
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda path, title: True)
    result = pipeline.analyze_identifier("10.1000/source", ENABLED, pdf_path=tmp_path / "source.pdf")
    assert result.stats["reference_source"] == "numbered_pdf_text"
    assert len(result.references) == 1
    assert result.provider_states["crossref"] == "no_references"


def test_mismatched_pdf_never_supplies_missing_crossref_references(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (SeedPaper(title="Source"), []))
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda path: [ReferencePaper(doi="10.1000/wrong")])
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda path, title: False)
    result = pipeline.analyze_identifier("10.1000/source", ENABLED, pdf_path=tmp_path / "wrong.pdf")
    assert result.references == []
    assert result.stats["reference_source"] == "crossref"
    assert result.stats["pdf_comparison"]["status"] == "unavailable"


def test_ambiguous_title_requires_doi(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    resolver.http.get_json = lambda _url, **_kwargs: {"message": {"items": [
        {"title": ["Example research paper"], "DOI": "10.1000/a"},
        {"title": ["Example research paper"], "DOI": "10.1000/b"},
    ]}}
    try:
        resolver.source_work("Example research paper")
    except ValueError as exc:
        assert "Several" in str(exc)
    else:
        raise AssertionError("Ambiguous title was silently selected")


def test_duplicate_search_results_for_same_doi_are_not_ambiguous(tmp_path):
    resolver = CrossrefResolver(ApiCache(tmp_path / "cache.db"))
    def get_json(url, **_kwargs):
        if url.endswith("/works"):
            return {"message": {"items": [
                {"title": ["Example research paper"], "DOI": "10.1000/a"},
                {"title": ["Example research paper"], "DOI": "10.1000/a"},
            ]}}
        return {"message": {"title": ["Example research paper"], "reference": [
            {"author": "A. Author", "year": "2020", "journal-title": "Journal", "volume": "4", "first-page": "12"},
        ]}}
    resolver.http.get_json = get_json
    _seed, references = resolver.source_work("Example research paper")
    assert len(references) == 1
    assert "A. Author" in references[0].raw_reference
    assert "Journal" in references[0].raw_reference


def test_selected_grobid_failure_does_not_return_empty_crossref_success(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (SeedPaper(title="Source"), []))
    monkeypatch.setattr(pipeline.grobid, "process_pdf", lambda path:
                        (_ for _ in ()).throw(requests.HTTPError("GROBID HTTP 500")))
    with pytest.raises(requests.HTTPError, match="GROBID HTTP 500"):
        pipeline.analyze_identifier("Source", ENABLED, pdf_path=tmp_path / "source.pdf", use_grobid=True)


def test_grobid_selected_without_pdf_does_not_silently_use_crossref(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (SeedPaper(title="Source"), []))
    with pytest.raises(ValueError, match="PDF"):
        pipeline.analyze_identifier("Source", ENABLED, use_grobid=True)


def test_selected_grobid_references_take_precedence_over_crossref(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    seed = SeedPaper(title="Source")
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args:
                        (seed, [ReferencePaper(title="Publisher reference")]))
    monkeypatch.setattr(pipeline.grobid, "process_pdf", lambda path:
                        (seed, [ReferencePaper(title="PDF reference")]))
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: True)

    result = pipeline.analyze_identifier("Source", ENABLED, pdf_path=tmp_path / "source.pdf", use_grobid=True)
    assert result.stats["reference_source"] == "grobid"
    assert [paper.title for paper in result.references] == ["PDF reference"]
    assert not any("Crossref 未提供參考文獻" in warning for warning in result.warnings)


@pytest.mark.parametrize("lookup_error", [
    NetworkAccessError("Windows denied source lookup"),
    ValueError("No sufficiently close Crossref title match; enter a DOI"),
])
def test_grobid_retry_after_empty_title_result_survives_source_lookup_failure(tmp_path, monkeypatch, lookup_error):
    title = "Language Models Predict Empathy Gaps Between Social In-groups and Out-groups"
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    lookups = []

    def lookup(*args):
        lookups.append(args)
        if len(lookups) == 1:
            return SeedPaper(title=title), []
        raise lookup_error

    monkeypatch.setattr(CrossrefResolver, "source_work", lookup)
    monkeypatch.setattr(pipeline.grobid, "process_pdf", lambda path:
                        (SeedPaper(title=title), [ReferencePaper(title="PDF reference")]))
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: True)

    first = pipeline.analyze_identifier(title, ENABLED)
    assert first.references == []
    refreshed = pipeline.analyze_identifier("", ENABLED, pdf_path=tmp_path / "source.pdf", use_grobid=True)
    retried = pipeline.analyze_identifier(title, ENABLED, pdf_path=tmp_path / "source.pdf", use_grobid=True)

    assert [paper.title for paper in retried.references] == [paper.title for paper in refreshed.references]
    assert retried.stats["reference_source"] == "grobid"
    assert any("Crossref" in warning for warning in retried.warnings)


@pytest.mark.parametrize("identifier, seed", [
    ("A completely different research paper title", SeedPaper(title="Language Models Predict Empathy Gaps Between Social In-groups and Out-groups")),
    ("10.1000/selected", SeedPaper(title="Source", doi="10.1000/other")),
])
def test_grobid_source_lookup_failure_never_accepts_known_mismatched_pdf(tmp_path, monkeypatch, identifier, seed):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args:
                        (_ for _ in ()).throw(NetworkAccessError("blocked source lookup")))
    monkeypatch.setattr(pipeline.grobid, "process_pdf", lambda path:
                        (seed, [ReferencePaper(title="A reference")]))
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: False)

    with pytest.raises(ValueError, match="PDF"):
        pipeline.analyze_identifier(identifier, ENABLED, pdf_path=tmp_path / "wrong.pdf", use_grobid=True)


@pytest.mark.parametrize("identifier", ["", "A valid source paper title", "10.1000/unverified"])
@pytest.mark.parametrize("error", [ValueError("No source found"), NetworkAccessError("blocked source lookup")])
def test_local_pdf_extraction_survives_source_lookup_failure(tmp_path, monkeypatch, identifier, error):
    pipeline = AnalysisPipeline(Settings(cache_enabled=False))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (_ for _ in ()).throw(error))
    monkeypatch.setattr("core.pipeline.verified_seed_doi", lambda *args: None)
    monkeypatch.setattr("core.pipeline.pdf_title_hints", lambda *args: ["A valid source paper title"])
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: True)
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda *args: [ReferencePaper(title="Extracted local reference")])
    result = pipeline.analyze_identifier(identifier, ENABLED, pdf_path=tmp_path / "source.pdf")
    assert len(result.references) == 1
    assert result.stats["reference_source"] == "numbered_pdf_text"
    assert result.stats["source_lookup"] == "unavailable"
    assert result.seed.doi is None
    assert result.warnings


def test_local_pdf_fallback_rejects_a_different_entered_title(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_enabled=False))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (_ for _ in ()).throw(ValueError("not found")))
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: False)
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda *args: [ReferencePaper(title="Reference")])
    with pytest.raises(ValueError, match="matches the entered title"):
        pipeline.analyze_identifier("A different entered title", ENABLED, pdf_path=tmp_path / "source.pdf")
