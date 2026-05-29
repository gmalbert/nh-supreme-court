"""
cases.py — Granite State Appeals app entrypoint with Streamlit navigation.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, APP_TAGLINE, OUTCOME_COLORS, OUTCOME_LABELS, VOTE_COLORS
from utils.data_loader import data_last_updated, load_opinion_text, load_opinions, load_opinions_json
from utils.charts import bench_diagram

# Streamlit page config must be declared once in the entrypoint when using st.navigation.
st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚖️",
    layout="wide",
)


def _clean_summary_text(value: str) -> str:
    cleaned = str(value).replace("\ufffd", "").strip()
    cleaned = re.sub(r"^\s*[][(){}\"'“”‘’`]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[][(){}\"'“”‘’`]+\s*$", "", cleaned)
    return cleaned.strip()

_SECTION_HEADER_RE = re.compile(
    r"(?m)^[ \t]*(?:I\.?\s+)?(?:Background|Facts|BACKGROUND|FACTS|"
    r"Discussion|DISCUSSION|Procedural History|Procedural|PROCEDURAL|"
    r"History|HISTORY|Analysis|ANALYSIS|The Facts|The Background)\s*$",
    re.MULTILINE,
)
_AUTHOR_LINE_RE = re.compile(
    r"^(PER CURIAM|[A-Z][A-Z\-]+(?:\s+[A-Z][A-Z\-]+)?,\s+(?:C\.J\.|J\.))[.\s]",
    re.MULTILINE,
)


def _extract_intro_text(text: str) -> str:
    """Return all paragraphs before the first Background/Facts section header."""
    if not text:
        return ""
    m = _AUTHOR_LINE_RE.search(text)
    body = text[m.end():].lstrip() if m else text
    sm = _SECTION_HEADER_RE.search(body)
    intro = body[:sm.start()].strip() if sm else body[:3000].strip()
    intro = re.sub(r"\n{3,}", "\n\n", intro)
    return intro[:4000]

def render_case_explorer() -> None:
    """Main case explorer page."""
    logo_path = ROOT / "data_files" / "logo.png"

    col_logo, col_title = st.columns([2, 8])
    with col_logo:
        if logo_path.exists():
            st.image(str(logo_path), width=220)
    with col_title:
        st.title(APP_NAME)
        st.caption(APP_TAGLINE)

    st.divider()

    df = load_opinions()
    opinions_json = load_opinions_json()

    json_map: dict = {r["case_number"]: r for r in opinions_json}

    with st.sidebar:
        st.header("Case Explorer")

        if df.empty:
            st.warning(
                "No data loaded yet. Run the data pipeline first:\n\n"
                "```\npython scripts/update.py\n```"
            )
            st.stop()

        available_years = sorted(df["term_year"].dropna().unique().astype(int), reverse=True)
        selected_year = st.selectbox("Term Year", available_years, index=0)

        year_df = df[df["term_year"] == selected_year].copy()
        case_options = year_df.sort_values("case_name")["case_name"].tolist()

        if not case_options:
            st.info(f"No cases found for {selected_year}")
            st.stop()

        labels = [
            f"{row['case_name']} ({row['case_number']})"
            for _, row in year_df.sort_values("case_name").iterrows()
        ]
        selected_label = st.selectbox("Select Case", labels)
        selected_cn = labels.index(selected_label)
        case_row = year_df.sort_values("case_name").iloc[selected_cn]

        st.divider()
        st.caption(f"Last updated: {data_last_updated()}")
        st.caption(f"{len(df)} opinions in dataset")

    cn = case_row["case_number"]
    full_rec = json_map.get(cn, {})
    _full_text = load_opinion_text(cn)

    col1, col2 = st.columns([3, 2])

    with col1:
        citation = case_row.get("citation") or "—"
        pdf_url = case_row.get("pdf_url", "")
        st.subheader(str(case_row.get("case_name", "Unknown Case")))
        if pdf_url and str(pdf_url) not in ("", "nan"):
            st.markdown(f"**Citation:** {citation} \u00a0 [View PDF ↗]({pdf_url})")
        else:
            st.markdown(f"**Citation:** {citation}")

        date_argued = case_row.get("date_argued")
        date_issued = case_row.get("date_issued")
        days = case_row.get("days_to_decision")
        dates_str = []
        if pd.notna(date_argued) and str(date_argued) != "nan":
            dates_str.append(f"Argued: {str(date_argued)[:10]}")
        if pd.notna(date_issued) and str(date_issued) != "nan":
            dates_str.append(f"Decided: {str(date_issued)[:10]}")
        if days and pd.notna(days):
            dates_str.append(f"({int(days)} days)")
        st.markdown(" · ".join(dates_str) if dates_str else "")

        meta_parts = []
        lc = case_row.get("lower_court")
        if lc and str(lc) != "nan":
            meta_parts.append(f"**Lower Court:** {lc}")
        lc_judge = case_row.get("lower_court_judge")
        if lc_judge and str(lc_judge) != "nan":
            meta_parts.append(f"**Trial Court Judge:** {lc_judge}")
        appeal = case_row.get("appeal_type")
        if appeal and str(appeal) != "nan":
            meta_parts.append(f"**Appeal Type:** {appeal.replace('_', ' ').title()}")
        for p in meta_parts:
            st.markdown(p)

        outcome = case_row.get("outcome")
        if outcome and str(outcome) != "nan":
            color = OUTCOME_COLORS.get(outcome, "#607D8B")
            label = OUTCOME_LABELS.get(outcome, outcome.replace("_", " ").title())
            st.markdown(
                f'<span style="background-color:{color};color:white;padding:4px 12px;'
                f'border-radius:4px;font-weight:bold;">{label}</span>',
                unsafe_allow_html=True,
            )
            st.markdown("")

        topics_raw = case_row.get("topics", "[]")
        try:
            topics = ast.literal_eval(topics_raw) if isinstance(topics_raw, str) else topics_raw
        except Exception:
            topics = []
        if topics:
            tags_html = " ".join(
                f'<span style="background:#E3F2FD;color:#003057;padding:2px 8px;'
                f'border-radius:12px;font-size:0.85em;margin:2px;">{t.replace("_", " ").title()}</span>'
                for t in topics
            )
            st.markdown(tags_html, unsafe_allow_html=True)
            st.markdown("")

        votes = full_rec.get("votes", {})
        if votes:
            st.markdown("**Bench Vote**")
            fig = bench_diagram(votes)
            st.plotly_chart(fig, width="stretch", key=f"bench_{cn}")

            legend_html = ""
            for vote_type, color in VOTE_COLORS.items():
                legend_html += (
                    f'<span style="background:{color};color:white;'
                    f'padding:2px 8px;border-radius:4px;font-size:0.78em;margin:2px;">'
                    f'{vote_type.replace("_", " ").title()}</span> '
                )
            st.markdown(legend_html, unsafe_allow_html=True)

    with col2:
        author_display = case_row.get("author_display", "")
        vote_str = case_row.get("vote_string", "")
        if author_display and str(author_display) != "nan":
            st.markdown("**Opinion Author**")
            st.markdown(
                f"<div style='font-size:2rem;font-weight:700;line-height:1.2;margin-bottom:0.6rem;'>{author_display}</div>",
                unsafe_allow_html=True,
            )
        if vote_str and str(vote_str) != "nan":
            st.markdown("**Vote**")
            st.markdown(
                f"<div style='font-size:2rem;font-weight:700;line-height:1.2;margin-bottom:0.8rem;'>{vote_str}</div>",
                unsafe_allow_html=True,
            )

        is_unanimous = case_row.get("is_unanimous")
        has_dissent = case_row.get("has_dissent")
        if is_unanimous:
            st.success("Unanimous decision")
        elif has_dissent:
            st.error("Divided decision (dissent)")

        rsa_raw = case_row.get("rsa_citations", "[]")
        try:
            rsas = ast.literal_eval(rsa_raw) if isinstance(rsa_raw, str) else rsa_raw
        except Exception:
            rsas = []
        if rsas:
            st.markdown("**Statutes at Issue**")
            for rsa in rsas[:8]:
                st.markdown(f"- {rsa}")

    intro_text = _extract_intro_text(_full_text)
    if intro_text:
        st.divider()
        st.markdown("**Summary**")
        st.markdown(
            f'<div style="font-family:sans-serif;line-height:1.7;font-size:0.95em;">{intro_text}</div>',
            unsafe_allow_html=True,
        )
    elif case_row.get("summary_paragraph") and str(case_row.get("summary_paragraph")) != "nan":
        st.divider()
        st.markdown("**Summary**")
        st.markdown(_clean_summary_text(case_row["summary_paragraph"]))

    with st.expander("Read Full Opinion Text"):
        if _full_text:
            highlighted = re.sub(
                r"(RSA\s+[\d\-A-Z:]+)",
                r'<mark style="background:#FFF9C4;">\1</mark>',
                _full_text,
            )
            st.markdown(
                f'<div style="font-family:sans-serif;line-height:1.7;white-space:pre-wrap;'
                f'font-size:0.92em;">{highlighted}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Full text not available for this opinion.")

    st.divider()
    st.caption(
        "Granite State Appeals — NH Supreme Court Analytics | "
        "Data sourced from courts.nh.gov | Not legal advice"
    )


navigation = st.navigation(
    [
        st.Page(render_case_explorer, title="Case Explorer", icon="⚖️", default=True),
        st.Page("pages/01_Opinions.py", title="Opinions", icon="📜"),
        st.Page("pages/02_Justices.py", title="Justices", icon="👩‍⚖️"),
        st.Page("pages/03_Analysis.py", title="Analysis", icon="📊"),
        st.Page("pages/04_Topics.py", title="Topics", icon="📚"),
        st.Page("pages/05_Case_Orders.py", title="Case Orders/3JX", icon="📋"),
        st.Page("pages/07_Trial_Courts.py", title="Trial Courts", icon="🏛️"),
        st.Page("pages/06_About.py", title="About", icon="ℹ️"),
    ],
    position="sidebar",
)

navigation.run()

