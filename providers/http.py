from __future__ import annotations

import requests
import time
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class RateLimitedError(requests.RequestException):
    pass


class HttpClient:
    def __init__(self, headers: dict[str, str] | None = None, timeout: int = 30, min_interval: float = 0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NextRead/0.1"} | (headers or {}))
        self.timeout = timeout
        self.min_interval = min_interval
        self.last_request_at: float | None = None
        self.request_count = 0

    def _pace(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        if self.last_request_at is not None:
            time.sleep(max(0, self.min_interval - (now - self.last_request_at)))
        self.last_request_at = time.monotonic()

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, RateLimitedError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def get_json(self, url: str, **kwargs) -> dict:
        self._pace()
        self.request_count += 1
        response = self.session.get(url, timeout=self.timeout, **kwargs)
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
        response = self.session.post(url, timeout=self.timeout, **kwargs)
        if response.status_code == 429:
            raise RateLimitedError(f"Rate limited by {url}", response=response)
        response.raise_for_status()
        return response.json()
