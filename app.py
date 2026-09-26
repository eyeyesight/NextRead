from __future__ import annotations

import base64
import json
import logging
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from core.config import load_settings
from core.models import AnalysisResult, ReferencePaper
from core.pipeline import AnalysisPipeline
from parsers.grobid_service import GrobidUnavailableError, check_grobid_ready


LEGACY_FIELD_ALIASES = {
    "evidence_coverage": "data_coverage",
}


def paper_value(paper: object, field: str):
    """Read fields from current and pre-revision session objects."""
    if hasattr(paper, field):
        return getattr(paper, field)
    legacy_field = LEGACY_FIELD_ALIASES.get(field)
    return getattr(paper, legacy_field, None) if legacy_field else None

APP_DIR = Path(__file__).resolve().parent
CRITERIA_GUIDE_PATH = APP_DIR / "criteria_intro.md"

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler("logs/app.log", encoding="utf-8")])
st.set_page_config(
    page_title="NextRead",
    page_icon=str(APP_DIR / "assets" / "nextread-icon.png"),
    layout="wide",
)

MODES = {
    "parser": {"crossref": False, "openalex": False, "semantic_scholar": False},
    "standard": {"crossref": True, "openalex": True, "semantic_scholar": False},
    "complete": {"crossref": True, "openalex": True, "semantic_scholar": True},
}
MODE_TEXT = {
    "parser": (("僅解析", "Parse only"), ("只取得參考文獻，不查詢外部指標。", "Extract references without external metrics.")),
    "standard": (("標準分析（推薦）", "Standard (recommended)"), ("加入 Crossref、OpenAlex、SJR 和清單內的引用關係。", "Use Crossref, OpenAlex, SJR, and the local citation graph.")),
    "complete": (("完整分析", "Complete analysis"), ("再加入 Semantic Scholar 的語意相似度與具影響力引用關係。", "Also add Semantic Scholar similarity and influential citation relationships.")),
}
language_choice = st.session_state.get("language_selector", "繁體中文")
language = "zh-TW" if language_choice == "繁體中文" else "en"


def t(zh: str, en: str) -> str:
    return zh if language == "zh-TW" else en


def request_grobid_recheck() -> None:
    st.session_state["grobid_check_done"] = False
    st.session_state["grobid_recheck_requested"] = True


