from __future__ import annotations

import math

import requests

from core.models import ReferencePaper, SeedPaper
from providers.base import Capability, DataProvider
from providers.http import HttpClient
from storage.cache import ApiCache


class SemanticScholarProvider(DataProvider):
    name = "semantic_scholar"
    batch_url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    paper_url = "https://api.semanticscholar.org/graph/v1/paper"
    fields = "title,url,embedding.specter_v2"

    def __init__(self, cache: ApiCache, api_key: str = ""):
        headers = {"x-api-key": api_key} if api_key else {}
        self.cache = cache
        self.api_key = api_key
        self.http = HttpClient(headers=headers)

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> set[Capability]:
        return {Capability.INFLUENTIAL_CITATIONS, Capability.SPECTER2_EMBEDDING}

    def enrich(self, papers: list[ReferencePaper], force_refresh: bool = False) -> None:
        self.enrich_with_seed(None, papers, force_refresh)

    def enrich_with_seed(self, seed: SeedPaper | None, papers: list[ReferencePaper], force_refresh: bool = False) -> None:
        doi_targets = ([seed.doi] if seed and seed.doi else []) + [paper.doi for paper in papers if paper.doi]
        unique_dois = list(dict.fromkeys(doi for doi in doi_targets if doi))
        records: dict[str, dict] = {}
        missing: list[str] = []
        for doi in unique_dois:
            cached = self.cache.get(self.name, f"doi:{doi}", force_refresh)
            if cached is None:
                missing.append(doi)
            else:
                records[doi] = cached
        for start in range(0, len(missing), 100):
            chunk = missing[start : start + 100]
            try:
                response = self.http.post_json(
                    self.batch_url,
                    params={"fields": self.fields},
                    json={"ids": [f"DOI:{doi}" for doi in chunk]},
                )
            except requests.HTTPError as exc:
                api_error = ""
                if exc.response is not None and exc.response.status_code == 400:
                    try:
                        api_error = exc.response.json().get("error", "")
                    except (requests.JSONDecodeError, AttributeError):
                        pass
                if api_error == "No valid paper ids given":
                    for doi in chunk:
                        self.cache.set(self.name, f"doi:{doi}", {})
                    continue
                raise
            for doi, record in zip(chunk, response):
                if record:
                    records[doi] = record
                    self.cache.set(self.name, f"doi:{doi}", record)
        seed_embedding = self._embedding(records.get(seed.doi)) if seed and seed.doi else None
        seed_record = records.get(seed.doi) if seed and seed.doi else None
        influential_edges = self._influential_edges(seed_record, force_refresh)
        for paper in papers:
            record = records.get(paper.doi or "")
            if not record:
                continue
            paper.provider_data["semantic_scholar"] = record
            paper.semantic_scholar_id = record.get("paperId")
            paper.semantic_scholar_url = record.get("url")
            paper.is_influential_citation = influential_edges.get(record.get("paperId"))
            paper.embedding = self._embedding(record)
            if seed_embedding and paper.embedding and len(seed_embedding) == len(paper.embedding):
                paper.semantic_similarity = cosine_similarity(seed_embedding, paper.embedding)

    def _influential_edges(self, seed_record: dict | None, force_refresh: bool) -> dict[str, bool]:
        seed_id = (seed_record or {}).get("paperId")
        if not seed_id:
            return {}
        cache_key = f"references:{seed_id}"
        response = self.cache.get(self.name, cache_key, force_refresh)
        if response and response.get("data") and not any(
            (item.get("citedPaper") or {}).get("paperId")
            for item in response["data"]
        ):
            response = None
        if response is None:
            data = []
            offset = 0
            while True:
                page = self.http.get_json(
                    f"{self.paper_url}/{seed_id}/references",
                    params={"fields": "isInfluential,title", "limit": 1000, "offset": offset},
                )
                data.extend(page.get("data", []))
                next_offset = page.get("next")
                if next_offset is None or next_offset <= offset:
                    break
                offset = next_offset
            response = {"data": data}
            self.cache.set(self.name, cache_key, response)
        return {
            cited_paper["paperId"]: item["isInfluential"]
            for item in response.get("data", [])
            if isinstance(item.get("isInfluential"), bool)
            and (cited_paper := item.get("citedPaper") or {}).get("paperId")
        }

    @staticmethod
    def _embedding(record: dict | None) -> list[float] | None:
        embedding = (record or {}).get("embedding") or {}
        return embedding.get("vector")


def cosine_similarity(left: list[float], right: list[float]) -> float | None:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return None
    return numerator / (left_norm * right_norm)
