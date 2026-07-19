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
from utils.data_loader import (
    data_last_updated,
    load_brief_counsel,
    load_case_orders,
    load_docket_crosswalk,
    load_official_pdf_manifest_audit,
    load_opinions,
    load_orphan_official_pdf_recovery_candidates,
    load_pending_oral_argument_cases,
    load_oral_arguments,
    load_unmatched_disposition_reconciliation,
    load_unmatched_argument_review_queue,
    load_argument_dispositions,
    load_argument_dispositions_metadata,
)
from utils.case_resolution import (
    ASSESSMENT_LABELS,
    RESOLUTION_LABELS,
    argument_resolution_summary,
    assess_unmatched_arguments,
    disposition_source_summary,
)
from utils.dockets import apply_docket_crosswalk, parse_docket_numbers
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
from utils.enhanced_tab5 import render_enhanced_tab5
from utils.justice_authorship_analysis import render_justice_authorship_analysis
from utils.threejx_routing_analysis import render_3jx_routing_analysis
from footer import add_gavel_glimpse_footer


# The published written-opinion archive begins in 2002.  A few older decisions
# are embedded in later archive PDFs, but they are not annual-trend coverage.
WRITTEN_DECISION_COVERAGE_START = 2002
SHOW_UNMATCHED_ARGUMENT_ASSESSMENT = False


def _format_outcome(value):
    if pd.isna(value):
        return "—"
    key = str(value).strip().lower()
    return OUTCOME_LABELS.get(key, key.replace("_", " ").title())


def _format_chart_label(value):
    if pd.isna(value):
        return "—"
    return str(value).strip().replace("_", " ").title()


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out

logo_path = ROOT / "data_files" / "logo.png"
st.title("Analysis")
st.page_link(
    "pages/08_Oral_Arguments.py",
    label="Explore 2026 oral-argument statistics",
    icon="🎙️",
)

df = load_opinions()
df = df[
    pd.to_numeric(df["term_year"], errors="coerce") >= WRITTEN_DECISION_COVERAGE_START
].copy()

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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "Term Statistics",
        "Statutory Spotlight",
        "Win Rate Analysis",
        "Close Decisions",
        "Arguments & Dispositions",
        "Justice Authorship",
        "3JX Routing",
    ]
)

