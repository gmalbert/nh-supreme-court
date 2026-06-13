"""
pages/04_Topics.py — Legal topic explorer and RSA tracker
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, OUTCOME_COLORS, OUTCOME_LABELS
from utils.data_loader import load_opinions, load_topic_taxonomy, data_last_updated
from footer import add_gavel_glimpse_footer


def parse_topic_list(cell) -> list[str]:
    try:
        parsed = ast.literal_eval(cell) if isinstance(cell, str) else cell
    except Exception:
        parsed = []
    return parsed if isinstance(parsed, list) else []


def format_topic_labels(cell) -> str:
    topics = parse_topic_list(cell)
    if not topics:
        return "—"
    return " | ".join(t.replace("_", " ").title() for t in topics)


def parse_rsa_list(cell) -> list[str]:
    try:
        parsed = ast.literal_eval(cell) if isinstance(cell, str) else cell
    except Exception:
        parsed = []
    return parsed if isinstance(parsed, list) else []

logo_path = ROOT / "data_files" / "logo.png"
st.title("Legal Topics Explorer")

df = load_opinions()
taxonomy = load_topic_taxonomy()

if df.empty:
    st.warning("No data available. Run: `python scripts/update.py`")
    st.stop()

with st.sidebar:
    st.header("Topics")
    years = sorted(df["term_year"].dropna().unique().astype(int))
    year_range = st.slider("Year Range", min(years), max(years), (min(years), max(years)))
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

filtered = df[
    (df["term_year"] >= year_range[0]) & (df["term_year"] <= year_range[1])
].copy()

tab1, tab2, tab3 = st.tabs(["Topic Overview", "RSA Tracker", "Criminal/Civil/Family"])

# ── Tab 1: Topic Overview ──────────────────────────────────────────────────────
with tab1:
    # Expand topic lists
    all_topics_flat = []
    for cell in filtered["topics"].dropna():
        try:
            t_list = ast.literal_eval(cell) if isinstance(cell, str) else cell
            all_topics_flat.extend(t_list)
        except Exception:
            pass

    if not all_topics_flat:
        st.info("No topic data available.")
    else:
        t_counts = pd.Series(all_topics_flat).value_counts().reset_index()
        t_counts.columns = ["topic_key", "count"]
        t_counts["topic_label"] = t_counts["topic_key"].map(
            lambda k: taxonomy.get(k, {}).get("label", k.replace("_", " ").title())
        )

        available_topics = t_counts["topic_key"].tolist()
        requested_topic = st.query_params.get("topic", "")
        default_topics = [requested_topic] if requested_topic in available_topics else []
        selected_topics = st.multiselect(
            "Select Topics to Explore",
            options=available_topics,
            default=default_topics,
            format_func=lambda k: taxonomy.get(k, {}).get("label", k.replace("_", " ").title()),
        )

        col_a, col_b = st.columns(2)
        with col_a:
            fig_tc = px.bar(
                t_counts.head(15),
                x="count", y="topic_label", orientation="h",
                color_discrete_sequence=["#003057"],
                title="Opinions Per Topic",
            )
            fig_tc.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_tc, width="stretch")

        if selected_topics:
            # Filter to selected topics
            def has_topic(cell, topics):
                try:
                    t_list = ast.literal_eval(cell) if isinstance(cell, str) else cell
                    return any(t in t_list for t in topics)
                except Exception:
                    return False

            topic_df = filtered[filtered["topics"].apply(lambda c: has_topic(c, selected_topics))]
            with col_b:
                st.metric("Matching Opinions", len(topic_df))

                if "outcome" in topic_df.columns:
                    out_counts = topic_df["outcome"].value_counts().reset_index()
                    out_counts.columns = ["outcome", "count"]
                    out_counts["label"] = out_counts["outcome"].map(
                        lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title())
                    )
                    out_color_map = {
                        OUTCOME_LABELS.get(k, k.replace("_", " ").title()): v
                        for k, v in OUTCOME_COLORS.items()
                    }
                    fig_out = px.pie(
                        out_counts, values="count", names="label",
                        color="label",
                        color_discrete_map=out_color_map,
                        title="Outcome Distribution",
                    )
                    st.plotly_chart(fig_out, width="stretch")

            topic_display = topic_df[["citation", "case_number", "case_name", "date_issued", "outcome", "author_display", "pdf_url"]].copy()
            topic_display["citation"] = topic_display["citation"].fillna("").astype(str).str.strip()
            topic_display.loc[topic_display["citation"] == "", "citation"] = (
                topic_display["case_number"].fillna("unknown").astype(str)
            )
            topic_display["outcome"] = topic_display["outcome"].map(
                lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title()) if pd.notna(o) else "—"
            )
            topic_display = topic_display.rename(
                columns={
                    "citation": "Citation",
                    "case_name": "Case Name",
                    "date_issued": "Date Issued",
                    "outcome": "Outcome",
                    "author_display": "Author",
                    "pdf_url": "Opinion",
                }
            )
            topic_display = topic_display[["Citation", "Case Name", "Date Issued", "Outcome", "Author", "Opinion"]]
            st.dataframe(
                topic_display,
                width="stretch",
                hide_index=True,
                column_config={
                    "Opinion": st.column_config.LinkColumn("Opinion", display_text="View ↗", width="small"),
                },
            )

            # Year trend for selected topics
            if "term_year" in topic_df.columns:
                year_counts = topic_df.groupby("term_year").size().reset_index(name="count")
                fig_trend = px.line(
                    year_counts, x="term_year", y="count", markers=True,
                    title="Topic Trend Over Years",
                    labels={"term_year": "Year", "count": "Count"},
                    color_discrete_sequence=["#003057"],
                )
                fig_trend.update_layout(plot_bgcolor="white")
                st.plotly_chart(fig_trend, width="stretch")

# ── Tab 2: RSA Tracker ─────────────────────────────────────────────────────────
with tab2:
    rsa_query = st.text_input("Enter RSA chapter or section (e.g. 135, 135-C, 265-A:39)")

    if rsa_query:
        q = rsa_query.strip()
        mask = filtered["rsa_citations"].str.contains(
            re.escape(q), case=False, na=False
        ) if "rsa_citations" in filtered.columns else pd.Series(False, index=filtered.index)
        rsa_df = filtered[mask]
        st.caption(f"{len(rsa_df)} opinions mention RSA {q}")

        if not rsa_df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Opinions", len(rsa_df))
            if "outcome" in rsa_df.columns:
                affirm = (rsa_df["outcome"] == "affirmed").sum()
                c2.metric("Affirmed", int(affirm))
                reverse = rsa_df["outcome"].str.contains("revers", na=False).sum()
                c3.metric("Reversed", int(reverse))

            # Timeline
            if "term_year" in rsa_df.columns:
                yr_counts = rsa_df.groupby("term_year").size().reset_index(name="count")
                fig_r = px.bar(
                    yr_counts, x="term_year", y="count",
                    color_discrete_sequence=["#C8960C"],
                    title=f"RSA {q} — Litigation Timeline",
                )
                fig_r.update_layout(plot_bgcolor="white")
                st.plotly_chart(fig_r, width="stretch")

                rsa_display = rsa_df[["citation", "case_number", "case_name", "date_issued", "outcome", "author_display", "pdf_url"]].copy()
                rsa_display["citation"] = rsa_display["citation"].fillna("").astype(str).str.strip()
                rsa_display.loc[rsa_display["citation"] == "", "citation"] = (
                    rsa_display["case_number"].fillna("unknown").astype(str)
                )
                rsa_display["outcome"] = rsa_display["outcome"].apply(
                    lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title()) if pd.notna(o) else "—"
                )
                rsa_display = rsa_display.rename(
                    columns={
                        "citation": "Citation",
                        "case_name": "Case Name",
                        "date_issued": "Date Issued",
                        "outcome": "Outcome",
                        "author_display": "Author",
                        "pdf_url": "Opinion",
                    }
                )
                rsa_display = rsa_display[["Citation", "Case Name", "Date Issued", "Outcome", "Author", "Opinion"]]
                st.dataframe(
                    rsa_display,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Opinion": st.column_config.LinkColumn("Opinion", display_text="View ↗", width="small"),
                    },
                )

    else:
        st.info("Enter an RSA chapter or section number to see related opinions.")

# ── Tab 3: Criminal/Civil/Family ───────────────────────────────────────────────
with tab3:
    def classify_case_group(row) -> str:
        case_type = str(row.get("case_type", "")).strip().lower()
        topics = parse_topic_list(row.get("topics", "[]"))
        rsa_values = parse_rsa_list(row.get("rsa_citations", "[]"))

        if case_type in {"family/domestic", "domestic/family", "family", "domestic"}:
            return "family/domestic"
        if case_type == "criminal":
            return "criminal"
        if case_type == "civil":
            return "civil"

        if "family_law" in topics or "domestic_violence" in topics:
            return "family/domestic"
        if "criminal" in topics:
            return "criminal"

        for rsa in rsa_values:
            rsa_txt = str(rsa)
            if re.match(r"RSA\s+(?:169-C|173-B|458|461-A)", rsa_txt, flags=re.IGNORECASE):
                return "family/domestic"
            if re.match(r"RSA\s+(?:6\d{2}|265-A)", rsa_txt, flags=re.IGNORECASE):
                return "criminal"

        return "civil"

    grouped = filtered.copy()
    grouped["case_group"] = grouped.apply(classify_case_group, axis=1)

    criminal_df = grouped[grouped["case_group"] == "criminal"].copy()
    civil_df = grouped[grouped["case_group"] == "civil"].copy()
    family_df = grouped[grouped["case_group"] == "family/domestic"].copy()

    def render_group(col, label: str, frame: pd.DataFrame, topic_color: str):
        with col:
            st.subheader(label)
            st.metric("Total", len(frame))
            if frame.empty or "outcome" not in frame.columns:
                st.info("No data for selected range.")
                return

            group_name = (
                label.replace(" Appeals", "")
                .replace("Family/Domestic Appeals", "Family/Domestic")
                .strip()
            )

            out_counts = frame["outcome"].value_counts().reset_index()
            out_counts.columns = ["outcome", "count"]
            out_counts["label"] = out_counts["outcome"].map(
                lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title())
            )
            color_map = {
                OUTCOME_LABELS.get(k, k.replace("_", " ").title()): v
                for k, v in OUTCOME_COLORS.items()
            }
            fig_out = px.pie(
                out_counts,
                values="count",
                names="label",
                color="label",
                color_discrete_map=color_map,
                title=f"{label} — Outcomes",
            )
            fig_out.update_traces(textinfo="none")
            fig_out.update_layout(
                plot_bgcolor="white",
                height=320,
                margin={"l": 10, "r": 10, "t": 55, "b": 85},
                legend=dict(orientation="h", yanchor="top", y=-0.28, xanchor="left", x=0),
                title=dict(x=0.0, xanchor="left"),
            )
            st.plotly_chart(fig_out, width="stretch")

            grp_topics = []
            for cell in frame["topics"].dropna():
                grp_topics.extend(parse_topic_list(cell))
            if grp_topics:
                grp_topic_counts = pd.Series(grp_topics).value_counts().head(8).reset_index()
                grp_topic_counts.columns = ["topic", "count"]
                grp_topic_counts["topic"] = grp_topic_counts["topic"].str.replace("_", " ").str.title()
                fig_topics = px.bar(
                    grp_topic_counts,
                    x="count",
                    y="topic",
                    orientation="h",
                    title=f"{group_name} Topics",
                    color_discrete_sequence=[topic_color],
                )
                fig_topics.update_layout(
                    plot_bgcolor="white",
                    height=320,
                    margin={"l": 10, "r": 10, "t": 55, "b": 45},
                    title=dict(x=0.0, xanchor="left"),
                    yaxis={"autorange": "reversed"},
                )
                st.plotly_chart(fig_topics, width="stretch")

            display_df = frame[["citation", "case_number", "case_name", "date_issued", "outcome", "pdf_url"]].copy()
            display_df["citation"] = display_df["citation"].fillna("").astype(str).str.strip()
            display_df.loc[display_df["citation"] == "", "citation"] = (
                display_df["case_number"].fillna("unknown").astype(str)
            )
            display_df["outcome"] = display_df["outcome"].map(
                lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title()) if pd.notna(o) else "—"
            )
            display_df = display_df.rename(
                columns={
                    "citation": "Citation",
                    "case_name": "Case Name",
                    "date_issued": "Date Issued",
                    "outcome": "Outcome",
                    "pdf_url": "Opinion",
                }
            )
            display_df = display_df[["Citation", "Case Name", "Date Issued", "Outcome", "Opinion"]].head(20)

            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Opinion": st.column_config.LinkColumn("Opinion", display_text="View ↗", width="small"),
                },
            )

    c1, c2, c3 = st.columns(3)
    render_group(c1, "Criminal", criminal_df, "#8B0000")
    render_group(c2, "Civil", civil_df, "#003057")
    render_group(c3, "Family/Domestic", family_df, "#2E7D32")

add_gavel_glimpse_footer()

