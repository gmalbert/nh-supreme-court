"""
pages/03_Analysis.py — Analytics dashboard
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, OUTCOME_COLORS, OUTCOME_LABELS
from utils.data_loader import load_opinions, data_last_updated
from utils.charts import (
    outcome_bar,
    opinions_per_year,
    rsa_citation_bar,
    avg_decision_time_per_year,
    avg_word_count_by_case_type,
    avg_word_count_by_year,
    avg_word_count_by_justice,
    avg_word_count_by_year_per_justice,
)


def _format_outcome(value):
    if pd.isna(value):
        return "—"
    key = str(value).strip().lower()
    return OUTCOME_LABELS.get(key, key.replace("_", " ").title())


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out

logo_path = ROOT / "data_files" / "logo.png"
st.title("Analysis")

df = load_opinions()

if df.empty:
    st.warning("No data available. Run: `python scripts/update.py`")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    years = sorted(df["term_year"].dropna().unique().astype(int))
    year_range = st.slider("Year Range", min(years), max(years), (min(years), max(years)))
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

filtered = df[
    (df["term_year"] >= year_range[0]) & (df["term_year"] <= year_range[1])
].copy()

tab1, tab2, tab3, tab4 = st.tabs(
    ["Term Statistics", "Statutory Spotlight", "Win Rate Analysis", "Close Decisions"]
)

# ── Tab 1: Term Statistics ─────────────────────────────────────────────────────
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Opinions", len(filtered))
    col2.metric(
        "Unanimous",
        int(filtered["is_unanimous"].sum()) if "is_unanimous" in filtered.columns else 0,
    )
    col3.metric(
        "With Dissent",
        int(filtered["has_dissent"].sum()) if "has_dissent" in filtered.columns else 0,
    )
    avg_days = filtered["days_to_decision"].dropna().mean()
    col4.metric("Avg Days to Decision", f"{avg_days:.0f}" if pd.notna(avg_days) else "—")

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        fig_out = outcome_bar(filtered)
        st.plotly_chart(fig_out, width="stretch")

    with col_b:
        fig_yr = opinions_per_year(filtered)
        st.plotly_chart(fig_yr, width="stretch")

    fig_avg_time = avg_decision_time_per_year(filtered)
    if fig_avg_time.data:
        st.plotly_chart(fig_avg_time, width="stretch")

    col_wc1, col_wc2 = st.columns(2)
    with col_wc1:
        fig_wc_type = avg_word_count_by_case_type(filtered)
        if fig_wc_type.data:
            st.plotly_chart(fig_wc_type, width="stretch")

    with col_wc2:
        fig_wc_year = avg_word_count_by_year(filtered)
        if fig_wc_year.data:
            st.plotly_chart(fig_wc_year, width="stretch")

    fig_wc_justice = avg_word_count_by_justice(filtered)
    if fig_wc_justice.data:
        st.plotly_chart(fig_wc_justice, width="stretch")

    fig_wc_justice_year = avg_word_count_by_year_per_justice(filtered)
    if fig_wc_justice_year.data:
        st.plotly_chart(fig_wc_justice_year, width="stretch")

    # Topic breakdown
    if "topics" in filtered.columns:
        all_topics = []
        for cell in filtered["topics"].dropna():
            try:
                topics_list = ast.literal_eval(cell) if isinstance(cell, str) else cell
                all_topics.extend(topics_list)
            except Exception:
                pass
        if all_topics:
            topic_counts = (
                pd.Series(all_topics)
                .value_counts()
                .reset_index()
            )
            topic_counts.columns = ["topic", "count"]
            topic_counts["topic"] = topic_counts["topic"].str.replace("_", " ").str.title()
            fig_topic = px.bar(
                topic_counts.head(12),
                x="count",
                y="topic",
                orientation="h",
                color_discrete_sequence=["#003057"],
                labels={"count": "# Opinions", "topic": "Topic"},
                title="Topic Distribution",
            )
            fig_topic.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_topic, width="stretch")

    # Longest/shortest
    if "days_to_decision" in filtered.columns:
        days_df = filtered[filtered["days_to_decision"].notna()].copy()
        if not days_df.empty:
            st.subheader("Fastest & Slowest Decisions")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Fastest (fewest days)**")
                fastest = days_df.nsmallest(5, "days_to_decision")[
                    ["case_name", "citation", "case_number", "days_to_decision", "pdf_url"]
                ].copy()
                fastest["citation"] = fastest["citation"].fillna("").astype(str).str.strip()
                fastest.loc[fastest["citation"] == "", "citation"] = (
                    fastest["case_number"].fillna("unknown").astype(str)
                )
                fastest = fastest[["case_name", "citation", "days_to_decision", "pdf_url"]]
                fastest = _title_columns(fastest)
                fastest.rename(columns={"Pdf Url": "PDF"}, inplace=True)
                st.dataframe(fastest, hide_index=True, width="stretch",
                             column_config={"PDF": st.column_config.LinkColumn("PDF", display_text="View \u2197")})
            with c2:
                st.markdown("**Slowest (most days)**")
                slowest = days_df.nlargest(5, "days_to_decision")[
                    ["case_name", "citation", "case_number", "days_to_decision", "pdf_url"]
                ].copy()
                slowest["citation"] = slowest["citation"].fillna("").astype(str).str.strip()
                slowest.loc[slowest["citation"] == "", "citation"] = (
                    slowest["case_number"].fillna("unknown").astype(str)
                )
                slowest = slowest[["case_name", "citation", "days_to_decision", "pdf_url"]]
                slowest = _title_columns(slowest)
                slowest.rename(columns={"Pdf Url": "PDF"}, inplace=True)
                st.dataframe(slowest, hide_index=True, width="stretch",
                             column_config={"PDF": st.column_config.LinkColumn("PDF", display_text="View \u2197")})

# ── Tab 2: Statutory Spotlight ──────────────────────────────────────────────────
with tab2:
    fig_rsa = rsa_citation_bar(filtered)
    st.plotly_chart(fig_rsa, width="stretch")

    rsa_search = st.text_input("Search opinions by RSA chapter/section (e.g. RSA 135)")
    if rsa_search:
        q = rsa_search.strip().upper()
        mask = filtered["rsa_citations"].str.upper().str.contains(q, na=False)
        rsa_filtered = filtered[mask]
        st.caption(f"{len(rsa_filtered)} opinions cite {rsa_search}")
        if not rsa_filtered.empty:
            rsa_display = rsa_filtered[["citation", "case_number", "case_name", "date_issued", "outcome", "topics"]].copy()
            rsa_display["citation"] = rsa_display["citation"].fillna("").astype(str).str.strip()
            rsa_display.loc[rsa_display["citation"] == "", "citation"] = rsa_display["case_number"].fillna("unknown").astype(str)
            rsa_display["outcome"] = rsa_display["outcome"].map(_format_outcome)
            rsa_display = rsa_display[["citation", "case_name", "date_issued", "outcome", "topics"]]
            rsa_display = _title_columns(rsa_display)
            st.dataframe(
                rsa_display,
                width="stretch",
                hide_index=True,
            )

    st.divider()
    si_flag = filtered.get("involves_statutory_interpretation", pd.Series(dtype=bool))
    si_count = int(si_flag.sum()) if not si_flag.empty else 0
    pct = si_count / len(filtered) * 100 if len(filtered) > 0 else 0
    st.metric("Statutory Interpretation Cases", si_count, delta=f"{pct:.1f}% of total")

    # Standard of review breakdown
    if "standard_of_review" in filtered.columns:
        standards = []
        for cell in filtered["standard_of_review"].dropna():
            try:
                s_list = ast.literal_eval(cell) if isinstance(cell, str) else cell
                standards.extend(s_list)
            except Exception:
                pass
        if standards:
            s_counts = pd.Series(standards).value_counts().reset_index()
            s_counts.columns = ["standard", "count"]
            s_counts["standard"] = s_counts["standard"].str.replace("_", " ").str.title()
            fig_s = px.pie(
                s_counts, values="count", names="standard",
                title="Standard of Review Distribution",
            )
            st.plotly_chart(fig_s, width="stretch")

# ── Tab 3: Win Rate Analysis ────────────────────────────────────────────────────
with tab3:
    st.subheader("Outcome by Appeal Type")
    if "appeal_type" in filtered.columns and "outcome" in filtered.columns:
        pivot = (
            filtered.groupby(["appeal_type", "outcome"])
            .size()
            .reset_index(name="count")
        )
        if not pivot.empty:
            fig_pivot = px.bar(
                pivot,
                x="appeal_type",
                y="count",
                color="outcome",
                color_discrete_map=OUTCOME_COLORS,
                title="Outcome by Appeal Type",
                labels={"appeal_type": "Appeal Type", "count": "# Opinions"},
                barmode="stack",
            )
            fig_pivot.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_pivot, width="stretch")

    st.subheader("Outcome by Lower Court Type")
    if "lower_court_type" in filtered.columns:
        lc_pivot = (
            filtered[filtered["lower_court_type"].notna()]
            .groupby(["lower_court_type", "outcome"])
            .size()
            .reset_index(name="count")
        )
        if not lc_pivot.empty:
            fig_lc = px.bar(
                lc_pivot,
                x="lower_court_type",
                y="count",
                color="outcome",
                color_discrete_map=OUTCOME_COLORS,
                title="Reversal Rate by Lower Court",
                barmode="stack",
            )
            fig_lc.update_layout(plot_bgcolor="white", xaxis_tickangle=-20)
            st.plotly_chart(fig_lc, width="stretch")

    st.subheader("Win Rates Over Time")
    if "term_year" in filtered.columns and "outcome" in filtered.columns:
        yearly_out = (
            filtered.groupby(["term_year", "outcome"])
            .size()
            .reset_index(name="count")
        )
        fig_time = px.line(
            yearly_out,
            x="term_year",
            y="count",
            color="outcome",
            color_discrete_map=OUTCOME_COLORS,
            markers=True,
            title="Outcome Trends Over Time",
        )
        fig_time.update_layout(plot_bgcolor="white")
        st.plotly_chart(fig_time, width="stretch")

# ── Tab 4: Close Decisions ──────────────────────────────────────────────────────
with tab4:
    dissent_df = filtered[filtered.get("has_dissent", pd.Series(False, index=filtered.index)) == True]

    st.subheader("Divided Decisions")
    st.metric("Cases with Dissent", len(dissent_df))

    if not dissent_df.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            # Topic breakdown of dissented cases
            all_topics = []
            for cell in dissent_df.get("topics", pd.Series(dtype=str)).dropna():
                try:
                    topics_list = ast.literal_eval(cell) if isinstance(cell, str) else cell
                    all_topics.extend(topics_list)
                except Exception:
                    pass
            if all_topics:
                t_counts = pd.Series(all_topics).value_counts().reset_index()
                t_counts.columns = ["topic", "count"]
                t_counts["topic"] = t_counts["topic"].str.replace("_", " ").str.title()
                fig_td = px.bar(
                    t_counts.head(10),
                    x="count", y="topic", orientation="h",
                    color_discrete_sequence=["#C62828"],
                    title="Topics in Divided Cases",
                )
                fig_td.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_td, width="stretch")

        with col_b:
            # Timeline of dissents
            dis_timeline = dissent_df.groupby("term_year").size().reset_index(name="dissents")
            fig_dt = px.bar(
                dis_timeline,
                x="term_year", y="dissents",
                color_discrete_sequence=["#C62828"],
                title="Divided Decisions Per Year",
            )
            fig_dt.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_dt, width="stretch")

        dissent_display = dissent_df[["citation", "case_number", "case_name", "date_issued", "vote_string", "outcome", "pdf_url"]].copy()
        dissent_display["citation"] = dissent_display["citation"].fillna("").astype(str).str.strip()
        dissent_display.loc[dissent_display["citation"] == "", "citation"] = dissent_display["case_number"].fillna("unknown").astype(str)
        dissent_display["outcome"] = dissent_display["outcome"].map(_format_outcome)
        dissent_display = dissent_display[["citation", "case_name", "date_issued", "vote_string", "outcome", "pdf_url"]]
        dissent_display = _title_columns(dissent_display)
        dissent_display = dissent_display.rename(columns={"Pdf Url": "Decision"})
        st.dataframe(
            dissent_display,
            width="stretch",
            hide_index=True,
            column_config={
                "Decision": st.column_config.LinkColumn("Decision", display_text="View ↗", width="small"),
            },
        )