def svg_mask(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'url("data:image/svg+xml;base64,{encoded}")'


def apply_component_styles() -> None:
    controls_icon = svg_mask(APP_DIR / "assets" / "interface-adjustments.svg")
    traditional_chinese_icon = svg_mask(APP_DIR / "assets" / "language-traditional-chinese.svg")
    english_icon = svg_mask(APP_DIR / "assets" / "language-english.svg")
    st.html(f"""
        <style>
        .st-key-interface_options {{ display: flex; justify-content: flex-end; }}
        .st-key-interface_options button[data-testid="stPopoverButton"] {{
            width: 2.5rem;
            min-width: 2.5rem;
            height: 2.5rem;
            padding: 0;
            position: relative;
            border-color: transparent;
            background: transparent;
        }}
        .st-key-interface_options button[data-testid="stPopoverButton"]:hover {{
            background: color-mix(in srgb, currentColor 8%, transparent);
        }}
        .st-key-interface_options button[data-testid="stPopoverButton"] p {{
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip: rect(0 0 0 0);
        }}
        .st-key-interface_options button[data-testid="stPopoverButton"] [data-testid="stIconMaterial"] {{
            display: none;
        }}
        .st-key-interface_options button[data-testid="stPopoverButton"]::before {{
            content: "";
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 1.25rem;
            height: 1.25rem;
            background-color: currentColor;
            mask: {controls_icon} center / contain no-repeat;
            -webkit-mask: {controls_icon} center / contain no-repeat;
        }}
        [data-testid="stPopoverBody"]:has(.st-key-language_selector) {{
            min-width: 15.25rem;
            padding: .65rem;
        }}
        [data-testid="stPopoverBody"]:has(.st-key-language_selector) > [data-testid="stVerticalBlock"] {{
            gap: .25rem;
        }}
        .st-key-language_selector [role="radiogroup"] {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .25rem;
            border: 0;
            background: transparent;
        }}
        .st-key-language_selector [role="radio"] {{
            min-height: 4.25rem;
            padding: .35rem .3rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: .2rem;
            text-align: center;
            border: 0;
            border-radius: .65rem;
        }}
        .st-key-language_selector [role="radio"] > div,
        .st-key-language_selector [role="radio"] p {{
            width: 100%;
            justify-content: center;
            text-align: center;
        }}
        .st-key-language_selector [role="radio"]::before {{
            content: "";
            width: 1.5rem;
            height: 1.5rem;
            flex: 0 0 1.5rem;
            background-color: currentColor;
            mask-position: center;
            mask-size: contain;
            mask-repeat: no-repeat;
            -webkit-mask-position: center;
            -webkit-mask-size: contain;
            -webkit-mask-repeat: no-repeat;
        }}
        .st-key-language_selector [role="radio"]:nth-of-type(1)::before {{
            mask-image: {traditional_chinese_icon};
            -webkit-mask-image: {traditional_chinese_icon};
        }}
        .st-key-language_selector [role="radio"]:nth-of-type(2)::before {{
            mask-image: {english_icon};
            -webkit-mask-image: {english_icon};
        }}
        [data-testid="stPopoverBody"]:has(.st-key-language_selector) hr {{
            margin: .1rem 0;
        }}
        .st-key-metrics_guide_button {{
            margin-top: 1rem;
        }}
        .st-key-metrics_guide_button button {{
            min-height: 2.35rem;
            padding-block: .35rem;
        }}
        </style>
    """)


RESOLUTION_STATUS_TEXT = {
    "exact_doi": ("DOI 精確符合", "Exact DOI match"),
    "high_confidence": ("高可信度符合", "High-confidence match"),
    "medium_confidence": ("中等可信度符合", "Medium-confidence match"),
    "unresolved": ("尚未辨識", "Unresolved"),
}


def resolution_status_label(status: str | None) -> str:
    if not status:
        return t("尚未辨識", "Unresolved")
    labels = RESOLUTION_STATUS_TEXT.get(status)
    return t(*labels) if labels else status.replace("_", " ").title()


def metric_guide_markdown() -> str:
    """Return the user-facing guide while omitting its editor instructions."""
    guide = CRITERIA_GUIDE_PATH.read_text(encoding="utf-8")
    section_marker = "## 排名 Rank"
    _instructions, marker, content = guide.partition(section_marker)
    return f"{marker}{content}" if marker else guide


@st.dialog("指標說明 Metrics Guide", width="small", icon=":material/menu_book:")
def metric_help_dialog() -> None:
    st.markdown(metric_guide_markdown())


def rows_for(result: AnalysisResult) -> list[dict]:
    rows = []
    for rank, p in enumerate(result.references, 1):
        rows.append({
            t("排名", "Rank"): rank,
            t("閱讀優先度", "Reading Priority"): p.priority_score,
            t("文章標題", "Title"): p.title or p.raw_reference,
            t("作者", "Authors"): "; ".join(p.authors) or p.first_author_name,
            t("年份", "Year"): p.year, t("期刊／來源", "Journal / Source"): p.source_name,
            "Local PageRank": p.local_pagerank, "Local In-Degree": p.local_in_degree,
            "Semantic Similarity": p.semantic_similarity, "Influential Citation": paper_value(p, "is_influential_citation"),
            "FWCI": p.fwci, "Citation Count": p.citation_count,
            "SJR Quartile": p.sjr_quartile, "SJR Score": p.sjr_score,
            "Median Author h-index": paper_value(p, "author_h_index_median"),
            "Maximum Author h-index": paper_value(p, "author_h_index_max"),
            t("作者資料涵蓋率 (%)", "Author Metadata Coverage (%)"): (
                round(100 * coverage, 1)
                if (coverage := paper_value(p, "author_metadata_coverage")) is not None else None
            ),
            "Source h-index": p.source_h_index,
            t("主領域 Field", "Field"): p.field,
            t("子領域 Subfield", "Subfield"): p.subfield,
            t("主題", "Topic"): p.primary_topic,
            t("證據涵蓋率 (%)", "Evidence Coverage (%)"): paper_value(p, "evidence_coverage"),
            t("辨識狀態", "Resolution Status"): resolution_status_label(p.resolution_status),
            "DOI": p.doi,
            "_paper_index": rank - 1,
        })
    return rows


def filtered_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    df = pd.DataFrame(rows)
    title, author, year = t("文章標題", "Title"), t("作者", "Authors"), t("年份", "Year")
    priority, coverage, status = t("閱讀優先度", "Reading Priority"), t("證據涵蓋率 (%)", "Evidence Coverage (%)"), t("辨識狀態", "Resolution Status")
    st.sidebar.header(t("篩選條件", "Filters"))
    query = st.sidebar.text_input(t("搜尋標題或作者", "Search title or author"))
    only_q1 = st.sidebar.checkbox(t("只顯示 SJR Q1", "Show SJR Q1 only"))
    available_q = [q for q in ("Q1", "Q2", "Q3", "Q4") if q in set(df["SJR Quartile"].dropna())]
    selected_q = st.sidebar.multiselect("SJR Quartile", available_q, default=available_q)
    if only_q1:
        df = df[df["SJR Quartile"] == "Q1"]
    elif selected_q:
        df = df[df["SJR Quartile"].isin(selected_q) | df["SJR Quartile"].isna()]
    min_priority = st.sidebar.slider(t("最低閱讀優先度", "Minimum Reading Priority"), 0, 100, 0)
    min_coverage = st.sidebar.slider(t("最低證據涵蓋率 (%)", "Minimum Evidence Coverage (%)"), 0, 100, 0)
    years = [int(x) for x in df[year].dropna().unique()]
    if len(years) > 1:
        period = st.sidebar.slider(t("出版年份", "Publication year"), min(years), max(years), (min(years), max(years)))
        df = df[df[year].isna() | df[year].between(*period)]
    elif years:
        st.sidebar.caption(t(f"出版年份：{years[0]}", f"Publication year: {years[0]}"))
    for label, column in ((t("主領域 Field", "Field"), t("主領域 Field", "Field")), (t("子領域 Subfield", "Subfield"), t("子領域 Subfield", "Subfield")), (t("主題", "Topic"), t("主題", "Topic"))):
        choices = sorted(df[column].dropna().unique())
        chosen = st.sidebar.multiselect(label, choices)
        if chosen:
            df = df[df[column].isin(chosen)]
    min_fwci = st.sidebar.number_input(t("最低 FWCI", "Minimum FWCI"), min_value=0.0, value=0.0, step=0.1)
    min_cites = st.sidebar.number_input(t("最低 Citation Count", "Minimum Citation Count"), min_value=0, value=0, step=1)
    statuses = sorted(df[status].dropna().unique())
    selected_statuses = st.sidebar.multiselect(t("辨識狀態", "Resolution Status"), statuses, default=statuses)
    if query:
        df = df[df[title].fillna("").str.contains(query, case=False, regex=False) | df[author].fillna("").str.contains(query, case=False, regex=False)]
    df = df[(df[priority].fillna(0) >= min_priority) & (df[coverage].fillna(0) >= min_coverage)]
    df = df[(df["FWCI"].isna() | (df["FWCI"] >= min_fwci)) & (df["Citation Count"].isna() | (df["Citation Count"] >= min_cites))]
    if selected_statuses:
        df = df[df[status].isin(selected_statuses)]
    return df.to_dict("records")


def criteria_specs() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        (t("引用網路", "Citation Network"), [("Local PageRank", "local_pagerank"), ("Local In-Degree", "local_in_degree")]),
        (t("語意關聯", "Semantic Relevance"), [("Semantic Similarity", "semantic_similarity")]),
        (t("研究影響", "Research Impact"), [("Influential Citation", "is_influential_citation"), ("FWCI", "fwci")]),
        (t("引用規模", "Citation Volume"), [("Citation Count", "citation_count")]),
        (t("期刊品質", "Journal Quality"), [("SJR Quartile", "sjr_quartile"), ("SJR Score", "sjr_score")]),
        (t("學術資歷", "Academic Track Record"), [("Median Author h-index", "author_h_index_median"), ("Maximum Author h-index", "author_h_index_max"), ("Source h-index", "source_h_index")]),
    ]


