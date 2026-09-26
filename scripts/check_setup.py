"""Check a fresh NextRead installation without printing API keys."""

from __future__ import annotations

import sys
from collections.abc import Callable

import requests

from core.config import Settings, load_settings
from providers.sjr import SjrProvider


def run_checks(
    settings: Settings,
    get: Callable[..., requests.Response] = requests.get,
) -> tuple[list[str], bool]:
    lines = [
        f"OpenAlex API Key：{'已載入' if settings.openalex_api_key else '未設定（可使用公開額度）'}",
        f"Semantic Scholar API Key：{'已載入' if settings.semantic_scholar_api_key else '未設定（可使用公開額度）'}",
        f"SJR：{'已安裝' if SjrProvider(settings.sjr_data_path).available else '未安裝，請依 README 下載 SCImago CSV'}",
    ]
    checks = [
        ("Crossref", "https://api.crossref.org/works", {"rows": 0}, {}),
        (
            "OpenAlex",
            "https://api.openalex.org/works",
            {"per-page": 1} | ({"api_key": settings.openalex_api_key} if settings.openalex_api_key else {}),
            {},
        ),
        (
            "Semantic Scholar",
            "https://api.semanticscholar.org/graph/v1/paper/649def34f8be52c8b66281af98ae884c09aef38b",
            {"fields": "title"},
            {"x-api-key": settings.semantic_scholar_api_key} if settings.semantic_scholar_api_key else {},
        ),
    ]
    reachable = True
    for name, url, params, headers in checks:
        try:
            response = get(url, params=params, headers=headers, timeout=8)
            if response.status_code == 200:
                status = "可連線"
            elif response.status_code in (401, 403):
                status = f"HTTP {response.status_code}，請檢查 API Key 或服務授權"
            elif response.status_code == 429:
                status = "HTTP 429，已達查詢額度或遭節流，請稍後再試"
            else:
                status = f"HTTP {response.status_code}，請檢查服務狀態"
        except requests.ConnectionError as exc:
            status = (
                "Windows 拒絕 Python 對外連線，請檢查防火牆、代理伺服器或防毒軟體"
                if "WinError 10013" in str(exc)
                else "連線失敗，請檢查網路、DNS 或代理伺服器"
            )
        except requests.Timeout:
            status = "連線逾時，請檢查網路或代理伺服器"
        except requests.RequestException:
            status = "請求失敗，請檢查網路或服務狀態"
        if status != "可連線":
            reachable = False
        lines.append(f"{name}：{status}")
    return lines, reachable


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Python：{sys.executable}")
    report, all_reachable = run_checks(load_settings())
    print("\n".join(report))
    raise SystemExit(0 if all_reachable else 1)