# ── Tab 1: Term Statistics ─────────────────────────────────────────────────────
with tab1:
    st.caption("Annual written-decision trends use the published archive coverage period: 2002 onward.")
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
            pivot["appeal_type_label"] = pivot["appeal_type"].map(
                _format_chart_label
            )
            pivot["outcome_label"] = pivot["outcome"].map(_format_chart_label)
            outcome_color_map = {
                _format_chart_label(outcome): OUTCOME_COLORS.get(outcome, "#607D8B")
                for outcome in pivot["outcome"].dropna().unique()
            }
            fig_pivot = px.bar(
                pivot,
                x="appeal_type_label",
                y="count",
                color="outcome_label",
                color_discrete_map=outcome_color_map,
                title="Outcome by Appeal Type",
                labels={
                    "appeal_type_label": "Appeal Type",
                    "count": "# Opinions",
                    "outcome_label": "Outcome",
                },
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
            lc_pivot["lower_court_type_label"] = lc_pivot["lower_court_type"].map(
                _format_chart_label
            )
            lc_pivot["outcome_label"] = lc_pivot["outcome"].map(_format_chart_label)
            outcome_color_map = {
                _format_chart_label(outcome): OUTCOME_COLORS.get(outcome, "#607D8B")
                for outcome in lc_pivot["outcome"].dropna().unique()
            }
            fig_lc = px.bar(
                lc_pivot,
                x="lower_court_type_label",
                y="count",
                color="outcome_label",
                color_discrete_map=outcome_color_map,
                title="Reversal Rate by Lower Court",
                labels={
                    "lower_court_type_label": "Lower Court Type",
                    "count": "Count",
                    "outcome_label": "Outcome",
                },
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
        yearly_out["outcome_label"] = yearly_out["outcome"].map(_format_chart_label)
        outcome_color_map = {
            _format_chart_label(outcome): OUTCOME_COLORS.get(outcome, "#607D8B")
            for outcome in yearly_out["outcome"].dropna().unique()
        }
        fig_time = px.line(
            yearly_out,
            x="term_year",
            y="count",
            color="outcome_label",
            color_discrete_map=outcome_color_map,
            markers=True,
            title="Outcome Trends Over Time",
            labels={
                "term_year": "Term Year",
                "count": "Count",
                "outcome_label": "Outcome",
            },
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
                t_counts["topic_label"] = t_counts["topic"].map(_format_chart_label)
                fig_td = px.bar(
                    t_counts.head(10),
                    x="count",
                    y="topic_label",
                    orientation="h",
                    color_discrete_sequence=["#C62828"],
                    title="Topics in Divided Cases",
                    labels={"count": "Count", "topic_label": "Topic"},
                )
                fig_td.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_td, width="stretch")

        with col_b:
            # Timeline of dissents
            dis_timeline = dissent_df.groupby("term_year").size().reset_index(name="dissents")
            dis_timeline["term_year_label"] = dis_timeline["term_year"].map(
                _format_chart_label
            )
            fig_dt = px.bar(
                dis_timeline,
                x="term_year_label",
                y="dissents",
                color_discrete_sequence=["#C62828"],
                title="Divided Decisions Per Year",
                labels={"term_year_label": "Term Year", "dissents": "Dissents"},
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

# ── Tab 5: Arguments & Dispositions ───────────────────────────────────────────
with tab5:
    # Call enhanced Phase 2 implementation
    render_enhanced_tab5(year_range)

    # Legacy content below
    st.subheader("How Oral Arguments Resolved")
    st.caption(
        "Recorded oral arguments are joined to published case orders, 3JX orders, "
        "and opinions by docket number. Combined dockets match any component docket."
    )

    oral_arguments = load_oral_arguments()
    case_orders = load_case_orders()
    docket_crosswalk = load_docket_crosswalk()
    manifest_audit = load_official_pdf_manifest_audit()
    docket_review_queue = load_unmatched_argument_review_queue()
    pending_argument_cases = load_pending_oral_argument_cases()
    reconciliation = load_unmatched_disposition_reconciliation()
    orphan_pdf_recovery = load_orphan_official_pdf_recovery_candidates()
    disposition_orders = pd.concat(
        [
            apply_docket_crosswalk(case_orders[case_orders["order_source"] == "case_order"], docket_crosswalk, "case_order"),
            apply_docket_crosswalk(case_orders[case_orders["order_source"] == "3jx_order"], docket_crosswalk, "3jx_order"),
        ],
        ignore_index=True,
    )
    disposition_opinions = apply_docket_crosswalk(df, docket_crosswalk, "opinion")
    brief_counsel = load_brief_counsel()
    arguments_in_range = [
        record
        for record in oral_arguments
        if year_range[0] <= pd.to_numeric(record.get("term_year"), errors="coerce") <= year_range[1]
    ]
    resolutions = argument_resolution_summary(arguments_in_range, disposition_orders, disposition_opinions)

    if resolutions.empty:
        st.info("No oral-argument records are available for the selected term range.")
    else:
        resolved_count = int(
            resolutions["resolution"].isin(["case_order", "3jx_order", "opinion", "multiple"]).sum()
        )
        col1, col2, col3 = st.columns(3)
        col1.metric("Recorded Oral Arguments", len(resolutions))
        col2.metric("With a Matching Disposition", resolved_count)
        col3.metric("Without Posted Disposition", len(resolutions) - resolved_count)

        resolution_counts = (
            resolutions["resolution"].value_counts().rename_axis("resolution").reset_index(name="count")
        )
        resolution_counts["label"] = resolution_counts["resolution"].map(RESOLUTION_LABELS)
        fig_resolutions = px.bar(
            resolution_counts,
            x="label",
            y="count",
            color="resolution",
            title="Disposition for Recorded Oral Arguments",
            labels={"label": "Disposition", "count": "Arguments", "resolution": ""},
            color_discrete_map={
                "case_order": "#005A9C",
                "3jx_order": "#4A7C59",
                "opinion": "#7E57C2",
                "multiple": "#E09F3E",
                "needs_review": "#E09F3E",
                "unmatched": "#9E9E9E",
            },
        )
        fig_resolutions.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(fig_resolutions, width="stretch")

        missing_dispositions = manifest_audit[
            manifest_audit["audit_status"].eq("missing_from_local_corpus")
        ].copy()
        gap_dockets = set(missing_dispositions["listed_case_number"])
        pending_dockets = {
            docket
            for value in pending_argument_cases.get("case_number", pd.Series(dtype=str))
            for docket in parse_docket_numbers(value)
        }
        unmatched_assessment = assess_unmatched_arguments(
            resolutions, arguments_in_range, gap_dockets, pending_dockets
        )
        if SHOW_UNMATCHED_ARGUMENT_ASSESSMENT and not unmatched_assessment.empty:
            st.subheader("Why Some Arguments Do Not Yet Have a Verified Match")
            assessment_counts = (
                unmatched_assessment["assessment"].value_counts().rename_axis("assessment").reset_index(name="Arguments")
            )
            assessment_counts["Assessment"] = assessment_counts["assessment"].map(ASSESSMENT_LABELS)
            st.dataframe(
                assessment_counts[["Assessment", "Arguments"]], hide_index=True, width="stretch"
            )
            stale_caption_count = int(
                unmatched_assessment["caption_metadata_status"].eq("transcript_title_needs_roster_backfill").sum()
            )
            if stale_caption_count:
                st.caption(
                    f"{stale_caption_count} rows have a transcript-derived display title that should be "
                    "backfilled from the annual oral-argument roster. This does not affect docket matching."
                )
            with st.expander("Review unmatched-argument assessment"):
                assessment_display = unmatched_assessment.copy()
                assessment_display["assessment"] = assessment_display["assessment"].map(ASSESSMENT_LABELS)
                assessment_display = assessment_display.rename(
                    columns={
                        "case_number": "Docket",
                        "argument_date": "Argument date",
                        "term_year": "Term",
                        "case_name": "Case / extracted caption",
                        "assessment": "Assessment",
                    }
                )
                st.dataframe(assessment_display, hide_index=True, width="stretch")
            if not docket_review_queue.empty:
                with st.expander(f"Docket-file review queue ({len(docket_review_queue)} remaining)", expanded=True):
                    review_display = docket_review_queue.merge(
                        reconciliation[
                            [
                                "case_number",
                                "reconciliation_status",
                                "catalog_disposition_type",
                                "official_pdf_url",
                                "catalog_url",
                            ]
                        ]
                        if not reconciliation.empty
                        else pd.DataFrame(columns=["case_number"]),
                        on="case_number",
                        how="left",
                    ).merge(
                        orphan_pdf_recovery[["case_number", "recovery_status", "candidate_url"]]
                        if not orphan_pdf_recovery.empty
                        else pd.DataFrame(columns=["case_number"]),
                        on="case_number",
                        how="left",
                    )[
                        [
                            "case_number",
                            "argument_date",
                            "case_name",
                            "recovery_status",
                            "candidate_url",
                            "reconciliation_status",
                            "catalog_disposition_type",
                            "official_pdf_url",
                            "catalog_url",
                            "case_status_report_url",
                        ]
                    ].rename(
                        columns={
                            "case_number": "Docket",
                            "argument_date": "Argument date",
                            "case_name": "Case",
                            "recovery_status": "Official-PDF probe",
                            "candidate_url": "Official PDF candidate",
                            "reconciliation_status": "Investigation result",
                            "catalog_disposition_type": "Catalog record type",
                            "official_pdf_url": "Official PDF found",
                            "catalog_url": "Docket research",
                            "case_status_report_url": "Current case-status report",
                        }
                    )
                    st.dataframe(
                        review_display,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "Current case-status report": st.column_config.LinkColumn(
                                "Current case-status report", display_text="Court report ↗"
                            ),
                            "Official PDF found": st.column_config.LinkColumn(
                                "Official PDF found", display_text="Official PDF ↗"
                            ),
                            "Official PDF candidate": st.column_config.LinkColumn(
                                "Official PDF candidate", display_text="Checked URL ↗"
                            ),
                            "Docket research": st.column_config.LinkColumn(
                                "Docket research", display_text="Research record ↗"
                            ),
                        },
                    )
    st.divider()
    st.subheader("Written Dispositions Associated with Arguments or Brief Counsel")
    st.caption(
        "Counts are unique dockets. ‘Published brief counsel’ means the court’s "
        "written decision names lawyers who filed briefs in the case. It does not "
        "indicate whether there was an oral argument."
    )
    source_summary = disposition_source_summary(
        oral_arguments, brief_counsel, disposition_orders, disposition_opinions
    )
    st.dataframe(source_summary, hide_index=True, width="stretch")
    source_chart = source_summary.melt(
        id_vars="Disposition", var_name="Participation", value_name="Dockets"
    )
    fig_sources = px.bar(
        source_chart,
        x="Disposition",
        y="Dockets",
        color="Participation",
        barmode="group",
        title="Published Dispositions Linked by Docket",
        color_discrete_sequence=["#005A9C", "#E09F3E"],
    )
    fig_sources.update_layout(plot_bgcolor="white")
    st.plotly_chart(fig_sources, width="stretch")

# ── Tab 6: Justice Authorship (Phase 4) ────────────────────────────────────────
with tab6:
    render_justice_authorship_analysis(year_range)

# ── Tab 7: 3JX Routing (Phase 4) ────────────────────────────────────────────────
with tab7:
    render_3jx_routing_analysis(year_range)

add_gavel_glimpse_footer()
