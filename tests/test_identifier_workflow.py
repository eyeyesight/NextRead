from core.config import Settings
from core.models import ReferencePaper, SeedPaper
from core.pipeline import AnalysisPipeline
from resolvers.crossref import CrossrefResolver
from storage.cache import ApiCache


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
    assert "尚未證實" in result.warnings[0]


def test_missing_crossref_references_are_explicit(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (SeedPaper(title="Source"), []))
    result = pipeline.analyze_identifier("10.1000/source", ENABLED)
    assert result.references == []
    assert result.provider_states["crossref"] == "no_references"
    assert any("沒有提供參考文獻" in warning for warning in result.warnings)


def test_optional_pdf_extraction_failure_keeps_unverified_crossref_result(tmp_path, monkeypatch):
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    monkeypatch.setattr("core.pipeline.CrossrefResolver.source_work", lambda self, identifier, refresh: (
        SeedPaper(title="Source"), [ReferencePaper(doi="10.1000/ref")]
    ))
    monkeypatch.setattr("core.pipeline.extract_numbered_references", lambda path: (_ for _ in ()).throw(ValueError("unsupported PDF")))
    result = pipeline.analyze_identifier("10.1000/source", ENABLED, pdf_path=tmp_path / "source.pdf")
    assert len(result.references) == 1
    assert result.stats["pdf_comparison"]["status"] == "unavailable"
    assert "尚未證實" in result.warnings[0]


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
    assert any("無法證明完整清單" in warning for warning in result.warnings)


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
