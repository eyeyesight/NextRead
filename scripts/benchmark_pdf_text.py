"""Compare the experimental numbered-PDF path with a saved GROBID run.

Run ``python -m scripts.benchmark_pdf_text`` from the repository root after
creating local-only/benchmark-grobid.json.
This benchmark does not call GROBID or any external API.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from parsers.pdf_text import extract_numbered_references


def main() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    baseline = json.loads(Path("local-only/benchmark-grobid.json").read_text(encoding="utf-8"))
    totals = {key: 0 for key in ("scanned", "supported", "references", "grobid_references", "dois", "grobid_dois", "matching_dois", "pdf_only_dois")}
    start = time.perf_counter()
    for name, result in baseline.items():
        if "error" in result:
            continue
        totals["scanned"] += 1
        try:
            references = extract_numbered_references(name)
        except ValueError:
            continue
        found = {paper.doi for paper in references if paper.doi}
        expected = {paper["doi"] for paper in result["references"] if paper["doi"]}
        totals["supported"] += 1
        totals["references"] += len(references)
        totals["grobid_references"] += len(result["references"])
        totals["dois"] += len(found)
        totals["grobid_dois"] += len(expected)
        totals["matching_dois"] += len(found & expected)
        totals["pdf_only_dois"] += len(found - expected)
        print(f"{Path(name).name}\t{len(references)} refs\t{len(found)} DOI\t{len(found & expected)} matching GROBID")
    print("TOTAL", json.dumps(totals), f"{time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    main()
