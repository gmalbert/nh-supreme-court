"""
Topic disposition profile module for Phase 3.
Generates topic-specific disposition outcomes, timing, and attorney/firm specialization.
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


def render_topic_disposition_profile(topic_name: str):
    """
    Render disposition profile section for a legal topic.

    Args:
        topic_name: Name of the legal topic
    """

    st.subheader(f"Disposition Outcomes for {topic_name}")
    st.caption(
        "Oral arguments tagged with this topic, joined to their published dispositions. "
        "Shows how the court has resolved this legal area through opinions, orders, and 3JX decisions."
    )

    # Load data
    arg_disp = load_argument_dispositions()
    arg_participants = load_argument_participants()
    arg_topics = load_argument_topics()

    if arg_disp.empty or arg_topics.empty:
        st.info(
            "Disposition outcomes data not available. "
            "Run: `python scripts/build_argument_dispositions.py`"
        )
        return

    # Filter to topic's arguments
    topic_arg_ids = set(
        arg_topics[arg_topics["topic"] == topic_name]["argument_id"]
    )

    if not topic_arg_ids:
        st.info(f"No oral argument disposition records found for topic: {topic_name}")
        return

    topic_disp = arg_disp[arg_disp["argument_id"].isin(topic_arg_ids)].copy()

    if topic_disp.empty:
        st.info(f"No matched dispositions found for {topic_name} arguments.")
        return

    # Funnel metrics
    st.markdown("### Oral Argument → Disposition Funnel")
    resolved = topic_disp[
        topic_disp["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])
    ]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Arguments", len(topic_disp))
    col2.metric("With Disposition", len(resolved))
    col3.metric("Resolution Rate", f"{len(resolved)/len(topic_disp)*100:.1f}%")

    if len(resolved) > 0:
        median_days = resolved["days_to_disposition"].median()
        col4.metric(
            "Median Days",
            f"{median_days:.0f}" if pd.notna(median_days) else "—"
        )
    else:
        col4.metric("Median Days", "—")

    # Disposition mix
    st.markdown("### Disposition Mix")
    col_a, col_b = st.columns(2)

    with col_a:
        resolution_counts = topic_disp["resolution_type"].value_counts().reset_index()
        resolution_counts.columns = ["resolution_type", "count"]
        resolution_counts["label"] = resolution_counts["resolution_type"].map(RESOLUTION_LABELS)

        fig_res = px.pie(
            resolution_counts,
            names="label",
            values="count",
            title=f"{topic_name} Disposition Types",
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
            topic_disp.groupby(["term_year", "resolution_type"])
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
                title=f"{topic_name} Disposition Trend",
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
    st.markdown("### Timing Profile")

    timing_data = resolved[resolved["days_to_disposition"].notna()].copy()

    if not timing_data.empty:
        # Percentiles
        percentiles = timing_data["days_to_disposition"].quantile([0.25, 0.50, 0.75, 0.90]).to_dict()

        perc_col1, perc_col2, perc_col3, perc_col4 = st.columns(4)
        perc_col1.metric("25th %ile", f"{percentiles[0.25]:.0f} days")
        perc_col2.metric("Median", f"{percentiles[0.50]:.0f} days")
        perc_col3.metric("75th %ile", f"{percentiles[0.75]:.0f} days")
        perc_col4.metric("90th %ile", f"{percentiles[0.90]:.0f} days")

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            # Distribution histogram
            fig_timing = px.histogram(
                timing_data,
                x="days_to_disposition",
                nbins=25,
                title=f"{topic_name} Days to Disposition",
                labels={"days_to_disposition": "Days", "count": "Arguments"},
                color_discrete_sequence=["#005A9C"],
            )
            fig_timing.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_timing, width="stretch")

        with col_t2:
            # Timing by disposition type
            timing_by_type = (
                timing_data.groupby("resolution_type")["days_to_disposition"]
                .agg(["median", "count"])
                .reset_index()
            )
            timing_by_type["label"] = timing_by_type["resolution_type"].map(RESOLUTION_LABELS)
            timing_by_type = timing_by_type.sort_values("median", ascending=False)

            fig_timing_type = px.bar(
                timing_by_type,
                x="median",
                y="label",
                orientation="h",
                title="Median Days by Disposition Type",
                labels={"median": "Median Days", "label": "Disposition"},
                color_discrete_sequence=["#005A9C"],
                text="count",
            )
            fig_timing_type.update_traces(texttemplate='n=%{text}', textposition='outside')
            fig_timing_type.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_timing_type, width="stretch")
    else:
        st.info("No timing data available for this topic.")

    # Case mix
    st.markdown("### Case Type Distribution")

    case_type_dist = topic_disp["case_type"].value_counts().reset_index()
    case_type_dist.columns = ["Case Type", "Count"]
    case_type_dist = case_type_dist[case_type_dist["Case Type"].notna()]

    if not case_type_dist.empty:
        fig_ct = px.bar(
            case_type_dist,
            x="Count",
            y="Case Type",
            orientation="h",
            title=f"{topic_name} Arguments by Case Type",
            color_discrete_sequence=["#7E57C2"],
        )
        fig_ct.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
        st.plotly_chart(fig_ct, width="stretch")
    else:
        st.info("Case type data not available for this topic.")

    # Attorney/firm specialization
    st.markdown("### Attorney & Firm Specialization")

    if not arg_participants.empty:
        # Get attorneys who argued this topic
        topic_participants = arg_participants[
            arg_participants["argument_id"].isin(topic_arg_ids)
        ].copy()

        if not topic_participants.empty:
            tab1, tab2 = st.tabs(["Attorneys", "Firms"])

            with tab1:
                attorney_counts = topic_participants["attorney_name"].value_counts().reset_index()
                attorney_counts.columns = ["Attorney", "Arguments"]
                attorney_counts = attorney_counts.head(15)  # Top 15 attorneys

                fig_attorneys = px.bar(
                    attorney_counts,
                    x="Arguments",
                    y="Attorney",
                    orientation="h",
                    title=f"Top 15 Attorneys Arguing {topic_name}",
                    color_discrete_sequence=["#4A7C59"],
                )
                fig_attorneys.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_attorneys, width="stretch")

                st.dataframe(_title_columns(attorney_counts), hide_index=True, width="stretch")

            with tab2:
                firm_counts = topic_participants["firm"].value_counts().reset_index()
                firm_counts.columns = ["Firm", "Arguments"]
                firm_counts = firm_counts[firm_counts["Firm"].notna()]
                firm_counts = firm_counts.head(15)  # Top 15 firms

                if not firm_counts.empty:
                    fig_firms = px.bar(
                        firm_counts,
                        x="Arguments",
                        y="Firm",
                        orientation="h",
                        title=f"Top 15 Firms Arguing {topic_name}",
                        color_discrete_sequence=["#E09F3E"],
                    )
                    fig_firms.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                    st.plotly_chart(fig_firms, width="stretch")

                    st.dataframe(_title_columns(firm_counts), hide_index=True, width="stretch")
                else:
                    st.info("Firm data not available for this topic.")
        else:
            st.info("Participant data not available for this topic.")
    else:
        st.info("Attorney/firm specialization data not available.")

    # Outcomes (if available)
    st.markdown("### Court Outcomes")

    outcome_data = resolved[resolved["outcome"].notna()].copy()

    if not outcome_data.empty:
        st.markdown(
            f"**{len(outcome_data)} of {len(resolved)} resolved matters** have a recorded outcome."
        )

        outcome_dist = outcome_data["outcome"].value_counts().reset_index()
        outcome_dist.columns = ["Outcome", "Count"]

        col_o1, col_o2 = st.columns(2)

        with col_o1:
            fig_outcome = px.pie(
                outcome_dist,
                names="Outcome",
                values="Count",
                title=f"{topic_name} Outcomes",
                color_discrete_sequence=px.colors.sequential.Blues_r,
                hole=0.3,
            )
            fig_outcome.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_outcome, width="stretch")

        with col_o2:
            st.dataframe(_title_columns(outcome_dist), hide_index=True, width="stretch")
    else:
        st.info("Outcome data not available for this topic's resolved matters.")

    # Export data
    st.markdown("### Export Topic Disposition Data")

    export_df = topic_disp[[
        "argument_id", "case_name", "argument_date", "term_year",
        "resolution_type", "disposition_date", "days_to_disposition",
        "outcome", "case_type", "lower_court", "author"
    ]].copy()

    csv = export_df.to_csv(index=False)

    st.download_button(
        label=f"📥 Download {topic_name} Disposition Data (CSV)",
        data=csv,
        file_name=f"topic_{topic_name.replace(' ', '_').replace('/', '-')}_dispositions.csv",
        mime="text/csv",
        help="Download disposition data for arguments tagged with this topic"
    )
