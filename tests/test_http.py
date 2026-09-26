import requests
import pytest

from providers.http import HttpClient, NetworkAccessError


def test_minimum_interval_paces_consecutive_requests(monkeypatch):
    clock = [100.0]
    waits = []
    monkeypatch.setattr("providers.http.time.monotonic", lambda: clock[0])

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("providers.http.time.sleep", sleep)
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    client = HttpClient(min_interval=1.1)
    client.session.get = lambda *_args, **_kwargs: response

    client.get_json("https://example.org/first")
    client.get_json("https://example.org/second")

    assert waits == [1.1]


@pytest.mark.parametrize("method", ["get_json", "post_json"])
def test_windows_socket_refusal_is_not_retried_or_exposes_raw_url(method):
    client = HttpClient()
    calls = []

    def blocked(*_args, **_kwargs):
        calls.append(1)
        raise requests.ConnectionError("HTTPSConnectionPool(host='api.semanticscholar.org'): [WinError 10013]")

    setattr(client.session, "get" if method == "get_json" else "post", blocked)

    with pytest.raises(NetworkAccessError, match="Windows 拒絕 NextRead 連線到 Semantic Scholar") as error:
        getattr(client, method)("https://api.semanticscholar.org/graph/v1/paper/batch")

    assert len(calls) == 1
    assert "HTTPSConnectionPool" not in str(error.value)
