from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts_without_private_keys_sjr_csv_or_docker(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
    monkeypatch.setenv("SJR_DATA_PATH", str(tmp_path / "missing.csv"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15).run()

    assert not app.exception
    assert any("尚未安裝 SJR 資料" in warning.value for warning in app.warning)
    assert [caption.value for caption in app.caption].count("API Key 未設定") == 2
    assert any(metric.label == "GROBID" and metric.value == "未選用" for metric in app.metric)
