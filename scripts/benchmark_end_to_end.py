"""Offline reference and recommendation comparison for the saved PDF corpus.

Run from the repository root: ``python -m scripts.benchmark_end_to_end``.
All API reads use the existing SQLite cache. Missing records stay missing.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

from rapidfuzz.fuzz import ratio

from core.config import load_settings
from core.models import ReferencePaper, SeedPaper
from core.ranking import DIMENSION_FIELDS, rank_papers
from graph.local_citation_graph import build_local_graph
from parsers.grobid import normalize_doi
from providers.openalex import OpenAlexProvider
from providers.semantic_scholar import SemanticScholarProvider
from providers.sjr import SjrProvider
from resolvers.crossref import CrossrefResolver, _normalize


ROOT = Path(__file__).resolve().parent.parent


class ReadOnlyCache:
    """Return an empty response on cache miss so providers never use HTTP."""

    def __init__(self, path: Path):
        with sqlite3.connect(path) as connection:
            self.records = {
                (provider, identifier): json.loads(payload)
                for provider, identifier, payload in connection.execute(
                    "SELECT provider, identifier, response_json FROM api_cache"
                )
            }
        self.hits = Counter()
        self.misses = Counter()

    def get(self, provider: str, identifier: str, force_refresh: bool = False) -> dict:
        value = self.records.get((provider, identifier))
        (self.hits if value is not None else self.misses)[provider] += 1
        return value if value is not None else {}

    def set(self, provider: str, identifier: str, response: dict) -> None:
        raise AssertionError("Benchmark cache is read-only")


def grobid_papers(rows: list[dict]) -> list[ReferencePaper]:
    return [
        ReferencePaper(
            raw_reference=row.get("raw") or "",
            title=row.get("title"),
            doi=row.get("doi"),
            year=row.get("year"),
            authors=row.get("authors") or [],
            source_name=row.get("source"),
        )
        for row in rows
    ]


def crossref_papers(rows: list[dict]) -> list[ReferencePaper]:
    papers = []
    for row in rows:
        year = row.get("year")
        try:
            year = int(year) if year else None
        except ValueError:
            year = None
        title = row.get("article-title")
        author = row.get("author")
        raw = row.get("unstructured") or title or row.get("DOI") or ""
        papers.append(
            ReferencePaper(
                raw_reference=raw,
                title=title,
                doi=row.get("DOI"),
                year=year,
                authors=[author] if author else [],
            )
        )
    return papers


def identify(papers: list[ReferencePaper], resolver: CrossrefResolver) -> None:
    for paper in papers:
        resolver.resolve(paper)


def match_works(left: list[ReferencePaper], right: list[ReferencePaper]) -> Counter:
    """Conservative one-to-one DOI match, then near-exact title and year match."""
    result = Counter()
    unused = set(range(len(right)))
    matched_left = set()
    for i, paper in enumerate(left):
        doi = normalize_doi(paper.doi) if paper.doi else None
        if not doi:
            continue
        j = next((j for j in sorted(unused) if right[j].doi and normalize_doi(right[j].doi) == doi), None)
        if j is not None:
            result["doi"] += 1
            unused.remove(j)
            matched_left.add(i)
    for i, paper in enumerate(left):
        title = _normalize(paper.title)
        if i in matched_left or len(title) < 12:
            continue
        candidates = [
            j for j in unused
            if len(_normalize(right[j].title)) >= 12
            and not (paper.doi and right[j].doi)
            and (not paper.year or not right[j].year or abs(paper.year - right[j].year) <= 1)
            and ratio(title, _normalize(right[j].title)) >= 95
        ]
        if len(candidates) == 1:
            result["title"] += 1
            unused.remove(candidates[0])
    return result


def enrich_and_rank(
    seed: SeedPaper,
    papers: list[ReferencePaper],
    resolver: CrossrefResolver,
    openalex: OpenAlexProvider,
    semantic: SemanticScholarProvider,
    sjr: SjrProvider,
    weights: dict[str, float],
) -> dict:
    identify(papers, resolver)
    openalex.enrich(papers)
    semantic.enrich_with_seed(seed, papers)
    sjr.enrich(papers)
    build_local_graph(papers)
    rank_papers(papers, weights)
    scored = [paper for paper in papers if paper.priority_score is not None]
    ordered = list(dict.fromkeys(normalize_doi(paper.doi) for paper in scored if paper.doi))
    features = {
        name: sum(getattr(paper, field) is not None for paper in papers)
        for name, field in DIMENSION_FIELDS.items()
    }
    return {
        "references": len(papers),
        "resolved": sum(bool(paper.doi) for paper in papers),
        "rankable": len(scored),
        "ranked_dois": ordered,
        "features": features,
        "evidence_coverage_mean": round(sum(paper.evidence_coverage or 0 for paper in scored) / len(scored), 1) if scored else None,
        "papers": papers,
    }


def spearman_on_shared(left: list[str], right: list[str]) -> float | None:
    shared = set(left) & set(right)
    if len(shared) < 2:
        return None
    a = [doi for doi in left if doi in shared]
    b = [doi for doi in right if doi in shared]
    positions = {doi: i for i, doi in enumerate(b)}
    n = len(shared)
    return 1 - 6 * sum((i - positions[doi]) ** 2 for i, doi in enumerate(a)) / (n * (n * n - 1))


def summarize_pair(grobid: dict, crossref: dict) -> dict:
    a, b = grobid["ranked_dois"], crossref["ranked_dois"]
    shared = set(a) & set(b)
    a_shared = [doi for doi in a if doi in shared]
    b_shared = [doi for doi in b if doi in shared]
    return {
        "matched": dict(match_works(grobid["papers"], crossref["papers"])),
        "shared_ranked_dois": len(shared),
        "top5_full_overlap": len(set(a[:5]) & set(b[:5])),
        "top10_full_overlap": len(set(a[:10]) & set(b[:10])),
        "top5_shared_overlap": len(set(a_shared[:5]) & set(b_shared[:5])),
        "top10_shared_overlap": len(set(a_shared[:10]) & set(b_shared[:10])),
        "spearman_shared": spearman_on_shared(a, b),
    }


def main() -> None:
    start = time.perf_counter()
    baseline = json.loads((ROOT / "local-only/benchmark-grobid.json").read_text(encoding="utf-8"))
    deposited = json.loads((ROOT / "local-only/benchmark-crossref.json").read_text(encoding="utf-8"))
    settings = load_settings(ROOT / "config/settings.yaml")
    cache = ReadOnlyCache(ROOT / "data/cache.db")
    resolver = CrossrefResolver(cache)
    openalex = OpenAlexProvider(cache)
    semantic = SemanticScholarProvider(cache)
    sjr = SjrProvider(ROOT / settings.sjr_data_path)
    rows = []
    for name, original in baseline.items():
        if "error" in original:
            continue
        source = deposited.get(name)
        if not source or not source.get("references"):
            continue
        seed = SeedPaper(
            title=original["seed"].get("title"),
            doi=source["seed_doi"],
            authors=original["seed"].get("authors") or [],
            year=original["seed"].get("year"),
        )
        g_papers = grobid_papers(original["references"])
        c_papers = crossref_papers(source["references"])
        raw_match = dict(match_works(g_papers, c_papers))
        g = enrich_and_rank(seed, g_papers, resolver, openalex, semantic, sjr, settings.ranking_weights)
        c = enrich_and_rank(seed, c_papers, resolver, openalex, semantic, sjr, settings.ranking_weights)
        pair = summarize_pair(g, c)
        rows.append({
            "paper": Path(name).name,
            "seed_doi": seed.doi,
            "raw_matched": raw_match,
            "grobid": {key: value for key, value in g.items() if key != "papers"},
            "crossref": {key: value for key, value in c.items() if key != "papers"},
            **pair,
        })
    totals = {
        "papers": len(rows),
        "references": {route: sum(row[route]["references"] for row in rows) for route in ("grobid", "crossref")},
        "resolved": {route: sum(row[route]["resolved"] for row in rows) for route in ("grobid", "crossref")},
        "rankable": {route: sum(row[route]["rankable"] for row in rows) for route in ("grobid", "crossref")},
        "matched": dict(sum((Counter(row["matched"]) for row in rows), Counter())),
        "raw_matched": dict(sum((Counter(row["raw_matched"]) for row in rows), Counter())),
        "feature_available": {
            route: dict(sum((Counter(row[route]["features"]) for row in rows), Counter()))
            for route in ("grobid", "crossref")
        },
        "full_top5_overlap": sum(row["top5_full_overlap"] for row in rows),
        "full_top10_overlap": sum(row["top10_full_overlap"] for row in rows),
        "shared_top5_overlap": sum(row["top5_shared_overlap"] for row in rows),
        "shared_top10_overlap": sum(row["top10_shared_overlap"] for row in rows),
        "shared_ranked_dois": sum(row["shared_ranked_dois"] for row in rows),
        "spearman_shared_mean": round(sum(row["spearman_shared"] for row in rows if row["spearman_shared"] is not None) / sum(row["spearman_shared"] is not None for row in rows), 3) if any(row["spearman_shared"] is not None for row in rows) else None,
        "cache_hits": dict(cache.hits),
        "cache_misses": dict(cache.misses),
        "elapsed_seconds": round(time.perf_counter() - start, 2),
    }
    print(json.dumps({"totals": totals, "papers": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
