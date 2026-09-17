from core.models import ReferencePaper
from graph.local_citation_graph import build_local_graph


def test_local_graph_only_connects_references_in_the_set():
    first = ReferencePaper(openalex_id="W1", referenced_works=["W2", "W999"])
    second = ReferencePaper(openalex_id="W2", referenced_works=[])
    graph = build_local_graph([first, second, ReferencePaper()])
    assert set(graph.edges) == {("W1", "W2")}
    assert second.local_in_degree == 1
    assert first.local_connectivity == 1
