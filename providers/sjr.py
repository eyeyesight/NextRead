from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from core.models import ReferencePaper


def _normalize_issn(value: str | None) -> str:
    return re.sub(r"[^0-9X]", "", (value or "").upper())


def _normalize_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _number(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


class SjrProvider:
    """Local lookup against the official SCImago journal-rank CSV export."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.year = self._year_from_name(self.path.name)
        self.by_issn: dict[str, dict[str, str]] = {}
        self.by_title: dict[str, dict[str, str]] = {}
        if self.path.is_file():
            self._load()

    @property
    def available(self) -> bool:
        return bool(self.by_title)

    @staticmethod
    def _year_from_name(name: str) -> int | None:
        match = re.search(r"(?:19|20)\d{2}", name)
        return int(match.group()) if match else None

    def _load(self) -> None:
        try:
            content = self.path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = self.path.read_text(encoding="latin-1")
        reader = csv.DictReader(content.splitlines(), delimiter=";")
        header_years = [
            int(match.group(1))
            for field in (reader.fieldnames or [])
            if (match := re.search(r"Total Docs\. \((20\d{2})\)", field))
        ]
        if header_years:
            self.year = header_years[0]
        for row in reader:
            title = _normalize_title(row.get("Title"))
            if not title:
                continue
            self.by_title[title] = row
            for issn in re.split(r"[,;]", row.get("Issn") or ""):
                normalized = _normalize_issn(issn)
                if normalized:
                    self.by_issn[normalized] = row

    def enrich(self, papers: list[ReferencePaper]) -> None:
        if not self.available:
            return
        for paper in papers:
            row = None
            match_method = None
            for issn in [paper.source_issn_l, *paper.source_issns]:
                row = self.by_issn.get(_normalize_issn(issn))
                if row:
                    match_method = "issn"
                    break
            if row is None:
                row = self.by_title.get(_normalize_title(paper.source_name))
                if row:
                    match_method = "title"
            if row is None:
                continue
            paper.sjr_score = _number(row.get("SJR"))
            paper.sjr_quartile = (row.get("SJR Best Quartile") or "").strip() or None
            paper.sjr_year = self.year
            paper.sjr_categories = (row.get("Categories") or "").strip() or None
            paper.sjr_match_method = match_method