def metric_value(paper: ReferencePaper, field: str) -> float | None:
    value = paper_value(paper, field)
    if field == "sjr_quartile":
        return {"Q1": 4.0, "Q2": 3.0, "Q3": 2.0, "Q4": 1.0}.get(value)
    return float(value) if value is not None else None


def metric_label(paper: ReferencePaper, field: str) -> str:
    value = paper_value(paper, field)
    if value is None:
        return t("無資料", "No data")
    if field == "sjr_quartile":
        return str(value)
    if field == "is_influential_citation":
        return t("是", "Yes") if value else t("否", "No")
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):.4g}"


def paper_axis_label(paper: ReferencePaper, rank: int) -> str:
    title = paper.title or paper.raw_reference or t("未辨識文獻", "Unresolved reference")
    short_title = title if len(title) <= 58 else f"{title[:55]}…"
    return f"#{rank}  {short_title}"


def sjr_quality_chart(papers: list[ReferencePaper]) -> None:
    records = []
    for index, paper in enumerate(papers):
        records.append({
            "paper": paper_axis_label(paper, index + 1),
            "score": paper.sjr_score,
            "score_label": t("無資料", "No data") if paper.sjr_score is None else f"{paper.sjr_score:.3f}",
            "quartile": paper.sjr_quartile or t("無資料", "No data"),
            "title": paper.title or paper.raw_reference,
            "author": "; ".join(paper.authors) or paper.first_author_name or t("無資料", "N/A"),
            "year": paper.year,
            "source": paper.source_name,
        })
    order = [item["paper"] for item in sorted(records, key=lambda item: item["score"] if item["score"] is not None else -1, reverse=True)]
    frame = pd.DataFrame(records)
    available = frame[frame["score"].notna()]
    if available.empty:
        st.info(t("目前沒有可用的 SJR 資料。", "No SJR data is currently available."))
        return
    st.caption(t(
        "長條顯示原始 SJR Score，顏色顯示 SCImago 官方的 Best Quartile。Q1–Q4 依期刊所屬學科劃分，圖中因此沒有共用的分區界線。",
        "Bar length shows the raw SJR Score. Color shows the official SCImago Best Quartile. Q1–Q4 are category-specific, so no shared cutoff lines are used.",
    ))
    quartile_domain = ["Q1", "Q2", "Q3", "Q4", t("無資料", "No data")]
    quartile_colors = ["#6F9282", "#7F96A8", "#B39F73", "#A98580", "#94A3B8"]
    bars = alt.Chart(available).mark_bar(cornerRadiusEnd=3, opacity=0.84).encode(
        x=alt.X("score:Q", title="SJR Score", axis=alt.Axis(labelColor="currentColor", titleColor="currentColor", gridOpacity=0.16, domainOpacity=0.3, tickOpacity=0.3)),
        y=alt.Y("paper:N", title=None, sort=order, axis=alt.Axis(labelLimit=430, labelColor="currentColor", domainOpacity=0, tickOpacity=0)),
        color=alt.Color("quartile:N", title="SJR Quartile", scale=alt.Scale(domain=quartile_domain, range=quartile_colors)),
        tooltip=[
            alt.Tooltip("title:N", title=t("文章標題", "Title")),
            alt.Tooltip("author:N", title=t("作者", "Author")),
            alt.Tooltip("year:Q", title=t("年份", "Year"), format="d"),
            alt.Tooltip("source:N", title=t("期刊／來源", "Journal / Source")),
            alt.Tooltip("score:Q", title="SJR Score", format=".3f"),
            alt.Tooltip("quartile:N", title="SJR Quartile"),
        ],
    )
    score_text = alt.Chart(available).mark_text(align="left", dx=5, color="currentColor", opacity=0.76).encode(
        x=alt.X("score:Q"), y=alt.Y("paper:N", sort=order), text="score_label:N"
    )
    missing = frame[frame["score"].isna()].copy()
    chart = bars + score_text
    if not missing.empty:
        missing["x"] = 0
        missing_text = alt.Chart(missing).mark_text(align="left", dx=5, color="#94A3B8").encode(
            x=alt.X("x:Q"), y=alt.Y("paper:N", sort=order), text="score_label:N"
        )
        chart += missing_text
    chart = chart.properties(height=max(360, 27 * len(papers))).configure_legend(
        labelColor="currentColor", titleColor="currentColor", symbolOpacity=0.84, orient="top"
    ).configure_view(strokeOpacity=0)
    st.altair_chart(chart, width="stretch")


