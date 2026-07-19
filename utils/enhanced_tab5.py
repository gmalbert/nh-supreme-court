"""
Enhanced Tab 5 content for Phase 2: Advanced filters and timing analysis.
This file contains the enhanced code that would replace the existing tab5 section.
"""

import ast
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.case_resolution import RESOLUTION_LABELS
from utils.data_loader import (
    load_argument_dispositions,
    load_argument_dispositions_metadata,
    load_argument_topics,
)


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out


def _format_label(value: object) -> object:
    """Make stored identifier-style values readable in charts and tables."""
    if pd.isna(value):
        return value
    return str(value).replace("_", " ").title().replace("3Jx", "3JX")


def _resolution_label(value: object) -> object:
    """Return a reader-facing disposition label."""
    if pd.isna(value):
        return value
    return _format_label(RESOLUTION_LABELS.get(value, value))


def _format_date_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Render table dates without time-of-day values."""
    out = frame.copy()
    for column in ("argument_date", "disposition_date"):
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    return out


def render_enhanced_tab5(year_range: tuple[int, int]):
    """Render the enhanced Arguments & Dispositions tab with Phase 2 features."""

    st.subheader("Argument Outcomes Explorer")
    st.caption(
        "Explore how recorded oral arguments resolved through opinions, case orders, and 3JX decisions."
    )

    # Load fact table
    arg_disp = load_argument_dispositions()

    if arg_disp.empty:
        st.info("Argument dispositions fact table not available. Run: `python scripts/build_argument_dispositions.py`")
        return

    # Apply year filter
    arg_disp_filtered = arg_disp[
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") >= year_range[0]) &
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") <= year_range[1])
    ].copy()

    # Advanced filters
    with st.expander("🔍 Advanced Filters", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            disposition_types = ["All"] + sorted(arg_disp_filtered["resolution_type"].dropna().unique().tolist())
            disposition_filter = st.selectbox("Disposition Type", disposition_types)

        with col2:
            case_types = ["All"] + sorted([ct for ct in arg_disp_filtered["case_type"].dropna().unique().tolist() if ct])
            case_type_filter = st.selectbox("Case Type", case_types)

        with col3:
            # Get unique topics for multi-select
            arg_topics_df = load_argument_topics()
            if not arg_topics_df.empty:
                # Join to get topics for filtered arguments
                filtered_arg_ids = set(arg_disp_filtered["argument_id"])
                available_topics = sorted(
                    arg_topics_df[arg_topics_df["argument_id"].isin(filtered_arg_ids)]["topic"].dropna().unique().tolist()
                )
                topic_filter = st.multiselect("Topics (multi-select)", available_topics)
            else:
                topic_filter = []

        col4, col5 = st.columns(2)

        with col4:
            age_buckets = ["All", "0-90 days", "91-180 days", "181-365 days", "365+ days", "Pending/Unmatched"]
            age_filter = st.selectbox("Time to Disposition", age_buckets)

        with col5:
            outcome_options = ["All"] + sorted([o for o in arg_disp_filtered["outcome"].dropna().unique().tolist() if o])
            outcome_filter = st.selectbox("Outcome", outcome_options)

    # Apply advanced filters
    if disposition_filter != "All":
        arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["resolution_type"] == disposition_filter]

    if case_type_filter != "All":
        arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["case_type"] == case_type_filter]

    if topic_filter:
        # Filter to arguments that have at least one of the selected topics
        arg_topics_df = load_argument_topics()
        if not arg_topics_df.empty:
            matching_arg_ids = arg_topics_df[arg_topics_df["topic"].isin(topic_filter)]["argument_id"].unique()
            arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["argument_id"].isin(matching_arg_ids)]

    if outcome_filter != "All":
        arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["outcome"] == outcome_filter]

    if age_filter != "All":
        if age_filter == "0-90 days":
            arg_disp_filtered = arg_disp_filtered[
                (arg_disp_filtered["days_to_disposition"] >= 0) &
                (arg_disp_filtered["days_to_disposition"] <= 90)
            ]
        elif age_filter == "91-180 days":
            arg_disp_filtered = arg_disp_filtered[
                (arg_disp_filtered["days_to_disposition"] > 90) &
                (arg_disp_filtered["days_to_disposition"] <= 180)
            ]
        elif age_filter == "181-365 days":
            arg_disp_filtered = arg_disp_filtered[
                (arg_disp_filtered["days_to_disposition"] > 180) &
                (arg_disp_filtered["days_to_disposition"] <= 365)
            ]
        elif age_filter == "365+ days":
            arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["days_to_disposition"] > 365]
        elif age_filter == "Pending/Unmatched":
            arg_disp_filtered = arg_disp_filtered[arg_disp_filtered["days_to_disposition"].isna()]

    # Funnel metrics
    st.markdown("### Oral Argument → Disposition Funnel")
    resolved = arg_disp_filtered[
        arg_disp_filtered["resolution_type"].isin(["opinion", "case_order", "3jx_order", "multiple"])
    ]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Arguments", f"{len(arg_disp_filtered):,}")
    col2.metric("With Disposition", f"{len(resolved):,}",
               delta=f"{len(resolved)/len(arg_disp_filtered)*100:.1f}%" if len(arg_disp_filtered) > 0 else "0%")
    col3.metric("Pending/Unmatched", f"{len(arg_disp_filtered) - len(resolved):,}")

    if len(resolved) > 0:
        median_days = resolved["days_to_disposition"].median()
        col4.metric("Median Days to Disposition", f"{median_days:.0f}" if pd.notna(median_days) else "—")
    else:
        col4.metric("Median Days to Disposition", "—")

    # Disposition mix charts
    st.markdown("### Disposition Mix")
    col_a, col_b = st.columns(2)

    with col_a:
        resolution_counts = (
            arg_disp_filtered["resolution_type"]
            .value_counts()
            .reset_index()
        )
        resolution_counts.columns = ["resolution_type", "count"]
        resolution_counts["label"] = resolution_counts["resolution_type"].map(_resolution_label)

        fig_res = px.bar(
            resolution_counts,
            x="label",
            y="count",
            color="resolution_type",
            title="Arguments by Disposition Type",
            labels={"label": "Disposition", "count": "Arguments"},
            color_discrete_map={
                "opinion": "#7E57C2",
                "case_order": "#005A9C",
                "3jx_order": "#4A7C59",
                "multiple": "#E09F3E",
                "needs_review": "#FFA726",
                "unmatched": "#9E9E9E",
            },
        )
        fig_res.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(fig_res, width="stretch")

    with col_b:
        # Disposition mix by year
        yearly_mix = (
            arg_disp_filtered.groupby(["term_year", "resolution_type"])
            .size()
            .reset_index(name="count")
        )
        if not yearly_mix.empty:
            yearly_mix["label"] = yearly_mix["resolution_type"].map(_resolution_label)

            fig_yearly = px.bar(
                yearly_mix,
                x="term_year",
                y="count",
                color="label",
                title="Disposition Mix by Year",
                labels={
                    "term_year": "Term Year",
                    "count": "Arguments",
                    "label": "Disposition Type",
                },
                color_discrete_map={
                    _resolution_label("opinion"): "#7E57C2",
                    _resolution_label("case_order"): "#005A9C",
                    _resolution_label("3jx_order"): "#4A7C59",
                    _resolution_label("multiple"): "#E09F3E",
                    _resolution_label("needs_review"): "#FFA726",
                    _resolution_label("unmatched"): "#9E9E9E",
                },
                barmode="stack",
            )
            fig_yearly.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_yearly, width="stretch")

    # Timing analysis (comprehensive)
    st.markdown("### Timing Analysis")

    timing_data = resolved[
        resolved["days_to_disposition"].notna()
        & (resolved["days_to_disposition"] >= 0)
    ].copy()

    if not timing_data.empty:
        # Percentile metrics
        st.markdown("#### Distribution Percentiles")
        percentiles = timing_data["days_to_disposition"].quantile([0.1, 0.25, 0.50, 0.75, 0.90]).to_dict()

        perc_cols = st.columns(5)
        perc_cols[0].metric("10th %ile", f"{percentiles[0.10]:.0f} days")
        perc_cols[1].metric("25th %ile", f"{percentiles[0.25]:.0f} days")
        perc_cols[2].metric("Median (50th)", f"{percentiles[0.50]:.0f} days")
        perc_cols[3].metric("75th %ile", f"{percentiles[0.75]:.0f} days")
        perc_cols[4].metric("90th %ile", f"{percentiles[0.90]:.0f} days")

        # Charts
        col_t1, col_t2 = st.columns(2)

        with col_t1:
            # Distribution histogram
            fig_dist = px.histogram(
                timing_data,
                x="days_to_disposition",
                nbins=30,
                range_x=[0, max(1, timing_data["days_to_disposition"].max())],
                title="Distribution of Days to Disposition",
                labels={"days_to_disposition": "Days", "count": "Arguments"},
                color_discrete_sequence=["#005A9C"],
            )
            fig_dist.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_dist, width="stretch")

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
                labels={"median": "Median Days", "label": "Disposition Type"},
                color_discrete_sequence=["#005A9C"],
                text="count",
            )
            fig_timing_type.update_traces(texttemplate='n=%{text}', textposition='outside')
            fig_timing_type.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
            st.plotly_chart(fig_timing_type, width="stretch")

        # Timing by case type (if available)
        if case_type_filter == "All" and "case_type" in timing_data.columns:
            case_type_timing = timing_data[timing_data["case_type"].notna()].copy()
            if not case_type_timing.empty:
                st.markdown("#### Timing by Case Type")
                ct_timing = (
                    case_type_timing.groupby("case_type")["days_to_disposition"]
                    .agg(["median", "count"])
                    .reset_index()
                    .sort_values("median", ascending=False)
                )
                ct_timing["case_type_label"] = ct_timing["case_type"].map(_format_label)

                fig_ct = px.bar(
                    ct_timing,
                    x="median",
                    y="case_type_label",
                    orientation="h",
                    title="Median Days to Disposition by Case Type",
                    labels={"median": "Median Days", "case_type_label": "Case Type"},
                    color_discrete_sequence=["#7E57C2"],
                    text="count",
                )
                fig_ct.update_traces(texttemplate='n=%{text}', textposition='outside')
                fig_ct.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_ct, width="stretch")

        # Timing by outcome (if available)
        if outcome_filter == "All" and "outcome" in timing_data.columns:
            outcome_timing = timing_data[timing_data["outcome"].notna()].copy()
            if not outcome_timing.empty:
                st.markdown("#### Timing by Outcome")
                out_timing = (
                    outcome_timing.groupby("outcome")["days_to_disposition"]
                    .agg(["median", "count"])
                    .reset_index()
                    .sort_values("median", ascending=False)
                )
                out_timing["outcome_label"] = out_timing["outcome"].map(_format_label)

                fig_out = px.bar(
                    out_timing,
                    x="median",
                    y="outcome_label",
                    orientation="h",
                    title="Median Days to Disposition by Outcome",
                    labels={"median": "Median Days", "outcome_label": "Outcome"},
                    color_discrete_sequence=["#4A7C59"],
                    text="count",
                )
                fig_out.update_traces(texttemplate='n=%{text}', textposition='outside')
                fig_out.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_out, width="stretch")

        # Fastest and slowest
        st.markdown("#### Fastest & Slowest Dispositions")
        st.markdown("**Fastest (10 cases)**")
        fastest = timing_data.nsmallest(10, "days_to_disposition")[
            ["case_name", "case_number", "days_to_disposition", "resolution_type", "argument_date", "disposition_date"]
        ].copy()
        fastest["resolution_type"] = fastest["resolution_type"].map(_resolution_label)
        fastest = _format_date_columns(fastest)
        fastest = _title_columns(fastest)
        st.dataframe(fastest, hide_index=True, width="stretch")

        st.markdown("**Slowest (10 cases)**")
        slowest = timing_data.nlargest(10, "days_to_disposition")[
            ["case_name", "case_number", "days_to_disposition", "resolution_type", "argument_date", "disposition_date"]
        ].copy()
        slowest["resolution_type"] = slowest["resolution_type"].map(_resolution_label)
        slowest = _format_date_columns(slowest)
        slowest = _title_columns(slowest)
        st.dataframe(slowest, hide_index=True, width="stretch")
    else:
        st.info("No timing data available for the selected filters.")

    # Coverage and quality indicators
    st.markdown("### Data Coverage & Quality")

    ccol1, ccol2, ccol3, ccol4 = st.columns(4)

    with ccol1:
        coverage_rate = len(resolved) / len(arg_disp_filtered) * 100 if len(arg_disp_filtered) > 0 else 0
        st.metric("Match Coverage", f"{coverage_rate:.1f}%",
                 help="Percentage of arguments with a matching disposition")

    with ccol2:
        has_transcript = arg_disp_filtered["has_transcript"].sum()
        transcript_rate = has_transcript / len(arg_disp_filtered) * 100 if len(arg_disp_filtered) > 0 else 0
        st.metric("Transcript Availability", f"{transcript_rate:.1f}%",
                 help="Percentage of arguments with transcript text")

    with ccol3:
        combined_count = arg_disp_filtered["is_combined_docket"].sum()
        st.metric("Combined Dockets", f"{combined_count:,}",
                 help="Number of arguments with multiple docket numbers")

    with ccol4:
        if len(timing_data) > 0:
            avg_days = timing_data["days_to_disposition"].mean()
            st.metric("Mean Days", f"{avg_days:.0f}",
                     help="Average days from argument to disposition")
        else:
            st.metric("Mean Days", "—")

    # CSV Export
    st.markdown("### Export Data")

    # Prepare export
    export_df = arg_disp_filtered[[
        "argument_id", "case_name", "argument_date", "term_year",
        "resolution_type", "disposition_date", "days_to_disposition",
        "outcome", "case_type", "author", "is_unanimous", "has_dissent",
        "lower_court", "duration_seconds", "has_transcript"
    ]].copy()

    csv = export_df.to_csv(index=False)

    st.download_button(
        label="📥 Download Filtered Data (CSV)",
        data=csv,
        file_name=f"argument_dispositions_filtered.csv",
        mime="text/csv",
        help="Download the filtered argument dispositions data"
    )

    # Metadata
    metadata = load_argument_dispositions_metadata()
    if metadata:
        with st.expander("📊 Dataset Metadata"):
            st.markdown(f"**Last Updated:** {metadata.get('last_updated', 'Unknown')}")
            st.markdown(f"**Total Records:** {metadata.get('record_count', 0):,}")
            st.markdown(f"**Date Range:** {metadata.get('date_range', {}).get('earliest_argument', 'N/A')} to {metadata.get('date_range', {}).get('latest_argument', 'N/A')}")

            if "resolution_summary" in metadata:
                st.markdown("**Resolution Summary:**")
                for res_type, count in metadata["resolution_summary"].items():
                    st.markdown(f"  - {RESOLUTION_LABELS.get(res_type, res_type)}: {count:,}")
