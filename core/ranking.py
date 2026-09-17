from __future__ import annotations

from core.models import ReferencePaper
from core.normalization import log1p, mean_available, percentile_scores


DIMENSION_FIELDS = {
    "field_impact": "field_impact_score",
    "local_network": "local_network_score",
    "semantic_relevance": "semantic_relevance_score",
    "influential_citations": "influential_citation_score",
    "author_impact": "author_impact_score",
    "source_impact": "source_impact_score",
}

AUTHOR_MEDIAN_WEIGHT = 0.6097
AUTHOR_MAX_WEIGHT = 0.3903


def rank_papers(papers: list[ReferencePaper], weights: dict[str, float]) -> None:
    if not papers:
        return
    fwci = percentile_scores([paper.fwci for paper in papers], log1p)
    citations = percentile_scores([paper.citation_count for paper in papers], log1p)
    indegree = percentile_scores([paper.local_in_degree for paper in papers], log1p)
    pagerank = percentile_scores([paper.local_pagerank for paper in papers])
    connectivity = percentile_scores([paper.local_connectivity for paper in papers], log1p)
    author_median_h = percentile_scores([paper.author_h_index_median for paper in papers], log1p)
    author_max_h = percentile_scores([paper.author_h_index_max for paper in papers], log1p)
    source_h = percentile_scores([paper.source_h_index for paper in papers], log1p)
    source_mean = percentile_scores([paper.source_2yr_mean_citedness for paper in papers], log1p)

    total_configured_weight = sum(max(0.0, weight) for weight in weights.values())
    for index, paper in enumerate(papers):
        percentile = paper.citation_percentile
        paper.field_impact_score = (
            max(0.0, min(1.0, percentile))
            if percentile is not None
            else fwci[index] if fwci[index] is not None else citations[index]
        )
        paper.local_network_score = mean_available(indegree[index], pagerank[index], connectivity[index])
        paper.semantic_relevance_score = None if paper.semantic_similarity is None else max(0.0, min(1.0, (paper.semantic_similarity + 1) / 2))
        paper.influential_citation_score = (
            None if paper.is_influential_citation is None
            else float(paper.is_influential_citation)
        )
        if author_median_h[index] is None or author_max_h[index] is None:
            paper.author_impact_score = None
        else:
            paper.author_impact_score = (
                AUTHOR_MEDIAN_WEIGHT * author_median_h[index]
                + AUTHOR_MAX_WEIGHT * author_max_h[index]
            )
        paper.source_impact_score = mean_available(source_h[index], source_mean[index])

        weighted_sum = 0.0
        available_weight = 0.0
        for dimension, attribute in DIMENSION_FIELDS.items():
            score = getattr(paper, attribute)
            weight = max(0.0, weights.get(dimension, 0.0))
            if score is not None and weight:
                weighted_sum += score * weight
                available_weight += weight
        paper.priority_score = round(100 * weighted_sum / available_weight, 1) if available_weight else None
        paper.evidence_coverage = round(100 * available_weight / total_configured_weight, 1) if total_configured_weight else None

    papers.sort(key=lambda paper: paper.priority_score if paper.priority_score is not None else -1, reverse=True)
