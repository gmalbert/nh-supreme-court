"""Editable feedback form for reviewing law-firm merges and naming cleanup."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from footer import add_gavel_glimpse_footer
from utils.data_loader import load_attorney_statistics


st.set_page_config(page_title="Review Law Firms", layout="wide")

ROOT = Path(__file__).resolve().parent.parent
FIRM_SOURCE_FILE = ROOT / "data" / "nh_supreme_court_firms_enriched_v7.csv"
REVIEW_ACTIONS = [
    "Keep",
    "Merge into existing firm",
    "Rename firm",
    "Remove from directory",
    "Needs research",
]


def load_review_rows() -> pd.DataFrame:
    """Return every current directory firm with source aliases and counts."""
    attorney_data = load_attorney_statistics()
    firm_stats = attorney_data.get("firm_stats", []) if attorney_data else []
    if not firm_stats:
        return pd.DataFrame()

    source = pd.read_csv(FIRM_SOURCE_FILE, keep_default_na=False)
    source = source[
        ~source["review_status"].str.lower().str.startswith("skipped —")
        & source["full_name"].str.strip().ne("")
    ]
    aliases = (
        source.groupby("full_name")["short_name"]
        .agg(lambda values: ", ".join(sorted(set(value for value in values if value))))
        .to_dict()
    )
    statuses = (
        source.groupby("full_name")["review_status"]
        .agg(lambda values: " | ".join(sorted(set(value for value in values if value))))
        .to_dict()
    )

    rows = [
        {
            "Canonical firm name": firm["firm_name"],
            "Known abbreviation(s)": aliases.get(firm["firm_name"], ""),
            "Arguments": firm["total_arguments"],
            "Attorneys": firm["unique_attorneys"],
            "Source review status": statuses.get(firm["firm_name"], ""),
            "Feedback action": "Keep",
            "Merge / canonical target": "",
            "Notes": "",
        }
        for firm in firm_stats
    ]
    return pd.DataFrame(rows).sort_values("Canonical firm name", ignore_index=True)


st.title("Review Law Firm Directory")
st.caption(
    "Use this form to identify duplicate firms, historical aliases, naming corrections, "
    "or records that should not be profiles. Download your feedback when finished."
)

review_rows = load_review_rows()
if review_rows.empty:
    st.error("The firm directory statistics are unavailable.")
    st.stop()

st.metric("Current law-firm records", len(review_rows))
st.info(
    "For **Merge into existing firm** or **Rename firm**, enter the surviving or corrected "
    "firm name in **Merge / canonical target**. For **Remove** or **Needs research**, add a note."
)

edited_rows = st.data_editor(
    review_rows,
    width="stretch",
    hide_index=True,
    disabled=[
        "Canonical firm name",
        "Known abbreviation(s)",
        "Arguments",
        "Attorneys",
        "Source review status",
    ],
    column_config={
        "Arguments": st.column_config.NumberColumn(format="%d"),
        "Attorneys": st.column_config.NumberColumn(format="%d"),
        "Feedback action": st.column_config.SelectboxColumn(
            "Feedback action", options=REVIEW_ACTIONS, required=True
        ),
        "Merge / canonical target": st.column_config.TextColumn(
            "Merge / canonical target", width="large"
        ),
        "Notes": st.column_config.TextColumn("Notes", width="large"),
    },
    key="firm_review_editor",
)

feedback_rows = edited_rows[edited_rows["Feedback action"] != "Keep"]
st.caption(f"{len(feedback_rows):,} proposed change(s)")
st.download_button(
    "Download feedback CSV",
    feedback_rows.to_csv(index=False),
    file_name="nh_law_firm_review_feedback.csv",
    mime="text/csv",
    disabled=feedback_rows.empty,
)

add_gavel_glimpse_footer()
