"""Searchable 2026 oral-argument transcripts and collection statistics."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ORAL_ARGUMENT_COLLECTION_START_YEAR = 2015

from footer import add_gavel_glimpse_footer
from utils.data_loader import (
    load_attorney_justice_interactions,
    load_attorney_statistics,
    load_enhanced_statistics,
    load_firm_metadata,
    load_oral_argument,
    load_oral_argument_markdown,
    load_oral_argument_text,
    load_oral_arguments,
    load_speaker_statistics,
)
from utils.oral_arguments import (
    collection_statistics,
    format_duration,
    has_confirmed_argument_date,
    search_oral_arguments,
)


def _style_page() -> None:
    st.markdown(
        """
        <style>
        .oa-kicker {
            color: #9b3f22;
            font-size: .78rem;
            font-weight: 800;
            letter-spacing: .12em;
            text-transform: uppercase;
        }
        .oa-intro {
            color: #485568;
            font-family: Georgia, serif;
            font-size: 1.08rem;
            line-height: 1.65;
            max-width: 780px;
        }
        .oa-card {
            background: linear-gradient(135deg, #fffdf7 0%, #f5f0e4 100%);
            border: 1px solid #d9cfbc;
            border-left: 5px solid #b54f2f;
            border-radius: 8px;
            margin: .65rem 0;
            padding: 1rem 1.15rem;
        }
        .oa-card a {
            color: #003057;
            font-family: Georgia, serif;
            font-size: 1.08rem;
            font-weight: 800;
            text-decoration: none;
        }
        .oa-card a:hover { text-decoration: underline; }
        .oa-meta { color: #687182; font-size: .84rem; margin: .2rem 0 .55rem; }
        .oa-snippet { color: #343b47; line-height: 1.55; margin: 0; }
        .oa-disclosure {
            background: #fff7df;
            border: 1px solid #e5c979;
            border-radius: 8px;
            color: #5e4813;
            margin: .8rem 0 1.2rem;
            padding: .8rem 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _metric_row(stats: dict[str, float | int]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Arguments", f"{stats['argument_count']:,}")
    col2.metric("Total argument time", f"{float(stats['total_duration_seconds']) / 3600:.1f} hours")
    col3.metric("Transcript words", f"{int(stats['total_word_count']):,}")
    col4.metric("Median duration", format_duration(stats["median_duration_seconds"]))


def _render_reader(case_number: str) -> None:
    record = load_oral_argument(case_number)
    if not record:
        st.error("That oral argument could not be found.")
        st.markdown(
            '<a href="/oral-arguments" target="_self">Back to all oral arguments</a>',
            unsafe_allow_html=True,
        )
        return

    key = str(record["case_number"])
    transcript_text = load_oral_argument_text(key)
    transcript_markdown = load_oral_argument_markdown(key)
    st.markdown(
        '<a href="/oral-arguments" target="_self">Back to all oral arguments</a>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="oa-kicker">Oral argument transcript</div>', unsafe_allow_html=True)
    st.title(str(record.get("case_name", "Oral Argument")))
    st.caption(f"Docket {key} | Argued {record.get('argument_date', 'Unknown date')}")
    st.markdown(
        """
        <div class="oa-disclosure">
        <strong>Machine-generated beta transcript.</strong> This text may contain errors.
        Speaker labels are inferred for readability and are not certified diarization.
        Check the original video or court record before relying on a passage.
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Argument date", str(record.get("argument_date", "Unknown")))
    col2.metric("Duration", format_duration(record.get("duration_seconds")))
    col3.metric("Transcript words", f"{int(record.get('word_count', 0)):,}")
    col4.metric("Words per minute", f"{float(record.get('words_per_minute', 0)):.1f}")
    
    # Add speaker statistics if available
    speaker_stats_all = load_speaker_statistics()
    if speaker_stats_all:
        case_stats = next((s for s in speaker_stats_all if s["case_number"] == key), None)
        if case_stats and case_stats["total_segments"] > 0:
            st.markdown("##### Speaking Breakdown")
            cols = st.columns(4)
            cols[0].metric(
                "Justice speaking time",
                format_duration(case_stats["justice_time"]),
                delta=f"{case_stats['justice_time_pct']:.1f}%"
            )
            cols[1].metric(
                "Counsel speaking time", 
                format_duration(case_stats["counsel_time"]),
                delta=f"{case_stats['counsel_time_pct']:.1f}%"
            )
            cols[2].metric(
                "Justice pace",
                f"{case_stats['justice_pace_wpm']:.0f} wpm" if case_stats['justice_pace_wpm'] > 0 else "N/A"
            )
            cols[3].metric(
                "Counsel pace",
                f"{case_stats['counsel_pace_wpm']:.0f} wpm" if case_stats['counsel_pace_wpm'] > 0 else "N/A"
            )
    
    # Add attorney information if available
    attorney_data = load_attorney_statistics()
    if attorney_data and attorney_data.get("case_attorneys"):
        case_attorneys = attorney_data["case_attorneys"].get(key, [])
        if case_attorneys:
            st.markdown("##### Attorneys")
            
            # Group attorneys by side
            sides = {}
            for attorney in case_attorneys:
                side = attorney.get("side", "Other")
                if side not in sides:
                    sides[side] = []
                sides[side].append(attorney)
            
            # Display attorneys grouped by side
            for side, attorneys in sides.items():
                st.markdown(f"**{side.capitalize()}**")
                for attorney in attorneys:
                    name = attorney.get("name", "Unknown")
                    firm = attorney.get("firm", "")
                    profile_url = f"/attorney-profile?attorney={quote(str(name), safe='')}"
                    
                    # Find this attorney's stats
                    attorney_stat = next(
                        (a for a in attorney_data["attorney_stats"] if a["attorney_name"] == name),
                        None
                    )
                    
                    if firm:
                        info_text = f"- [**{name}**]({profile_url}) ({firm})"
                    else:
                        info_text = f"- [**{name}**]({profile_url})"
                    
                    # Add career stats if available
                    if attorney_stat:
                        info_text += f" — {attorney_stat['total_arguments']} career arguments"
                        if attorney_stat['average_duration_minutes'] > 0:
                            info_text += f" (avg {attorney_stat['average_duration_minutes']:.0f} min)"
                    
                    st.markdown(info_text)

    actions = st.columns([1, 1, 1, 2])
    with actions[0]:
        if record.get("vimeo_url"):
            st.link_button("Watch Video", str(record["vimeo_url"]))
    with actions[1]:
        st.download_button(
            "Download text",
            transcript_text,
            file_name=f"{key}-oral-argument.txt",
            mime="text/plain",
            disabled=not transcript_text,
        )
    with actions[2]:
        st.download_button(
            "Download Markdown",
            transcript_markdown,
            file_name=f"{key}-oral-argument.md",
            mime="text/markdown",
            disabled=not transcript_markdown,
        )

    st.divider()
    if transcript_markdown:
        st.markdown(transcript_markdown)
    else:
        st.info("The readable transcript is unavailable for this argument.")


def _render_attorney_statistics() -> None:
    """Render attorney and firm statistics."""
    attorney_data = load_attorney_statistics()
    
    if not attorney_data or not attorney_data.get("attorney_stats"):
        st.info("Attorney statistics are being generated. Check back soon.")
        return
    
    attorney_stats = attorney_data["attorney_stats"]
    firm_stats = attorney_data["firm_stats"]
    firm_lookup = load_firm_metadata().get("lookup", {})

    def _display_firm_name(firm_name: str) -> str:
        return firm_lookup.get(firm_name, {}).get("full_name", firm_name)
    
    st.subheader("Attorneys & Law Firms")
    
    # Export buttons
    col_export1, col_export2, col_export3 = st.columns([1, 1, 3])
    with col_export1:
        # Prepare attorney CSV
        attorney_export_df = pd.DataFrame(attorney_stats)
        attorney_export_cols = ["attorney_name", "firm", "total_arguments", "total_duration_hours", "average_duration_minutes", "first_argument_date", "last_argument_date"]
        attorney_export_df = attorney_export_df[[c for c in attorney_export_cols if c in attorney_export_df.columns]]
        attorney_csv = attorney_export_df.to_csv(index=False)
        
        st.download_button(
            "📥 Download Attorneys CSV",
            attorney_csv,
            file_name="nh_attorneys_stats.csv",
            mime="text/csv"
        )
    
    with col_export2:
        # Prepare firm CSV
        firm_export_df = pd.DataFrame(firm_stats)
        firm_export_cols = ["firm_name", "total_arguments", "unique_attorneys", "total_duration_hours", "average_duration_minutes", "first_argument_date", "last_argument_date"]
        firm_export_df = firm_export_df[[c for c in firm_export_cols if c in firm_export_df.columns]]
        firm_csv = firm_export_df.to_csv(index=False)
        
        st.download_button(
            "📥 Download Firms CSV",
            firm_csv,
            file_name="nh_firms_stats.csv",
            mime="text/csv"
        )
    
    st.caption(f"{len(attorney_stats)} attorneys from {len(firm_stats)} firms have argued before the court.")
    
    # Search and filter controls
    st.markdown("#### Search & Filter")
    col_search1, col_search2, col_search3 = st.columns([2, 1, 1])
    with col_search1:
        search_query = st.text_input(
            "Search attorneys or firms",
            placeholder="Enter name, firm, or keyword...",
            label_visibility="collapsed"
        )
    with col_search2:
        # Present full firm names while retaining raw values for filtering.
        display_to_firm_names: dict[str, set[str]] = {}
        all_firm_names = {
            f["firm_name"] for f in firm_stats if f.get("firm_name")
        }
        for a in attorney_stats:
            if a.get("firm"):
                all_firm_names.add(a["firm"])

        for firm_name in all_firm_names:
            display_name = _display_firm_name(firm_name)
            display_to_firm_names.setdefault(display_name, set()).add(firm_name)

        firm_names = sorted(display_to_firm_names)
        firm_filter = st.selectbox(
            "Filter by firm",
            ["All firms"] + firm_names,
            label_visibility="collapsed"
        )
    with col_search3:
        min_args = st.number_input(
            "Min arguments",
            min_value=1,
            value=1,
            step=1,
            label_visibility="collapsed"
        )

    # Apply filters to attorneys
    filtered_attorneys = attorney_stats
    if search_query:
        query_lower = search_query.lower()
        filtered_attorneys = [
            a for a in filtered_attorneys
            if query_lower in a["attorney_name"].lower()
            or query_lower in a.get("firm", "").lower()
            or query_lower in _display_firm_name(a.get("firm", "")).lower()
        ]
    if firm_filter != "All firms":
        selected_firm_names = display_to_firm_names[firm_filter]
        selected_attorney_names = {
            attorney_name
            for firm in firm_stats
            if firm.get("firm_name") in selected_firm_names
            for attorney_name in firm.get("attorneys", [])
        }
        filtered_attorneys = [
            a for a in filtered_attorneys
            if a["attorney_name"] in selected_attorney_names
        ]
    if min_args > 1:
        filtered_attorneys = [a for a in filtered_attorneys if a["total_arguments"] >= min_args]
    
    # Apply filters to firms
    filtered_firms = firm_stats
    if search_query:
        query_lower = search_query.lower()
        filtered_firms = [
            f for f in filtered_firms
            if query_lower in f["firm_name"].lower()
            or query_lower in _display_firm_name(f["firm_name"]).lower()
        ]
    if firm_filter != "All firms":
        filtered_firms = [
            f for f in filtered_firms
            if f.get("firm_name") in selected_firm_names
        ]
    if min_args > 1:
        filtered_firms = [f for f in filtered_firms if f["total_arguments"] >= min_args]
    
    st.caption(f"Showing {len(filtered_attorneys)} attorneys and {len(filtered_firms)} firms")
    
    # Top attorneys
    st.markdown("#### Most Active Attorneys")
    top_attorneys = pd.DataFrame(filtered_attorneys[:20])
    if top_attorneys.empty:
        st.info("No attorneys match your filters.")
    else:
        top_attorneys = top_attorneys[["attorney_name", "firm", "total_arguments"]]
        top_attorneys.columns = ["Attorney", "Firm", "Arguments"]
    
        fig_attorneys = px.bar(
            top_attorneys.head(15),
            x="Arguments",
            y="Attorney",
            orientation="h",
            title="Top 15 Attorneys by Argument Count",
            color="Arguments",
            color_continuous_scale="Blues"
        )
        fig_attorneys.update_layout(plot_bgcolor="white", yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_attorneys, width="stretch")
    
    with st.expander("View all attorneys"):
        st.dataframe(top_attorneys, width="stretch", hide_index=True)
        st.caption("To view attorney profiles, use the 'Attorney Profile' page in the sidebar.")
    
    # Top firms
    st.markdown("#### Most Active Law Firms")
    top_firms = pd.DataFrame(filtered_firms[:20])
    if top_firms.empty:
        st.info("No firms match your filters.")
    else:
        top_firms = top_firms[["firm_name", "total_arguments", "unique_attorneys"]]
        top_firms.columns = ["Firm", "Arguments", "Attorneys"]
        
        fig_firms = px.bar(
            top_firms.head(15),
            x="Arguments",
            y="Firm",
            orientation="h",
            title="Top 15 Firms by Argument Count",
            color="Arguments",
            color_continuous_scale="Reds"
        )
        fig_firms.update_layout(plot_bgcolor="white", yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_firms, width="stretch")
        
    with st.expander("View all firms"):
        all_firms = pd.DataFrame(filtered_firms)
        if not all_firms.empty:
            all_firms = all_firms[["firm_name", "total_arguments", "unique_attorneys"]]
            all_firms.columns = ["Firm", "Arguments", "Attorneys"]
            all_firms["Firm"] = all_firms["Firm"].map(_display_firm_name)
            all_firms["Average # of Arguments"] = (
                all_firms["Arguments"] / all_firms["Attorneys"]
            ).round(2)
        st.dataframe(
            all_firms,
            width="stretch",
            hide_index=True,
            column_config={
                "Average # of Arguments": st.column_config.NumberColumn(format="%.2f")
            },
        )
        st.caption("To view firm profiles, use the 'Firm Profile' page in the sidebar.")
    
    # Distribution analysis
    st.markdown("#### Distribution Analysis")
    left3, right3 = st.columns(2)
    
    with left3:
        # Arguments per attorney distribution
        attorney_df = pd.DataFrame(filtered_attorneys)
        if not attorney_df.empty:
            bins = [1, 2, 5, 10, 20, 50, 200]
            labels = ["1", "2-4", "5-9", "10-19", "20-49", "50+"]
            attorney_df["argument_range"] = pd.cut(
                attorney_df["total_arguments"],
                bins=bins,
                labels=labels,
                right=False
            )
            attorney_dist = attorney_df.groupby("argument_range", observed=False).size().reset_index(name="count")
            
            fig_attorney_dist = px.bar(
                attorney_dist,
                x="argument_range",
                y="count",
                title="Attorney Argument Count Distribution",
                labels={"argument_range": "Number of Arguments", "count": "Attorneys"},
                color_discrete_sequence=["#003057"]
            )
            fig_attorney_dist.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_attorney_dist, width="stretch")
        else:
            st.info("No data to display")
    
    with right3:
        # Firm size distribution
        firm_df = pd.DataFrame(filtered_firms)
        if not firm_df.empty:
            bins_firm = [1, 2, 5, 10, 50, 200]
            labels_firm = ["1", "2-4", "5-9", "10-49", "50+"]
            firm_df["argument_range"] = pd.cut(
            firm_df["total_arguments"],
            bins=bins_firm,
            labels=labels_firm,
            right=False
        )
            firm_dist = firm_df.groupby("argument_range", observed=False).size().reset_index(name="count")
            
            fig_firm_dist = px.bar(
                firm_dist,
                x="argument_range",
                y="count",
                title="Firm Argument Count Distribution",
                labels={"argument_range": "Number of Arguments", "count": "Firms"},
                color_discrete_sequence=["#b54f2f"]
            )
            fig_firm_dist.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_firm_dist, width="stretch")
        else:
            st.info("No data to display")
    
    # Duration analysis
    st.markdown("#### Duration Analysis")
    left4, right4 = st.columns(2)
    
    with left4:
        # Top attorneys by total argument time
        top_by_time = sorted(
            [a for a in filtered_attorneys if a.get("total_duration_hours", 0) > 0],
            key=lambda x: x.get("total_duration_hours", 0),
            reverse=True
        )[:15]
        if top_by_time:
            time_df = pd.DataFrame(top_by_time)
            time_df = time_df[["attorney_name", "total_duration_hours"]]
            time_df.columns = ["Attorney", "Total Hours"]
            
            fig_time = px.bar(
                time_df,
                x="Total Hours",
                y="Attorney",
                orientation="h",
                title="Top 15 Attorneys by Total Argument Time",
                color="Total Hours",
                color_continuous_scale="Greens"
            )
            fig_time.update_layout(plot_bgcolor="white", yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_time, width="stretch")
        else:
            st.info("No duration data available")
    
    with right4:
        # Average argument duration by attorney (min 5 arguments)
        frequent_attorneys = [a for a in filtered_attorneys if a["total_arguments"] >= 5 and a.get("average_duration_minutes", 0) > 0]
        if frequent_attorneys:
            avg_duration_df = pd.DataFrame(frequent_attorneys)
            avg_duration_df = avg_duration_df.nlargest(15, "average_duration_minutes")[["attorney_name", "average_duration_minutes", "total_arguments"]]
            avg_duration_df.columns = ["Attorney", "Avg Minutes", "Arguments"]
            
            fig_avg = px.bar(
                avg_duration_df,
                x="Avg Minutes",
                y="Attorney",
                orientation="h",
                title="Longest Average Arguments (≥5 cases)",
                color="Avg Minutes",
                color_continuous_scale="Oranges",
                hover_data=["Arguments"]
            )
            fig_avg.update_layout(plot_bgcolor="white", yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_avg, width="stretch")
        else:
            st.info("No duration data available")
    
    # Time trends
    st.markdown("#### Activity Over Time")
    
    # Build year-by-year data for top filtered attorneys
    top_attorneys_names = [a["attorney_name"] for a in filtered_attorneys[:10]]
    year_data = []
    for attorney in filtered_attorneys:
        if attorney["attorney_name"] in top_attorneys_names:
            for year, count in attorney.get("years_active", {}).items():
                year_data.append({
                    "Attorney": attorney["attorney_name"],
                    "Year": year,
                    "Arguments": count
                })
    
    if year_data:
        year_df = pd.DataFrame(year_data)
        year_df = year_df.sort_values("Year")
        
        fig_trends = px.line(
            year_df,
            x="Year",
            y="Arguments",
            color="Attorney",
            title="Top 10 Attorneys: Arguments Over Time",
            markers=True
        )
        fig_trends.update_layout(plot_bgcolor="white", xaxis_title="Year", yaxis_title="Arguments", xaxis={'type': 'category'})
        st.plotly_chart(fig_trends, width="stretch")
        
        st.caption(f"Showing activity for the top 10 most frequent attorneys ({len(filtered_attorneys):,} total).")
    
    # Advanced visualizations
    st.markdown("#### Advanced Visualizations")
    
    viz_type = st.selectbox(
        "Select visualization",
        ["Firm-Attorney Hierarchy", "Arguments vs Duration Scatter", "Top Firms Breakdown"]
    )
    
    if viz_type == "Firm-Attorney Hierarchy":
        # Sunburst chart showing firm-attorney relationships
        hierarchy_data = []
        for firm in firm_stats[:20]:  # Top 20 firms
            firm_name = firm["firm_name"]
            for attorney_name in firm["attorneys"]:
                attorney = next((a for a in attorney_stats if a["attorney_name"] == attorney_name), None)
                if attorney:
                    hierarchy_data.append({
                        "Firm": firm_name,
                        "Attorney": attorney_name,
                        "Arguments": attorney["total_arguments"]
                    })
        
        if hierarchy_data:
            hierarchy_df = pd.DataFrame(hierarchy_data)
            fig_sunburst = px.sunburst(
                hierarchy_df,
                path=["Firm", "Attorney"],
                values="Arguments",
                title="Top 20 Firms: Attorney Distribution by Arguments",
                color="Arguments",
                color_continuous_scale="Blues"
            )
            fig_sunburst.update_layout(height=700)
            st.plotly_chart(fig_sunburst, width="stretch")
            st.caption("Click on segments to drill down. Size represents total arguments.")
        else:
            st.info("No hierarchy data available")
    
    elif viz_type == "Arguments vs Duration Scatter":
        # Scatter plot showing relationship between arguments and duration
        scatter_data = []
        for attorney in attorney_stats:
            if attorney.get("total_duration_hours", 0) > 0:
                scatter_data.append({
                    "Attorney": attorney["attorney_name"],
                    "Firm": attorney.get("firm", "Unknown"),
                    "Arguments": attorney["total_arguments"],
                    "Total Hours": attorney["total_duration_hours"],
                    "Avg Minutes": attorney.get("average_duration_minutes", 0)
                })
        
        if scatter_data:
            scatter_df = pd.DataFrame(scatter_data)
            fig_scatter = px.scatter(
                scatter_df,
                x="Arguments",
                y="Total Hours",
                size="Avg Minutes",
                color="Firm",
                hover_data=["Attorney"],
                title="Attorney Arguments vs Total Time (bubble size = avg duration)",
                labels={"Total Hours": "Total Argument Time (hours)", "Arguments": "Number of Arguments"}
            )
            fig_scatter.update_layout(plot_bgcolor="white", height=600)
            st.plotly_chart(fig_scatter, width="stretch")
            st.caption("Hover over points to see attorney names. Bubble size indicates average argument duration.")
        else:
            st.info("No duration data available")
    
    else:  # Top Firms Breakdown
        # Treemap of top firms
        treemap_data = []
        for firm in firm_stats[:15]:
            treemap_data.append({
                "Firm": firm["firm_name"],
                "Arguments": firm["total_arguments"],
                "Attorneys": firm["unique_attorneys"],
                "Hours": firm.get("total_duration_hours", 0)
            })
        
        if treemap_data:
            treemap_df = pd.DataFrame(treemap_data)
            fig_treemap = px.treemap(
                treemap_df,
                path=["Firm"],
                values="Arguments",
                color="Hours",
                hover_data=["Attorneys"],
                title="Top 15 Firms: Arguments and Time Breakdown",
                color_continuous_scale="Reds"
            )
            fig_treemap.update_layout(height=600)
            st.plotly_chart(fig_treemap, width="stretch")
            st.caption("Size = number of arguments, color = total hours. Click to see details.")
        else:
            st.info("No firm data available")
    
    # Attorney-Justice Interactions
    st.markdown("#### Attorney-Justice Interactions")
    
    interaction_data = load_attorney_justice_interactions()
    
    if interaction_data and interaction_data.get("attorney_interactions"):
        st.caption(
            f"{interaction_data['summary']['total_arguments_analyzed']} arguments analyzed | "
            f"{interaction_data['summary']['unique_attorneys']} attorneys before "
            f"{interaction_data['summary']['unique_justices']} justices"
        )
        
        interaction_viz = st.selectbox(
            "Select view",
            ["Top Attorneys by Justice", "Justice Workload", "Attorney-Justice Heatmap"]
        )
        
        if interaction_viz == "Top Attorneys by Justice":
            # Show top attorneys for each justice
            justice_to_show = st.selectbox(
                "Select justice",
                [j["justice"] for j in interaction_data["justice_interactions"]]
            )
            
            justice_info = next(
                (j for j in interaction_data["justice_interactions"] if j["justice"] == justice_to_show),
                None
            )
            
            if justice_info:
                st.metric("Total Arguments", justice_info["total_arguments"])
                st.metric("Unique Attorneys", justice_info["unique_attorneys"])
                
                top_attorneys_for_justice = pd.DataFrame(justice_info["top_attorneys"][:20])
                fig_justice_attorneys = px.bar(
                    top_attorneys_for_justice,
                    x="arguments",
                    y="attorney",
                    orientation="h",
                    title=f"Top 20 Attorneys Before {justice_to_show}",
                    labels={"arguments": "Arguments", "attorney": "Attorney"},
                    color="arguments",
                    color_continuous_scale="Blues"
                )
                fig_justice_attorneys.update_layout(
                    plot_bgcolor="white",
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig_justice_attorneys, width="stretch")
        
        elif interaction_viz == "Justice Workload":
            # Show argument count per justice
            justice_workload = pd.DataFrame(interaction_data["justice_interactions"])
            justice_workload = justice_workload[["justice", "total_arguments", "unique_attorneys"]]
            justice_workload.columns = ["Justice", "Arguments", "Attorneys"]
            
            col_work1, col_work2 = st.columns(2)
            
            with col_work1:
                fig_workload = px.bar(
                    justice_workload,
                    x="Arguments",
                    y="Justice",
                    orientation="h",
                    title="Arguments Heard by Justice (2015-2026)",
                    color="Arguments",
                    color_continuous_scale="Reds"
                )
                fig_workload.update_layout(
                    plot_bgcolor="white",
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig_workload, width="stretch")
            
            with col_work2:
                fig_attorneys_per_justice = px.bar(
                    justice_workload,
                    x="Attorneys",
                    y="Justice",
                    orientation="h",
                    title="Unique Attorneys per Justice",
                    color="Attorneys",
                    color_continuous_scale="Greens"
                )
                fig_attorneys_per_justice.update_layout(
                    plot_bgcolor="white",
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig_attorneys_per_justice, width="stretch")
        
        else:  # Attorney-Justice Heatmap
            # Create heatmap showing interaction frequency
            # Top 20 attorneys x all justices
            top_attorneys_for_heatmap = interaction_data["attorney_interactions"][:20]
            all_justices = [j["justice"] for j in interaction_data["justice_interactions"]]
            
            heatmap_data = []
            for attorney_info in top_attorneys_for_heatmap:
                attorney_name = attorney_info["attorney_name"]
                for interaction in attorney_info["interactions"]:
                    heatmap_data.append({
                        "Attorney": attorney_name,
                        "Justice": interaction["justice"],
                        "Arguments": interaction["arguments"]
                    })
            
            if heatmap_data:
                heatmap_df = pd.DataFrame(heatmap_data)
                # Pivot for heatmap
                heatmap_pivot = heatmap_df.pivot(index="Attorney", columns="Justice", values="Arguments").fillna(0)
                
                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(x="Justice", y="Attorney", color="Arguments"),
                    title="Attorney-Justice Interaction Heatmap (Top 20 Attorneys)",
                    color_continuous_scale="YlOrRd",
                    aspect="auto"
                )
                fig_heatmap.update_layout(height=700)
                st.plotly_chart(fig_heatmap, width="stretch")
                st.caption("Darker colors = more frequent interactions. Shows arguments per attorney-justice pair.")
            else:
                st.info("No heatmap data available")
    else:
        st.info("Attorney-justice interaction data not available. Run `python scripts/analyze_attorney_justice_interactions.py` to generate.")


def _render_attorney_firm_comparison() -> None:
    """Render attorney and firm comparisons in a dedicated tab."""
    attorney_data = load_attorney_statistics()
    attorney_stats = attorney_data.get("attorney_stats", [])
    firm_stats = attorney_data.get("firm_stats", [])

    if not attorney_stats or not firm_stats:
        st.info("Attorney and firm statistics are being generated. Check back soon.")
        return

    st.subheader("Compare Attorneys & Firms")
    comp_type = st.radio("Compare", ["Attorneys", "Firms"], horizontal=True)

    if comp_type == "Attorneys":
        attorney_names = [a["attorney_name"] for a in attorney_stats]
        selected_attorneys = st.multiselect(
            "Select attorneys to compare (2-5)",
            attorney_names,
            default=attorney_names[:2] if len(attorney_names) >= 2 else attorney_names,
        )

        if len(selected_attorneys) < 2:
            st.info("Select at least 2 attorneys to compare.")
            return
        if len(selected_attorneys) > 5:
            st.warning("Please select no more than 5 attorneys for a clear comparison.")
            return

        comparison_rows = []
        compared_attorneys = [
            attorney for attorney in attorney_stats
            if attorney["attorney_name"] in selected_attorneys
        ]
        for attorney in compared_attorneys:
            comparison_rows.append({
                "Attorney": attorney["attorney_name"],
                "Firm": attorney.get("firm", ""),
                "Arguments": attorney["total_arguments"],
                "Total Hours": attorney.get("total_duration_hours", 0),
                "Avg Minutes": attorney.get("average_duration_minutes", 0),
                "Years Active": (
                    f"{attorney.get('first_argument_date', '')[:4]} - "
                    f"{attorney.get('last_argument_date', '')[:4]}"
                ),
            })

        comparison_df = pd.DataFrame(comparison_rows)
        st.dataframe(comparison_df, width="stretch", hide_index=True)

        left_chart, right_chart = st.columns(2)
        with left_chart:
            arguments_chart = px.bar(
                comparison_df,
                x="Attorney",
                y="Arguments",
                title="Total Arguments Comparison",
                color="Attorney",
            )
            arguments_chart.update_layout(plot_bgcolor="white", showlegend=False)
            st.plotly_chart(arguments_chart, width="stretch")

        with right_chart:
            time_chart = px.bar(
                comparison_df,
                x="Attorney",
                y="Total Hours",
                title="Total Argument Time Comparison",
                color="Attorney",
            )
            time_chart.update_layout(plot_bgcolor="white", showlegend=False)
            st.plotly_chart(time_chart, width="stretch")

        timeline_rows = [
            {
                "Attorney": attorney["attorney_name"],
                "Year": year,
                "Arguments": count,
            }
            for attorney in compared_attorneys
            for year, count in attorney.get("years_active", {}).items()
        ]
        if timeline_rows:
            timeline_df = pd.DataFrame(timeline_rows).sort_values("Year")
            timeline_chart = px.line(
                timeline_df,
                x="Year",
                y="Arguments",
                color="Attorney",
                title="Activity Timeline Comparison",
                markers=True,
            )
            timeline_chart.update_layout(plot_bgcolor="white", xaxis={"type": "category"})
            st.plotly_chart(timeline_chart, width="stretch")
        return

    firm_names = sorted((f["firm_name"] for f in firm_stats), key=str.casefold)
    selected_firms = st.multiselect(
        "Select firms to compare (2-5)",
        firm_names,
        default=[],
    )

    if len(selected_firms) < 2:
        st.info("Select at least 2 firms to compare.")
        return
    if len(selected_firms) > 5:
        st.warning("Please select no more than 5 firms for a clear comparison.")
        return

    comparison_rows = []
    for firm in firm_stats:
        if firm["firm_name"] not in selected_firms:
            continue
        comparison_rows.append({
            "Firm": firm["firm_name"],
            "Arguments": firm["total_arguments"],
            "Attorneys": firm["unique_attorneys"],
            "Total Hours": firm.get("total_duration_hours", 0),
            "Avg Minutes": firm.get("average_duration_minutes", 0),
            "Years Active": (
                f"{firm.get('first_argument_date', '')[:4]} - "
                f"{firm.get('last_argument_date', '')[:4]}"
            ),
        })

    comparison_df = pd.DataFrame(comparison_rows).sort_values("Firm", key=lambda column: column.str.casefold())
    st.dataframe(comparison_df, width="stretch", hide_index=True)

    left_chart, right_chart = st.columns(2)
    with left_chart:
        arguments_chart = px.bar(
            comparison_df,
            x="Firm",
            y="Arguments",
            title="Total Arguments Comparison",
            color="Firm",
        )
        arguments_chart.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(arguments_chart, width="stretch")

    with right_chart:
        attorneys_chart = px.bar(
            comparison_df,
            x="Firm",
            y="Attorneys",
            title="Number of Attorneys Comparison",
            color="Firm",
        )
        attorneys_chart.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(attorneys_chart, width="stretch")


def _render_transcript_search(records: list[dict]) -> None:
    """Enhanced transcript search with advanced filters."""
    
    # Search and filters in columns
    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input(
            "Search transcripts",
            placeholder="Search a party, legal issue, phrase, docket, or argument date",
        )
    with col2:
        # Quick export button
        if st.button("⬇ Export All to CSV", help="Export filtered results to CSV"):
            results_df = pd.DataFrame(records)
            csv = results_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="oral_arguments.csv",
                mime="text/csv"
            )
    
    # Advanced filters in expander
    with st.expander("🔍 Advanced Filters", expanded=False):
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            # Date filter
            date_options = sorted({str(row.get("argument_date", "")) for row in records if row.get("argument_date")})
            selected_dates = st.multiselect(
                "Argument dates", 
                date_options, 
                placeholder="All dates"
            )
            
            # Year range filter
            years = sorted({pd.to_datetime(row.get("argument_date")).year for row in records if row.get("argument_date")})
            if years:
                year_range = st.slider(
                    "Year range",
                    min_value=min(years),
                    max_value=max(years),
                    value=(min(years), max(years))
                )
        
        with filter_col2:
            # Duration filter
            durations = [row.get("duration_seconds", 0) / 60 for row in records if row.get("duration_seconds")]
            if durations:
                duration_range = st.slider(
                    "Duration (minutes)",
                    min_value=0,
                    max_value=int(max(durations)) + 1,
                    value=(0, int(max(durations)) + 1)
                )
            else:
                duration_range = (0, 999)
            
            # Case type filter (inferred from case name)
            case_type = st.selectbox(
                "Case type",
                ["All", "Criminal (State v.)", "Civil", "Family/Probate"],
                index=0
            )
        
        with filter_col3:
            # Segment count filter (proxy for complexity)
            segments = [row.get("segment_count", 0) for row in records if row.get("segment_count")]
            if segments:
                segment_range = st.slider(
                    "Segments (complexity)",
                    min_value=0,
                    max_value=max(segments),
                    value=(0, max(segments)),
                    help="Number of speaking segments - higher numbers indicate more complex arguments"
                )
            else:
                segment_range = (0, 9999)
    
    # Apply all filters
    results = search_oral_arguments(records, query)
    
    if selected_dates:
        results = [row for row in results if row.get("argument_date") in selected_dates]
    
    if 'year_range' in locals():
        results = [
            row for row in results 
            if row.get("argument_date") and 
            year_range[0] <= pd.to_datetime(row.get("argument_date")).year <= year_range[1]
        ]
    
    if duration_range:
        results = [
            row for row in results 
            if row.get("duration_seconds") and 
            duration_range[0] <= (row.get("duration_seconds", 0) / 60) <= duration_range[1]
        ]
    
    if case_type != "All":
        if case_type == "Criminal (State v.)":
            results = [row for row in results if "state v." in row.get("case_name", "").lower() or "state of new hampshire v." in row.get("case_name", "").lower()]
        elif case_type == "Civil":
            results = [row for row in results if " v. " in row.get("case_name", "").lower() and "state v." not in row.get("case_name", "").lower()]
        elif case_type == "Family/Probate":
            results = [row for row in results if "in re" in row.get("case_name", "").lower() or "in the matter" in row.get("case_name", "").lower()]
    
    if segment_range:
        results = [
            row for row in results 
            if row.get("segment_count") and 
            segment_range[0] <= row.get("segment_count", 0) <= segment_range[1]
        ]
    
    # Results info
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"Showing {len(results):,} of {len(records):,} oral arguments")
    with col_b:
        display_count = st.select_slider(
            "Results per page", 
            options=[12, 24, 48, 100], 
            value=24
        )
    
    if not results:
        st.info("No transcripts matched. Try adjusting your filters or search query.")
        return

    # Display results
    for record in results[:display_count]:
        case_number = str(record["case_number"])
        href = f"/oral-arguments?argument={quote(case_number)}"
        opinion_href = f"/opinions?docket={quote(case_number)}"
        snippet = record.get("_snippet") or str(record.get("transcript_text", ""))[:310]
        duration = format_duration(record.get("duration_seconds"))
        segments = record.get("segment_count", 0)
        st.markdown(
            f"""
            <div class="oa-card">
              <a href="{href}" target="_self">{html.escape(str(record.get('case_name', 'Unknown case')))}</a>
              <div class="oa-meta">Docket {html.escape(case_number)} &middot; Argued {html.escape(str(record.get('argument_date', '')))} &middot; {duration} &middot; {segments:,} segments &middot; <a href="{opinion_href}" target="_self" style="color: #b54f2f;">View Opinion</a></div>
              <p class="oa-snippet">{html.escape(str(snippet))}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    if len(results) > display_count:
        st.info(f"Showing first {display_count:,} of {len(results):,} results. Adjust slider to see more.")


def _render_statistics(records: list[dict]) -> None:
    """Render statistics charts."""
    # Term-start defaults (October 1) are not real argument dates.  Retain
    # those records in the transcript collection, while excluding them from
    # date-based charts so they cannot create artificial October spikes.
    frame = pd.DataFrame([row for row in records if has_confirmed_argument_date(row)])
    if frame.empty:
        st.info("No oral arguments with confirmed dates are available for statistics.")
        return
    frame["argument_date"] = pd.to_datetime(frame["argument_date"], errors="coerce")
    frame["argument_year"] = frame["argument_date"].dt.year
    frame["argument_month"] = frame["argument_date"].dt.to_period("M").astype(str)
    frame["duration_minutes"] = frame["duration_seconds"] / 60
    
    # Year-based chart
    by_year = (
        frame[frame["argument_year"] >= ORAL_ARGUMENT_COLLECTION_START_YEAR]
        .groupby("argument_year", as_index=False)
        .size()
        .rename(columns={"size": "arguments"})
    )
    fig_year = px.bar(
        by_year,
        x="argument_year",
        y="arguments",
        title="Arguments by Year",
        color_discrete_sequence=["#003057"],
        labels={"argument_year": "Year argued", "arguments": "Arguments"},
    )
    fig_year.update_layout(plot_bgcolor="white", xaxis={'type': 'category'})
    st.plotly_chart(fig_year, width="stretch")

    # Month-based chart
    by_month = (
        frame[frame["argument_year"] >= ORAL_ARGUMENT_COLLECTION_START_YEAR]
        .groupby("argument_month", as_index=False)
        .size()
        .rename(columns={"size": "arguments"})
    )
    fig_month = px.line(
        by_month,
        x="argument_month",
        y="arguments",
        markers=True,
        title="Arguments by Month",
        color_discrete_sequence=["#b54f2f"],
        labels={"argument_month": "Month", "arguments": "Arguments"},
    )
    fig_month.update_layout(plot_bgcolor="white")
    st.plotly_chart(fig_month, width="stretch")

    # Distribution charts
    left, right = st.columns(2)
    with left:
        fig_duration = px.histogram(
            frame,
            x="duration_minutes",
            nbins=12,
            title="Argument Duration Distribution",
            color_discrete_sequence=["#357266"],
            labels={"duration_minutes": "Duration (minutes)"},
        )
        fig_duration.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(fig_duration, width="stretch")
    with right:
        fig_words = px.histogram(
            frame,
            x="word_count",
            nbins=12,
            title="Transcript Word-Count Distribution",
            color_discrete_sequence=["#b54f2f"],
            labels={"word_count": "Transcript words"},
        )
        fig_words.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(fig_words, width="stretch")
    
    # Speaker statistics
    st.markdown("---")
    st.subheader("Speaking Patterns")
    
    speaker_stats = load_speaker_statistics()
    if speaker_stats:
        stats_frame = pd.DataFrame(speaker_stats)
        
        # Time allocation
        left2, right2 = st.columns(2)
        with left2:
            time_data = pd.DataFrame({
                "Role": ["Counsel", "Justices"],
                "Minutes": [stats_frame["counsel_time"].sum() / 60, stats_frame["justice_time"].sum() / 60]
            })
            fig_time = px.pie(
                time_data,
                values="Minutes",
                names="Role",
                title="Speaking Time by Role",
                color="Role",
                color_discrete_map={"Counsel": "#b54f2f", "Justices": "#003057"}
            )
            fig_time.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_time, width="stretch")
        
        with right2:
            # Speaking pace comparison
            pace_data = pd.DataFrame({
                "Role": ["Counsel", "Justices"],
                "Words per Minute": [
                    stats_frame[stats_frame["counsel_pace_wpm"] > 0]["counsel_pace_wpm"].mean(),
                    stats_frame[stats_frame["justice_pace_wpm"] > 0]["justice_pace_wpm"].mean()
                ]
            })
            fig_pace = px.bar(
                pace_data,
                x="Role",
                y="Words per Minute",
                title="Average Speaking Pace",
                color="Role",
                color_discrete_map={"Counsel": "#b54f2f", "Justices": "#003057"}
            )
            fig_pace.update_layout(plot_bgcolor="white", showlegend=False)
            st.plotly_chart(fig_pace, width="stretch")
        
        st.caption(
            f"Based on {len(stats_frame):,} arguments. "
            f"Counsel speaks {stats_frame['counsel_time_pct'].mean():.1f}% of the time on average, "
            f"Justices {stats_frame['justice_time_pct'].mean():.1f}%."
        )

    st.caption(
        "Statistics describe the machine-generated transcript collection. "
        "They are not measures of case importance, speaker performance, or transcript accuracy."
    )


def _render_trends_analysis() -> None:
    """Render temporal trends and complexity analysis."""
    enhanced_stats = load_enhanced_statistics()
    
    st.markdown("### Temporal Trends")
    st.markdown("Analyze how oral arguments have evolved over time.")
    
    temporal = enhanced_stats.get("temporal_trends", {})
    complexity = enhanced_stats.get("complexity_analysis", {})
    networks = enhanced_stats.get("attorney_networks", {})
    parties = enhanced_stats.get("case_parties", {})
    
    if not temporal:
        st.info("Enhanced statistics not available. Run `python scripts/generate_enhanced_stats.py`.")
        return
    
    # Yearly trends
    st.markdown("#### Arguments by Year")
    yearly_data = temporal.get("yearly", {})
    if yearly_data:
        yearly_df = pd.DataFrame.from_dict(yearly_data, orient="index")
        yearly_df.index = yearly_df.index.astype(int)
        yearly_df = yearly_df.sort_index()
        
        col1, col2 = st.columns(2)
        with col1:
            fig_yearly = px.bar(
                yearly_df.reset_index(),
                x="index",
                y="total_arguments",
                title="Total Arguments Per Year",
                labels={"index": "Year", "total_arguments": "Arguments"}
            )
            fig_yearly.update_layout(plot_bgcolor="white", showlegend=False, xaxis={'type': 'category'})
            st.plotly_chart(fig_yearly, width="stretch")
        
        with col2:
            duration_df = yearly_df.reset_index().rename(columns={
                "avg_duration_min": "Avg Duration Min",
                "median_duration_min": "Median Duration Min",
            })
            fig_duration = px.line(
                duration_df,
                x="index",
                y=["Avg Duration Min", "Median Duration Min"],
                title="Argument Duration Trends",
                labels={"index": "Year", "value": "Minutes", "variable": "Metric"}
            )
            fig_duration.update_layout(plot_bgcolor="white", xaxis={'type': 'category'})
            st.plotly_chart(fig_duration, width="stretch")
        
        # Year-over-year growth
        yoy_growth = temporal.get("yoy_growth", {})
        if yoy_growth:
            growth_df = pd.DataFrame.from_dict(yoy_growth, orient="index", columns=["Growth %"])
            growth_df.index = growth_df.index.astype(int)
            growth_df = growth_df.sort_index()
            
            fig_growth = px.bar(
                growth_df.reset_index(),
                x="index",
                y="Growth %",
                title="Year-over-Year Change in Oral Argument Volume",
                labels={"index": "Year"},
                color="Growth %",
                color_continuous_scale=["red", "white", "green"]
            )
            fig_growth.update_layout(plot_bgcolor="white", xaxis={'type': 'category'})
            st.plotly_chart(fig_growth, width="stretch")
    
    # Seasonal patterns
    st.markdown("#### Seasonal Patterns")
    col3, col4 = st.columns(2)
    
    with col3:
        monthly_data = temporal.get("monthly", {})
        if monthly_data:
            monthly_df = pd.DataFrame.from_dict(monthly_data, orient="index")
            monthly_df.index = monthly_df.index.astype(int)
            monthly_df = monthly_df.sort_index()
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            monthly_df["Month"] = [month_names[i-1] for i in monthly_df.index]
            
            fig_monthly = px.bar(
                monthly_df,
                x="Month",
                y="total_arguments",
                title="Arguments by Month (All Years)",
                labels={"total_arguments": "Total Arguments"}
            )
            fig_monthly.update_layout(plot_bgcolor="white", showlegend=False)
            st.plotly_chart(fig_monthly, width="stretch")
    
    with col4:
        quarterly_data = temporal.get("quarterly", {})
        if quarterly_data:
            quarterly_df = pd.DataFrame.from_dict(quarterly_data, orient="index")
            quarterly_df.index = [f"Q{i}" for i in quarterly_df.index.astype(int)]
            
            fig_quarterly = px.pie(
                quarterly_df,
                values="total_arguments",
                names=quarterly_df.index,
                title="Arguments by Quarter"
            )
            st.plotly_chart(fig_quarterly, width="stretch")
    
    # Case complexity
    st.markdown("#### Case Complexity Analysis")
    st.markdown("Cases categorized by argument duration (quartiles).")
    
    if complexity:
        complexity_df = pd.DataFrame.from_dict(complexity, orient="index")
        complexity_df = complexity_df.reindex(["Simple", "Moderate", "Complex", "Very Complex"])
        
        col5, col6 = st.columns(2)
        with col5:
            fig_complexity = px.bar(
                complexity_df.reset_index(),
                x="index",
                y="count",
                title="Cases by Complexity",
                labels={"index": "Complexity", "count": "Number of Cases"},
                color="count",
                color_continuous_scale="Reds",
                text="count"
            )
            fig_complexity.update_traces(texttemplate='%{text:,}', textposition='outside')
            fig_complexity.update_layout(plot_bgcolor="white", showlegend=False)
            st.plotly_chart(fig_complexity, width="stretch")
        
        with col6:
            # Duration range chart
            duration_df = complexity_df[["min_duration", "avg_duration", "max_duration"]].reset_index()
            fig_duration = px.bar(
                duration_df,
                x="index",
                y=["min_duration", "avg_duration", "max_duration"],
                title="Duration Range by Complexity",
                labels={"index": "Complexity", "value": "Minutes", "variable": "Duration"},
                barmode="group"
            )
            fig_duration.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_duration, width="stretch")
        
        # Complexity details table
        with st.expander("View complexity details"):
            st.markdown(
                "This table groups cases by how long the oral argument lasted. ``Simple`` means shorter arguments, while ``Very Complex`` means longer arguments relative to the full collection." 
                "The categories are created by splitting the argument lengths into four equal groups."
            )
            complexity_df_display = complexity_df.copy()
            complexity_df_display.columns = ["Cases", "Avg Min", "Min Min", "Max Min", "Avg Segments"]
            st.dataframe(complexity_df_display, width="stretch")
    
    # Case types
    st.markdown("#### Case Types")
    case_types = parties.get("case_types", {})
    if case_types:
        fig_types = px.pie(
            values=list(case_types.values()),
            names=list(case_types.keys()),
            title="Distribution of Case Types"
        )
        st.plotly_chart(fig_types, width="stretch")
    
    # Attorney networks
    st.markdown("#### Attorney Networks")
    top_firms = networks.get("top_firms", [])
    if top_firms:
        firms_df = pd.DataFrame(top_firms[:15])
        fig_firms = px.bar(
            firms_df,
            x="attorney_count",
            y="firm",
            orientation="h",
            title="Largest Firms by Attorney Count",
            labels={"attorney_count": "Number of Attorneys", "firm": ""},
            color="attorney_count",
            color_continuous_scale="Reds"
        )
        fig_firms.update_layout(plot_bgcolor="white", yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_firms, width="stretch")
    
    solo_count = len(networks.get("solo_practitioners", []))
    if solo_count > 0:
        st.info(f"**{solo_count:,}** attorneys argue as solo practitioners.")


_style_page()
records = load_oral_arguments()
if not records:
    st.title("Oral Arguments")
    st.warning("No oral-argument data is available. Run `python scripts/refresh_oral_arguments.py`.")
    st.stop()

requested_argument = str(st.query_params.get("argument", "")).strip()
if requested_argument:
    _render_reader(requested_argument)
    add_gavel_glimpse_footer()
    st.stop()

st.markdown('<div class="oa-kicker">The court in its own words</div>', unsafe_allow_html=True)
st.title("Oral Arguments")
st.markdown(
    '<p class="oa-intro">Search and read machine-generated transcripts of New Hampshire Supreme Court oral arguments, then explore the shape of the collection.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="oa-disclosure"><strong>Beta collection:</strong> transcripts may contain errors, and speaker labels are inferred. Every record links to the original video.</div>',
    unsafe_allow_html=True,
)

_metric_row(collection_statistics(records))

statistics_tab, transcripts_tab, attorneys_tab, compare_tab, trends_tab = st.tabs([
    "Statistics", "Transcripts", "Attorneys & Firms", "Compare", "Trends & Analysis"
])
with statistics_tab:
    _render_statistics(records)
with transcripts_tab:
    _render_transcript_search(records)
with attorneys_tab:
    _render_attorney_statistics()
with compare_tab:
    _render_attorney_firm_comparison()
with trends_tab:
    _render_trends_analysis()

add_gavel_glimpse_footer()
