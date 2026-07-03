"""Individual attorney profile page showing their oral argument history and statistics.

This page displays:
- Attorney career statistics (total arguments, duration, time range)
- List of all their oral arguments with links
- Charts showing activity over time
- Firm affiliation
- Side representation breakdown

Usage:
    Navigate via attorney name link from Attorneys & Firms tab, or direct URL with attorney name
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from footer import add_gavel_glimpse_footer
from utils.data_loader import load_attorney_statistics, load_oral_arguments


def format_duration(seconds: int | None) -> str:
    """Format duration as MM:SS or HH:MM:SS."""
    if not seconds:
        return "0:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _render_attorney_profile(attorney_name: str) -> None:
    """Render an individual attorney's profile page."""
    attorney_data = load_attorney_statistics()
    
    if not attorney_data or not attorney_data.get("attorney_stats"):
        st.error("Attorney statistics are not available.")
        return
    
    # Find the attorney
    attorney = next(
        (a for a in attorney_data["attorney_stats"] if a["attorney_name"] == attorney_name),
        None
    )
    
    if not attorney:
        st.error(f"Attorney '{attorney_name}' not found.")
        st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
        return
    
    # Header
    st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
    st.title(attorney_name)
    if attorney["firm"]:
        st.caption(attorney["firm"])
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Arguments", attorney["total_arguments"])
    col2.metric("Total Time", f"{attorney['total_duration_hours']:.1f} hours")
    col3.metric("Avg Duration", f"{attorney['average_duration_minutes']:.0f} min")
    col4.metric(
        "Active Period",
        f"{attorney.get('first_argument_date', '')[:4]} - {attorney.get('last_argument_date', '')[:4]}"
    )
    
    # Side representation breakdown
    st.subheader("Side Representation")
    sides_data = []
    for side, count in attorney["sides"].items():
        if count > 0:
            sides_data.append({"Side": side.capitalize(), "Cases": count})
    
    if sides_data:
        sides_df = pd.DataFrame(sides_data)
        fig_sides = px.pie(
            sides_df,
            names="Side",
            values="Cases",
            title="Cases by Side",
            hole=0.3
        )
        st.plotly_chart(fig_sides, width="stretch")
    else:
        st.info("Side information not available.")
    
    # Activity over time
    st.subheader("Arguments Over Time")
    if attorney.get("years_active"):
        year_data = [{"Year": year, "Arguments": count} for year, count in attorney["years_active"].items()]
        year_df = pd.DataFrame(year_data).sort_values("Year")
        
        fig_timeline = px.bar(
            year_df,
            x="Year",
            y="Arguments",
            title="Annual Argument Count",
            color_discrete_sequence=["#003057"]
        )
        fig_timeline.update_layout(plot_bgcolor="white", xaxis={'type': 'category'})
        st.plotly_chart(fig_timeline, width="stretch")
    else:
        st.info("Timeline data not available.")
    
    # Case list
    st.subheader(f"All {attorney['total_arguments']} Arguments")
    
    # Load full oral arguments data to get case names and dates
    oral_args = load_oral_arguments()
    case_details = []
    for case_num in attorney["cases"]:
        case = next((c for c in oral_args if c["case_number"] == case_num), None)
        if case:
            case_details.append({
                "Docket": case_num,
                "Case Name": case.get("case_name", ""),
                "Argument Date": case.get("argument_date", ""),
                "Duration": format_duration(case.get("duration_seconds")),
                "Words": case.get("word_count", 0),
                "Opinion": f"/opinions?docket={case_num}"
            })
    
    if case_details:
        cases_df = pd.DataFrame(case_details)
        cases_df = cases_df.sort_values("Argument Date", ascending=False)
        
        st.dataframe(
            cases_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Docket": st.column_config.TextColumn("Docket", width="small"),
                "Case Name": st.column_config.TextColumn("Case Name", width="large"),
                "Argument Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                "Duration": st.column_config.TextColumn("Duration", width="small"),
                "Words": st.column_config.NumberColumn("Words", format="%d"),
                "Opinion": st.column_config.LinkColumn("Opinion", display_text="View")
            }
        )
    else:
        st.info("Case details not available.")


# Main entry point
attorney_name = None

# Check for query parameter first
if "attorney" in st.query_params:
    attorney_name = st.query_params["attorney"]

# Load all attorneys for selection
attorney_data = load_attorney_statistics()

if not attorney_data or not attorney_data.get("attorney_stats"):
    st.error("Attorney statistics are not available.")
    st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
else:
    # Attorney selection dropdown - sort by last name
    def get_last_name(full_name: str) -> str:
        """Extract last name for sorting."""
        parts = full_name.strip().split()
        # Handle suffixes (Jr., III, etc.)
        if len(parts) > 1 and parts[-1].rstrip('.') in ['Jr', 'Sr', 'II', 'III', 'IV', 'Esq']:
            return parts[-2] if len(parts) > 2 else parts[-1]
        return parts[-1] if parts else full_name
    
    attorney_names = sorted(
        [a["attorney_name"] for a in attorney_data["attorney_stats"]],
        key=lambda name: (get_last_name(name), name)
    )
    
    # Show landing page or profile
    if attorney_name and attorney_name in attorney_names:
        # Coming from a link - show profile directly
        _render_attorney_profile(attorney_name)
        
        # Add selector at bottom to switch attorneys
        st.divider()
        st.markdown("### View Another Attorney")
        default_index = attorney_names.index(attorney_name)
        selected_attorney = st.selectbox(
            "Select an attorney:",
            attorney_names,
            index=default_index,
            key="attorney_selector"
        )
        if selected_attorney != attorney_name:
            st.query_params["attorney"] = selected_attorney
            st.rerun()
    else:
        # Landing page - show selector
        st.title("Attorney Profiles")
        st.markdown(f"Select from **{len(attorney_names):,}** attorneys who have argued before the NH Supreme Court.")
        
        selected_attorney = st.selectbox(
            "Select an attorney to view their profile:",
            [""] + attorney_names,
            index=0
        )
        
        if selected_attorney:
            _render_attorney_profile(selected_attorney)

add_gavel_glimpse_footer()
