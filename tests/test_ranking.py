import pytest

from core.models import ReferencePaper
from core.ranking import rank_papers


WEIGHTS = {
    "field_impact": 0.30,
    "local_network": 0.25,
    "semantic_relevance": 0.25,
    "influential_citations": 0.10,
    "author_impact": 0.06,
    "source_impact": 0.04,
}


def test_missing_dimensions_are_excluded_and_reduce_coverage():
    papers = [
        ReferencePaper(citation_count=100, local_in_degree=2, local_pagerank=0.6, local_connectivity=3),
        ReferencePaper(citation_count=10, local_in_degree=0, local_pagerank=0.4, local_connectivity=0),
    ]
    rank_papers(papers, WEIGHTS)
    assert papers[0].priority_score > papers[1].priority_score
    assert papers[0].evidence_coverage == pytest.approx(55.0)
    assert papers[0].semantic_relevance_score is None


def test_no_evidence_produces_no_priority_score():
    paper = ReferencePaper()
    rank_papers([paper], WEIGHTS)
    assert paper.priority_score is None
    assert paper.evidence_coverage == 0.0


def test_field_impact_prefers_openalex_normalized_percentile():
    papers = [
        ReferencePaper(citation_percentile=0.9, fwci=0.1, citation_count=1),
        ReferencePaper(citation_percentile=0.2, fwci=10.0, citation_count=1000),
    ]
    rank_papers(papers, WEIGHTS)
    by_percentile = {paper.citation_percentile: paper for paper in papers}
    assert by_percentile[0.9].field_impact_score == 0.9
    assert by_percentile[0.2].field_impact_score == 0.2


def test_influential_citation_is_edge_level_and_keeps_unknown_missing():
    papers = [
        ReferencePaper(is_influential_citation=True),
        ReferencePaper(is_influential_citation=False),
        ReferencePaper(is_influential_citation=None),
    ]
    rank_papers(papers, WEIGHTS)
    by_value = {paper.is_influential_citation: paper for paper in papers}
    assert by_value[True].influential_citation_score == 1.0
    assert by_value[False].influential_citation_score == 0.0
    assert by_value[None].influential_citation_score is None
    assert by_value[None].evidence_coverage == 0.0


def test_author_impact_uses_median_and_max_h_index():
    papers = [
        ReferencePaper(author_h_index_median=5, author_h_index_max=80),
        ReferencePaper(author_h_index_median=25, author_h_index_max=30),
    ]
    rank_papers(papers, WEIGHTS)
    by_median = {paper.author_h_index_median: paper for paper in papers}
    assert by_median[25].author_impact_score == pytest.approx(0.6097)
    assert by_median[5].author_impact_score == pytest.approx(0.3903)