def performance_charts(papers: list[ReferencePaper]) -> None:
    st.header(t("各項指標的文獻表現", "Performance across all references"))
    st.caption(t(
        "期刊品質顯示原始 SJR Score；其他圖表的橫軸顯示這份清單內的相對位置。100 是該項指標的最高值，50 約為中間位置。缺少資料不會記為 0。將游標移到長條上，可查看原始數值與書目資料。",
        "Journal Quality shows raw SJR Scores. All other charts use relative position within this reference list, where 100 is the highest and 50 is around the middle. Missing data is not treated as zero. Hover over a bar for raw values and bibliographic details.",
    ))
    st.caption(t(
        "可由左至右閱讀：先看文獻與研究主題的關係，再看引用、期刊和作者指標。",
        "Read from left to right. Start with the paper's position in the research context, then assess citations, journal quality, and academic track record.",
    ))
    specs = criteria_specs()
    tabs = st.tabs([title for title, _metrics in specs])
    palette = ["#78909C", "#B8A27A"]
    for tab, (_title, metrics) in zip(tabs, specs):
        with tab:
            if {field for _name, field in metrics} == {"sjr_quartile", "sjr_score"}:
                sjr_quality_chart(papers)
                continue
            st.caption(" · ".join(name for name, _field in metrics))
            records: list[dict] = []
            performance_by_paper: dict[int, list[float]] = {index: [] for index in range(len(papers))}
            for metric_name, field in metrics:
                valid = [(index, metric_value(paper, field)) for index, paper in enumerate(papers)]
                valid = [(index, value) for index, value in valid if value is not None]
                if not valid:
                    continue
                values = pd.Series([value for _index, value in valid])
                percentiles = values.rank(method="average", pct=True) * 100
                for (paper_index, _value), relative in zip(valid, percentiles):
                    paper = papers[paper_index]
                    performance_by_paper[paper_index].append(float(relative))
                    records.append({
                        "paper_index": paper_index,
                        "paper": paper_axis_label(paper, paper_index + 1),
                        "metric": metric_name,
                        "performance": float(relative),
                        "raw": metric_label(paper, field),
                        "title": paper.title or paper.raw_reference,
                        "author": "; ".join(paper.authors) or paper.first_author_name or t("無資料", "N/A"),
                        "year": paper.year,
                        "source": paper.source_name,
                    })
            order_indices = sorted(range(len(papers)), key=lambda index: sum(performance_by_paper[index]) / len(performance_by_paper[index]) if performance_by_paper[index] else -1, reverse=True)
            order = [paper_axis_label(papers[index], index + 1) for index in order_indices]
            if records:
                frame = pd.DataFrame(records)
                metric_names = [name for name, _field in metrics if name in set(frame["metric"])]
                bars = alt.Chart(frame).mark_bar(cornerRadiusEnd=3, opacity=0.82).encode(
                    x=alt.X("performance:Q", title=t("清單內相對表現（0–100）", "Relative performance within list (0–100)"), scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelColor="currentColor", titleColor="currentColor", gridOpacity=0.16, domainOpacity=0.3, tickOpacity=0.3)),
                    y=alt.Y("paper:N", title=None, sort=order, axis=alt.Axis(labelLimit=430, labelColor="currentColor", domainOpacity=0, tickOpacity=0)),
                    yOffset=alt.YOffset("metric:N"),
                    color=alt.Color("metric:N", title=None, scale=alt.Scale(domain=metric_names, range=palette[:len(metric_names)])),
                    tooltip=[
                        alt.Tooltip("title:N", title=t("文章標題", "Title")),
                        alt.Tooltip("author:N", title=t("作者", "Author")),
                        alt.Tooltip("year:Q", title=t("年份", "Year"), format="d"),
                        alt.Tooltip("source:N", title=t("期刊／來源", "Journal / Source")),
                        alt.Tooltip("metric:N", title=t("指標", "Metric")),
                        alt.Tooltip("raw:N", title=t("原始數值", "Raw value")),
                        alt.Tooltip("performance:Q", title=t("相對表現", "Relative performance"), format=".1f"),
                    ],
                )
                missing = [
                    {"paper": paper_axis_label(papers[index], index + 1), "label": t("無資料", "No data"), "x": 2}
                    for index in order_indices if not performance_by_paper[index]
                ]
                chart = bars
                if missing:
                    missing_text = alt.Chart(pd.DataFrame(missing)).mark_text(align="left", color="#94A3B8").encode(
                        x=alt.X("x:Q"), y=alt.Y("paper:N", sort=order), text="label:N"
                    )
                    chart = bars + missing_text
                chart = chart.properties(height=max(360, 27 * len(papers))).configure_legend(
                    labelColor="currentColor", titleColor="currentColor", symbolOpacity=0.82
                ).configure_view(strokeOpacity=0)
                st.altair_chart(chart, width="stretch")
            else:
                st.info(t("這項指標目前沒有可用資料。", "No data is currently available for this criterion."))


