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
