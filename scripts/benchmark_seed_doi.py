"""Offline first-page DOI benchmark using previously cached Crossref titles.

The cache is used only to answer title lookups for DOI candidates found in a
PDF. Expected DOIs are compared afterward, never supplied to the extractor.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from parsers.pdf_text import title_matches_first_page, verified_seed_doi


def main() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    baseline = json.loads(Path("local-only/benchmark-grobid.json").read_text(encoding="utf-8"))
    crossref = json.loads(Path("local-only/benchmark-crossref.json").read_text(encoding="utf-8"))
    titles = {record["seed_doi"]: record["title"] for record in crossref.values() if record.get("title")}
    tested = correct = wrong = 0
    for name, result in baseline.items():
        if "error" in result:
            continue
        tested += 1
        found = verified_seed_doi(name, titles.get)
        expected = crossref.get(name, {}).get("seed_doi")
        status = "correct" if found and found == expected else "wrong" if found else "unresolved"
        correct += status == "correct"
        wrong += status == "wrong"
        print(f"{status}\t{Path(name).name}\t{found or ''}")
    print(f"TOTAL tested={tested} correct={correct} wrong={wrong} unresolved={tested - correct - wrong}")

    # Negative controls: every known source title against every other PDF.
    # This is a rough specificity check, not a representative false-positive rate.
    from pypdf import PdfReader

    pages = {name: PdfReader(name).pages[0].extract_text() or "" for name in crossref}
    mismatches = [
        (source, target)
        for source, record in crossref.items()
        for target, page_text in pages.items()
        if source != target and record.get("title") and title_matches_first_page(record["title"], page_text)
    ]
    positive_failures = [name for name, record in crossref.items() if record.get("title") and not title_matches_first_page(record["title"], pages[name])]
    print(f"TITLE_CONTROLS cross_paper_matches={len(mismatches)} of {len(titles) * (len(pages) - 1)} positive_failures={len(positive_failures)}")
    for name in positive_failures:
        print("TITLE_NOT_ON_FIRST_PAGE", Path(name).name)


if __name__ == "__main__":
    main()