def metric_boxplot(peers: list[ReferencePaper], current: ReferencePaper, label: str, field: str) -> None:
    values = [value for peer in peers if (value := metric_value(peer, field)) is not None]
    current_value = metric_value(current, field)
    if not values or current_value is None:
        st.caption(f"{label} · {t('無資料', 'No data')}")
        return
    axis = alt.Axis(title=label)
    if field == "sjr_quartile":
        axis = alt.Axis(title=t("SJR 分區（Q1 最高）", "SJR quartile (Q1 highest)"), values=[1, 2, 3, 4], labelExpr="'Q' + (5 - datum.value)")
    distribution = pd.DataFrame({"value": values})
    selected = pd.DataFrame({"value": [current_value], "raw": [metric_label(current, field)]})
    box = alt.Chart(distribution).mark_boxplot(extent="min-max", size=30, color="#78909C", opacity=0.78).encode(x=alt.X("value:Q", axis=axis, scale=alt.Scale(zero=False)))
    point = alt.Chart(selected).mark_point(shape="diamond", filled=True, size=150, color="#C47B6B").encode(
        x=alt.X("value:Q"), tooltip=[alt.Tooltip("raw:N", title=t("目前文章", "Current paper"))]
    )
    st.altair_chart((box + point).properties(height=72), width="stretch")


def paper_detail(p: ReferencePaper, peers: list[ReferencePaper]) -> None:
    st.subheader(p.title or t("未辨識的參考文獻", "Unresolved reference"))
    st.caption(p.raw_reference)
    links = ([f"[DOI](https://doi.org/{p.doi})"] if p.doi else []) + ([f"[OpenAlex]({p.openalex_id})"] if p.openalex_id else []) + ([f"[Semantic Scholar]({p.semantic_scholar_url})"] if p.semantic_scholar_url else [])
    if links:
        st.markdown(" · ".join(links))
    a, b, c = st.columns(3)
    a.metric("SJR Quartile", p.sjr_quartile or t("無資料", "N/A"))
    a.caption(f"SJR {p.sjr_score if p.sjr_score is not None else '—'} · {p.sjr_year or '—'}")
    b.metric(t("閱讀優先度", "Reading Priority"), t("無法計算", "N/A") if p.priority_score is None else f"{p.priority_score:.1f} / 100")
    evidence_coverage = paper_value(p, "evidence_coverage")
    c.metric(t("證據涵蓋率", "Evidence Coverage"), f"{evidence_coverage or 0:.1f}%")

    priority_values = [peer.priority_score for peer in peers if peer.priority_score is not None]
    priority_top_quartile = float(pd.Series(priority_values).quantile(0.75)) if priority_values else None
    if p.sjr_quartile == "Q1" and p.priority_score is not None and priority_top_quartile is not None and p.priority_score >= priority_top_quartile:
        st.success(t("這篇文章刊登於 SJR Q1 期刊，閱讀優先度也位居本清單前 25%，可考慮優先閱讀。", "Recommended for priority reading. It appears in an SJR Q1 journal and its Reading Priority is in the top 25% of this list."))

    st.markdown(f"### {t('目前文章在各項分布中的位置', 'Current paper within each distribution')}")
    st.caption(t("盒鬚圖顯示清單中所有文獻的分布：盒內線是中位數，兩端是最小值與最大值，暖色菱形是目前這篇文章。各指標保留原始尺度。", "Each box plot shows all references. The center line is the median, whiskers show the minimum and maximum, and the warm-colored diamond marks the current paper. Each metric keeps its original scale."))
    for criterion, metrics in criteria_specs():
        st.markdown(f"**{criterion}**")
        columns = st.columns(len(metrics))
        for column, (label, field) in zip(columns, metrics):
            with column:
                metric_boxplot(peers, p, label, field)

    with st.expander(t("查看原始指標與書目資料", "View raw metrics and bibliographic data")):
        metric_column, bibliography_column = st.columns([1, 1])
        with metric_column:
            st.markdown(f"**{t('原始指標', 'Raw metrics')}**")
            evidence = [(label, metric_label(p, field)) for _criterion, metrics in criteria_specs() for label, field in metrics]
            st.dataframe(pd.DataFrame({t("指標", "Metric"): [item[0] for item in evidence], t("數值", "Value"): [item[1] for item in evidence]}), hide_index=True, width="stretch")
        with bibliography_column:
            st.markdown(f"**{t('書目資料', 'Bibliographic data')}**")
            st.markdown(f"**{t('作者', 'Authors')}**  \n{'; '.join(p.authors) or p.first_author_name or t('無資料', 'N/A')}")
            st.markdown(f"**{t('年份', 'Year')}**  \n{p.year or t('無資料', 'N/A')}")
            st.markdown(f"**{t('期刊／來源', 'Journal / Source')}**  \n{p.source_name or t('無資料', 'N/A')}")
            st.markdown(f"**{t('領域分類', 'Classification')}**  \n{' → '.join(filter(None, [p.domain, p.field, p.subfield, p.primary_topic])) or t('無資料', 'N/A')}")
            st.markdown(f"**DOI**  \n{p.doi or t('無資料', 'N/A')}")


settings = load_settings()
pipeline = AnalysisPipeline(settings)
apply_component_styles()
head, actions = st.columns([12, 1], vertical_alignment="center")
with actions:
    with st.popover(
        t("介面選項", "Interface options"),
        help=t("介面選項", "Interface options"),
        key="interface_options",
        use_container_width=True,
    ):
        language_choice = st.segmented_control(
            "語言 / Language",
            ["繁體中文", "English"],
            default=language_choice,
            key="language_selector",
            label_visibility="collapsed",
            width="stretch",
        ) or "繁體中文"
        st.divider()
        if st.button(
            t("指標說明", "Metrics Guide"),
            icon=":material/menu_book:",
            type="tertiary",
            key="metrics_guide_button",
            use_container_width=True,
        ):
            metric_help_dialog()
language = "zh-TW" if language_choice == "繁體中文" else "en"
with head:
    st.title("NextRead")
