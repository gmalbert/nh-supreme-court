"""
Opinion comparison page: side-by-side case analysis.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from utils.data_loader import load_opinions, load_opinion_text
from utils.similar_cases import explain_similarity
from utils.bookmarks import render_bookmark_button
from utils.site_chrome import render_data_status


st.set_page_config(page_title="Compare Cases", layout="wide")

render_data_status()

st.title("🔍 Compare Cases")
st.markdown("Side-by-side comparison of two NH Supreme Court opinions")

# Load opinions
opinions_df = load_opinions()

if opinions_df.empty:
    st.warning("No opinions data available")
    st.stop()

# Create selection inputs
col1, col2 = st.columns(2)

with col1:
    st.subheader("Case 1")
    
    # Search for first case
    search1 = st.text_input("Search case 1", key="search1", placeholder="Enter case name or number")
    
    if search1:
        filtered1 = opinions_df[
            opinions_df["case_name"].str.contains(search1, case=False, na=False) |
            opinions_df["case_number"].str.contains(search1, case=False, na=False)
        ]
    else:
        filtered1 = opinions_df.head(20)
    
    case1_options = filtered1.apply(
        lambda x: f"{x['case_number']} - {x['case_name']}", axis=1
    ).tolist()
    
    case1_selection = st.selectbox("Select case 1", case1_options, key="case1_select")
    
    if case1_selection:
        case1_number = case1_selection.split(" - ")[0]
        case1_row = opinions_df[opinions_df["case_number"] == case1_number].iloc[0]

with col2:
    st.subheader("Case 2")
    
    # Search for second case
    search2 = st.text_input("Search case 2", key="search2", placeholder="Enter case name or number")
    
    if search2:
        filtered2 = opinions_df[
            opinions_df["case_name"].str.contains(search2, case=False, na=False) |
            opinions_df["case_number"].str.contains(search2, case=False, na=False)
        ]
    else:
        filtered2 = opinions_df.head(20)
    
    case2_options = filtered2.apply(
        lambda x: f"{x['case_number']} - {x['case_name']}", axis=1
    ).tolist()
    
    case2_selection = st.selectbox("Select case 2", case2_options, key="case2_select")
    
    if case2_selection:
        case2_number = case2_selection.split(" - ")[0]
        case2_row = opinions_df[opinions_df["case_number"] == case2_number].iloc[0]

# Display comparison if both cases selected
if case1_selection and case2_selection:
    
    st.markdown("---")
    
    # Similarity explanation
    if case1_number != case2_number:
        explanations = explain_similarity(
            case1_row.to_dict(),
            case2_row.to_dict(),
        )
        
        if explanations:
            st.info("**Why these cases are related:**\n\n" + "\n".join(f"• {e}" for e in explanations))
    
    st.markdown("---")
    
    # Side-by-side metadata
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"### {case1_row['case_name']}")
        st.caption(case1_row.get("citation", case1_number))
        
        render_bookmark_button(
            case1_number,
            case1_row["case_name"],
            case1_row.get("citation", ""),
        )
        
        st.markdown("**Date Issued:** " + str(case1_row.get("date_issued", "N/A")))
        st.markdown("**Author:** " + str(case1_row.get("author", "N/A")))
        st.markdown("**Outcome:** " + str(case1_row.get("outcome", "N/A")))
        
        if pd.notna(case1_row.get("topics")):
            topics1 = case1_row["topics"]
            if isinstance(topics1, list):
                st.markdown("**Topics:** " + ", ".join(topics1))
            else:
                st.markdown("**Topics:** " + str(topics1))
        
        if pd.notna(case1_row.get("summary_paragraph")):
            with st.expander("Summary"):
                st.markdown(case1_row["summary_paragraph"])
    
    with col2:
        st.markdown(f"### {case2_row['case_name']}")
        st.caption(case2_row.get("citation", case2_number))
        
        render_bookmark_button(
            case2_number,
            case2_row["case_name"],
            case2_row.get("citation", ""),
        )
        
        st.markdown("**Date Issued:** " + str(case2_row.get("date_issued", "N/A")))
        st.markdown("**Author:** " + str(case2_row.get("author", "N/A")))
        st.markdown("**Outcome:** " + str(case2_row.get("outcome", "N/A")))
        
        if pd.notna(case2_row.get("topics")):
            topics2 = case2_row["topics"]
            if isinstance(topics2, list):
                st.markdown("**Topics:** " + ", ".join(topics2))
            else:
                st.markdown("**Topics:** " + str(topics2))
        
        if pd.notna(case2_row.get("summary_paragraph")):
            with st.expander("Summary"):
                st.markdown(case2_row["summary_paragraph"])
    
    st.markdown("---")
    
    # Load full texts
    text1 = load_opinion_text(case1_number)
    text2 = load_opinion_text(case2_number)
    
    # Display full texts side-by-side
    st.subheader("Full Opinion Text")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if text1:
            with st.container(height=600):
                st.markdown(text1)
        else:
            st.info("Full text not available")
    
    with col2:
        if text2:
            with st.container(height=600):
                st.markdown(text2)
        else:
            st.info("Full text not available")

else:
    st.info("Select two cases above to compare them side-by-side")
