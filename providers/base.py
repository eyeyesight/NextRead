from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from core.models import ReferencePaper


class Capability(StrEnum):
    CITATION_COUNT = "citation_count"
    FIELD_NORMALIZED_IMPACT = "field_normalized_impact"
    TOPICS = "topics"
    AUTHOR_METRICS = "author_metrics"
    SOURCE_METRICS = "source_metrics"
    CITATION_GRAPH = "citation_graph"
    INFLUENTIAL_CITATIONS = "influential_citations"
    SPECTER2_EMBEDDING = "specter2_embedding"


class DataProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def capabilities(self) -> set[Capability]: ...

    @abstractmethod
    def enrich(self, papers: list[ReferencePaper], force_refresh: bool = False) -> None: ...
