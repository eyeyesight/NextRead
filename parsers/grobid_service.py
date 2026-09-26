"""Read-only checks for the optional user-managed GROBID service."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from parsers.grobid import GrobidClient


class GrobidUnavailableError(RuntimeError):
    pass


def find_docker() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    local = os.getenv("LOCALAPPDATA")
    candidates = [
        Path(local) / "Programs/DockerDesktop/resources/bin/docker.exe" if local else None,
        Path(os.getenv("PROGRAMFILES", "")) / "Docker/Docker/resources/bin/docker.exe" if os.getenv("PROGRAMFILES") else None,
    ]
    return str(next((path for path in candidates if path and path.is_file()), "")) or None


def check_grobid_ready(
    client: GrobidClient,
    project_dir: Path,
    api_attempts: int = 1,
    on_retry: Callable[[int], None] | None = None,
) -> None:
    """Require an already-running Docker engine, Compose service, and GROBID API."""
    address = urlparse(client.base_url)
    if address.scheme != "http" or address.hostname not in ("localhost", "127.0.0.1") or address.port != 8070:
        if not client.is_available():
            raise GrobidUnavailableError("無法連線到自訂的 GROBID_URL；請先啟動對應服務。")
        return

    docker = find_docker()
    if not docker:
        raise GrobidUnavailableError("找不到 Docker 命令。請先安裝並開啟 Docker Desktop。")
    try:
        info = subprocess.run([docker, "info"], cwd=project_dir, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GrobidUnavailableError("Docker 引擎尚未就緒。請開啟 Docker Desktop 後重新檢查。") from exc
    if info.returncode:
        raise GrobidUnavailableError("Docker 引擎尚未就緒。請開啟 Docker Desktop 後重新檢查。")

    try:
        services = subprocess.run(
            [docker, "compose", "ps", "--status", "running", "--services", "grobid"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GrobidUnavailableError("無法確認 GROBID 容器狀態。請到 Docker Desktop 查看。") from exc
    if services.returncode or "grobid" not in services.stdout.splitlines():
        try:
            legacy = subprocess.run(
                [docker, "compose", "-p", "academicreferences", "ps", "--status", "running", "--services", "grobid"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GrobidUnavailableError("無法確認舊版 GROBID 容器狀態。請到 Docker Desktop 查看。") from exc
        if legacy.returncode or "grobid" not in legacy.stdout.splitlines():
            raise GrobidUnavailableError("GROBID 容器尚未執行。請到專案資料夾執行 `docker compose up -d grobid`，再重新檢查。")
    for attempt in range(1, api_attempts + 1):
        if client.is_available():
            return
        if attempt < api_attempts:
            if on_retry:
                on_retry(attempt)
            time.sleep(2)
    raise GrobidUnavailableError("GROBID 容器正在執行，但 API 尚未回應。請稍後重新檢查。")
