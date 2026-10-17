from core.config import Settings
from core.models import ReferencePaper, SeedPaper
from core.pipeline import AnalysisPipeline
from providers.http import NetworkAccessError


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
    assert "已取得的資料仍會保留" in result.warnings[0]


def test_all_openalex_failures_explain_windows_network_refusal(tmp_path, monkeypatch):
    class BlockedOpenAlex:
        def __init__(self, *_args, **_kwargs):
            pass

        def enrich(self, papers, _force_refresh):
            papers[0].provider_data["openalex_error"] = "Windows 拒絕 NextRead 連線到 OpenAlex。"

    monkeypatch.setattr("core.pipeline.OpenAlexProvider", BlockedOpenAlex)
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    pipeline.grobid = FakeGrobid()

    result = pipeline.analyze(tmp_path / "paper.pdf", {"crossref": False, "openalex": True, "semantic_scholar": False})

    assert any("Windows 拒絕 NextRead 連線到 OpenAlex" in warning for warning in result.warnings)
    assert result.provider_states["openalex"] == "failed"


def test_all_crossref_failures_explain_windows_network_refusal(tmp_path, monkeypatch):
    class BlockedCrossref:
        def __init__(self, *_args, **_kwargs):
            pass

        def resolve(self, _paper, _force_refresh):
            raise NetworkAccessError("Windows 拒絕 NextRead 連線到 Crossref。")

    monkeypatch.setattr("core.pipeline.CrossrefResolver", BlockedCrossref)
    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db"))
    pipeline.grobid = FakeGrobid()

    result = pipeline.analyze(tmp_path / "paper.pdf", {"crossref": True, "openalex": False, "semantic_scholar": False})

    assert any("Windows 拒絕 NextRead 連線到 Crossref" in warning for warning in result.warnings)


def test_unmatched_semantic_seed_reports_partial_without_losing_references(monkeypatch):
    class UnmatchedSeed:
        def __init__(self, *args):
            self.partial_errors = []
            self.seed_status = "unmatched"
            self.seed_warning = "No source identity"
            self.seed_match_method = None

        def enrich_with_seed(self, seed, papers, refresh):
            papers[0].semantic_scholar_id = "reference"

    monkeypatch.setattr("core.pipeline.SemanticScholarProvider", UnmatchedSeed)
    pipeline = AnalysisPipeline(Settings(cache_enabled=False))
    pipeline.grobid = FakeGrobid()
    result = pipeline.analyze("unused.pdf", {"semantic_scholar": True})
    assert len(result.references) == 1
    assert result.provider_states["semantic_scholar"] == "partial"
    assert result.stats["semantic_scholar_seed_status"] == "unmatched"
    assert any("尚未確認原始論文" in item for item in result.warnings)


def test_metadata_seed_match_discloses_version_limit_and_missing_embedding(monkeypatch):
    class MetadataSeed:
        def __init__(self, *args):
            self.partial_errors = []
            self.seed_status = "resolved"
            self.seed_warning = "No embedding"
            self.seed_match_method = "metadata"

        def enrich_with_seed(self, seed, papers, refresh):
            papers[0].semantic_scholar_id = "reference"
            papers[0].is_influential_citation = True

    monkeypatch.setattr("core.pipeline.SemanticScholarProvider", MetadataSeed)
    pipeline = AnalysisPipeline(Settings(cache_enabled=False))
    pipeline.grobid = FakeGrobid()
    result = pipeline.analyze("unused.pdf", {"semantic_scholar": True})
    assert result.references[0].influential_citation_score == 1.0
    assert result.stats["semantic_scholar_seed_match"] == "metadata"
    assert any("尚未確認 PDF 與該出版版本一致" in item for item in result.warnings)
    assert any("未提供原始論文的語意向量" in item for item in result.warnings)
    assert not any("無法計算語意相似度與具影響力引用" in item for item in result.warnings)
