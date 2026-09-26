import requests

from core.models import ReferencePaper, SeedPaper
from providers.http import RateLimitedError
from providers.semantic_scholar import SemanticScholarProvider
from storage.cache import ApiCache


class NoValidPaperIdsHttp:
    def post_json(self, *_args, **_kwargs):
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"error":"No valid paper ids given"}'
        raise requests.HTTPError(
            "400 Client Error: Bad Request",
            response=response,
        )


def test_batch_with_no_semantic_scholar_matches_is_not_a_provider_failure(tmp_path):
    cache = ApiCache(tmp_path / "cache.db")
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = NoValidPaperIdsHttp()
    paper = ReferencePaper(doi="10.1101/612218")

    provider.enrich([paper])

    assert paper.semantic_scholar_id is None
    assert cache.get("semantic_scholar", "doi:10.1101/612218") == {}


class SemanticScholarHttp:
    def post_json(self, *_args, **_kwargs):
        return [
            {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}},
            {"paperId": "influential", "embedding": {"vector": [1.0, 0.0]}},
            {"paperId": "incidental", "embedding": {"vector": [0.0, 1.0]}},
            {"paperId": "unclassified", "embedding": {"vector": [0.5, 0.5]}},
        ]

    def get_json(self, *_args, **_kwargs):
        return {
            "data": [
                {"citedPaper": {"paperId": "influential"}, "isInfluential": True},
                {"citedPaper": {"paperId": "incidental"}, "isInfluential": False},
            ]
        }


def test_influential_citation_uses_seed_to_reference_edge(tmp_path):
    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"), "test-key")
    provider.http = SemanticScholarHttp()
    seed = SeedPaper(doi="10.1000/seed")
    papers = [
        ReferencePaper(doi="10.1000/influential"),
        ReferencePaper(doi="10.1000/incidental"),
        ReferencePaper(doi="10.1000/unclassified"),
    ]

    provider.enrich_with_seed(seed, papers)

    assert papers[0].is_influential_citation is True
    assert papers[1].is_influential_citation is False
    assert papers[2].is_influential_citation is None


class FieldsSensitiveReferencesHttp:
    def __init__(self):
        self.calls = 0

    def get_json(self, *_args, **kwargs):
        self.calls += 1
        fields = kwargs["params"]["fields"]
        item = {"isInfluential": True}
        if "title" in fields:
            item["citedPaper"] = {"paperId": "reference", "title": "Reference"}
        return {"data": [item]}


def test_influential_edges_refresh_cached_responses_without_reference_ids(tmp_path):
    cache = ApiCache(tmp_path / "cache.db")
    cache.set(
        "semantic_scholar",
        "references:seed",
        {"data": [{"isInfluential": False}]},
    )
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = FieldsSensitiveReferencesHttp()

    edges = provider._influential_edges({"paperId": "seed"}, False)

    assert edges == {"reference": True}
    assert provider.http.calls == 1


def test_references_rate_limit_preserves_paper_metadata_and_similarity(tmp_path):
    class ReferencesRateLimitedHttp:
        def post_json(self, *_args, **_kwargs):
            return [
                {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}},
                {"paperId": "cited", "embedding": {"vector": [1.0, 0.0]}},
            ]

        def get_json(self, *_args, **_kwargs):
            raise RateLimitedError("Rate limited by references endpoint")

    provider = SemanticScholarProvider(ApiCache(tmp_path / "cache.db"), "test-key")
    provider.http = ReferencesRateLimitedHttp()
    paper = ReferencePaper(doi="10.1000/cited")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [paper])

    assert paper.semantic_scholar_id == "cited"
    assert paper.semantic_similarity == 1.0
    assert paper.is_influential_citation is None
    assert provider.partial_errors == ["Rate limited by references endpoint"]


def test_batch_rate_limit_preserves_cached_paper_metadata(tmp_path):
    class BatchRateLimitedHttp:
        def post_json(self, *_args, **_kwargs):
            raise RateLimitedError("Rate limited by batch endpoint")

        def get_json(self, *_args, **_kwargs):
            raise AssertionError("Do not send another request after a rate limit")

    cache = ApiCache(tmp_path / "cache.db")
    cache.set("semantic_scholar", "doi:10.1000/seed", {"paperId": "seed", "embedding": {"vector": [1.0, 0.0]}})
    cache.set("semantic_scholar", "doi:10.1000/cited", {"paperId": "cited", "embedding": {"vector": [1.0, 0.0]}})
    provider = SemanticScholarProvider(cache, "test-key")
    provider.http = BatchRateLimitedHttp()
    cited = ReferencePaper(doi="10.1000/cited")
    missing = ReferencePaper(doi="10.1000/missing")

    provider.enrich_with_seed(SeedPaper(doi="10.1000/seed"), [cited, missing])

    assert cited.semantic_scholar_id == "cited"
    assert cited.semantic_similarity == 1.0
    assert missing.semantic_scholar_id is None
    assert provider.partial_errors == ["Rate limited by batch endpoint"]