st.write(t("輸入論文 DOI 或標題，即可取得閱讀建議。也可以上傳 PDF，抽取或比對參考文獻。", "Enter a paper DOI or title for fast recommendations; optionally upload a PDF to extract or compare references."))
st.info(t(
    "Reading Priority 告訴你先讀哪篇，SJR Quartile 顯示期刊在所屬學科的分區，Local PageRank、Semantic Similarity 和 FWCI 則幫你了解推薦原因。",
    "Reading Priority determines the reading order for this reference list. Use SJR Quartile to quickly see a journal's standing within its subject category, then consult Local PageRank, Semantic Similarity, FWCI, and other metrics to understand why a paper may deserve priority.",
))
if pipeline.sjr.available:
    st.success(t(
        f"目前使用 SJR {pipeline.sjr.year or '年份未知'} 資料。如要更新，請到「進階設定 → 手動更新 SJR 資料」。",
        f"Currently using SJR {pipeline.sjr.year or 'year unknown'} data. To update it, use Advanced settings → Manually update SJR data.",
    ))
else:
    st.warning(t("尚未安裝 SJR 資料。請到「進階設定 → 手動更新 SJR 資料」，依照畫面上的步驟安裝。", "SJR data is not installed. Open Advanced settings and follow the three steps under Manually update SJR data."))
update_message = st.session_state.pop("sjr_update_message", None)
if update_message:
    st.success(update_message)

identifier = st.text_input(t("原始論文 DOI 或標題", "Source paper DOI or title"), placeholder="10.1234/example or paper title")
uploaded = st.file_uploader(t("選擇 PDF（選填）", "Select PDF (optional)"), type=["pdf"])
if uploaded:
    st.caption(f"{uploaded.name} · {uploaded.size / 1024 / 1024:.2f} MB")
mode = st.radio(t("分析模式", "Analysis mode"), list(MODES), index=1, horizontal=True, format_func=lambda x: t(*MODE_TEXT[x][0]))
st.caption(t(*MODE_TEXT[mode][1]))
defaults = MODES[mode]
grobid_status_note = None
with st.expander(t("進階設定", "Advanced settings")):
    use_grobid = st.checkbox(t("使用 GROBID 解析 PDF", "Use GROBID to parse PDF"), value=False)
    st.caption(t(
        "不裝 Docker 也能取得閱讀建議，若想從 PDF 盡量擷取完整的參考文獻，建議使用 GROBID 並將抽取結果與原文核對。",
        "GROBID is optional: fast recommendations work without Docker. For the most complete PDF-derived reference list, we recommend GROBID. Verify extracted references against the paper.",
    ))
    if use_grobid:
        st.caption(t("請先開啟 Docker Desktop，再到專案資料夾執行 `docker compose up -d grobid`。NextRead 只檢查服務是否就緒，不會自動啟動。", "Start Docker Desktop yourself, then run `docker compose up -d grobid` in the project folder. NextRead checks the service but does not start it."))
        if not st.session_state.get("grobid_check_done"):
            st.session_state["grobid_check_done"] = True
            rechecking = st.session_state.pop("grobid_recheck_requested", False)
            try:
                if rechecking:
                    with st.status(t("正在重新檢查 GROBID…", "Rechecking GROBID…"), expanded=True) as status:
                        progress_line = status.empty()
                        def report_retry(attempt: int) -> None:
                            progress_line.write(t(
                                f"容器已啟動，API 尚未回應。稍後重試（{attempt}/5）。",
                                f"Container is running; waiting for its API before retrying ({attempt}/5).",
                            ))
                        try:
                            check_grobid_ready(pipeline.grobid, APP_DIR, api_attempts=6, on_retry=report_retry)
                        except GrobidUnavailableError:
                            status.update(label=t("本次檢查完成：GROBID 仍未就緒", "Check complete: GROBID is not ready"), state="error")
                            raise
                        status.update(label=t("本次檢查完成：GROBID 已就緒", "Check complete: GROBID is ready"), state="complete", expanded=False)
                else:
                    with st.spinner(t("正在檢查 Docker 與 GROBID…", "Checking Docker and GROBID…")):
                        check_grobid_ready(pipeline.grobid, APP_DIR)
                st.session_state.pop("grobid_check_error", None)
            except GrobidUnavailableError as exc:
                st.session_state["grobid_check_error"] = str(exc)
        grobid_status_note = st.empty()
        if error := st.session_state.get("grobid_check_error"):
            grobid_status_note.warning(t(f"GROBID 尚未就緒：{error}", f"GROBID is not ready: {error}"))
        else:
            grobid_status_note.success(t("Docker 與 GROBID 已就緒。", "Docker and GROBID are ready."))
        st.button(t("重新檢查 GROBID", "Recheck GROBID"), on_click=request_grobid_recheck)
    else:
        st.session_state.pop("grobid_check_done", None)
        st.session_state.pop("grobid_check_error", None)
        st.session_state.pop("grobid_recheck_requested", None)
    crossref = st.checkbox(t("Crossref 逐筆書目辨識", "Crossref per-reference lookup"), value=defaults["crossref"])
    st.caption(t("輸入 DOI 或標題時，Crossref 都會查找論文及出版者提交的參考文獻，而這個選項只決定是否繼續逐筆查詢。", "The DOI/title entry always uses Crossref for the source paper and publisher-deposited list; this option controls subsequent per-reference lookup only."))
    openalex = st.checkbox("OpenAlex", value=defaults["openalex"])
    semantic_scholar = st.checkbox("Semantic Scholar", value=defaults["semantic_scholar"])
    force_refresh = st.checkbox(t("重新查詢外部 API（不使用快取）", "Re-query external APIs (skip cache)"))
    st.caption(t(
        "勾選後，這次分析會略過快取，向已啟用的 Crossref、OpenAlex 和 Semantic Scholar 重新查詢並更新快取，因此可能較慢，也會消耗 API 額度。",
        "Normally, cached API responses speed up analysis. This option skips existing Crossref, OpenAlex, and Semantic Scholar cache entries for this run, re-queries enabled services, and updates the cache. It may be slower and use API quota.",
    ))
    st.divider()
    st.markdown(f"### {t('手動更新 SJR 資料', 'Manually update SJR data')}")
    current_sjr = t(
        f"目前版本：**{pipeline.sjr.year or '年份未知'}**（{len(pipeline.sjr.by_title):,} 筆期刊）" if pipeline.sjr.available else "目前狀態：**尚未安裝**",
        f"Current version: **{pipeline.sjr.year or 'year unknown'}** ({len(pipeline.sjr.by_title):,} journals)" if pipeline.sjr.available else "Current status: **Not installed**",
    )
    st.markdown(current_sjr)
    st.markdown(t(
        "1. 到 [SCImago 官方網站](https://www.scimagojr.com/journalrank.php) 查看並下載最新年度的 CSV。\n"
        "2. 在下方選擇下載的 CSV。\n"
        "3. 按「驗證並更新」。通過格式檢查後，系統才會取代目前的資料。",
        "1. Check the [official SCImago website](https://www.scimagojr.com/journalrank.php) once a year and download the latest CSV.\n"
        "2. Select the downloaded CSV below.\n"
        "3. Choose Validate and update. The current version is replaced only after validation succeeds.",
    ))
    sjr_upload = st.file_uploader(t("選擇新版 SCImago CSV", "Select a newer SCImago CSV"), type=["csv"], key="sjr_update_file")
    if sjr_upload and st.button(t("驗證並更新 SJR 資料", "Validate and update SJR data"), type="secondary"):
        settings.sjr_data_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.sjr_data_path.parent, suffix=".csv", delete=False) as pending:
            pending.write(sjr_upload.getvalue())
            pending_path = Path(pending.name)
        candidate = pipeline.sjr.__class__(pending_path)
        if candidate.available and candidate.year:
            pending_path.replace(settings.sjr_data_path)
            pipeline.sjr = pipeline.sjr.__class__(settings.sjr_data_path)
            st.session_state["sjr_update_message"] = t(
                f"SJR 資料已更新為 {pipeline.sjr.year}，共載入 {len(pipeline.sjr.by_title):,} 筆期刊。",
                f"SJR data updated to {pipeline.sjr.year}; {len(pipeline.sjr.by_title):,} journals loaded.",
            )
            st.rerun()
        else:
            pending_path.unlink(missing_ok=True)
            st.error(t("更新失敗：檔案未通過格式或年份檢查；原有的 SJR 資料不受影響。", "Update failed: the file did not pass format or year validation. Existing SJR data was not replaced."))

