import subprocess

import pytest

from parsers.grobid import GrobidClient
from parsers.grobid_service import GrobidUnavailableError, check_grobid_ready


def _client(monkeypatch, alive=False):
    client = GrobidClient("http://localhost:8070")
    monkeypatch.setattr(client, "is_available", lambda: alive)
    monkeypatch.setattr("parsers.grobid_service.find_docker", lambda: "docker")
    monkeypatch.setattr("parsers.grobid_service.subprocess.Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Docker was started")))
    return client


def test_check_never_starts_docker_when_engine_is_off(tmp_path, monkeypatch):
    client = _client(monkeypatch)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr("parsers.grobid_service.subprocess.run", run)
    with pytest.raises(GrobidUnavailableError, match="開啟 Docker Desktop"):
        check_grobid_ready(client, tmp_path)
    assert calls == [["docker", "info"]]


def test_running_docker_but_stopped_grobid_is_not_started(tmp_path, monkeypatch):
    client = _client(monkeypatch)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("parsers.grobid_service.subprocess.run", run)
    with pytest.raises(GrobidUnavailableError, match="docker compose up -d grobid"):
        check_grobid_ready(client, tmp_path)
    assert calls == [
        ["docker", "info"],
        ["docker", "compose", "ps", "--status", "running", "--services", "grobid"],
        ["docker", "compose", "-p", "academicreferences", "ps", "--status", "running", "--services", "grobid"],
    ]


def test_existing_legacy_compose_project_stays_usable(tmp_path, monkeypatch):
    client = _client(monkeypatch, alive=True)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        output = "grobid\n" if "academicreferences" in command else ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("parsers.grobid_service.subprocess.run", run)
    check_grobid_ready(client, tmp_path)
    assert len(calls) == 3


def test_running_container_with_healthy_api_is_ready(tmp_path, monkeypatch):
    client = _client(monkeypatch, alive=True)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "grobid\n", "")

    monkeypatch.setattr("parsers.grobid_service.subprocess.run", run)
    check_grobid_ready(client, tmp_path)
    assert len(calls) == 2


def test_recheck_waits_for_api_warmup_without_starting_docker(tmp_path, monkeypatch):
    client = GrobidClient("http://localhost:8070")
    responses = iter([False, False, True])
    retries = []
    commands = []
    monkeypatch.setattr(client, "is_available", lambda: next(responses))
    monkeypatch.setattr("parsers.grobid_service.find_docker", lambda: "docker")
    monkeypatch.setattr("parsers.grobid_service.time.sleep", lambda seconds: None)

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "grobid\n", "")

    monkeypatch.setattr("parsers.grobid_service.subprocess.run", run)
    check_grobid_ready(client, tmp_path, api_attempts=3, on_retry=retries.append)
    assert retries == [1, 2]
    assert commands == [
        ["docker", "info"],
        ["docker", "compose", "ps", "--status", "running", "--services", "grobid"],
    ]


def test_running_container_without_healthy_api_is_not_ready(tmp_path, monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr("parsers.grobid_service.subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "grobid\n", ""))
    with pytest.raises(GrobidUnavailableError, match="API 尚未回應"):
        check_grobid_ready(client, tmp_path)


def test_missing_docker_is_actionable(tmp_path, monkeypatch):
    client = GrobidClient("http://localhost:8070")
    monkeypatch.setattr("parsers.grobid_service.find_docker", lambda: None)
    with pytest.raises(GrobidUnavailableError, match="開啟 Docker Desktop"):
        check_grobid_ready(client, tmp_path)


def test_custom_grobid_url_checks_only_remote_service(tmp_path, monkeypatch):
    client = GrobidClient("https://example.org/grobid")
    monkeypatch.setattr(client, "is_available", lambda: True)
    monkeypatch.setattr("parsers.grobid_service.find_docker", lambda: (_ for _ in ()).throw(AssertionError("Docker used")))
    check_grobid_ready(client, tmp_path)
