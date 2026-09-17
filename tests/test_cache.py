from storage.cache import ApiCache


def test_cache_survives_a_new_instance(tmp_path):
    path = tmp_path / "cache.db"
    ApiCache(path).set("provider", "id", {"answer": 42})
    assert ApiCache(path).get("provider", "id") == {"answer": 42}
