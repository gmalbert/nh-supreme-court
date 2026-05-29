"""
pages/05_Case_Orders.py — Non-precedential case orders browser
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME
from utils.data_loader import load_case_orders, data_last_updated

logo_path = ROOT / "data_files" / "logo.png"
st.title("Case Orders")
st.caption("Non-precedential orders (case orders + 3JX orders)")

df = load_case_orders()

if df.empty:
    st.info(
        "No case order data available yet.\n\n"
        "Run: `python scripts/update.py --type case_orders`"
    )
    st.stop()

SOURCE_LABELS = {
    "case_order": "Case Order",
    "3jx_order": "3JX Order",
}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    years = sorted(df["term_year"].dropna().unique().astype(int))
    selected_years = st.multiselect("Year(s)", years, default=years)

    type_map = {}
    if "case_type" in df.columns:
        for raw in sorted(df["case_type"].dropna().astype(str).unique()):
            label = raw.replace("_", " ").title()
            type_map[label] = raw
    selected_type_labels = st.multiselect("Case Type", sorted(type_map.keys()))
    selected_types = [type_map[label] for label in selected_type_labels]

    source_map = {}
    if "order_source" in df.columns:
        for raw in sorted(df["order_source"].dropna().astype(str).unique()):
            source_map[SOURCE_LABELS.get(raw, raw.replace("_", " ").title())] = raw
    selected_source_labels = st.multiselect("Order Source", sorted(source_map.keys()))
    selected_sources = [source_map[label] for label in selected_source_labels]

    search = st.text_input("Search case name")
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

# ── Apply filters ──────────────────────────────────────────────────────────────
filtered = df.copy()
if selected_years:
    filtered = filtered[filtered["term_year"].isin(selected_years)]
if selected_types:
    filtered = filtered[filtered["case_type"].isin(selected_types)]
if selected_sources:
    filtered = filtered[filtered["order_source"].isin(selected_sources)]
if search:
    filtered = filtered[filtered["case_name"].str.lower().str.contains(search.lower(), na=False)]

st.caption(f"Showing {len(filtered)} of {len(df)} orders")

# ── Case type distribution ───────────────────────────────────────────────────
if "case_type" in filtered.columns and not filtered.empty:
    col1, col2 = st.columns(2)
    with col1:
        ot_counts = filtered["case_type"].value_counts().reset_index()
        ot_counts.columns = ["case_type", "count"]
        ot_counts["case_type_label"] = (
            ot_counts["case_type"].astype(str).str.replace("_", " ").str.title()
        )
        fig_ot = px.bar(
            ot_counts,
            x="case_type_label", y="count",
            color_discrete_sequence=["#003057"],
            labels={"case_type_label": "Case Type", "count": "Orders"},
            title="Case Type Distribution",
        )
        fig_ot.update_layout(plot_bgcolor="white", xaxis_tickangle=-20)
        st.plotly_chart(fig_ot, width="stretch")

    with col2:
        if "term_year" in filtered.columns:
            yr_counts = filtered.groupby("term_year").size().reset_index(name="count")
            fig_yr = px.line(
                yr_counts, x="term_year", y="count", markers=True,
                labels={"term_year": "Year", "count": "Orders"},
                title="Orders Per Year",
                color_discrete_sequence=["#003057"],
            )
            fig_yr.update_layout(plot_bgcolor="white")
            st.plotly_chart(fig_yr, width="stretch")

# ── Table ──────────────────────────────────────────────────────────────────────
# Sort by date_issued descending, fall back to term_year then case_number
if "date_issued" in filtered.columns:
    filtered = filtered.copy()
    filtered["date_issued"] = pd.to_datetime(filtered["date_issued"], errors="coerce")
    filtered = filtered.sort_values("date_issued", ascending=False, na_position="last")

display_cols = [c for c in ["case_number", "case_name", "date_issued", "case_type", "outcome", "vote_string"]
                if c in filtered.columns]
if "order_source" in filtered.columns:
    display_cols.append("order_source")
table_df = filtered[display_cols].copy()
if "case_type" in table_df.columns:
    table_df["case_type"] = table_df["case_type"].astype(str).str.replace("_", " ").str.title()
if "outcome" in table_df.columns:
    table_df["outcome"] = table_df["outcome"].astype(str).str.replace("_", " ").str.title()
if "date_issued" in table_df.columns:
    table_df["date_issued"] = pd.to_datetime(table_df["date_issued"], errors="coerce").dt.date
if "order_source" in table_df.columns:
    table_df["order_source"] = table_df["order_source"].map(
        lambda v: SOURCE_LABELS.get(str(v), str(v).replace("_", " ").title())
    )
if "pdf_url" in filtered.columns:
    table_df["Decision"] = filtered["pdf_url"].fillna("").values

COL_LABELS = {
    "case_number": "Case Number",
    "case_name": "Case Name",
    "date_issued": "Date Issued",
    "case_type": "Case Type",
    "outcome": "Outcome",
    "vote_string": "Vote",
    "order_source": "Order Source",
    "Decision": "Decision",
}
table_df.columns = [COL_LABELS.get(c, c) for c in table_df.columns]

column_config = {}
if "Decision" in table_df.columns:
    column_config["Decision"] = st.column_config.LinkColumn("Decision", display_text="View ↗")

st.dataframe(
    table_df,
    width="stretch",
    hide_index=True,
    column_config=column_config,
)

# ── Download ───────────────────────────────────────────────────────────────────
st.sidebar.download_button(
    "⬇ Download Filtered CSV",
    data=filtered.to_csv(index=False),
    file_name="nh_sc_case_orders_filtered.csv",
    mime="text/csv",
)

