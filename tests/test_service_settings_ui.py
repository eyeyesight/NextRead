from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_api_key_feedback_describes_configuration_without_revealing_keys(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "test-openalex-secret")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-semantic-secret")
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["OpenAlex"] == "已啟用"
    assert metrics["Semantic Scholar"] == "已啟用"
    assert "OpenAlex API Key" not in metrics
    assert "Semantic Scholar API Key" not in metrics
    captions = "\n".join(item.value for item in app.caption)
    assert captions.count("API Key 已載入") == 2
    assert "不代表 Key 已驗證有效" not in captions
    assert "test-openalex-secret" not in str(app)
    assert "test-semantic-secret" not in str(app)
    assert not app.exception


def test_api_key_metrics_distinguish_missing_keys_from_enabled_services(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["OpenAlex"] == "已啟用"
    assert metrics["Semantic Scholar"] == "已啟用"
    captions = "\n".join(item.value for item in app.caption)
    assert captions.count("API Key 未設定") == 2
    assert not app.exception


def test_refresh_option_explains_cache_and_api_cost():
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    labels = [item.label for item in app.checkbox]
    captions = "\n".join(item.value for item in app.caption)
    assert any("不使用快取" in label for label in labels)
    assert "API 額度" in captions
    assert not app.exception


def test_sjr_content_change_invalidates_results_even_in_same_year(tmp_path, monkeypatch):
    from core.models import ReferencePaper, SeedPaper
    from resolvers.crossref import CrossrefResolver
    from tests.test_sjr import SJR_CSV

    path = tmp_path / "scimagojr 2024.csv"
    path.write_text(SJR_CSV, encoding="utf-8")
    monkeypatch.setenv("SJR_DATA_PATH", str(path))
    monkeypatch.setattr(CrossrefResolver, "source_work", lambda *args: (
        SeedPaper(title="Source"), [ReferencePaper(title="Reference", source_name="Journal of Motor Learning")]
    ))
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    for label in ("Crossref 逐筆書目辨識", "OpenAlex", "Semantic Scholar"):
        next(item for item in app.checkbox if item.label == label).set_value(False).run()
    app.text_input[0].set_value("Source").run()
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert app.session_state["result"].references[0].sjr_quartile == "Q1"

    # Invalid CSV upload must not replace the original or discard the result.
    app.file_uploader(key="sjr_update_file").upload("invalid.csv", b"invalid;header\n", "text/csv").run()
    next(button for button in app.button if button.label == "驗證並更新 SJR 資料").click().run()
    assert app.session_state["result"].references[0].sjr_quartile == "Q1"
    assert path.read_text(encoding="utf-8") == SJR_CSV

    path.write_text(SJR_CSV.replace("Q1", "Q2"), encoding="utf-8")
    app.run()
    assert "result" not in app.session_state
    assert any("輸入或分析設定已變更" in item.value for item in app.info)
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert app.session_state["result"].references[0].sjr_quartile == "Q2"
    assert not app.exception


def test_services_default_enabled_and_can_be_disabled_individually(monkeypatch):
    from core.pipeline import AnalysisPipeline

    requests = []

    def analyze(self, identifier, enabled, *args):
        requests.append(enabled.copy())
        return None

    monkeypatch.setattr(AnalysisPipeline, "analyze_identifier", analyze)
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    assert not any(item.label in ("分析模式", "Analysis mode") for item in app.radio)
    app.text_input[0].set_value("A source paper title").run()
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert requests[-1] == {"crossref": True, "openalex": True, "semantic_scholar": True}

    for label, provider in (("Semantic Scholar", "semantic_scholar"), ("OpenAlex", "openalex"), ("Crossref 逐筆書目辨識", "crossref")):
        next(item for item in app.checkbox if item.label == label).set_value(False).run()
        app.run()
        next(button for button in app.button if button.label == "開始分析").click().run()
        assert requests[-1][provider] is False
    assert requests[-1] == {"crossref": False, "openalex": False, "semantic_scholar": False}
    assert not app.exception
