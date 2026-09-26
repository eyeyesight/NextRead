from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_WEIGHTS = {
    "field_impact": 0.30,
    "local_network": 0.25,
    "semantic_relevance": 0.25,
    "influential_citations": 0.10,
    "author_impact": 0.06,
    "source_impact": 0.04,
}


@dataclass
class Settings:
    grobid_url: str = "http://localhost:8070"
    crossref_mailto: str = ""
    openalex_api_key: str = ""
    semantic_scholar_api_key: str = ""
    sjr_data_path: Path = Path("data/sjr/scimagojr 2024.csv")
    cache_enabled: bool = True
    cache_ttl_days: int = 30
    cache_path: Path = Path("data/cache.db")
    ranking_weights: dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    load_dotenv()
    data: dict[str, Any] = {}
    config_path = Path(path)
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cache = data.get("cache", {})
    ranking = DEFAULT_WEIGHTS | data.get("ranking", {})
    if sum(ranking.values()) <= 0:
        raise ValueError("Ranking weights must contain at least one positive value")
    return Settings(
        grobid_url=os.getenv("GROBID_URL", "http://localhost:8070").rstrip("/"),
        crossref_mailto=os.getenv("CROSSREF_MAILTO", ""),
        openalex_api_key=os.getenv("OPENALEX_API_KEY", "").strip(),
        semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip(),
        sjr_data_path=Path(os.getenv("SJR_DATA_PATH", "data/sjr/scimagojr 2024.csv")),
        cache_enabled=bool(cache.get("enabled", True)),
        cache_ttl_days=int(cache.get("ttl_days", 30)),
        ranking_weights={key: float(value) for key, value in ranking.items()},
    )