st.subheader(t("服務狀態", "Service status"))
cols = st.columns(6)
grobid_metric = cols[0].empty()
grobid_metric.metric("GROBID", (t("已就緒", "Ready") if not st.session_state.get("grobid_check_error") else t("未就緒", "Not ready")) if use_grobid else t("未選用", "Not selected"))
cols[1].metric(t("Crossref 逐筆查詢", "Crossref per-reference"), t("已啟用", "Enabled") if crossref else t("未啟用", "Disabled"))
cols[2].metric("OpenAlex", t("已啟用", "Enabled") if openalex else t("未啟用", "Disabled"))
cols[2].caption(t("API Key 已載入", "API key loaded") if settings.openalex_api_key else t("API Key 未設定", "API key not set"))
cols[3].metric("Semantic Scholar", t("未啟用", "Disabled") if not semantic_scholar else t("已啟用", "Enabled"))
cols[3].caption(t("API Key 已載入", "API key loaded") if settings.semantic_scholar_api_key else t("API Key 未設定", "API key not set"))
cols[4].metric("SJR", str(pipeline.sjr.year or t("已載入", "Loaded")) if pipeline.sjr.available else t("無資料", "No data"))
cols[5].metric("Scite", t("尚未實作", "Not implemented"))

if st.button(t("開始分析", "Start analysis"), type="primary", disabled=not (identifier.strip() or uploaded)):
    bar, text = st.progress(0), st.empty()
    def update(step: int, message: str) -> None:
        bar.progress(step / 7); text.write(f"{step}. {message}")
    path = None
    try:
        if use_grobid and uploaded:
            with st.spinner(t("正在確認 GROBID 服務…", "Checking GROBID service…")):
                check_grobid_ready(pipeline.grobid, APP_DIR)
            st.session_state.pop("grobid_check_error", None)
            grobid_status_note.success(t("Docker 與 GROBID 已就緒。", "Docker and GROBID are ready."))
            grobid_metric.metric("GROBID", t("已就緒", "Ready"))
        if uploaded:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
                temp.write(uploaded.getbuffer()); path = Path(temp.name)
        st.session_state["result"] = pipeline.analyze_identifier(
            identifier.strip(),
            {"crossref": crossref, "openalex": openalex, "semantic_scholar": semantic_scholar},
            path, force_refresh, update, language, use_grobid,
        )
        bar.progress(1.0); text.write(t("分析完成", "Analysis complete"))
    except GrobidUnavailableError as exc:
        st.session_state["grobid_check_error"] = str(exc)
        grobid_status_note.warning(t(f"GROBID 尚未就緒：{exc}", f"GROBID is not ready: {exc}"))
        grobid_metric.metric("GROBID", t("未就緒", "Not ready"))
        st.error(t(f"無法完成分析：{exc}", f"Analysis could not be completed: {exc}"))
    except Exception as exc:
        logging.exception("Analysis failed"); st.error(t(f"無法完成分析：{exc}", f"Analysis could not be completed: {exc}"))
    finally:
        if path:
            path.unlink(missing_ok=True)

