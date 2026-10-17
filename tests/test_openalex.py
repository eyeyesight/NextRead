from core.models import ReferencePaper
from providers.openalex import OpenAlexProvider
from storage.cache import ApiCache


def test_force_refresh_shares_author_and_source_requests_only_within_one_analysis(tmp_path):
    class SharedEntitiesHttp:
        def __init__(self):
            self.calls = []

        def get_json(self, url, **_kwargs):
            self.calls.append(url)
            if "/works/" in url:
                return {
                    "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Author"}}],
                    "primary_location": {"source": {"id": "https://openalex.org/S1"}},
                }
            return {"summary_stats": {"h_index": 7}}

    cache = ApiCache(tmp_path / "cache.db")
    cache.set("openalex", "authors:https://openalex.org/A1", {"summary_stats": {"h_index": 1}})
    provider = OpenAlexProvider(cache)
    provider.http = SharedEntitiesHttp()
    papers = [ReferencePaper(doi="10.1000/one"), ReferencePaper(doi="10.1000/two")]

    provider.enrich(papers, force_refresh=True)

    assert len(provider.http.calls) == 4
    assert [paper.author_h_index_median for paper in papers] == [7.0, 7.0]
    assert [paper.source_h_index for paper in papers] == [7, 7]
    assert cache.get("openalex", "authors:https://openalex.org/A1")["summary_stats"]["h_index"] == 7

    provider.enrich(papers, force_refresh=True)

    assert len(provider.http.calls) == 8


def test_repeated_openalex_author_failure_is_not_requested_again_in_same_analysis(tmp_path):
    class FailingAuthorHttp:
        def __init__(self):
            self.author_requests = 0

        def get_json(self, url, **_kwargs):
            if "/works/" in url:
                return {"authorships": [{"author": {"id": "https://openalex.org/A1"}}]}
            self.author_requests += 1
            raise RuntimeError("Author unavailable")

    provider = OpenAlexProvider(ApiCache(tmp_path / "cache.db", enabled=False))
    provider.http = FailingAuthorHttp()
    papers = [ReferencePaper(doi="10.1000/one"), ReferencePaper(doi="10.1000/two")]

    provider.enrich(papers, force_refresh=True)

    assert provider.http.author_requests == 1
    assert all(paper.provider_data["openalex_author_errors"] == ["Author unavailable"] for paper in papers)

    provider.enrich([ReferencePaper(doi="10.1000/three")], force_refresh=True)
    assert provider.http.author_requests == 2


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
