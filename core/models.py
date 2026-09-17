from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field
from typing import Any


@dataclass
class SeedPaper:
    title: str | None = None
    doi: str | None = None
    authors: list[str] = dataclass_field(default_factory=list)
    abstract: str | None = None
    year: int | None = None


@dataclass
class ReferencePaper:
    raw_reference: str = ""
    title: str | None = None
    doi: str | None = None
    year: int | None = None
    authors: list[str] = dataclass_field(default_factory=list)
    source_name: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None

    resolution_status: str = "unresolved"
    resolution_confidence: float | None = None

    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    semantic_scholar_url: str | None = None
    citation_count: int | None = None
    fwci: float | None = None
    citation_percentile: float | None = None
    work_type: str | None = None
    referenced_works: list[str] = dataclass_field(default_factory=list)
    is_open_access: bool | None = None
    open_access_url: str | None = None
    is_retracted: bool | None = None

    domain: str | None = None
    field: str | None = None
    subfield: str | None = None
    primary_topic: str | None = None
    other_topics: list[str] = dataclass_field(default_factory=list)

    local_in_degree: int | None = None
    local_pagerank: float | None = None
    local_connectivity: int | None = None

    semantic_similarity: float | None = None
    is_influential_citation: bool | None = None
    embedding: list[float] | None = dataclass_field(default=None, repr=False)

    first_author_name: str | None = None
    author_h_indices: list[int] = dataclass_field(default_factory=list)
    author_h_index_median: float | None = None
    author_h_index_max: int | None = None
    author_metadata_coverage: float | None = None

    source_openalex_id: str | None = None
    source_issn_l: str | None = None
    source_issns: list[str] = dataclass_field(default_factory=list)
    source_type: str | None = None
    source_works_count: int | None = None
    source_cited_by_count: int | None = None
    source_h_index: int | None = None
    source_i10_index: int | None = None
    source_2yr_mean_citedness: float | None = None

    sjr_score: float | None = None
    sjr_quartile: str | None = None
    sjr_year: int | None = None
    sjr_categories: str | None = None
    sjr_match_method: str | None = None

    priority_score: float | None = None
    evidence_coverage: float | None = None
    field_impact_score: float | None = None
    local_network_score: float | None = None
    semantic_relevance_score: float | None = None
    influential_citation_score: float | None = None
    author_impact_score: float | None = None
    source_impact_score: float | None = None

    provider_data: dict[str, Any] = dataclass_field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    seed: SeedPaper
    references: list[ReferencePaper]
    provider_states: dict[str, str]
    warnings: list[str] = dataclass_field(default_factory=list)
    stats: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": asdict(self.seed),
            "references": [paper.to_dict() for paper in self.references],
            "provider_states": self.provider_states,
            "warnings": self.warnings,
            "stats": self.stats,
        }
