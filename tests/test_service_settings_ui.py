from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_api_key_feedback_describes_configuration_without_revealing_keys(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "test-openalex-secret")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-semantic-secret")
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["OpenAlex"] == "已啟用"
    assert metrics["Semantic Scholar"] == "未啟用"
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
    app.radio[0].set_value("complete").run()
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
