from core.models import ReferencePaper
from providers.openalex import OpenAlexProvider
from storage.cache import ApiCache


def test_openalex_collects_h_index_for_all_available_authors(tmp_path, monkeypatch):
    provider = OpenAlexProvider(ApiCache(tmp_path / "cache.db"))
    authors = {
        "https://openalex.org/A1": {"summary_stats": {"h_index": 80}},
        "https://openalex.org/A2": {"summary_stats": {"h_index": 5}},
        "https://openalex.org/A3": {"summary_stats": {}},
        "https://openalex.org/A4": {"summary_stats": {"h_index": 3}},
    }
    monkeypatch.setattr(provider, "_get", lambda entity, identifier, _refresh: authors[identifier])
    paper = ReferencePaper()
    work = {
        "authorships": [
            {"author": {"id": author_id, "display_name": name}}
            for author_id, name in zip(authors, ["A", "B", "C", "D"])
        ]
    }

    provider._apply_work(paper, work, False)

    assert paper.authors == ["A", "B", "C", "D"]
    assert paper.author_h_indices == [80, 5, 3]
    assert paper.author_h_index_median == 5.0
    assert paper.author_h_index_max == 80
    assert paper.author_metadata_coverage == 0.75
