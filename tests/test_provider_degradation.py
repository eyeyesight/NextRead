from core.config import Settings
from core.models import ReferencePaper, SeedPaper
from core.pipeline import AnalysisPipeline


class FakeGrobid:
    def process_pdf(self, _path):
        return SeedPaper(title="Seed"), [ReferencePaper(title="Reference", doi="10.1000/test", resolution_status="exact_doi")]


class FailingOpenAlex:
    def __init__(self, *_args, **_kwargs):
        pass

    def enrich(self, *_args, **_kwargs):
        raise RuntimeError("temporary outage")


def test_openalex_failure_does_not_invalidate_parsed_references(tmp_path, monkeypatch):
    monkeypatch.setattr("core.pipeline.OpenAlexProvider", FailingOpenAlex)
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    pipeline.grobid = FakeGrobid()
    result = pipeline.analyze(
        tmp_path / "paper.pdf",
        {"crossref": False, "openalex": True, "semantic_scholar": False},
    )
    assert len(result.references) == 1
    assert result.provider_states["openalex"] == "failed"
    assert "temporary outage" in result.warnings[0]


class PartialSemanticScholar:
    def __init__(self, *_args, **_kwargs):
        self.partial_errors = []

    def enrich_with_seed(self, _seed, papers, _force_refresh):
        papers[0].semantic_scholar_id = "cached-paper"
        papers[0].semantic_similarity = 1.0
        self.partial_errors.append("Rate limited by references endpoint")


def test_semantic_scholar_partial_failure_keeps_cached_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr("core.pipeline.SemanticScholarProvider", PartialSemanticScholar)
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    pipeline.grobid = FakeGrobid()

    result = pipeline.analyze(
        tmp_path / "paper.pdf",
        {"crossref": False, "openalex": False, "semantic_scholar": True},
    )

    assert result.provider_states["semantic_scholar"] == "partial"
    assert result.stats["semantic_scholar_coverage"] == 1
    assert result.references[0].semantic_relevance_score == 1.0
    assert result.references[0].priority_score is not None
    assert "已保留取得的資料" in result.warnings[0]
