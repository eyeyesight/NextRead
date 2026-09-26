from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_api_key_feedback_describes_configuration_without_revealing_keys(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "test-openalex-secret")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-semantic-secret")
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    captions = "\n".join(item.value for item in app.caption)
    assert "OpenAlex API Key：已載入" in captions
    assert "Semantic Scholar API Key：已載入；本次未啟用" in captions
    assert "test-openalex-secret" not in captions
    assert "test-semantic-secret" not in captions
    assert not app.exception


def test_refresh_option_explains_cache_and_api_cost():
    app = AppTest.from_file(APP_PATH, default_timeout=15).run()
    labels = [item.label for item in app.checkbox]
    captions = "\n".join(item.value for item in app.caption)
    assert any("不使用快取" in label for label in labels)
    assert "API 額度" in captions
    assert not app.exception
