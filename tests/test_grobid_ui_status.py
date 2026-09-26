from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.pipeline import AnalysisPipeline
from parsers.grobid_service import GrobidUnavailableError


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
