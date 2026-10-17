"""Remove API credentials at error, log, and export boundaries."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import quote, quote_plus


_SECRET_NAME = re.compile(r"^(?:api[_-]?key|x-api-key|access[_-]?token|token|authorization)$", re.I)
_SECRET_VALUE = re.compile(
    r"(\b(?:api[_-]?key|x-api-key|access[_-]?token|token|authorization)\b['\"]?\s*[:=]\s*['\"]?)(?:(?:Bearer|Basic)\s+)?([^&\s'\"<>),]+)",
    re.I,
)


def redact_text(value: str, secrets=()) -> str:
    credentials = [*secrets, os.getenv("OPENALEX_API_KEY", ""), os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")]
    for secret in sorted({str(item) for item in credentials if item}, key=len, reverse=True):
        for spelling in {secret, quote(secret, safe=""), quote_plus(secret)}:
            value = value.replace(spelling, "[REDACTED]")
    return _SECRET_VALUE.sub(r"\1[REDACTED]", value)


def redact_data(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_NAME.fullmatch(str(key)) else redact_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_data(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Format first so chained exceptions and tracebacks are covered too.
        return redact_text(super().format(record))
