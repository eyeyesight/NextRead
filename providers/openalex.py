from __future__ import annotations

from statistics import median
from typing import Any

from core.models import ReferencePaper
from providers.base import Capability, DataProvider
from providers.http import HttpClient
from storage.cache import ApiCache


class OpenAlexProvider(DataProvider):
    name = "openalex"
    base_url = "https://api.openalex.org"

    def __init__(self, cache: ApiCache, api_key: str = "", mailto: str = ""):
        self.cache = cache
        self.api_key = api_key
        self.mailto = mailto
        self.http = HttpClient()

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> set[Capability]:
        return {
            Capability.CITATION_COUNT,
            Capability.FIELD_NORMALIZED_IMPACT,
            Capability.TOPICS,
            Capability.AUTHOR_METRICS,
            Capability.SOURCE_METRICS,
            Capability.CITATION_GRAPH,
        }

    def _params(self) -> dict[str, str]:
        params = {}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    def _get(self, entity: str, identifier: str, force_refresh: bool) -> dict[str, Any]:
        key = f"{entity}:{identifier}"
        cached = self.cache.get(self.name, key, force_refresh)
        if cached is not None:
            return cached
        payload = self.http.get_json(f"{self.base_url}/{entity}/{identifier}", params=self._params())
        self.cache.set(self.name, key, payload)
        return payload

    def enrich(self, papers: list[ReferencePaper], force_refresh: bool = False) -> None:
        for paper in papers:
            if not paper.doi:
                continue
            try:
                work = self._get("works", f"https://doi.org/{paper.doi}", force_refresh)
                self._apply_work(paper, work, force_refresh)
            except Exception as exc:
                paper.provider_data["openalex_error"] = str(exc)

    def _apply_work(self, paper: ReferencePaper, work: dict[str, Any], force_refresh: bool) -> None:
        paper.provider_data["openalex"] = work
        paper.openalex_id = work.get("id")
        paper.title = work.get("title") or paper.title
        paper.year = work.get("publication_year") or paper.year
        paper.work_type = work.get("type")
        paper.citation_count = work.get("cited_by_count")
        paper.fwci = work.get("fwci")
        percentile = work.get("citation_normalized_percentile") or {}
        paper.citation_percentile = percentile.get("value")
        paper.referenced_works = work.get("referenced_works") or []
        paper.is_retracted = work.get("is_retracted")
        oa = work.get("open_access") or {}
        paper.is_open_access = oa.get("is_oa")
        paper.open_access_url = oa.get("oa_url")

        topic = work.get("primary_topic") or {}
        subfield = topic.get("subfield") or {}
        field = topic.get("field") or {}
        domain = topic.get("domain") or {}
        paper.primary_topic = topic.get("display_name")
        paper.subfield = subfield.get("display_name")
        paper.field = field.get("display_name")
        paper.domain = domain.get("display_name")
        paper.other_topics = [item.get("display_name") for item in (work.get("topics") or [])[1:] if item.get("display_name")]

        authorships = work.get("authorships") or []
        if authorships:
            openalex_authors = [authorship.get("author") or {} for authorship in authorships]
            names = [author.get("display_name") for author in openalex_authors if author.get("display_name")]
            if names:
                paper.authors = names
                paper.first_author_name = names[0]
            h_indices = []
            author_ids = [author.get("id") for author in openalex_authors if author.get("id")]
            for author_id in author_ids:
                try:
                    author = self._get("authors", author_id, force_refresh)
                    h_index = (author.get("summary_stats") or {}).get("h_index")
                    if h_index is not None:
                        h_indices.append(int(h_index))
                except Exception as exc:
                    paper.provider_data.setdefault("openalex_author_errors", []).append(str(exc))
            paper.author_h_indices = h_indices
            paper.author_metadata_coverage = len(h_indices) / len(authorships)
            if h_indices:
                paper.author_h_index_median = float(median(h_indices))
                paper.author_h_index_max = max(h_indices)

        source = ((work.get("primary_location") or {}).get("source") or {})
        paper.source_name = source.get("display_name") or paper.source_name
        paper.source_openalex_id = source.get("id")
        paper.source_issn_l = source.get("issn_l")
        paper.source_issns = source.get("issn") or []
        paper.source_type = source.get("type")
        if paper.source_openalex_id:
            self._apply_source(paper, self._get("sources", paper.source_openalex_id, force_refresh))

    @staticmethod
    def _apply_source(paper: ReferencePaper, source: dict[str, Any]) -> None:
        summary = source.get("summary_stats") or {}
        paper.source_works_count = source.get("works_count")
        paper.source_cited_by_count = source.get("cited_by_count")
        paper.source_h_index = summary.get("h_index")
        paper.source_i10_index = summary.get("i10_index")
        paper.source_2yr_mean_citedness = summary.get("2yr_mean_citedness")
