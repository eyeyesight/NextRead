import io
import json
import logging
from pathlib import Path

import pytest
import requests

from core.models import AnalysisResult, ReferencePaper, SeedPaper
from core.security import RedactingFormatter, redact_text
from providers.http import HttpClient


def test_error_key_is_redacted_before_storage_and_export():
    client = HttpClient()
    response = requests.Response()
    response.status_code = 401
    response.url = "https://api.openalex.org/works/test?api_key=private-audit-key&mailto=user@example.com"
    client.session.get = lambda *args, **kwargs: response
    with pytest.raises(requests.HTTPError) as caught:
        client.get_json("https://api.openalex.org/works/test", params={"api_key": "private-audit-key"})
    detail = str(caught.value)
    assert "private-audit-key" not in detail
    assert "401" in detail
    assert "api.openalex.org" in detail
    assert caught.value.response is response
    paper = ReferencePaper(provider_data={"openalex_error": detail})
    assert "private-audit-key" not in json.dumps(AnalysisResult(SeedPaper(), [paper], {}).to_dict())


def test_exports_also_redact_legacy_error_urls_without_mutating_result():
    detail = "403 for url: https://api.openalex.org/works/test?api_key=legacy-key"
    paper = ReferencePaper(provider_data={"openalex_error": detail, "token": "nested-key"})
    result = AnalysisResult(SeedPaper(), [paper], {}, [detail])
    exported = json.dumps(result.to_dict())
    assert "legacy-key" not in exported
    assert "nested-key" not in exported
    assert paper.provider_data["openalex_error"] == detail


def test_log_formatter_covers_exception_chains_and_encoded_values(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "private/value+key")
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(RedactingFormatter())
    logger = logging.getLogger("test-nextread-redaction")
    logger.addHandler(handler)
    try:
        try:
            try:
                raise requests.HTTPError("failed ?api_key=url-key")
            except requests.HTTPError as exc:
                raise ValueError("private/value+key private%2Fvalue%2Bkey") from exc
        except ValueError:
            logger.exception("API failed")
    finally:
        logger.removeHandler(handler)
    text = output.getvalue()
    for secret in ("url-key", "private/value+key", "private%2Fvalue%2Bkey"):
        assert secret not in text
    assert "HTTPError" in text and "ValueError" in text
    assert redact_text("x-api-key: header-secret") == "x-api-key: [REDACTED]"
    assert redact_text("Authorization: Bearer unknown-secret") == "Authorization: [REDACTED]"
    assert redact_text('"Authorization": "Basic encoded-secret"') == '"Authorization": "[REDACTED]"'


def test_ui_redacts_legacy_warnings_and_new_analysis_errors(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from core.config import Settings
    from core.pipeline import AnalysisPipeline

    detail = "401 https://api.openalex.org/works/test?api_key=ui-secret"
    pipeline = AnalysisPipeline(Settings(cache_enabled=False))
    result = pipeline._finish(SeedPaper(title="Source"), [ReferencePaper(title="Reference")], {}, False, None, "zh-TW", "grobid")
    result.warnings.append(detail)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15)
    app.session_state["result"] = result
    app.run()
    assert "ui-secret" not in " ".join(item.value for item in app.warning)

    monkeypatch.setattr(AnalysisPipeline, "analyze_identifier", lambda *args: (_ for _ in ()).throw(requests.HTTPError(detail)))
    app.text_input[0].set_value("Source").run()
    next(button for button in app.button if button.label == "開始分析").click().run()
    assert app.error
    assert "ui-secret" not in " ".join(item.value for item in app.error)
    assert not app.exception
