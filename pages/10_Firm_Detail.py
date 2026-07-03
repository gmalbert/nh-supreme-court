"""Individual law firm profile page showing their oral argument history and attorneys.

This page displays:
- Firm career statistics (total arguments, attorneys, time range)
- List of all attorneys from the firm
- List of all their oral arguments with links
- Charts showing activity over time

Usage:
    Navigate via firm name link from Attorneys & Firms tab, or direct URL with firm name
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from footer import add_gavel_glimpse_footer
from utils.data_loader import load_attorney_statistics, load_firm_metadata, load_oral_arguments


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


def _render_firm_profile(firm_name: str) -> None:
    """Render an individual firm's profile page."""
    attorney_data = load_attorney_statistics()
    
    if not attorney_data or not attorney_data.get("firm_stats"):
        st.error("Firm statistics are not available.")
        return
    
    # Find the firm
    firm = next(
        (f for f in attorney_data["firm_stats"] if f["firm_name"] == firm_name),
        None
    )
    
    if not firm:
        st.error(f"Firm '{firm_name}' not found.")
        st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
        return
    
    # Load firm metadata
    firm_metadata = load_firm_metadata()
    firm_info = firm_metadata.get("lookup", {}).get(firm_name, {})
    
    # Header
    st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
    
    # Display full name and website if available
    if firm_info:
        full_name = firm_info.get("full_name", firm_name)
        st.title(full_name)
        
        # Show website link if available
        if firm_info.get("website"):
            st.markdown(f"🌐 [{firm_info['website']}]({firm_info['website']})")
        
        # Show short name if different from full name
        if full_name != firm_name:
            st.caption(f"Also known as: {firm_name}")
    else:
        st.title(firm_name)
    
    st.caption(f"{firm['unique_attorneys']} attorneys")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Arguments", firm["total_arguments"])
    col2.metric("Attorneys", firm["unique_attorneys"])
    col3.metric("Total Time", f"{firm['total_duration_hours']:.1f} hours")
    col4.metric(
        "Active Period",
        f"{firm.get('first_argument_date', '')[:4]} - {firm.get('last_argument_date', '')[:4]}"
    )
    
    # Attorneys list
    st.subheader(f"Attorneys from {firm_name}")
    
    # Get stats for each attorney from this firm
    firm_attorneys = []
    for attorney_name in firm["attorneys"]:
        attorney_stat = next(
            (a for a in attorney_data["attorney_stats"] if a["attorney_name"] == attorney_name),
            None
        )
        if attorney_stat:
            firm_attorneys.append({
                "Attorney": attorney_name,
                "Arguments": attorney_stat["total_arguments"],
                "Total Hours": attorney_stat["total_duration_hours"],
                "Avg Minutes": attorney_stat["average_duration_minutes"]
            })
    
    if firm_attorneys:
        attorneys_df = pd.DataFrame(firm_attorneys)
        attorneys_df = attorneys_df.sort_values("Arguments", ascending=False)
        
        st.dataframe(
            attorneys_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Attorney": st.column_config.TextColumn("Attorney", width="large"),
                "Arguments": st.column_config.NumberColumn("Arguments", format="%d"),
                "Total Hours": st.column_config.NumberColumn("Total Hours", format="%.1f"),
                "Avg Minutes": st.column_config.NumberColumn("Avg Minutes", format="%.0f")
            }
        )
        st.caption("To view individual attorney profiles, use the 'Attorney Profile' page in the sidebar.")
    else:
        st.info("Attorney details not available.")
    
    # Activity over time
    st.subheader("Arguments Over Time")
    if firm.get("years_active"):
        year_data = [{"Year": year, "Arguments": count} for year, count in firm["years_active"].items()]
        year_df = pd.DataFrame(year_data).sort_values("Year")
        
        fig_timeline = px.bar(
            year_df,
            x="Year",
            y="Arguments",
            title="Annual Argument Count",
            color_discrete_sequence=["#b54f2f"]
        )
        fig_timeline.update_layout(plot_bgcolor="white", xaxis={'type': 'category'})
        st.plotly_chart(fig_timeline, width="stretch")
    else:
        st.info("Timeline data not available.")
    
    # Case list
    st.subheader(f"All {firm['total_arguments']} Arguments")
    
    # Load full oral arguments data to get case names and dates
    oral_args = load_oral_arguments()
    case_details = []
    for case_num in firm["cases"]:
        case = next((c for c in oral_args if c["case_number"] == case_num), None)
        if case:
            # Find which attorney(s) from this firm argued this case
            case_attorneys = attorney_data["case_attorneys"].get(case_num, [])
            firm_attorneys_in_case = [
                a["name"] for a in case_attorneys
                if a.get("firm") == firm_name
            ]
            
            case_details.append({
                "Docket": case_num,
                "Case Name": case.get("case_name", ""),
                "Argument Date": case.get("argument_date", ""),
                "Attorney": ", ".join(firm_attorneys_in_case),
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
                "Attorney": st.column_config.TextColumn("Attorney", width="medium"),
                "Duration": st.column_config.TextColumn("Duration", width="small"),
                "Words": st.column_config.NumberColumn("Words", format="%d"),
                "Opinion": st.column_config.LinkColumn("Opinion", display_text="View")
            }
        )
    else:
        st.info("Case details not available.")


