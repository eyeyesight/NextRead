from __future__ import annotations

import re
import unicodedata
from typing import Any

from rapidfuzz.fuzz import ratio

from core.models import ReferencePaper
from parsers.grobid import normalize_doi
from providers.http import HttpClient
from storage.cache import ApiCache


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _first_author_surname(authors: list[str]) -> str:
    if not authors:
        return ""
    tokens = _normalize(authors[0]).split()
    return tokens[-1] if tokens else ""


def score_candidate(paper: ReferencePaper, candidate: dict[str, Any]) -> float:
    candidate_title = (candidate.get("title") or [""])[0]
    title_score = ratio(_normalize(paper.title), _normalize(candidate_title)) / 100
    candidate_year = None
    date_parts = (candidate.get("published") or candidate.get("issued") or {}).get("date-parts", [])
    if date_parts and date_parts[0]:
        candidate_year = date_parts[0][0]
    year_score = 0.0 if not paper.year or not candidate_year else (1.0 if paper.year == candidate_year else 0.5 if abs(paper.year - candidate_year) == 1 else 0.0)
    candidate_authors = [" ".join(filter(None, [author.get("given"), author.get("family")])) for author in candidate.get("author", [])]
    author_score = ratio(_first_author_surname(paper.authors), _first_author_surname(candidate_authors)) / 100 if paper.authors and candidate_authors else 0.0
    source = (candidate.get("container-title") or [""])[0]
    source_score = ratio(_normalize(paper.source_name), _normalize(source)) / 100 if paper.source_name and source else 0.0
    return 0.65 * title_score + 0.15 * year_score + 0.15 * author_score + 0.05 * source_score


class CrossrefResolver:
    name = "crossref"

    def __init__(self, cache: ApiCache, mailto: str = ""):
        self.cache = cache
        self.mailto = mailto
        self.http = HttpClient()

    def resolve(self, paper: ReferencePaper, force_refresh: bool = False) -> ReferencePaper:
        if paper.doi:
            paper.doi = normalize_doi(paper.doi)
            paper.resolution_status = "exact_doi"
            paper.resolution_confidence = 1.0
            return paper
        query = paper.raw_reference or " ".join(filter(None, [paper.title, paper.source_name, str(paper.year or "")]))
        if not query.strip():
            return paper
        key = _normalize(query)
        payload = self.cache.get(self.name, key, force_refresh)
        if payload is None:
            params: dict[str, str | int] = {"query.bibliographic": query, "rows": 5}
            if self.mailto:
                params["mailto"] = self.mailto
            payload = self.http.get_json("https://api.crossref.org/works", params=params)
            self.cache.set(self.name, key, payload)
        candidates = payload.get("message", {}).get("items", [])
        if not candidates:
            return paper
        candidate, confidence = max(((item, score_candidate(paper, item)) for item in candidates), key=lambda pair: pair[1])
        if confidence < 0.72:
            paper.resolution_confidence = round(confidence, 3)
            return paper
        paper.doi = normalize_doi(candidate.get("DOI"))
        if not paper.doi:
            return paper
        paper.resolution_confidence = round(confidence, 3)
        paper.resolution_status = "high_confidence" if confidence >= 0.85 else "medium_confidence"
        paper.title = (candidate.get("title") or [paper.title])[0]
        paper.source_name = (candidate.get("container-title") or [paper.source_name])[0]
        if not paper.authors:
            paper.authors = [
                " ".join(filter(None, [author.get("given"), author.get("family")]))
                for author in candidate.get("author", [])
            ]
        return paper
