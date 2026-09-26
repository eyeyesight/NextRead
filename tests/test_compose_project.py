from pathlib import Path

import yaml


def test_compose_project_name_is_stable_across_checkout_folders():
    compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["name"] == "nextread"
    assert "grobid" in compose["services"]
