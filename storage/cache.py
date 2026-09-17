from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class ApiCache:
    def __init__(self, path: str | Path = "data/cache.db", ttl_days: int = 30, enabled: bool = True):
        self.path = Path(path)
        self.ttl = timedelta(days=ttl_days)
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    provider TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (provider, identifier)
                )
                """
            )

    def get(self, provider: str, identifier: str, force_refresh: bool = False) -> dict[str, Any] | None:
        if not self.enabled or force_refresh:
            self.misses += 1
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json, fetched_at FROM api_cache WHERE provider = ? AND identifier = ?",
                (provider, identifier),
            ).fetchone()
        if not row:
            self.misses += 1
            return None
        fetched_at = datetime.fromisoformat(row[1])
        if datetime.now(timezone.utc) - fetched_at > self.ttl:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(row[0])

    def set(self, provider: str, identifier: str, response: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_cache(provider, identifier, response_json, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, identifier) DO UPDATE SET
                    response_json = excluded.response_json,
                    fetched_at = excluded.fetched_at
                """,
                (provider, identifier, json.dumps(response), datetime.now(timezone.utc).isoformat()),
            )
