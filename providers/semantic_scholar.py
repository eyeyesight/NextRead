from __future__ import annotations

import math
import re
import unicodedata

import requests

from core.models import ReferencePaper, SeedPaper
from core.security import redact_text
from parsers.grobid import normalize_doi
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
        self.http = HttpClient(headers=headers, min_interval=1.1)
        self.partial_errors: list[str] = []
        self.seed_status: str | None = None
        self.seed_warning: str | None = None
        self.seed_match_method: str | None = None

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> set[Capability]:
        return {Capability.INFLUENTIAL_CITATIONS, Capability.SPECTER2_EMBEDDING}

    def enrich(self, papers: list[ReferencePaper], force_refresh: bool = False) -> None:
        self.enrich_with_seed(None, papers, force_refresh)

    def enrich_with_seed(self, seed: SeedPaper | None, papers: list[ReferencePaper], force_refresh: bool = False) -> None:
        self.partial_errors = []
        self.seed_status = None
        self.seed_warning = None
        self.seed_match_method = None
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
                self.partial_errors.append(redact_text(str(exc), (self.api_key,)))
                break
            except requests.RequestException as exc:
                self.partial_errors.append(redact_text(str(exc), (self.api_key,)))
                break
            for doi, record in zip(chunk, response):
                if record:
                    records[doi] = record
                    self.cache.set(self.name, f"doi:{doi}", record)
        seed_record = records.get(seed.doi) if seed and seed.doi else None
        if seed:
            if not seed.doi and not self.partial_errors:
                try:
                    seed_record = self._seed_from_title(seed, force_refresh)
                except requests.RequestException as exc:
                    self.partial_errors.append(redact_text(str(exc), (self.api_key,)))
            if seed_record and seed_record.get("paperId"):
                self.seed_status = "resolved"
                self.seed_match_method = "doi" if seed.doi else "metadata"
                if not self._embedding(seed_record):
                    self.seed_warning = "Semantic Scholar 未提供原始論文的語意向量，無法計算語意相似度。"
            elif self.partial_errors:
                self.seed_status = "api_error"
            elif not self.seed_status:
                self.seed_status = "unmatched"
            if self.seed_status == "insufficient_metadata":
                self.seed_warning = "原始論文缺少 DOI 或完整的標題與作者資料，無法計算語意相似度與具影響力引用。"
            elif self.seed_status in {"unmatched", "api_error"}:
                self.seed_warning = "未能確認原始論文在 Semantic Scholar 中的相同發表版本，無法計算語意相似度與具影響力引用。"
        seed_embedding = self._embedding(seed_record)
        influential_edges = {}
        if not self.partial_errors:
            try:
                influential_edges = self._influential_edges(seed_record, force_refresh)
            except requests.RequestException as exc:
                self.partial_errors.append(redact_text(str(exc), (self.api_key,)))
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

    def _seed_from_title(self, seed: SeedPaper, force_refresh: bool) -> dict | None:
        if not _identity_text(seed.title) or not seed.authors or not all(_identity_text(name) for name in seed.authors):
            self.seed_status = "insufficient_metadata"
            return None
        # Keep punctuation-separated words in the cache key, including non-Latin scripts.
        key = f"seed-search-v1:{_identity_text(seed.title)}"
        payload = self.cache.get(self.name, key, force_refresh)
        if payload is None:
            payload = self.http.get_json(
                f"{self.paper_url}/search",
                params={
                    "query": seed.title,
                    "limit": 5,
                    "fields": "title,year,authors,externalIds,publicationTypes,venue",
                },
            )
            self.cache.set(self.name, key, payload)
        candidates = {
            candidate["paperId"]: candidate
            for candidate in payload.get("data", [])
            if candidate.get("paperId") and _matches_published_seed(seed, candidate)
        }
        if len(candidates) != 1:
            return None
        seed_id = next(iter(candidates))
        record_key = f"paper:{seed_id}"
        record = self.cache.get(self.name, record_key, force_refresh)
        if record is None:
            record = self.http.get_json(f"{self.paper_url}/{seed_id}", params={"fields": self.fields})
            self.cache.set(self.name, record_key, record)
        return record if record.get("paperId") == seed_id else None

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


def _identity_text(value: str | None) -> str:
    text = "".join(char for char in unicodedata.normalize("NFKD", value or "").casefold() if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def _same_author(left: str, right: str) -> bool:
    left_parts, right_parts = _identity_text(left).split(), _identity_text(right).split()
    if not left_parts or not right_parts or left_parts[-1] != right_parts[-1]:
        return False
    # An extracted surname alone does not establish identity; full names or given initials are required.
    if len(left_parts) < 2 or len(right_parts) < 2:
        return left_parts == right_parts and any(ord(char) > 127 for char in "".join(left_parts))
    return left_parts[0] == right_parts[0] or (
        left_parts[0][0] == right_parts[0][0] and min(len(left_parts[0]), len(right_parts[0])) == 1
    )


def _matches_published_seed(seed: SeedPaper, candidate: dict) -> bool:
    if _identity_text(seed.title) != _identity_text(candidate.get("title")):
        return False
    if seed.year is not None and seed.year != candidate.get("year"):
        return False
    authors = [author.get("name", "") for author in candidate.get("authors") or []]
    if len(authors) != len(seed.authors) or not all(_same_author(left, right) for left, right in zip(seed.authors, authors)):
        return False
    doi = normalize_doi((candidate.get("externalIds") or {}).get("DOI"))
    if not doi or doi.startswith(("10.48550/", "10.1101/", "10.21203/", "10.2139/", "10.31219/", "10.31234/")):
        return False
    venue = candidate.get("venue") or ""
    if re.search(r"arxiv|biorxiv|medrxiv|preprint|ssrn|research\s*square", venue, re.I):
        return False
    publication_types = set(candidate.get("publicationTypes") or [])
    return bool(venue.strip()) and (
        not publication_types or bool(publication_types & {"JournalArticle", "Conference"})
    )
