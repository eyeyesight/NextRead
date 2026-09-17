from core.models import ReferencePaper
from resolvers.crossref import score_candidate


def test_crossref_candidate_score_rewards_matching_metadata():
    paper = ReferencePaper(title="A Study of Local Citation Networks", year=2024, authors=["Ada Lovelace"], source_name="Research Systems")
    matching = {
        "title": ["A Study of Local Citation Networks"],
        "published": {"date-parts": [[2024]]},
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "container-title": ["Research Systems"],
    }
    wrong = {"title": ["Unrelated Work"], "published": {"date-parts": [[1999]]}}
    assert score_candidate(paper, matching) > 0.95
    assert score_candidate(paper, wrong) < 0.3
