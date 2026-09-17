from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from core.config import Settings
from core.models import AnalysisResult
from core.ranking import rank_papers
from graph.local_citation_graph import build_local_graph
from parsers.grobid import GrobidClient
from providers.openalex import OpenAlexProvider
from providers.semantic_scholar import SemanticScholarProvider
from providers.sjr import SjrProvider
from resolvers.crossref import CrossrefResolver
from storage.cache import ApiCache

logger = logging.getLogger(__name__)
Progress = Callable[[int, str], None]


class AnalysisPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = ApiCache(settings.cache_path, settings.cache_ttl_days, settings.cache_enabled)
        self.grobid = GrobidClient(settings.grobid_url)
        self.sjr = SjrProvider(settings.sjr_data_path)

    def analyze(
        self,
        pdf_path: str | Path,
        enabled: dict[str, bool],
        force_refresh: bool = False,
        progress: Progress | None = None,
        language: str = "zh-TW",
    ) -> AnalysisResult:
        update = progress or (lambda _step, _message: None)
        def message(zh_tw: str, en: str) -> str:
            return zh_tw if language == "zh-TW" else en

        states = {provider: "disabled" for provider in ("crossref", "openalex", "semantic_scholar")}
        warnings: list[str] = []
        logger.info("Analysis started: %s", Path(pdf_path).name)

        update(1, message("使用 GROBID 解析 PDF", "Parsing PDF with GROBID"))
        seed, papers = self.grobid.process_pdf(pdf_path)
        logger.info("Extracted %d references", len(papers))

        if enabled.get("crossref"):
            update(3, message("使用 Crossref 辨識參考文獻", "Resolving references with Crossref"))
            resolver = CrossrefResolver(self.cache, self.settings.crossref_mailto)
            states["crossref"] = "success"
            failures = 0
            for paper in papers:
                try:
                    resolver.resolve(paper, force_refresh)
                except Exception as exc:
                    failures += 1
                    paper.provider_data["crossref_error"] = str(exc)
            if failures:
                states["crossref"] = "partial" if failures < len(papers) else "failed"
                warnings.append(message(f"Crossref 有 {failures} 篇參考文獻查詢失敗。系統已保留未辨識項目。", f"Crossref failed for {failures} references; unresolved items were retained."))

        if enabled.get("openalex"):
            update(4, message("取得 OpenAlex 學術指標", "Fetching OpenAlex metrics"))
            provider = OpenAlexProvider(self.cache, self.settings.openalex_api_key, self.settings.crossref_mailto)
            try:
                provider.enrich(papers, force_refresh)
                failures = sum("openalex_error" in paper.provider_data for paper in papers if paper.doi)
                attempted = sum(bool(paper.doi) for paper in papers)
                states["openalex"] = "partial" if failures else "success"
                if failures:
                    warnings.append(message(f"OpenAlex 在 {attempted} 篇具有 DOI 的文獻中，有 {failures} 篇查詢失敗。", f"OpenAlex failed for {failures} of {attempted} references with a DOI."))
            except Exception as exc:
                states["openalex"] = "failed"
                warnings.append(message(f"OpenAlex 目前無法使用。排名將只採用其餘可用資料。（{exc}）", f"OpenAlex is unavailable; ranking uses the remaining data. ({exc})"))

        if enabled.get("semantic_scholar"):
            update(5, message("取得 Semantic Scholar 資料", "Fetching Semantic Scholar data"))
            provider = SemanticScholarProvider(self.cache, self.settings.semantic_scholar_api_key)
            try:
                provider.enrich_with_seed(seed, papers, force_refresh)
                states["semantic_scholar"] = "success"
            except Exception as exc:
                states["semantic_scholar"] = "failed"
                warnings.append(message(f"Semantic Scholar 目前無法使用。語意相關指標已排除。（{exc}）", f"Semantic Scholar is unavailable; semantic metrics were excluded. ({exc})"))

        self.sjr.enrich(papers)

        update(6, message("建立局部引用網路", "Building the local citation graph"))
        graph = build_local_graph(papers)
        update(7, message("計算閱讀優先分數", "Calculating Priority Scores"))
        rank_papers(papers, self.settings.ranking_weights)

        resolved = sum(paper.resolution_status != "unresolved" for paper in papers)
        openalex_coverage = sum(bool(paper.openalex_id) for paper in papers)
        semantic_coverage = sum(bool(paper.semantic_scholar_id) for paper in papers)
        sjr_coverage = sum(bool(paper.sjr_quartile) for paper in papers)
        active_dimensions = sum(
            any(getattr(paper, field) is not None for paper in papers)
            for field in (
                "field_impact_score", "local_network_score", "semantic_relevance_score",
                "influential_citation_score", "author_impact_score", "source_impact_score",
            )
        )
        stats = {
            "references_extracted": len(papers),
            "references_resolved": resolved,
            "resolution_rate": round(100 * resolved / len(papers), 1) if papers else 0.0,
            "openalex_coverage": openalex_coverage,
            "semantic_scholar_coverage": semantic_coverage,
            "sjr_coverage": sjr_coverage,
            "active_dimensions": active_dimensions,
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
            "cache_hits": self.cache.hits,
            "cache_misses": self.cache.misses,
        }
        logger.info("Analysis complete: %s", stats)
        return AnalysisResult(seed, papers, states, warnings, stats)
