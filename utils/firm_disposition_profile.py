"""
Firm disposition profile module for Phase 3.
Generates disposition outcomes, case mix, timing, and roster analysis for law firms.
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


def render_firm_disposition_profile(firm_name: str, min_cohort_size: int = 10):
    """
    Render disposition profile section for a law firm.

    Args:
        firm_name: Name of the law firm
        min_cohort_size: Minimum number of cases for comparative analysis
    """

    st.subheader("Firm Disposition Outcomes Profile")
    st.caption(
        "Oral argument dispositions matched to published opinions, case orders, and 3JX decisions. "
        "This shows observable court outcomes for the firm's matters, not firm effectiveness."
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

    # Filter to firm's arguments
    firm_arg_ids = set(
        arg_participants[arg_participants["firm"] == firm_name]["argument_id"]
    )

    if not firm_arg_ids:
        st.info(f"No oral argument disposition records found for {firm_name}.")
        return

    firm_disp = arg_disp[arg_disp["argument_id"].isin(firm_arg_ids)].copy()

    if firm_disp.empty:
        st.info(f"No matched dispositions found for {firm_name}'s arguments.")
        return

    # Get firm's attorneys
    firm_attorneys = arg_participants[
        arg_participants["firm"] == firm_name
    ]["attorney_name"].unique()

    # Metrics row
    resolved = firm_disp[
        firm_disp["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])
    ]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Firm Attorneys", len(firm_attorneys))
    col2.metric("Total Arguments", len(firm_disp))
    col3.metric("With Disposition", len(resolved))
    col4.metric("Match Rate", f"{len(resolved)/len(firm_disp)*100:.1f}%")

    if len(resolved) > 0:
        median_days = resolved["days_to_disposition"].median()
        col5.metric(
            "Median Days",
            f"{median_days:.0f}" if pd.notna(median_days) else "—"
        )
    else:
        col5.metric("Median Days", "—")

    # Attorney roster
    st.markdown("#### Firm Attorney Roster")

    # Build roster table
    roster_data = []
    for attorney in sorted(firm_attorneys):
        attorney_arg_ids = set(
            arg_participants[
                (arg_participants["firm"] == firm_name) &
                (arg_participants["attorney_name"] == attorney)
            ]["argument_id"]
        )
        attorney_count = len(attorney_arg_ids)
        roster_data.append({
            "Attorney": attorney,
            "Arguments": attorney_count,
            "% of Firm": f"{attorney_count / len(firm_disp) * 100:.1f}%"
        })

    roster_df = pd.DataFrame(roster_data).sort_values("Arguments", ascending=False)

    st.dataframe(
        _title_columns(roster_df),
        hide_index=True,
        width="stretch",
        column_config={
            "Attorney": st.column_config.LinkColumn(
                "Attorney",
                display_text=roster_df["Attorney"],
                help="Click to view attorney profile"
            )
        }
    )

    # Disposition mix
    st.markdown("#### Disposition Mix")
    col_a, col_b = st.columns(2)

    with col_a:
        resolution_counts = firm_disp["resolution_type"].value_counts().reset_index()
        resolution_counts.columns = ["resolution_type", "count"]
        resolution_counts["label"] = resolution_counts["resolution_type"].map(RESOLUTION_LABELS)

        fig_res = px.pie(
            resolution_counts,
            names="label",
            values="count",
            title=f"{firm_name} Disposition Types",
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
        # Disposition mix by year
        yearly_mix = (
            firm_disp.groupby(["term_year", "resolution_type"])
            .size()
            .reset_index(name="count")
        )
        if not yearly_mix.empty:
            yearly_mix["label"] = yearly_mix["resolution_type"].map(RESOLUTION_LABELS)

            fig_yearly = px.bar(
                yearly_mix,
                x="term_year",
                y="count",
                color="resolution_type",
                title=f"{firm_name} Disposition Mix by Year",
                labels={"term_year": "Year", "count": "Arguments"},
                color_discrete_map={
                    "opinion": "#7E57C2",
                    "case_order": "#005A9C",
                    "3jx_order": "#4A7C59",
                    "multiple": "#E09F3E",
                    "needs_review": "#FFA726",
                    "unmatched": "#9E9E9E",
                },
                barmode="stack",
            )
            fig_yearly.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_yearly, width="stretch")

    # Timing analysis
    st.markdown("#### Timing Analysis")

    timing_data = resolved[resolved["days_to_disposition"].notna()].copy()

    if not timing_data.empty:
        # Percentiles
        percentiles = timing_data["days_to_disposition"].quantile([0.25, 0.50, 0.75]).to_dict()

        perc_col1, perc_col2, perc_col3 = st.columns(3)
        perc_col1.metric("25th Percentile", f"{percentiles[0.25]:.0f} days")
        perc_col2.metric("Median", f"{percentiles[0.50]:.0f} days")
        perc_col3.metric("75th Percentile", f"{percentiles[0.75]:.0f} days")

        # Histogram
        fig_timing = px.histogram(
            timing_data,
            x="days_to_disposition",
            nbins=25,
            title=f"{firm_name} Days to Disposition Distribution",
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
        case_type_dist = firm_disp["case_type"].value_counts().reset_index()
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
        firm_topics = arg_topics[arg_topics["argument_id"].isin(firm_arg_ids)].copy()
        if not firm_topics.empty:
            topic_dist = firm_topics["topic"].value_counts().reset_index()
            topic_dist.columns = ["Topic", "Arguments"]
            topic_dist = topic_dist.head(20)  # Top 20 topics for firm

            fig_topics = px.bar(
                topic_dist,
                x="Arguments",
                y="Topic",
                orientation="h",
                title="Top 20 Topics (arguments may have multiple topics)",
                color_discrete_sequence=["#4A7C59"],
            )
            fig_topics.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_topics, width="stretch")

            st.dataframe(_title_columns(topic_dist), hide_index=True, width="stretch")
        else:
            st.info("Topic data not available.")

    with tab3:
        lower_court_dist = firm_disp["lower_court"].value_counts().reset_index()
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
                "This represents the court's disposition, not a firm performance metric."
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
            st.info("Outcome data not available for this firm's resolved matters.")

    # Export data
    st.markdown("#### Export Firm Disposition Data")

    export_df = firm_disp[[
        "argument_id", "case_name", "argument_date", "term_year",
        "resolution_type", "disposition_date", "days_to_disposition",
        "outcome", "case_type", "lower_court", "author"
    ]].copy()

    csv = export_df.to_csv(index=False)

    st.download_button(
        label=f"📥 Download {firm_name} Disposition Data (CSV)",
        data=csv,
        file_name=f"firm_{firm_name.replace(' ', '_')}_dispositions.csv",
        mime="text/csv",
        help="Download this firm's argument dispositions with case details"
    )