result: AnalysisResult | None = st.session_state.get("result")
if result:
    st.divider(); st.header(t("分析摘要", "Analysis summary"))
    if any(not hasattr(paper, "is_influential_citation") for paper in result.references):
        st.info(t(
            "目前顯示的是更新前儲存的分析結果。原有指標仍可查看；重新分析後，才能取得新版的具影響力引用與作者指標。",
            "This result was saved before the scoring update. Existing metrics remain visible; run the analysis again to obtain the revised influential-citation and author metrics.",
        ))
    st.write(f"**{t('原始論文', 'Seed paper')}：** {result.seed.title or t('無法取得標題', 'Title unavailable')}")
    source = result.stats.get("reference_source")
    if source == "crossref":
        st.info(t("參考文獻來自出版者提交給 Crossref 的資料，尚未與原文完整核對，可能有遺漏。", "Reference source: publisher-deposited Crossref data; not fully checked against the paper, and the list may be incomplete."))
    elif source:
        st.info(t(f"參考文獻從 PDF 以 {source} 抽取，尚未逐筆確認是否完整。", f"Reference source: PDF ({source} extraction); item-by-item completeness is unverified."))
    comparison = result.stats.get("pdf_comparison")
    if comparison and comparison.get("status") == "partial_comparison":
        st.caption(t(
            f"PDF 與 Crossref 的 DOI 局部比對：PDF 抽出 {comparison['pdf_references']} 筆參考文獻，其中 {comparison['pdf_dois']} 筆有 DOI；Crossref 有 {comparison['crossref_dois']} 筆 DOI。兩邊重疊 {comparison['shared_dois']} 筆，僅 PDF 有 {comparison['pdf_dois'] - comparison['shared_dois']} 筆，僅 Crossref 有 {comparison['crossref_dois'] - comparison['shared_dois']} 筆。這不代表兩份清單的文字完全一致。",
            f"Partial PDF–Crossref DOI comparison: {comparison['pdf_references']} PDF items, {comparison['pdf_dois']} with DOI; {comparison['crossref_dois']} Crossref DOIs, {comparison['shared_dois']} shared, {comparison['pdf_dois'] - comparison['shared_dois']} PDF only, {comparison['crossref_dois'] - comparison['shared_dois']} Crossref only. This does not verify full-text agreement.",
        ))
    summary = st.columns(6)
    summary[0].metric(t("參考文獻", "References"), result.stats["references_extracted"])
    summary[1].metric(t("成功辨識", "Resolved"), result.stats["references_resolved"], f"{result.stats['resolution_rate']}%")
    summary[2].metric("SJR Coverage", f"{result.stats.get('sjr_coverage', 0)} / {result.stats['references_extracted']}")
    summary[3].metric("OpenAlex Coverage", f"{result.stats['openalex_coverage']} / {result.stats['references_extracted']}")
    summary[4].metric("S2 Coverage", f"{result.stats['semantic_scholar_coverage']} / {result.stats['references_extracted']}")
    summary[5].metric(t("有效計分面向", "Active dimensions"), f"{result.stats['active_dimensions']} / 6")
    for warning in result.warnings:
        st.warning(warning)
    performance_charts(result.references)
    filtered = filtered_rows(rows_for(result))
    st.header(t("參考文獻閱讀順序", "Reference reading order"))
    visible = [key for key in filtered[0] if key != "_paper_index"] if filtered else []
    status_column = t("辨識狀態", "Resolution Status")
    st.dataframe(
        pd.DataFrame(filtered)[visible] if filtered else pd.DataFrame(),
        hide_index=True,
        width="stretch",
        column_config={
            status_column: st.column_config.TextColumn(
                status_column,
                help=t(
                    "「DOI 精確符合」表示原始文獻附有 DOI；「高／中可信度符合」表示系統根據書目資料找到候選文獻；「尚未辨識」表示目前沒有可靠的比對結果。",
                    "Exact DOI means the source reference supplied a DOI. High/medium confidence means a candidate was matched from bibliographic data. Unresolved means no reliable result was found.",
                ),
            ),
        },
    )
    if filtered:
        rank, title = t("排名", "Rank"), t("文章標題", "Title")
        labels = {f"#{row[rank]} — {row[title]}": row["_paper_index"] for row in filtered}
        selected = st.selectbox(t("查看文獻詳細資料", "View reference details"), labels)
        paper_detail(result.references[labels[selected]], result.references)
    st.header(t("匯出結果", "Export results"))
    export_rows = []
    for paper in result.references:
        row = paper.to_dict()
        row["reference_source"] = result.stats.get("reference_source", "unknown")
        row["source_list_verified_against_pdf"] = False
        for field in ("authors", "author_h_indices", "other_topics", "referenced_works", "source_issns"):
            row[field] = "; ".join(str(value) for value in row.get(field, []))
        row.pop("embedding", None); row.pop("provider_data", None); export_rows.append(row)
    csv_data = pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig")
    json_data = json.dumps(result.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
    left, right = st.columns(2, gap="small", width=420)
    with left:
        st.download_button(
            t("下載完整 CSV", "Download full CSV"),
            csv_data,
            "nextread-ranking.csv",
            "text/csv",
            key="export_csv",
            icon=":material/download:",
            on_click="ignore",
            width="stretch",
        )
    with right:
        st.download_button(
            t("下載完整 JSON", "Download full JSON"),
            json_data,
            "nextread-ranking.json",
            "application/json",
            key="export_json",
            icon=":material/download:",
            on_click="ignore",
            width="stretch",
        )
