import requests

from providers.http import HttpClient


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
