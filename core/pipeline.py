from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from core.config import Settings
from core.models import AnalysisResult
from core.ranking import rank_papers
from graph.local_citation_graph import build_local_graph
from parsers.grobid import GrobidClient
from parsers.pdf_text import extract_numbered_references, title_matches_first_page, verified_seed_doi
from providers.openalex import OpenAlexProvider
from providers.semantic_scholar import SemanticScholarProvider
from providers.sjr import SjrProvider
from resolvers.crossref import CrossrefResolver
from storage.cache import ApiCache

logger = logging.getLogger(__name__)
Progress = Callable[[int, str], None]


def pdf_matches_seed(pdf_path: str | Path, title: str | None) -> bool:
    from pypdf import PdfReader

    first_page = PdfReader(pdf_path).pages[0].extract_text() or ""
    return bool(title and title_matches_first_page(title, first_page))


def pdf_title_hints(pdf_path: str | Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    metadata_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    lines = [line.strip() for line in (reader.pages[0].extract_text() or "").splitlines() if line.strip()]
    hints = [metadata_title] if len(metadata_title) >= 35 and len(metadata_title.split()) >= 5 else []
    if len(lines) >= 3:
        hints.append(" ".join(lines[1:3]))
    return hints


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
        update(1, "正在用 GROBID 解析 PDF" if language == "zh-TW" else "Parsing PDF with GROBID")
        seed, papers = self.grobid.process_pdf(pdf_path)
        return self._finish(seed, papers, enabled, force_refresh, progress, language, "grobid")

    def analyze_identifier(
        self,
        identifier: str,
        enabled: dict[str, bool],
        pdf_path: str | Path | None = None,
        force_refresh: bool = False,
        progress: Progress | None = None,
        language: str = "zh-TW",
        use_grobid: bool = False,
    ) -> AnalysisResult:
        update = progress or (lambda _step, _message: None)
        resolver = CrossrefResolver(self.cache, self.settings.crossref_mailto)
        if not identifier.strip():
            if pdf_path is None:
                raise ValueError("Enter a DOI or title, or upload a PDF")
            if use_grobid:
                return self.analyze(pdf_path, enabled, force_refresh, progress, language)
            update(1, "正在從 PDF 辨識原始論文 DOI" if language == "zh-TW" else "Identifying the source DOI from PDF")
            def lookup_title(value: str) -> str | None:
                try:
                    return resolver.source_work(value, force_refresh)[0].title
                except Exception:
                    return None
            doi = verified_seed_doi(pdf_path, lookup_title)
            if doi:
                identifier = doi
            else:
                for hint in pdf_title_hints(pdf_path):
                    try:
                        candidate, _ = resolver.source_work(hint, force_refresh)
                        if pdf_matches_seed(pdf_path, candidate.title):
                            identifier = candidate.doi or ""
                            break
                    except ValueError:
                        continue
                if not identifier:
                    raise ValueError("Could not verify the source paper from PDF; enter its DOI or title")
        update(1, "正在從 Crossref 取得原始論文與參考文獻" if language == "zh-TW" else "Fetching source paper and references from Crossref")
        seed, papers = resolver.source_work(identifier, force_refresh)
        crossref_papers = papers
        pdf_references = None
        extraction = None
        comparison_error = None
        if pdf_path is not None:
            try:
                if use_grobid:
                    pdf_seed, pdf_references = self.grobid.process_pdf(pdf_path)
                    extraction = "grobid"
                else:
                    pdf_seed = None
                    pdf_references = extract_numbered_references(pdf_path)
                    extraction = "numbered_pdf_text"
                if pdf_seed and pdf_seed.doi and pdf_seed.doi != seed.doi:
                    raise ValueError("PDF source DOI differs from the selected Crossref paper")
                if not pdf_matches_seed(pdf_path, seed.title):
                    raise ValueError("Could not confirm that this PDF is the selected paper")
            except Exception as exc:
                comparison_error = str(exc)
                pdf_references = None
                extraction = None
        reference_source = "crossref"
        if not papers and pdf_references:
            papers = pdf_references
            reference_source = extraction
        result = self._finish(seed, papers, enabled, force_refresh, progress, language, reference_source)
        if reference_source == "crossref":
            result.warnings.insert(0, (
                "這份清單來自出版者提交給 Crossref 的資料，尚未與論文 PDF 完整核對，可能有遺漏。"
                if language == "zh-TW" else
                "This list is publisher-deposited Crossref data, not proven identical to the paper PDF; a nonempty list may still be incomplete."
            ))
        else:
            result.warnings.insert(0, (
                "Crossref 未提供參考文獻；這份清單從 PDF 抽取，尚未逐筆確認是否完整。"
                if language == "zh-TW" else
                "Crossref supplied no references; this list was extracted from the PDF and has not been checked item by item for completeness."
            ))
        if not crossref_papers:
            result.provider_states["crossref"] = "no_references"
        if not crossref_papers and not pdf_references:
            result.warnings.append(
                ("Crossref 沒有參考文獻清單。請上傳 PDF，從原文抽取。" if pdf_path is None else "Crossref 沒有參考文獻清單，PDF 也未能抽出可用清單。")
                if language == "zh-TW" else
                ("Crossref has no reference list. Upload the PDF to extract references from the source." if pdf_path is None else "Crossref has no reference list, and the PDF did not yield a usable list.")
            )
        if pdf_references is not None and crossref_papers:
            source_dois = {paper.doi for paper in crossref_papers if paper.doi}
            pdf_dois = {paper.doi for paper in pdf_references if paper.doi}
            result.stats["pdf_comparison"] = {
                "extractor": extraction,
                "pdf_references": len(pdf_references),
                "pdf_dois": len(pdf_dois),
                "crossref_dois": len(source_dois),
                "shared_dois": len(source_dois & pdf_dois),
                "status": "partial_comparison",
            }
            result.warnings.append(
                "PDF 比對只涵蓋成功抽出的 DOI，無法證明兩份清單或逐筆文字完全一致。"
                if language == "zh-TW" else
                "PDF comparison covers extracted DOIs only; it cannot prove complete list or item-by-item text agreement."
            )
        elif comparison_error:
            result.stats["pdf_comparison"] = {"status": "unavailable", "reason": comparison_error}
            result.warnings.append(
                f"無法與 PDF 中的參考文獻比對：{comparison_error}" if language == "zh-TW" else f"Could not compare PDF references: {comparison_error}"
            )
        return result

    def _finish(
        self,
        seed,
        papers,
        enabled,
        force_refresh,
        progress,
        language,
        reference_source,
    ) -> AnalysisResult:
        update = progress or (lambda _step, _message: None)
        def message(zh_tw: str, en: str) -> str:
            return zh_tw if language == "zh-TW" else en

        def network_hint(error_key: str) -> str:
            for paper in papers:
                detail = str(paper.provider_data.get(error_key, ""))
                if detail.startswith("Windows 拒絕 NextRead"):
                    return f" {detail}" if language == "zh-TW" else " Windows denied Python network access; check firewall, proxy, or antivirus settings."
            return ""

        states = {provider: "disabled" for provider in ("crossref", "openalex", "semantic_scholar")}
        warnings: list[str] = []
        logger.info("Analysis started: %s", seed.doi or seed.title)
        logger.info("Extracted %d references", len(papers))

        if enabled.get("crossref"):
            update(3, message("正在用 Crossref 辨識參考文獻", "Resolving references with Crossref"))
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
                warnings.append(message(f"Crossref 有 {failures} 篇參考文獻查詢失敗；未辨識的項目仍保留在清單中。", f"Crossref failed for {failures} references; unresolved items were retained.") + network_hint("crossref_error"))

        if enabled.get("openalex"):
            update(4, message("正在取得 OpenAlex 學術指標", "Fetching OpenAlex metrics"))
            provider = OpenAlexProvider(self.cache, self.settings.openalex_api_key, self.settings.crossref_mailto)
            try:
                provider.enrich(papers, force_refresh)
                failures = sum("openalex_error" in paper.provider_data for paper in papers if paper.doi)
                attempted = sum(bool(paper.doi) for paper in papers)
                states["openalex"] = "partial" if failures else "success"
                if failures:
                    warnings.append(message(f"{attempted} 篇有 DOI 的文獻中，有 {failures} 篇未能從 OpenAlex 取得資料。", f"OpenAlex failed for {failures} of {attempted} references with a DOI.") + network_hint("openalex_error"))
            except Exception as exc:
                states["openalex"] = "failed"
                warnings.append(message(f"目前無法取得 OpenAlex 資料；排名會使用其他已取得的資料。（{exc}）", f"OpenAlex is unavailable; ranking uses the remaining data. ({exc})"))

        if enabled.get("semantic_scholar"):
            update(5, message("正在取得 Semantic Scholar 資料", "Fetching Semantic Scholar data"))
            provider = SemanticScholarProvider(self.cache, self.settings.semantic_scholar_api_key)
            try:
                provider.enrich_with_seed(seed, papers, force_refresh)
                if provider.partial_errors:
                    states["semantic_scholar"] = "partial" if any(paper.semantic_scholar_id for paper in papers) else "failed"
                    detail = provider.partial_errors[0]
                    warnings.append(message(
                        f"部分 Semantic Scholar 查詢失敗；已取得的資料仍會保留，缺少的語意與影響力指標不計分。（{detail}）",
                        f"Some Semantic Scholar queries failed; available data was retained, and missing semantic and influential-citation signals were excluded. ({detail})",
                    ))
                else:
                    states["semantic_scholar"] = "success"
            except Exception as exc:
                states["semantic_scholar"] = "failed"
                warnings.append(message(f"目前無法取得 Semantic Scholar 資料；語意相關指標不計分。（{exc}）", f"Semantic Scholar is unavailable; semantic metrics were excluded. ({exc})"))

        self.sjr.enrich(papers)

        update(6, message("正在建立清單內引用網路", "Building the local citation graph"))
        graph = build_local_graph(papers)
        update(7, message("正在計算閱讀優先分數", "Calculating Priority Scores"))
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
            "reference_source": reference_source,
            "reference_verification": "unverified",
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
