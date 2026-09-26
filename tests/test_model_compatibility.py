from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType

import core.models as current_models
from core.models import AnalysisResult, SeedPaper
from parsers.grobid import GrobidClient
from streamlit.testing.v1 import AppTest


class LegacyPaper(SimpleNamespace):
    def to_dict(self):
        return vars(self).copy()


def test_app_import_survives_a_cached_pre_helper_models_module(monkeypatch):
    stale_models = ModuleType("core.models")
    stale_models.__dict__.update({
        name: value
        for name, value in vars(current_models).items()
        if name != "paper_value"
    })
    monkeypatch.setitem(sys.modules, "core.models", stale_models)
    monkeypatch.setattr(GrobidClient, "is_available", lambda _self: False)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=10)

    app.run()

    assert not app.exception


def test_app_renders_metrics_after_loading_a_pre_revision_result(monkeypatch):
    monkeypatch.setattr(GrobidClient, "is_available", lambda _self: False)
    paper = LegacyPaper(
        title="Legacy result",
        raw_reference="Legacy result citation",
        doi="10.1000/legacy",
        authors=["Author A", "Author B"],
        first_author_name="Author A",
        year=2024,
        source_name="Journal",
        openalex_id=None,
        semantic_scholar_url=None,
        priority_score=75.0,
        data_coverage=55.0,
        local_pagerank=0.5,
        local_in_degree=2,
        local_connectivity=3,
        semantic_similarity=0.8,
        influential_citation_count=10,
        fwci=2.5,
        citation_count=100,
        sjr_quartile="Q1",
        sjr_score=1.2,
        sjr_year=2024,
        first_author_h_index=20,
        author_h_indices=[20, 10],
        source_h_index=50,
        field="Computer Science",
        subfield="Artificial Intelligence",
        primary_topic="Information Retrieval",
        domain="Physical Sciences",
        resolution_status="exact_doi",
        other_topics=[],
        referenced_works=[],
        source_issns=[],
    )
    result = AnalysisResult(
        seed=SeedPaper(title="Seed paper"),
        references=[paper],
        provider_states={},
        stats={
            "references_extracted": 1,
            "references_resolved": 1,
            "resolution_rate": 100.0,
            "openalex_coverage": 1,
            "semantic_scholar_coverage": 1,
            "sjr_coverage": 1,
            "active_dimensions": 6,
        },
    )
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=10)
    app.session_state["result"] = result

    app.run()

    assert not app.exception
    assert any("更新前儲存" in message.value for message in app.info)
    assert any("Legacy result" in table.value.to_string() for table in app.dataframe)
