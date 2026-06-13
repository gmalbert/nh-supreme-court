"""
pages/02_Justices.py — Justice profiles, voting records, agreement matrix
"""

from __future__ import annotations

import ast
from datetime import date
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import APP_NAME, JUSTICE_DISPLAY, JUSTICE_KEYS, VOTE_COLORS
from utils.data_loader import load_opinions, load_opinions_json, load_justices, data_last_updated
from utils.charts import (
    agreement_heatmap,
    authorship_bar,
    opinions_per_year,
)
from footer import add_gavel_glimpse_footer


def _title_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [c.replace("_", " ").title() for c in out.columns]
    return out


def _format_token(value: str) -> str:
    return str(value).replace("_", " ").title()

logo_path = ROOT / "data_files" / "logo.png"
st.title("Justice Profiles & Voting")

df = load_opinions()
opinions_json = load_opinions_json()
justices_meta = load_justices()

if df.empty:
    st.warning("No data available. Run: `python scripts/update.py`")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Justices")
    active = [j for j in justices_meta.values() if j.get("is_active")]
    all_keys = [j["key"] for j in sorted(active, key=lambda x: (x["role"] != "chief_justice", x["last_name"]))]
    display_options = [JUSTICE_DISPLAY.get(k, k) for k in all_keys]
    selected_display = st.selectbox("Select Justice", display_options)
    selected_key = all_keys[display_options.index(selected_display)]

    st.divider()
    years = sorted(df["term_year"].dropna().unique().astype(int))
    year_range = st.slider("Year Range", min(years), max(years), (min(years), max(years)))
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

filtered_df = df[(df["term_year"] >= year_range[0]) & (df["term_year"] <= year_range[1])]


# ── Helper functions ───────────────────────────────────────────────────────────
def _get_participated(df, json_list, jkey, year_range):
    count = 0
    for rec in json_list:
        yr = rec.get("term_year") or rec.get("citation_year")
        if yr and year_range[0] <= int(yr) <= year_range[1] and _on_or_after_appointment(rec, jkey):
            votes = rec.get("votes", {})
            jvote = votes.get(jkey, {}).get("vote", "")
            if jvote in ("majority", "dissent", "concur_separate"):
                count += 1
    return count


def _get_dissent_cases(df, json_list, jkey, year_range):
    cases = []
    for rec in json_list:
        yr = rec.get("term_year") or rec.get("citation_year")
        if yr and year_range[0] <= int(yr) <= year_range[1] and _on_or_after_appointment(rec, jkey):
            votes = rec.get("votes", {})
            if votes.get(jkey, {}).get("vote") == "dissent":
                cases.append(rec)
    return cases


def _build_vote_table(df, json_list, jkey, year_range):
    rows = []
    for rec in json_list:
        yr = rec.get("term_year") or rec.get("citation_year")
        if yr and year_range[0] <= int(yr) <= year_range[1] and _on_or_after_appointment(rec, jkey):
            votes = rec.get("votes", {})
            jvote = votes.get(jkey, {}).get("vote", "not_participating")
            rows.append({
                "case_name": rec.get("case_name", ""),
                "citation": rec.get("citation", ""),
                "case_number": rec.get("case_number", ""),
                "date_issued": rec.get("date_issued", ""),
                "vote": jvote,
                "outcome": rec.get("outcome", ""),
            })
    return rows


def _parse_date_or_none(raw_value):
    if not raw_value:
        return None
    try:
        return date.fromisoformat(str(raw_value)[:10])
    except ValueError:
        return None


def _on_or_after_appointment(rec, jkey):
    meta = justices_meta.get(jkey, {})
    appointed = _parse_date_or_none(meta.get("date_appointed"))
    if not appointed:
        return True

    issued = _parse_date_or_none(rec.get("date_issued"))
    if issued:
        return issued >= appointed

    yr = rec.get("term_year") or rec.get("citation_year")
    try:
        return int(yr) >= appointed.year
    except (TypeError, ValueError):
        return True


