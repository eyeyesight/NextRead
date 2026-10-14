from __future__ import annotations

import requests
import time
from urllib.parse import urlsplit
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class RateLimitedError(requests.RequestException):
    pass


class NetworkAccessError(requests.RequestException):
    pass


class HttpClient:
    def __init__(self, headers: dict[str, str] | None = None, timeout: int = 30, min_interval: float = 0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NextRead/0.1"} | (headers or {}))
        self.timeout = timeout
        self.min_interval = min_interval
        self.last_request_at: float | None = None
        self.request_count = 0
        self.blocked_hosts: dict[str, str] = {}

    def _pace(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        if self.last_request_at is not None:
            time.sleep(max(0, self.min_interval - (now - self.last_request_at)))
        self.last_request_at = time.monotonic()

    def _request(self, method: str, url: str, **kwargs):
        host = urlsplit(url).hostname or "外部服務"
        if host in self.blocked_hosts:
            raise NetworkAccessError(self.blocked_hosts[host])
        try:
            return getattr(self.session, method)(url, timeout=self.timeout, **kwargs)
        except requests.ConnectionError as exc:
            if "WinError 10013" not in str(exc):
                raise
            service = {
                "api.crossref.org": "Crossref",
                "api.openalex.org": "OpenAlex",
                "api.semanticscholar.org": "Semantic Scholar",
            }.get(host, host)
            self.blocked_hosts[host] = (
                f"Windows 拒絕 NextRead 連線到 {service}；請從檔案總管開啟 check-nextread.cmd 檢查連線，"
                "再確認防火牆、代理伺服器或防毒軟體的 Python 網路權限。"
            )
            raise NetworkAccessError(self.blocked_hosts[host]) from exc

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, RateLimitedError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def get_json(self, url: str, **kwargs) -> dict:
        self._pace()
        self.request_count += 1
        response = self._request("get", url, **kwargs)
        if response.status_code == 429:
            raise RateLimitedError(f"Rate limited by {url}", response=response)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, RateLimitedError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def post_json(self, url: str, **kwargs):
        self._pace()
        self.request_count += 1
        response = self._request("post", url, **kwargs)
        if response.status_code == 429:
            raise RateLimitedError(f"Rate limited by {url}", response=response)
        response.raise_for_status()
        return response.json()
