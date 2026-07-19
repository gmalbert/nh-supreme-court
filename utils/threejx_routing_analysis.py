"""
3JX routing analysis module for Phase 4.
Analyzes how cases route to 3-justice panels vs full court opinions.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.case_resolution import RESOLUTION_LABELS
from utils.data_loader import load_argument_dispositions, load_argument_topics


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert dataframe columns to title case."""
    out = frame.copy()
    out.columns = [_format_label(c) for c in out.columns]
    return out


def _format_label(value: object) -> object:
    """Make stored identifier-style values readable in charts and tables."""
    if pd.isna(value):
        return value
    return str(value).replace("_", " ").title().replace("3Jx", "3JX")


def _resolution_label(value: object) -> object:
    """Use the canonical display text for disposition routing categories."""
    if pd.isna(value):
        return value
    return _format_label(RESOLUTION_LABELS.get(value, value))


def render_3jx_routing_analysis(year_range: tuple[int, int]):
    """
    Render 3JX routing and workload analysis.

    Args:
        year_range: Tuple of (min_year, max_year) for filtering
    """

    st.subheader("3JX Panel Routing Analysis")
    st.caption(
        "Analyzes how cases route to 3-justice panels versus full court signed opinions. "
        "3JX orders are procedural dispositions issued by a 3-justice subset, often for "
        "summary affirmances or dismissals."
    )

    # Load data
    arg_disp = load_argument_dispositions()

    if arg_disp.empty:
        st.info(
            "Argument dispositions data not available. "
            "Run: `python scripts/build_argument_dispositions.py`"
        )
        return

    # Filter to year range
    filtered = arg_disp[
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") >= year_range[0]) &
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") <= year_range[1])
    ].copy()

    if filtered.empty:
        st.info("No data available for the selected year range.")
        return

    # Calculate 3JX vs opinion split
    opinion_count = (filtered["resolution_type"] == "opinion").sum()
    case_order_count = (filtered["resolution_type"] == "case_order").sum()
    tjx_count = (filtered["resolution_type"] == "3jx_order").sum()
    multiple_count = (filtered["resolution_type"] == "multiple").sum()

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Signed Opinions", f"{opinion_count:,}")
    col2.metric("Case Orders", f"{case_order_count:,}")
    col3.metric("3JX Orders", f"{tjx_count:,}")
    col4.metric("Multiple Dispositions", f"{multiple_count:,}")

    # Routing mix
    st.markdown("### Disposition Routing Mix")

    routing_counts = filtered["resolution_type"].value_counts().reset_index()
    routing_counts.columns = ["resolution_type", "count"]
    routing_counts["label"] = routing_counts["resolution_type"].map(_resolution_label)

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        fig_routing = px.pie(
            routing_counts,
            names="label",
            values="count",
            title="Disposition Type Distribution",
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
        fig_routing.update_layout(plot_bgcolor="white")
        st.plotly_chart(fig_routing, width="stretch")

    with col_r2:
        # Routing by year
        routing_year = (
            filtered.groupby(["term_year", "resolution_type"])
            .size()
            .reset_index(name="count")
        )
        routing_year["label"] = routing_year["resolution_type"].map(_resolution_label)

        fig_routing_year = px.bar(
            routing_year,
            x="term_year",
            y="count",
            color="label",
            title="Disposition Routing Trend by Year",
            labels={
                "term_year": "Year",
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
        fig_routing_year.update_layout(plot_bgcolor="white")
        st.plotly_chart(fig_routing_year, width="stretch")

    # 3JX-specific analysis
    st.markdown("### 3JX Panel Workload Analysis")

    tjx_cases = filtered[filtered["resolution_type"] == "3jx_order"].copy()

    if not tjx_cases.empty:
        tab1, tab2, tab3, tab4 = st.tabs(["Case Types", "Lower Courts", "Topics", "Timing"])

        with tab1:
            # 3JX by case type
            tjx_case_types = tjx_cases["case_type"].value_counts().reset_index()
            tjx_case_types.columns = ["Case Type", "3JX Orders"]
            tjx_case_types = tjx_case_types[tjx_case_types["Case Type"].notna()]
            tjx_case_types["Case Type"] = tjx_case_types["Case Type"].map(_format_label)

            if not tjx_case_types.empty:
                # Add percentage
                tjx_case_types["% of 3JX"] = (
                    tjx_case_types["3JX Orders"] / tjx_case_types["3JX Orders"].sum() * 100
                )

                fig_tjx_ct = px.bar(
                    tjx_case_types,
                    x="3JX Orders",
                    y="Case Type",
                    orientation="h",
                    title="3JX Orders by Case Type",
                    color_discrete_sequence=["#4A7C59"],
                    text="3JX Orders",
                )
                fig_tjx_ct.update_traces(texttemplate='%{text}', textposition='outside')
                fig_tjx_ct.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_tjx_ct, width="stretch")

                st.dataframe(_title_columns(tjx_case_types), hide_index=True, width="stretch")
            else:
                st.info("No case type data available for 3JX orders.")

        with tab2:
            # 3JX by lower court
            tjx_lower_courts = tjx_cases["lower_court"].value_counts().reset_index()
            tjx_lower_courts.columns = ["Lower Court", "3JX Orders"]
            tjx_lower_courts = tjx_lower_courts[tjx_lower_courts["Lower Court"].notna()]
            tjx_lower_courts["Lower Court"] = tjx_lower_courts["Lower Court"].map(_format_label)

            if not tjx_lower_courts.empty:
                tjx_lower_courts["% of 3JX"] = (
                    tjx_lower_courts["3JX Orders"] / tjx_lower_courts["3JX Orders"].sum() * 100
                )

                fig_tjx_lc = px.bar(
                    tjx_lower_courts,
                    x="3JX Orders",
                    y="Lower Court",
                    orientation="h",
                    title="3JX Orders by Lower Court",
                    color_discrete_sequence=["#E09F3E"],
                    text="3JX Orders",
                )
                fig_tjx_lc.update_traces(texttemplate='%{text}', textposition='outside')
                fig_tjx_lc.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_tjx_lc, width="stretch")

                st.dataframe(_title_columns(tjx_lower_courts), hide_index=True, width="stretch")
            else:
                st.info("No lower court data available for 3JX orders.")

        with tab3:
            # 3JX by topic
            arg_topics = load_argument_topics()
            if not arg_topics.empty:
                tjx_arg_ids = set(tjx_cases["argument_id"])
                tjx_topics = arg_topics[arg_topics["argument_id"].isin(tjx_arg_ids)].copy()

                if not tjx_topics.empty:
                    topic_counts = tjx_topics["topic"].value_counts().reset_index()
                    topic_counts.columns = ["Topic", "3JX Orders"]
                    topic_counts = topic_counts.head(15)  # Top 15
                    topic_counts["Topic"] = topic_counts["Topic"].map(_format_label)

                    fig_tjx_topic = px.bar(
                        topic_counts,
                        x="3JX Orders",
                        y="Topic",
                        orientation="h",
                        title="Top 15 Topics in 3JX Orders",
                        color_discrete_sequence=["#005A9C"],
                    )
                    fig_tjx_topic.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                    st.plotly_chart(fig_tjx_topic, width="stretch")

                    st.dataframe(_title_columns(topic_counts), hide_index=True, width="stretch")
                else:
                    st.info("No topic data available for 3JX orders.")
            else:
                st.info("Topic bridge table not available.")

        with tab4:
            # 3JX timing analysis
            tjx_timing = tjx_cases[tjx_cases["days_to_disposition"].notna()].copy()

            if not tjx_timing.empty:
                # Percentiles
                percentiles = tjx_timing["days_to_disposition"].quantile([0.25, 0.50, 0.75, 0.90]).to_dict()

                perc_col1, perc_col2, perc_col3, perc_col4 = st.columns(4)
                perc_col1.metric("25th %ile", f"{percentiles[0.25]:.0f} days")
                perc_col2.metric("Median", f"{percentiles[0.50]:.0f} days")
                perc_col3.metric("75th %ile", f"{percentiles[0.75]:.0f} days")
                perc_col4.metric("90th %ile", f"{percentiles[0.90]:.0f} days")

                col_t1, col_t2 = st.columns(2)

                with col_t1:
                    # Distribution
                    fig_tjx_timing = px.histogram(
                        tjx_timing,
                        x="days_to_disposition",
                        nbins=20,
                        title="3JX Days to Disposition Distribution",
                        labels={"days_to_disposition": "Days", "count": "Orders"},
                        color_discrete_sequence=["#4A7C59"],
                    )
                    fig_tjx_timing.update_layout(plot_bgcolor="white")
                    fig_tjx_timing.update_xaxes(
                        range=[0, max(1, tjx_timing["days_to_disposition"].max())]
                    )
                    st.plotly_chart(fig_tjx_timing, width="stretch")

                with col_t2:
                    # Comparison: 3JX vs Opinion timing
                    opinion_timing = filtered[
                        (filtered["resolution_type"] == "opinion") &
                        (filtered["days_to_disposition"].notna())
                    ].copy()

                    if not opinion_timing.empty:
                        comparison_df = pd.DataFrame([
                            {
                                "Disposition Type": "3JX Order",
                                "Median Days": tjx_timing["days_to_disposition"].median(),
                                "n": len(tjx_timing)
                            },
                            {
                                "Disposition Type": "Signed Opinion",
                                "Median Days": opinion_timing["days_to_disposition"].median(),
                                "n": len(opinion_timing)
                            }
                        ])

                        fig_comparison = px.bar(
                            comparison_df,
                            x="Median Days",
                            y="Disposition Type",
                            orientation="h",
                            title="3JX vs Opinion: Median Days",
                            color="Disposition Type",
                            color_discrete_map={
                                "3JX Order": "#4A7C59",
                                "Signed Opinion": "#7E57C2"
                            },
                            text="n",
                        )
                        fig_comparison.update_traces(texttemplate='n=%{text}', textposition='outside')
                        fig_comparison.update_layout(plot_bgcolor="white", showlegend=False)
                        st.plotly_chart(fig_comparison, width="stretch")

                        st.dataframe(_title_columns(comparison_df), hide_index=True, width="stretch")
                    else:
                        st.info("No opinion timing data available for comparison.")
            else:
                st.info("No timing data available for 3JX orders.")
    else:
        st.info("No 3JX order data available for the selected year range.")

    # Routing patterns: which case types/lower courts → 3JX vs opinion?
    st.markdown("### Routing Patterns: 3JX vs Opinion")

    # Filter to opinions and 3JX only for comparison
    routing_comparison = filtered[
        filtered["resolution_type"].isin(["opinion", "3jx_order"])
    ].copy()

    if not routing_comparison.empty:
        tab_r1, tab_r2 = st.tabs(["By Case Type", "By Lower Court"])

        with tab_r1:
            if "case_type" in routing_comparison.columns:
                ct_routing = (
                    routing_comparison[routing_comparison["case_type"].notna()]
                    .groupby(["case_type", "resolution_type"])
                    .size()
                    .reset_index(name="count")
                )

                if not ct_routing.empty:
                    ct_routing["case_type_label"] = ct_routing["case_type"].map(_format_label)
                    ct_routing["resolution_label"] = ct_routing["resolution_type"].map(_resolution_label)
                    # Calculate percentages
                    ct_totals = ct_routing.groupby("case_type")["count"].sum().reset_index()
                    ct_totals.columns = ["case_type", "total"]
                    ct_routing = ct_routing.merge(ct_totals, on="case_type")
                    ct_routing["percentage"] = ct_routing["count"] / ct_routing["total"] * 100

                    fig_ct_routing = px.bar(
                        ct_routing,
                        x="case_type_label",
                        y="count",
                        color="resolution_label",
                        title="Case Type Routing: 3JX vs Opinion",
                        labels={"case_type_label": "Case Type", "count": "Arguments"},
                        color_discrete_map={
                            _resolution_label("opinion"): "#7E57C2",
                            _resolution_label("3jx_order"): "#4A7C59"
                        },
                        barmode="group",
                    )
                    fig_ct_routing.update_layout(plot_bgcolor="white")
                    st.plotly_chart(fig_ct_routing, width="stretch")

                    # Pivot table
                    ct_pivot = ct_routing.pivot(
                        index="case_type",
                        columns="resolution_type",
                        values="count"
                    ).fillna(0).astype(int)

                    if "opinion" in ct_pivot.columns and "3jx_order" in ct_pivot.columns:
                        ct_pivot["3JX Rate %"] = (
                            ct_pivot["3jx_order"] / (ct_pivot["opinion"] + ct_pivot["3jx_order"]) * 100
                        ).round(1)

                    ct_pivot.index = ct_pivot.index.map(_format_label)

                    st.dataframe(_title_columns(ct_pivot.reset_index()), hide_index=True, width="stretch")
                else:
                    st.info("No case type routing data available.")
            else:
                st.info("Case type field not available.")

        with tab_r2:
            if "lower_court" in routing_comparison.columns:
                lc_routing = (
                    routing_comparison[routing_comparison["lower_court"].notna()]
                    .groupby(["lower_court", "resolution_type"])
                    .size()
                    .reset_index(name="count")
                )

                if not lc_routing.empty:
                    lc_routing["lower_court_label"] = lc_routing["lower_court"].map(_format_label)
                    lc_routing["resolution_label"] = lc_routing["resolution_type"].map(_resolution_label)
                    # Calculate percentages
                    lc_totals = lc_routing.groupby("lower_court")["count"].sum().reset_index()
                    lc_totals.columns = ["lower_court", "total"]
                    lc_routing = lc_routing.merge(lc_totals, on="lower_court")
                    lc_routing["percentage"] = lc_routing["count"] / lc_routing["total"] * 100

                    fig_lc_routing = px.bar(
                        lc_routing,
                        x="lower_court_label",
                        y="count",
                        color="resolution_label",
                        title="Lower Court Routing: 3JX vs Opinion",
                        labels={"lower_court_label": "Lower Court", "count": "Arguments"},
                        color_discrete_map={
                            _resolution_label("opinion"): "#7E57C2",
                            _resolution_label("3jx_order"): "#4A7C59"
                        },
                        barmode="group",
                    )
                    fig_lc_routing.update_layout(plot_bgcolor="white")
                    st.plotly_chart(fig_lc_routing, width="stretch")

                    # Pivot table
                    lc_pivot = lc_routing.pivot(
                        index="lower_court",
                        columns="resolution_type",
                        values="count"
                    ).fillna(0).astype(int)

                    if "opinion" in lc_pivot.columns and "3jx_order" in lc_pivot.columns:
                        lc_pivot["3JX Rate %"] = (
                            lc_pivot["3jx_order"] / (lc_pivot["opinion"] + lc_pivot["3jx_order"]) * 100
                        ).round(1)

                    lc_pivot.index = lc_pivot.index.map(_format_label)

                    st.dataframe(_title_columns(lc_pivot.reset_index()), hide_index=True, width="stretch")
                else:
                    st.info("No lower court routing data available.")
            else:
                st.info("Lower court field not available.")

    # Export
    st.markdown("### Export 3JX Routing Data")

    export_df = filtered[[
        "argument_id", "case_name", "argument_date", "term_year",
        "resolution_type", "disposition_date", "days_to_disposition",
        "case_type", "lower_court", "outcome"
    ]].copy()

    csv = export_df.to_csv(index=False)

    st.download_button(
        label="📥 Download Disposition Routing Data (CSV)",
        data=csv,
        file_name=f"3jx_routing_{year_range[0]}_{year_range[1]}.csv",
        mime="text/csv",
        help="Download routing data for 3JX vs opinion analysis"
    )