def _build_agreement_matrix(json_list, year_range):
    active_keys = JUSTICE_KEYS
    co_counts = {k1: {k2: 0 for k2 in active_keys} for k1 in active_keys}
    agree_counts = {k1: {k2: 0 for k2 in active_keys} for k1 in active_keys}

    for rec in json_list:
        yr = rec.get("term_year") or rec.get("citation_year")
        if not yr or not (year_range[0] <= int(yr) <= year_range[1]):
            continue
        votes = rec.get("votes", {})
        for k1 in active_keys:
            v1 = votes.get(k1, {}).get("vote", "not_participating")
            if v1 in ("not_participating", "recused", "disqualified"):
                continue
            for k2 in active_keys:
                if k1 == k2:
                    continue
                v2 = votes.get(k2, {}).get("vote", "not_participating")
                if v2 in ("not_participating", "recused", "disqualified"):
                    continue
                co_counts[k1][k2] += 1
                if v1 == v2:
                    agree_counts[k1][k2] += 1

    matrix_data = {}
    for k1 in active_keys:
        row = {}
        for k2 in active_keys:
            if k1 == k2:
                row[k2] = 1.0
            elif co_counts[k1][k2] > 0:
                row[k2] = agree_counts[k1][k2] / co_counts[k1][k2]
            else:
                row[k2] = 0.0
        matrix_data[k1] = row

    return pd.DataFrame(matrix_data, index=active_keys, columns=active_keys)


tab1, tab2, tab3, tab4 = st.tabs(
    ["Justice Profile", "Voting Record", "Agreement Matrix", "Authorship Patterns"]
)

