from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.pipeline import AnalysisPipeline
from parsers.grobid_service import GrobidUnavailableError
from parsers.grobid import GrobidClient
from core.models import ReferencePaper, SeedPaper
from resolvers.crossref import CrossrefResolver


def test_successful_analysis_check_clears_earlier_grobid_warning(monkeypatch):
    checks = iter([GrobidUnavailableError("not ready"), None])

    def check(_client, _project_dir, **_kwargs):
        error = next(checks)
        if error:
            raise error

    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", check)
    monkeypatch.setattr(AnalysisPipeline, "analyze_identifier", lambda self, *args, **kwargs: None)

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.checkbox[0].set_value(True).run()
    assert app.session_state["grobid_check_error"] == "not ready"

    app.file_uploader[0].upload("paper.pdf", b"%PDF-1.4", "application/pdf").run()
    app.button[-1].click().run()

    assert "grobid_check_error" not in app.session_state
    assert not any("GROBID 尚未就緒" in warning.value for warning in app.warning)
    assert any(metric.label == "GROBID" and metric.value == "已就緒" for metric in app.metric)
    assert not app.exception


def test_recheck_button_updates_status_without_toggling_checkbox(monkeypatch):
    checks = iter([GrobidUnavailableError("not ready"), None])
    calls = []
    app_runs = []
    original_init = AnalysisPipeline.__init__

    def count_app_run(self, settings):
        app_runs.append(True)
        original_init(self, settings)

    def check(_client, _project_dir, **kwargs):
        calls.append(kwargs)
        error = next(checks)
        if error:
            raise error

    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", check)
    monkeypatch.setattr(AnalysisPipeline, "__init__", count_app_run)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.checkbox[0].set_value(True).run()
    assert app.session_state["grobid_check_error"] == "not ready"

    recheck = next(button for button in app.button if "GROBID" in button.label)
    runs_before_click = len(app_runs)
    recheck.click().run()

    assert len(calls) == 2
    assert calls[1]["api_attempts"] == 6
    assert len(app_runs) - runs_before_click == 1
    assert app.checkbox[0].value is True
    assert "grobid_check_error" not in app.session_state
    assert any(metric.label == "GROBID" and metric.value == "已就緒" for metric in app.metric)
    assert not app.exception


def test_recheck_shows_completed_feedback_when_api_is_still_warming(monkeypatch):
    def check(_client, _project_dir, **kwargs):
        if on_retry := kwargs.get("on_retry"):
            on_retry(1)
            on_retry(2)
        raise GrobidUnavailableError("API 尚未回應")

    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", check)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.checkbox[0].set_value(True).run()
    recheck = next(button for button in app.button if "GROBID" in button.label)
    recheck.click().run()

    assert any("本次檢查完成" in status.label for status in app.status)
    assert len(app.status[0].markdown) == 1
    assert any("GROBID 尚未就緒" in warning.value for warning in app.warning)
    assert not app.exception


def test_grobid_selected_with_only_title_requires_pdf(monkeypatch):
    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", lambda *args, **kwargs: None)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.text_input[0].set_value("Language Models Predict Empathy Gaps Between Social In-groups and Out-groups").run()
    app.checkbox[0].set_value(True).run()

    assert next(button for button in app.button if button.label == "開始分析").disabled
    assert any("請先上傳 PDF" in warning.value for warning in app.warning)
    assert not app.exception


def test_failed_analysis_does_not_keep_an_old_empty_result(monkeypatch):
    from core.models import AnalysisResult, SeedPaper

    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(AnalysisPipeline, "analyze_identifier", lambda *args, **kwargs:
                        (_ for _ in ()).throw(ValueError("GROBID extraction failed")))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.checkbox[0].set_value(True).run()
    app.file_uploader[0].upload("paper.pdf", b"%PDF-1.4", "application/pdf").run()
    app.session_state["result"] = AnalysisResult(SeedPaper(title="Old result"), [], {})
    next(button for button in app.button if button.label == "開始分析").click().run()

    assert "result" not in app.session_state
    assert any("GROBID extraction failed" in error.value for error in app.error)
    assert not any(header.value == "分析摘要" for header in app.header)
    assert not app.exception


def test_switch_from_empty_title_search_to_grobid_clears_stale_result(monkeypatch):
    title = "Language Models Predict Empathy Gaps Between Social In-groups and Out-groups"
    seed = SeedPaper(title=title)
    grobid_calls = []

    def process_pdf(self, path):
        grobid_calls.append(path.read_bytes())
        return seed, [ReferencePaper(title=f"Reference {i}") for i in range(79)]

    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (seed, []))
    monkeypatch.setattr(GrobidClient, "process_pdf", process_pdf)
    monkeypatch.setattr("core.pipeline.pdf_matches_seed", lambda *args: True)
    monkeypatch.setattr("parsers.grobid_service.check_grobid_ready", lambda *args, **kwargs: None)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()
    app.radio[0].set_value("parser").run()
    app.text_input[0].set_value(title).run()
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert app.session_state["result"].stats["references_extracted"] == 0

    app.checkbox[0].set_value(True).run()
    assert "result" not in app.session_state
    assert not any(header.value == "分析摘要" for header in app.header)
    assert any("輸入或分析設定已變更" in info.value for info in app.info)

    app.file_uploader[0].upload("paper.pdf", b"%PDF-1.4", "application/pdf").run()
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert grobid_calls == [b"%PDF-1.4"]
    assert app.session_state["result"].stats["references_extracted"] == 79
    assert app.session_state["result"].stats["reference_source"] == "grobid"
    assert not any("輸入或分析設定已變更" in info.value for info in app.info)

    app.run()
    assert app.session_state["result"].stats["references_extracted"] == 79
    assert len(grobid_calls) == 1
    assert not app.exception

    app.file_uploader[0].upload("paper.pdf", b"%PDF-1.4 updated", "application/pdf").run()
    assert "result" not in app.session_state
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert grobid_calls[-1] == b"%PDF-1.4 updated"
    assert app.session_state["result"].stats["references_extracted"] == 79

    app.text_input[0].set_value("A different paper title").run()
    assert "result" not in app.session_state
    assert not app.exception
