"""
Justice authorship and voting patterns module for Phase 4.
Generates authorship, vote, dissent, and timing analysis by justice.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.data_loader import load_argument_dispositions


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert dataframe columns to title case."""
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out


def _format_label(value: object) -> object:
    """Make stored identifier-style values readable in charts and tables."""
    if pd.isna(value):
        return value
    return str(value).replace("_", " ").title()


def render_justice_authorship_analysis(year_range: tuple[int, int]):
    """
    Render justice authorship and voting pattern analysis.

    Args:
        year_range: Tuple of (min_year, max_year) for filtering
    """

    st.subheader("Justice Authorship & Voting Patterns")
    st.caption(
        "Analyzes opinion authorship, vote splits, dissents, and decision timing by justice. "
        "Based on oral arguments that resolved through published opinions."
    )

    # Load data
    arg_disp = load_argument_dispositions()

    if arg_disp.empty:
        st.info(
            "Argument dispositions data not available. "
            "Run: `python scripts/build_argument_dispositions.py`"
        )
        return

    # Filter to year range and opinions only
    opinions = arg_disp[
        (arg_disp["resolution_type"] == "opinion") &
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") >= year_range[0]) &
        (pd.to_numeric(arg_disp["term_year"], errors="coerce") <= year_range[1])
    ].copy()

    if opinions.empty:
        st.info("No opinion data available for the selected year range.")
        return

    # Overall metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Opinions", len(opinions))

    unanimous_count = opinions["is_unanimous"].sum()
    col2.metric("Unanimous", f"{unanimous_count:,}")
    col3.metric("Unanimity Rate", f"{unanimous_count/len(opinions)*100:.1f}%")

    dissent_count = opinions["has_dissent"].sum()
    col4.metric("With Dissent", f"{dissent_count:,}")

    # Authorship analysis
    st.markdown("### Opinion Authorship")

    author_data = opinions[opinions["author"].notna()].copy()
    # Source values are normalized identifiers (for example, ``bassett`` or
    # ``per_curiam``).  Use reader-friendly labels throughout this analysis.
    author_data["author"] = author_data["author"].map(_format_label)
    author_data["outcome"] = author_data["outcome"].map(_format_label)

    if not author_data.empty:
        tab1, tab2, tab3 = st.tabs(["Authorship Volume", "Timing by Author", "Vote Splits"])

        with tab1:
            author_counts = author_data["author"].value_counts().reset_index()
            author_counts.columns = ["Author", "Opinions"]

            col_a1, col_a2 = st.columns(2)

            with col_a1:
                fig_author = px.bar(
                    author_counts,
                    x="Opinions",
                    y="Author",
                    orientation="h",
                    title="Opinions Authored",
                    color_discrete_sequence=["#7E57C2"],
                )
                fig_author.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_author, width="stretch")

            with col_a2:
                # Authorship by year
                author_year = (
                    author_data.groupby(["term_year", "author"])
                    .size()
                    .reset_index(name="count")
                )

                fig_author_year = px.bar(
                    author_year,
                    x="term_year",
                    y="count",
                    color="author",
                    title="Authorship by Year",
                    labels={"term_year": "Year", "count": "Opinions"},
                    barmode="stack",
                )
                fig_author_year.update_layout(plot_bgcolor="white")
                st.plotly_chart(fig_author_year, width="stretch")

            st.dataframe(_title_columns(author_counts), hide_index=True, width="stretch")

        with tab2:
            # Timing by author
            timing_data = author_data[author_data["days_to_disposition"].notna()].copy()

            if not timing_data.empty:
                author_timing = (
                    timing_data.groupby("author")["days_to_disposition"]
                    .agg(["median", "mean", "count"])
                    .reset_index()
                    .sort_values("median", ascending=False)
                )
                author_timing.columns = ["Author", "Median Days", "Mean Days", "Opinions"]

                col_t1, col_t2 = st.columns(2)

                with col_t1:
                    fig_timing = px.bar(
                        author_timing,
                        x="Median Days",
                        y="Author",
                        orientation="h",
                        title="Median Days to Opinion by Author",
                        color_discrete_sequence=["#005A9C"],
                        text="Opinions",
                    )
                    fig_timing.update_traces(texttemplate='n=%{text}', textposition='outside')
                    fig_timing.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                    st.plotly_chart(fig_timing, width="stretch")

                with col_t2:
                    # Distribution comparison
                    fig_timing_dist = px.box(
                        timing_data,
                        x="author",
                        y="days_to_disposition",
                        title="Days to Opinion Distribution by Author",
                        labels={"author": "Author", "days_to_disposition": "Days"},
                        color="author",
                    )
                    fig_timing_dist.update_layout(plot_bgcolor="white", showlegend=False)
                    st.plotly_chart(fig_timing_dist, width="stretch")

                st.dataframe(_title_columns(author_timing), hide_index=True, width="stretch")
            else:
                st.info("No timing data available.")

        with tab3:
            # Vote split analysis
            unanimous_by_author = (
                author_data.groupby("author")
                .agg(
                    total=("author", "size"),
                    unanimous=("is_unanimous", "sum"),
                    dissent=("has_dissent", "sum")
                )
                .reset_index()
            )
            unanimous_by_author["Unanimity Rate"] = (
                unanimous_by_author["unanimous"] / unanimous_by_author["total"] * 100
            )
            unanimous_by_author["Dissent Rate"] = (
                unanimous_by_author["dissent"] / unanimous_by_author["total"] * 100
            )
            unanimous_by_author = unanimous_by_author.rename(
                columns={
                    "author": "Author",
                    "total": "Total Opinions",
                    "unanimous": "Unanimous",
                    "dissent": "With Dissent"
                }
            )

            col_v1, col_v2 = st.columns(2)

            with col_v1:
                fig_unanimity = px.bar(
                    unanimous_by_author,
                    x="Unanimity Rate",
                    y="Author",
                    orientation="h",
                    title="Unanimity Rate by Author",
                    color_discrete_sequence=["#4A7C59"],
                    text="Total Opinions",
                )
                fig_unanimity.update_traces(texttemplate='n=%{text}', textposition='outside')
                fig_unanimity.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_unanimity, width="stretch")

            with col_v2:
                fig_dissent = px.bar(
                    unanimous_by_author,
                    x="Dissent Rate",
                    y="Author",
                    orientation="h",
                    title="Dissent Rate by Author",
                    color_discrete_sequence=["#E09F3E"],
                    text="Total Opinions",
                )
                fig_dissent.update_traces(texttemplate='n=%{text}', textposition='outside')
                fig_dissent.update_layout(plot_bgcolor="white", yaxis={"autorange": "reversed"})
                st.plotly_chart(fig_dissent, width="stretch")

            st.dataframe(
                unanimous_by_author.sort_values("Total Opinions", ascending=False),
                hide_index=True,
                width="stretch"
            )
    else:
        st.info("No author data available.")

    # Topic and case type patterns
    st.markdown("### Authorship by Subject Area")

    if "case_type" in author_data.columns:
        tab_ct1, tab_ct2 = st.tabs(["By Case Type", "By Outcome"])

        with tab_ct1:
            author_case_type = (
                author_data[author_data["case_type"].notna()]
                .groupby(["author", "case_type"])
                .size()
                .reset_index(name="count")
            )

            if not author_case_type.empty:
                # Heatmap
                author_ct_pivot = author_case_type.pivot(
                    index="author",
                    columns="case_type",
                    values="count"
                ).fillna(0)

                fig_ct_heat = px.imshow(
                    author_ct_pivot,
                    labels=dict(x="Case Type", y="Author", color="Opinions"),
                    title="Authorship Heatmap: Justice × Case Type",
                    color_continuous_scale="Blues",
                )
                st.plotly_chart(fig_ct_heat, width="stretch")

                st.dataframe(
                    _title_columns(author_ct_pivot.reset_index()),
                    hide_index=True,
                    width="stretch"
                )
            else:
                st.info("No case type data available.")

        with tab_ct2:
            author_outcome = (
                author_data[author_data["outcome"].notna()]
                .groupby(["author", "outcome"])
                .size()
                .reset_index(name="count")
            )

            if not author_outcome.empty:
                # Stacked bar
                fig_outcome = px.bar(
                    author_outcome,
                    x="author",
                    y="count",
                    color="outcome",
                    title="Outcomes in Authored Opinions",
                    labels={"author": "Author", "count": "Opinions"},
                    barmode="stack",
                )
                fig_outcome.update_layout(plot_bgcolor="white")
                st.plotly_chart(fig_outcome, width="stretch")

                # Pivot table
                author_out_pivot = author_outcome.pivot(
                    index="author",
                    columns="outcome",
                    values="count"
                ).fillna(0).astype(int)

                st.dataframe(
                    _title_columns(author_out_pivot.reset_index()),
                    hide_index=True,
                    width="stretch"
                )
            else:
                st.info("No outcome data available.")

    # Export
    st.markdown("### Export Justice Authorship Data")

    export_df = author_data[[
        "argument_id", "case_name", "argument_date", "disposition_date",
        "days_to_disposition", "author", "is_unanimous", "has_dissent",
        "outcome", "case_type", "vote_string"
    ]].copy()

    csv = export_df.to_csv(index=False)

    st.download_button(
        label="📥 Download Justice Authorship Data (CSV)",
        data=csv,
        file_name=f"justice_authorship_{year_range[0]}_{year_range[1]}.csv",
        mime="text/csv",
        help="Download opinion authorship data with voting patterns"
    )