# Main entry point
firm_short_name = None

# Check for query parameter first
if "firm" in st.query_params:
    firm_short_name = st.query_params["firm"]

# Load all firms for selection
attorney_data = load_attorney_statistics()
firm_metadata = load_firm_metadata()

if not attorney_data or not attorney_data.get("firm_stats"):
    st.error("Firm statistics are not available.")
    st.markdown('<a href="oral-arguments" target="_self">← Back to Oral Arguments</a>', unsafe_allow_html=True)
else:
    # Create a mapping from short name to full name and vice-versa
    firm_stats_short_names = {f["firm_name"] for f in attorney_data["firm_stats"]}
    
    short_to_full_name = {
        short: firm_metadata.get("lookup", {}).get(short, {}).get("full_name", short)
        for short in firm_stats_short_names
    }
    full_to_short_name = {v: k for k, v in short_to_full_name.items()}
    
    # Firm selection dropdown
    sorted_full_names = sorted(list(full_to_short_name.keys()))
    
    # Show landing page or profile
    if firm_short_name and firm_short_name in firm_stats_short_names:
        # Coming from a link - show profile directly
        _render_firm_profile(firm_short_name)
        
        # Add selector at bottom to switch firms
        st.divider()
        st.markdown("### View Another Firm")
        
        current_full_name = short_to_full_name.get(firm_short_name, firm_short_name)
        try:
            default_index = sorted_full_names.index(current_full_name)
        except ValueError:
            default_index = 0
            
        selected_full_name = st.selectbox(
            "Select a firm:",
            sorted_full_names,
            index=default_index,
            key="firm_selector"
        )
        
        selected_short_name = full_to_short_name.get(selected_full_name)
        if selected_short_name and selected_short_name != firm_short_name:
            st.query_params["firm"] = selected_short_name
            st.rerun()
    else:
        # Landing page - show selector
        st.title("Law Firm Profiles")
        st.markdown(f"Select from **{len(sorted_full_names):,}** law firms that have argued before the NH Supreme Court.")
        
        selected_full_name = st.selectbox(
            "Select a firm to view their profile:",
            [""] + sorted_full_names,
            index=0
        )
        
        if selected_full_name:
            selected_short_name = full_to_short_name.get(selected_full_name)
            if selected_short_name:
                # Set query param and rerun to load the profile page
                st.query_params["firm"] = selected_short_name
                st.rerun()
            else:
                st.error("Could not find the selected firm.")

add_gavel_glimpse_footer()
