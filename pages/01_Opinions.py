"""
pages/01_Opinions.py — Full searchable/filterable opinions browser
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, OUTCOME_COLORS, OUTCOME_LABELS, JUSTICE_DISPLAY
from utils.data_loader import load_opinions, load_opinion_text, data_last_updated


def _clean_summary_text(value: str) -> str:
    cleaned = str(value).replace("\ufffd", "").strip()
    cleaned = re.sub(r"^\s*[][(){}\"'“”‘’`]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[][(){}\"'“”‘’`]+\s*$", "", cleaned)
    return cleaned.strip()

logo_path = ROOT / "data_files" / "logo.png"
st.title("Opinions Browser")

df = load_opinions()

if df.empty:
    st.warning("No data available. Run the data pipeline first: `python scripts/update.py`")
    st.stop()

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    years = sorted(df["term_year"].dropna().unique().astype(int))
    selected_years = st.multiselect("Year(s)", years, default=years[-3:] if len(years) >= 3 else years)

    outcomes = sorted(df["outcome"].dropna().astype(str).unique())
    outcome_labels = [OUTCOME_LABELS.get(o, o.replace("_", " ").title()) for o in outcomes]
    selected_outcome_labels = st.multiselect("Outcome", outcome_labels)
    selected_outcomes = [o for o in outcomes if OUTCOME_LABELS.get(o, o.replace("_", " ").title()) in selected_outcome_labels]

    authors = sorted(df["author"].dropna().unique())
    author_labels = [JUSTICE_DISPLAY.get(a, a) for a in authors]
    selected_author_labels = st.multiselect("Opinion Author", author_labels)
    selected_authors = [a for a, l in zip(authors, author_labels) if l in selected_author_labels]

    vote_filter = st.selectbox(
        "Decision Type",
        ["All", "Unanimous", "Divided (dissent)", "Separate concurrence"],
    )

    search_query = st.text_input("Search case name or RSA", "")
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

# ── Apply filters ──────────────────────────────────────────────────────────────
filtered = df.copy()

if selected_years:
    filtered = filtered[filtered["term_year"].isin(selected_years)]

if selected_outcomes:
    filtered = filtered[filtered["outcome"].isin(selected_outcomes)]

if selected_authors:
    filtered = filtered[filtered["author"].isin(selected_authors)]

if vote_filter == "Unanimous":
    filtered = filtered[filtered["is_unanimous"] == True]
elif vote_filter == "Divided (dissent)":
    filtered = filtered[filtered["has_dissent"] == True]
elif vote_filter == "Separate concurrence":
    filtered = filtered[filtered["has_separate_concurrence"] == True]

if search_query:
    q = search_query.lower()
    mask = (
        filtered["case_name"].str.lower().str.contains(q, na=False)
        | filtered["rsa_citations"].str.lower().str.contains(q, na=False)
        | filtered["case_number"].str.lower().str.contains(q, na=False)
    )
    filtered = filtered[mask]

st.caption(f"Showing {len(filtered)} of {len(df)} opinions")

# ── Table ──────────────────────────────────────────────────────────────────────
display_cols = ["citation", "case_name", "date_issued", "author_display", "vote_string", "outcome"]
available = [c for c in display_cols if c in filtered.columns]

# Prettify for display
table_df = filtered[available].copy()
if "outcome" in table_df.columns:
    table_df["outcome"] = (
        table_df["outcome"]
        .map(lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title()) if pd.notna(o) else "—")
        .fillna("—")
    )
table_df.columns = [c.replace("_", " ").title() for c in available]
# Add PDF link column
if "pdf_url" in filtered.columns:
    table_df["PDF"] = filtered["pdf_url"].fillna("").values

selected_rows = st.dataframe(
    table_df,
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="opinions_table",
    column_config={
        "PDF": st.column_config.LinkColumn("PDF", display_text="View ↗"),
    },
)

# ── Detail panel on row click ──────────────────────────────────────────────────
if selected_rows and selected_rows.selection.rows:
    idx = selected_rows.selection.rows[0]
    row = filtered.iloc[idx]
    cn = row["case_number"]

    st.divider()
    st.subheader(str(row.get("case_name", "—")))

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"**Citation:** {row.get('citation', '—')}")
        st.markdown(f"**Case Number:** {cn}")
        _pdf = row.get("pdf_url", "")
        if _pdf and str(_pdf) not in ("", "nan"):
            st.markdown(f"[View Full Opinion PDF ↗]({_pdf})")
        date_argued = row.get("date_argued")
        date_issued = row.get("date_issued")
        if pd.notna(date_argued) and str(date_argued) != "nan":
            st.markdown(f"**Argued:** {str(date_argued)[:10]}")
        if pd.notna(date_issued) and str(date_issued) != "nan":
            st.markdown(f"**Decided:** {str(date_issued)[:10]}")

        outcome = row.get("outcome")
        if outcome and str(outcome) != "nan":
            color = OUTCOME_COLORS.get(outcome, "#607D8B")
            label = OUTCOME_LABELS.get(outcome, outcome.replace("_", " ").title())
            st.markdown(
                f'<span style="background:{color};color:white;padding:4px 12px;'
                f'border-radius:4px;font-weight:bold;">{label}</span>',
                unsafe_allow_html=True,
            )

        summary = row.get("summary_paragraph", "")
        if summary and str(summary) != "nan":
            clean_summary = _clean_summary_text(summary)
            st.markdown(f"\n{clean_summary[:500]}..." if len(str(clean_summary)) > 500 else f"\n{clean_summary}")

    with c2:
        st.markdown(f"**Author:** {row.get('author_display', '—')}")
        st.markdown(f"**Vote:** {row.get('vote_string', '—')}")

    # Download single case
    case_text = load_opinion_text(cn)
    if case_text:
        with st.expander("Read Full Opinion"):
            st.text(case_text[:5000] + ("..." if len(case_text) > 5000 else ""))

# ── CSV download ───────────────────────────────────────────────────────────────
st.sidebar.download_button(
    "⬇ Download Filtered CSV",
    data=filtered.to_csv(index=False),
    file_name="nh_sc_opinions_filtered.csv",
    mime="text/csv",
)

