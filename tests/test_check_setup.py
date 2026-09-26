from types import SimpleNamespace

import requests

from core.config import Settings
from scripts.check_setup import run_checks


def test_clean_clone_reports_optional_local_data_without_exposing_keys(tmp_path):
    settings = Settings(
        openalex_api_key="private-openalex-key",
        semantic_scholar_api_key="private-s2-key",
        sjr_data_path=tmp_path / "missing.csv",
    )
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200)

    lines, reachable = run_checks(settings, get=get)
    output = "\n".join(lines)

    assert reachable
    assert "SJR：未安裝" in output
    assert "OpenAlex API Key：已載入" in output
    assert "Semantic Scholar API Key：已載入" in output
    assert "private-openalex-key" not in output
    assert "private-s2-key" not in output
    assert len(calls) == 3
    assert calls[1][1]["params"]["api_key"] == "private-openalex-key"
    assert calls[2][1]["headers"]["x-api-key"] == "private-s2-key"


def test_windows_socket_refusal_is_diagnosed_without_raw_pool_error(tmp_path):
    settings = Settings(sjr_data_path=tmp_path / "missing.csv")
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if "semanticscholar" in url:
            raise requests.ConnectionError("HTTPSConnectionPool: [WinError 10013]")
        return SimpleNamespace(status_code=200)

    lines, reachable = run_checks(settings, get=get)
    output = "\n".join(lines)

    assert not reachable
    assert "Semantic Scholar：Windows 拒絕 Python 對外連線" in output
    assert "HTTPSConnectionPool" not in output
    assert "api_key" not in calls[1][1]["params"]
    assert "x-api-key" not in calls[2][1]["headers"]
