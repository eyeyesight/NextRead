from __future__ import annotations

import networkx as nx

from core.models import ReferencePaper


def build_local_graph(papers: list[ReferencePaper]) -> nx.DiGraph:
    graph = nx.DiGraph()
    by_id = {paper.openalex_id: paper for paper in papers if paper.openalex_id}
    graph.add_nodes_from(by_id)
    for paper in by_id.values():
        for target_id in paper.referenced_works:
            if target_id in by_id:
                graph.add_edge(paper.openalex_id, target_id)

    pagerank = nx.pagerank(graph) if graph.number_of_nodes() else {}
    for paper in papers:
        if not paper.openalex_id:
            continue
        paper.local_in_degree = graph.in_degree(paper.openalex_id)
        paper.local_connectivity = graph.degree(paper.openalex_id)
        paper.local_pagerank = pagerank.get(paper.openalex_id, 0.0)
    return graph