# ── Tab 1: Justice Profile ─────────────────────────────────────────────────────
with tab1:
    meta = justices_meta.get(selected_key, {})
    jname = JUSTICE_DISPLAY.get(selected_key, selected_key)
    appointed_on = _parse_date_or_none(meta.get("date_appointed"))

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader(jname)
        if meta:
            if meta.get('wikipedia_url'):
                st.markdown(f"[Wikipedia profile]({meta['wikipedia_url']})")
            st.markdown(f"**Role:** {meta.get('role','').replace('_',' ').title()}")
            st.markdown(f"**Appointed by:** {meta.get('appointed_by', '—')}")
            st.markdown(f"**Date Appointed:** {meta.get('date_appointed', '—')}")
            st.markdown(f"**Status:** {'Active' if meta.get('is_active') else 'Retired'}")

    with col2:
        # Stats
        authored = filtered_df[filtered_df["author"] == selected_key].copy()
        if appointed_on is not None and "date_issued" in authored.columns:
            authored = authored[
                pd.to_datetime(authored["date_issued"], errors="coerce").dt.date >= appointed_on
            ]
        participated = _get_participated(filtered_df, opinions_json, selected_key, year_range)
        dissent_cases = _get_dissent_cases(filtered_df, opinions_json, selected_key, year_range)

        m1, m2, m3 = st.columns(3)
        m1.metric("Opinions Authored", len(authored))
        m2.metric("Cases Participated", participated)
        m3.metric("Dissents Written", len(dissent_cases))

        if participated > 0:
            authorship_rate = len(authored) / participated * 100
            dissent_rate = len(dissent_cases) / participated * 100
            st.progress(authorship_rate / 100, text=f"Authorship rate: {authorship_rate:.1f}%")
            st.progress(dissent_rate / 100, text=f"Dissent rate: {dissent_rate:.1f}%")

    # Opinions per year for this justice
    if not authored.empty:
        per_year = authored.groupby("term_year").size().reset_index(name="count")
        import plotly.express as px
        fig = px.bar(
            per_year, x="term_year", y="count",
            labels={"term_year": "Year", "count": "Opinions Authored"},
            title=f"{jname} — Opinions Authored Per Year",
            color_discrete_sequence=["#003057"],
        )
        fig.update_layout(plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")

# ── Tab 2: Voting Record ───────────────────────────────────────────────────────
with tab2:
    vote_rows = _build_vote_table(filtered_df, opinions_json, selected_key, year_range)
    if vote_rows:
        vote_df = pd.DataFrame(vote_rows)
        vote_df["citation"] = vote_df["citation"].fillna("").astype(str).str.strip()
        vote_df.loc[vote_df["citation"] == "", "citation"] = vote_df["case_number"].fillna("unknown").astype(str)
        vote_df["vote"] = vote_df["vote"].map(_format_token)
        vote_df["outcome"] = vote_df["outcome"].map(_format_token)

        st.markdown(f"### {jname} — Voting Record ({year_range[0]}–{year_range[1]})")
        st.caption("Cases before this justice's appointment date are excluded.")

        # Summary pie
        vote_counts = vote_df["vote"].value_counts()
        import plotly.express as px
        fig_pie = px.pie(
            values=vote_counts.values,
            names=vote_counts.index,
            color=vote_counts.index,
            color_discrete_map={_format_token(k): v for k, v in VOTE_COLORS.items()},
            title="Vote Distribution",
        )
        st.plotly_chart(fig_pie, width="stretch")

        vote_display = vote_df[["case_name", "citation", "date_issued", "vote", "outcome"]]
        vote_display = _title_columns(vote_display)
        st.dataframe(
            vote_display,
            width="stretch",
            hide_index=True,
        )

        # Dissent list
        dissents = vote_df[vote_df["vote"].str.lower() == "dissent"]
        if not dissents.empty:
            with st.expander(f"Dissents ({len(dissents)})"):
                dissent_display = dissents[["case_name", "citation", "date_issued", "outcome"]]
                dissent_display = _title_columns(dissent_display)
                st.dataframe(
                    dissent_display,
                    width="stretch",
                    hide_index=True,
                )
    else:
        st.info("No voting records found in this date range.")

# ── Tab 3: Agreement Matrix ────────────────────────────────────────────────────
with tab3:
    st.markdown("### Pairwise Justice Agreement Rate")
    st.caption("Percentage of cases where both justices voted the same way (majority or dissent)")

    matrix = _build_agreement_matrix(opinions_json, year_range)
    if not matrix.empty:
        fig_heat = agreement_heatmap(matrix)
        st.plotly_chart(fig_heat, width="stretch")

        # Top aligned pairs
        pairs = []
        keys = matrix.index.tolist()
        for i, k1 in enumerate(keys):
            for k2 in keys[i+1:]:
                pairs.append({
                    "Justice A": JUSTICE_DISPLAY.get(k1, k1),
                    "Justice B": JUSTICE_DISPLAY.get(k2, k2),
                    "Agreement Rate": f"{matrix.loc[k1, k2]:.1%}",
                    "_rate": matrix.loc[k1, k2],
                })
        pair_df = pd.DataFrame(pairs).sort_values("_rate", ascending=False).drop(columns="_rate")
        st.subheader("Agreement Pairs")
        st.dataframe(pair_df, width="stretch", hide_index=True)
    else:
        st.info("Not enough data to compute agreement matrix.")

# ── Tab 4: Authorship Patterns ─────────────────────────────────────────────────
with tab4:
    st.markdown("### Authorship Distribution")
    fig_auth = authorship_bar(filtered_df)
    st.plotly_chart(fig_auth, width="stretch")

    # Per curiam trend
    pc_df = filtered_df[filtered_df["author"] == "per_curiam"]
    if not pc_df.empty:
        pc_per_year = pc_df.groupby("term_year").size().reset_index(name="per_curiam")
        total_per_year = filtered_df.groupby("term_year").size().reset_index(name="total")
        merged = pc_per_year.merge(total_per_year, on="term_year")
        merged["pct"] = merged["per_curiam"] / merged["total"] * 100
        import plotly.express as px
        fig_pc = px.line(
            merged, x="term_year", y="pct", markers=True,
            labels={"term_year": "Year", "pct": "% Per Curiam"},
            title="Per Curiam Frequency",
            color_discrete_sequence=["#C8960C"],
        )
        fig_pc.update_layout(plot_bgcolor="white")
        st.plotly_chart(fig_pc, width="stretch")

add_gavel_glimpse_footer()

