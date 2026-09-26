"""Probe Crossref title search for PDFs lacking first-page DOI clues.

Uses only PDF metadata and the first two content lines; expected DOIs are
read from the saved benchmark only after search results have been selected.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import requests
from pypdf import PdfReader
from rapidfuzz.fuzz import ratio

from parsers.pdf_text import title_matches_first_page


def query_from_pdf(path: str) -> tuple[str, str]:
    reader = PdfReader(path)
    metadata_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    if len(metadata_title) >= 35 and len(metadata_title.split()) >= 5:
        return metadata_title, "metadata"
    lines = [line.strip() for line in (reader.pages[0].extract_text() or "").splitlines() if line.strip()]
    return " ".join(lines[1:3]), "first_page_lines"


def main() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    crossref = json.loads(Path("local-only/benchmark-crossref.json").read_text(encoding="utf-8"))
    names = [name for name in crossref if Path(name).name.startswith(("01_1983", "02_1984", "03_1985", "Guo et"))]
    if "--remaining" in sys.argv:
        names = [name for name in names if Path(name).name.startswith(("03_1985", "Guo et"))]
    session = requests.Session()
    session.headers["User-Agent"] = "NextRead-benchmark/0.1 (https://github.com/eyeyesight/NextRead)"
    for name in names:
        query, source = query_from_pdf(name)
        response = session.get("https://api.crossref.org/works", params={"query.bibliographic": query, "rows": 3, "select": "DOI,title"}, timeout=25)
        if response.status_code == 429:
            print("RATE_LIMITED", response.headers.get("Retry-After"), flush=True)
            return
        response.raise_for_status()
        items = response.json()["message"]["items"]
        first_page = PdfReader(name).pages[0].extract_text() or ""
        accepted = []
        for item in items:
            title = (item.get("title") or [""])[0]
            score = ratio(query.casefold(), title.casefold())
            valid = score >= 90 if source == "metadata" else title_matches_first_page(title, first_page) and score >= 85
            if valid:
                accepted.append(item["DOI"].lower())
            print(Path(name).name, source, round(score, 1), item.get("DOI"), "ACCEPT" if valid else "reject", flush=True)
        chosen = accepted[0] if len(accepted) == 1 else None
        print("SELECTED", chosen, "EXPECTED", crossref[name]["seed_doi"], flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
