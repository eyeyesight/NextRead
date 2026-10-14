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


def test_missing_metrics_shows_reference_list_without_recommendation(tmp_path):
    from core.config import Settings
    from core.models import ReferencePaper, SeedPaper
    from core.pipeline import AnalysisPipeline

    pipeline = AnalysisPipeline(Settings(cache_path=tmp_path / "cache.db", sjr_data_path=tmp_path / "missing.csv"))
    result = pipeline._finish(SeedPaper(title="Example"), [ReferencePaper(title="Reference")], {}, False, None, "zh-TW", "grobid")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=15)
    app.session_state["result"] = result
    app.run()

    assert not app.exception
    assert any("尚無法建議閱讀順序" in item.value for item in app.info)
    assert any(item.value == "參考文獻清單" for item in app.header)
    assert not any(item.value == "參考文獻閱讀順序" for item in app.header)
