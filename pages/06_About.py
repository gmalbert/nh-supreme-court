"""
pages/06_About.py — About Granite State Appeals, methodology, and data sources
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME
from utils.data_loader import load_justices, load_opinions, data_last_updated

logo_path = ROOT / "data_files" / "logo.png"
st.title(f"About {APP_NAME}")
st.caption("NH Supreme Court Analytics")

df = load_opinions()
justices_meta = load_justices()

with st.sidebar:
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

st.markdown("""
## What is Granite State Appeals?

**Granite State Appeals** is an open-source data analytics platform for exploring the opinions and 
orders of the New Hampshire Supreme Court. It parses and structures the court's 
published PDFs to make the court's work searchable, analyzable, and accessible.

> **Not legal advice.** This tool is for research, journalism, and public interest purposes only.

---

## Methodology

### Vote Parsing
The concurrence/dissent block at the end of each opinion is parsed using regular expressions 
to identify each justice's vote (majority, dissent, concurred separately, not participating).

### Topic Tagging
Topics are assigned using keyword matching against a curated taxonomy of legal topic keywords. 
Assignments are approximate — complex cases touching multiple areas may not be fully captured.

### Known Limitations
- PDFs with unusual formatting may parse partially or incorrectly
- Per curiam opinions have no single author
- Justice roster changes (retirements, appointments) require manual updates
- Case orders receive simpler parsing than full opinions

---
""")

# ── Justice Roster ─────────────────────────────────────────────────────────────
st.subheader("Current Justice Roster")
if justices_meta:
    import pandas as pd
    active = [j for j in justices_meta.values() if j.get("is_active")]
    retired = [j for j in justices_meta.values() if not j.get("is_active")]

    active_df = pd.DataFrame(active)[
        ["display_name", "role", "appointed_by", "date_appointed", "political_affiliation"]
    ].rename(columns={
        "display_name": "Justice",
        "role": "Role",
        "appointed_by": "Appointed By",
        "date_appointed": "Date Appointed",
        "political_affiliation": "Appointing Gov. Party",
    })
    active_df["Role"] = active_df["Role"].str.replace("_", " ").str.title()
    st.dataframe(active_df, width="stretch", hide_index=True)

    with st.expander("Retired Justices"):
        if retired:
            ret_df = pd.DataFrame(retired)[
                ["display_name", "role", "appointed_by", "date_appointed", "date_retired"]
            ].copy()
            ret_df["date_appointed"] = ret_df["date_appointed"].apply(
                lambda x: str(x)[:4] if x and str(x) not in ("", "nan", "None") else "—"
            )
            ret_df["date_retired"] = ret_df["date_retired"].apply(
                lambda x: str(x)[:4] if x and str(x) not in ("", "nan", "None") else "—"
            )
            ret_df.columns = ["Justice", "Role", "Appointed By", "Year Appointed", "Year Retired"]
            ret_df["Role"] = ret_df["Role"].str.replace("_", " ").str.title()
            st.dataframe(ret_df, width="stretch", hide_index=True)

st.divider()

# ── Dataset Stats ──────────────────────────────────────────────────────────────
st.subheader("Dataset Statistics")
if not df.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opinions", len(df))
    col2.metric("Years Covered", f"{int(df['term_year'].min())}–{int(df['term_year'].max())}")
    col3.metric("Last Updated", data_last_updated())

st.markdown("""
---

*Granite State Appeals is not affiliated with the New Hampshire Judicial Branch or any government entity.*
""")

