"""
Attorney disposition profile module for Phase 3.
Generates disposition outcomes, case mix, timing, and comparative analysis for attorneys.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.case_resolution import RESOLUTION_LABELS
from utils.data_loader import (
    load_argument_dispositions,
    load_argument_participants,
    load_argument_topics,
)


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert dataframe columns to title case."""
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out


def render_attorney_disposition_profile(attorney_name: str, min_cohort_size: int = 10):
    """
    Render disposition profile section for an attorney.

    Args:
        attorney_name: Full name of the attorney
        min_cohort_size: Minimum number of cases for comparative analysis
    """

    st.subheader("Disposition Outcomes Profile")
    st.caption(
        "Oral argument dispositions matched to published opinions, case orders, and 3JX decisions. "
        "This shows observable court outcomes, not advocate effectiveness."
    )

    # Load data
    arg_disp = load_argument_dispositions()
    arg_participants = load_argument_participants()
    arg_topics = load_argument_topics()

    if arg_disp.empty or arg_participants.empty:
        st.info(
            "Disposition outcomes data not available. "
            "Run: `python scripts/build_argument_dispositions.py`"
        )
        return

    # Filter to attorney's arguments
    attorney_arg_ids = set(
        arg_participants[arg_participants["attorney_name"] == attorney_name]["argument_id"]
    )

    if not attorney_arg_ids:
        st.info(f"No oral argument disposition records found for {attorney_name}.")
        return

    attorney_disp = arg_disp[arg_disp["argument_id"].isin(attorney_arg_ids)].copy()

    if attorney_disp.empty:
        st.info(f"No matched dispositions found for {attorney_name}'s arguments.")
        return

    # Get attorney's participation details (side, role)
    attorney_parts = arg_participants[
        arg_participants["attorney_name"] == attorney_name
    ].copy()

    # Metrics row
    resolved = attorney_disp[
        attorney_disp["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])
    ]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Arguments", len(attorney_disp))
    col2.metric("With Disposition", len(resolved))
    col3.metric("Match Rate", f"{len(resolved)/len(attorney_disp)*100:.1f}%")

    if len(resolved) > 0:
        median_days = resolved["days_to_disposition"].median()
        col4.metric(
            "Median Days",
            f"{median_days:.0f}" if pd.notna(median_days) else "—"
        )
    else:
        col4.metric("Median Days", "—")

    # Disposition mix
    st.markdown("#### Disposition Mix")
    col_a, col_b = st.columns(2)

    with col_a:
        resolution_counts = attorney_disp["resolution_type"].value_counts().reset_index()
        resolution_counts.columns = ["resolution_type", "count"]
        resolution_counts["label"] = resolution_counts["resolution_type"].map(RESOLUTION_LABELS)

        fig_res = px.pie(
            resolution_counts,
            names="label",
            values="count",
            title=f"{attorney_name} Disposition Types",
            color="resolution_type",
            color_discrete_map={
                "opinion": "#7E57C2",
                "case_order": "#005A9C",
                "3jx_order": "#4A7C59",
                "multiple": "#E09F3E",
                "needs_review": "#FFA726",
                "unmatched": "#9E9E9E",
            },
            hole=0.3,
        )
        fig_res.update_layout(plot_bgcolor="white", showlegend=True)
        st.plotly_chart(fig_res, width="stretch")

    with col_b:
        # Timing distribution
        timing_data = resolved[resolved["days_to_disposition"].notna()].copy()
        if not timing_data.empty:
            fig_timing = px.histogram(
                timing_data,
                x="days_to_disposition",
                nbins=20,
                title=f"{attorney_name} Days to Disposition",
                labels={"days_to_disposition": "Days", "count": "Arguments"},
                color_discrete_sequence=["#005A9C"],
            )
            fig_timing.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_timing, width="stretch")
        else:
            st.info("No timing data available.")

    # Case mix profile
    st.markdown("#### Case Mix Profile")

    tab1, tab2, tab3, tab4 = st.tabs(["Case Types", "Topics", "Lower Courts", "Outcomes"])

    with tab1:
        case_type_dist = attorney_disp["case_type"].value_counts().reset_index()
        case_type_dist.columns = ["Case Type", "Count"]
        case_type_dist = case_type_dist[case_type_dist["Case Type"].notna()]

        if not case_type_dist.empty:
            fig_ct = px.bar(
                case_type_dist,
                x="Count",
                y="Case Type",
                orientation="h",
                title="Arguments by Case Type",
                color_discrete_sequence=["#7E57C2"],
            )
            fig_ct.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_ct, width="stretch")

            st.dataframe(_title_columns(case_type_dist), hide_index=True, width="stretch")
        else:
            st.info("Case type data not available.")

    with tab2:
        # Join to topics
        attorney_topics = arg_topics[arg_topics["argument_id"].isin(attorney_arg_ids)].copy()
        if not attorney_topics.empty:
            topic_dist = attorney_topics["topic"].value_counts().reset_index()
            topic_dist.columns = ["Topic", "Arguments"]
            topic_dist = topic_dist.head(15)  # Top 15 topics

            fig_topics = px.bar(
                topic_dist,
                x="Arguments",
                y="Topic",
                orientation="h",
                title="Top 15 Topics (arguments may have multiple topics)",
                color_discrete_sequence=["#4A7C59"],
            )
            fig_topics.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_topics, width="stretch")

            st.dataframe(_title_columns(topic_dist), hide_index=True, width="stretch")
        else:
            st.info("Topic data not available.")

    with tab3:
        lower_court_dist = attorney_disp["lower_court"].value_counts().reset_index()
        lower_court_dist.columns = ["Lower Court", "Count"]
        lower_court_dist = lower_court_dist[lower_court_dist["Lower Court"].notna()]

        if not lower_court_dist.empty:
            fig_lc = px.bar(
                lower_court_dist,
                x="Count",
                y="Lower Court",
                orientation="h",
                title="Arguments by Lower Court",
                color_discrete_sequence=["#E09F3E"],
            )
            fig_lc.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_lc, width="stretch")

            st.dataframe(_title_columns(lower_court_dist), hide_index=True, width="stretch")
        else:
            st.info("Lower court data not available.")

    with tab4:
        # Outcome analysis (conservative - only where verified)
        outcome_data = resolved[resolved["outcome"].notna()].copy()

        if not outcome_data.empty:
            st.markdown(
                f"**{len(outcome_data)} of {len(resolved)} resolved matters** have a recorded outcome. "
                "This represents the court's disposition, not a win/loss record."
            )

            outcome_dist = outcome_data["outcome"].value_counts().reset_index()
            outcome_dist.columns = ["Outcome", "Count"]

            fig_outcome = px.bar(
                outcome_dist,
                x="Count",
                y="Outcome",
                orientation="h",
                title="Court Outcomes (where available)",
                color_discrete_sequence=["#005A9C"],
            )
            fig_outcome.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_outcome, width="stretch")

            st.dataframe(_title_columns(outcome_dist), hide_index=True, width="stretch")
        else:
            st.info("Outcome data not available for this attorney's resolved matters.")

    # Comparable cohort analysis
    st.markdown("#### Comparable Cohort Comparison")

    # Define cohort filter
    cohort_filter = st.selectbox(
        "Compare against:",
        [
            "All attorneys (all case types)",
            "Attorneys in same primary case type",
            "Attorneys in same time period",
        ],
        help="Select a comparison group to contextualize this attorney's disposition profile"
    )

    # Build cohort
    if cohort_filter == "All attorneys (all case types)":
        cohort = arg_disp.copy()
        cohort_desc = "all attorneys and case types"
    elif cohort_filter == "Attorneys in same primary case type":
        # Find attorney's primary case type
        primary_case_type = attorney_disp["case_type"].mode()[0] if not attorney_disp["case_type"].mode().empty else None
        if primary_case_type:
            cohort = arg_disp[arg_disp["case_type"] == primary_case_type].copy()
            cohort_desc = f"attorneys in {primary_case_type} cases"
        else:
            cohort = arg_disp.copy()
            cohort_desc = "all attorneys (no primary case type identified)"
    else:  # Same time period
        min_year = attorney_disp["term_year"].min()
        max_year = attorney_disp["term_year"].max()
        cohort = arg_disp[
            (arg_disp["term_year"] >= min_year) & (arg_disp["term_year"] <= max_year)
        ].copy()
        cohort_desc = f"attorneys active {min_year}-{max_year}"

    # Calculate cohort metrics
    cohort_resolved = cohort[
        cohort["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])
    ]

    if len(cohort) >= min_cohort_size:
        st.markdown(f"**Comparison group:** {cohort_desc} ({len(cohort):,} total arguments)")

        comp_col1, comp_col2, comp_col3 = st.columns(3)

        # Match rate comparison
        attorney_match_rate = len(resolved) / len(attorney_disp) * 100 if len(attorney_disp) > 0 else 0
        cohort_match_rate = len(cohort_resolved) / len(cohort) * 100 if len(cohort) > 0 else 0

        comp_col1.metric(
            "Match Rate",
            f"{attorney_match_rate:.1f}%",
            delta=f"{attorney_match_rate - cohort_match_rate:+.1f}% vs cohort",
            help=f"Cohort average: {cohort_match_rate:.1f}%"
        )

        # Median days comparison
        if len(resolved) > 0 and len(cohort_resolved) > 0:
            attorney_median = resolved["days_to_disposition"].median()
            cohort_median = cohort_resolved["days_to_disposition"].median()

            if pd.notna(attorney_median) and pd.notna(cohort_median):
                comp_col2.metric(
                    "Median Days",
                    f"{attorney_median:.0f}",
                    delta=f"{attorney_median - cohort_median:+.0f} days vs cohort",
                    help=f"Cohort median: {cohort_median:.0f} days"
                )

        # Opinion rate comparison
        attorney_opinion_rate = (
            (attorney_disp["resolution_type"] == "opinion").sum() / len(attorney_disp) * 100
            if len(attorney_disp) > 0 else 0
        )
        cohort_opinion_rate = (
            (cohort["resolution_type"] == "opinion").sum() / len(cohort) * 100
            if len(cohort) > 0 else 0
        )

        comp_col3.metric(
            "Opinion Rate",
            f"{attorney_opinion_rate:.1f}%",
            delta=f"{attorney_opinion_rate - cohort_opinion_rate:+.1f}% vs cohort",
            help=f"Cohort average: {cohort_opinion_rate:.1f}%"
        )

        st.caption(
            "⚠️ These comparisons are descriptive only. Differences may reflect case mix, "
            "selection effects, time period, or random variation—not attorney quality."
        )
    else:
        st.info(f"Cohort too small for comparison (n={len(cohort)}, minimum: {min_cohort_size}).")

    # Export data
    st.markdown("#### Export Attorney Disposition Data")

    export_df = attorney_disp[[
        "argument_id", "case_name", "argument_date", "term_year",
        "resolution_type", "disposition_date", "days_to_disposition",
        "outcome", "case_type", "lower_court", "author"
    ]].copy()

    # Add attorney-specific fields from participants
    export_parts = attorney_parts[[
        "argument_id", "side", "role", "firm", "source"
    ]].copy()
    export_parts.columns = ["argument_id", "attorney_side", "attorney_role", "attorney_firm", "roster_source"]

    export_df = export_df.merge(export_parts, on="argument_id", how="left")

    csv = export_df.to_csv(index=False)

    st.download_button(
        label=f"📥 Download {attorney_name} Disposition Data (CSV)",
        data=csv,
        file_name=f"attorney_{attorney_name.replace(' ', '_')}_dispositions.csv",
        mime="text/csv",
        help="Download this attorney's argument dispositions with case details"
    )
