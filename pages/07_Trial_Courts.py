"""
pages/07_Trial_Courts.py — Lower / trial court outcome analysis
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import OUTCOME_COLORS, OUTCOME_LABELS
from utils.data_loader import load_opinions, data_last_updated

# ── Page header ────────────────────────────────────────────────────────────────
st.title("Trial Courts")
st.caption("How the NH Supreme Court rules on appeals from each lower court and judge")

df = load_opinions()
if df.empty:
    st.warning("No data available. Run: `python scripts/update.py`")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
logo_path = ROOT / "data_files" / "logo.png"
with st.sidebar:
    st.header("Filters")
    years = sorted(df["term_year"].dropna().unique().astype(int))
    selected_years = st.multiselect("Year(s)", years, default=years)
    min_cases = st.slider("Min cases to show", 2, 10, 3)
    if logo_path.exists():
        st.image(str(logo_path), width=150)
    st.caption(f"Last updated: {data_last_updated()}")

# Apply year filter before everything else
if selected_years:
    df = df[df["term_year"].isin(selected_years)].copy()

# ── Derive fields ──────────────────────────────────────────────────────────────
# Extract the base court name (strip trailing "(Judge, J.)" if present)
_JUDGE_PAREN_RE = re.compile(r"\s*\([A-Za-z\s.'\u2018\u2019-]+,\s*(?:C\.J\.|JJ\.|J\.)\)\s*$")
# Extract judge last name from parenthetical "(Smith, J.)"
_JUDGE_EXTRACT_RE = re.compile(r"\(([A-Za-z\s.'\u2018\u2019-]+),\s*(?:C\.J\.|JJ\.|J\.)\)")

df_lc = df[df["lower_court"].notna()].copy()

df_lc["court_base"] = df_lc["lower_court"].str.replace(_JUDGE_PAREN_RE, "", regex=True).str.strip()


def _clean_court_base(value: str) -> str:
    s = str(value).strip()
    # Trim obvious sentence fragments that leak in from opinion text.
    s = s.split(";")[0].strip()
    s = re.sub(r"\s+", " ", s)
    low = s.lower()
    if "family court" in low and "circuit" not in low:
        return "Family Court"
    return s


df_lc["court_base"] = df_lc["court_base"].apply(_clean_court_base)

# Extract judge from lower_court column (better coverage than lower_court_judge)
def _extract_judge(lc: str) -> str | None:
    m = _JUDGE_EXTRACT_RE.search(lc)
    return m.group(1).strip() if m else None

df_lc["judge"] = df_lc["lower_court"].apply(_extract_judge)

# Derive broad court type
def _court_type(base: str) -> str:
    b = base.lower()
    if "circuit" in b and "family" in b:
        return "Circuit Court – Family Division"
    if "circuit" in b and "district" in b:
        return "Circuit Court – District Division"
    if "circuit" in b and "probate" in b:
        return "Circuit Court – Probate Division"
    if "circuit" in b:
        return "Circuit Court"
    if "superior" in b:
        return "Superior Court"
    if "probate" in b:
        return "Probate Court"
    return base

df_lc["court_type"] = df_lc["court_base"].apply(_court_type)

# Map outcomes to clean labels
df_lc["outcome_label"] = df_lc["outcome"].map(
    lambda o: OUTCOME_LABELS.get(o, str(o).replace("_", " ").title()) if pd.notna(o) else None
)
df_lc_out = df_lc[df_lc["outcome_label"].notna()].copy()

# ── Overview metrics ───────────────────────────────────────────────────────────
total_with_court = len(df_lc)
affirmed = (df_lc_out["outcome"] == "affirmed").sum()
reversed_total = df_lc_out["outcome"].isin(["reversed", "reversed_and_remanded"]).sum()
affirm_rate = affirmed / len(df_lc_out) * 100 if len(df_lc_out) else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Cases with Court Data", total_with_court)
m2.metric("Affirmance Rate", f"{affirm_rate:.0f}%")
m3.metric("Affirmed", affirmed)
m4.metric("Reversed / Rev'd & Remanded", reversed_total)

st.divider()

# ── Helper: ordered outcome category list ─────────────────────────────────────
OUTCOME_ORDER = [
    "Affirmed", "Remanded", "Affirmed & Remanded",
    "Reversed & Remanded", "Reversed", "Vacated", "Dismissed",
]


def _apply_compact_stacked_layout_horizontal(fig: go.Figure) -> go.Figure:
    """Improve horizontal stacked bar readability on narrower screens."""
    fig.update_traces(
        text=None,
        hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor="white",
        barmode="stack",
        legend_title_text="Outcome",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.2,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        xaxis=dict(title="Number of Cases", automargin=True),
        yaxis=dict(title="", autorange="reversed", automargin=True, tickfont=dict(size=11)),
        margin={"l": 10, "r": 10, "t": 50, "b": 90},
        hovermode="y",
    )
    return fig


def _apply_compact_stacked_layout_vertical(fig: go.Figure) -> go.Figure:
    """Improve vertical stacked bar readability on narrower screens."""
    fig.update_traces(
        text=None,
        hovertemplate="%{x}<br>%{fullData.name}: %{y}<extra></extra>",
    )
    fig.update_layout(
        plot_bgcolor="white",
        barmode="stack",
        legend_title_text="Outcome",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.25,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        xaxis=dict(title="", automargin=True, tickangle=-32, tickfont=dict(size=11)),
        yaxis=dict(title="Number of Cases", automargin=True),
        margin={"l": 10, "r": 10, "t": 50, "b": 150},
        hovermode="x",
    )
    return fig

def _stacked_bar(
    grouped: pd.DataFrame,
    axis_col: str,
    title: str,
    category_order: list[str],
    orientation: str = "h",
    category_values: list[str] | None = None,
    height: int = 400,
) -> go.Figure:
    """Return a Plotly stacked bar chart of outcome counts."""
    if category_values is None:
        category_values = sorted(grouped[axis_col].unique())

    if orientation == "v":
        fig = px.bar(
            grouped,
            x=axis_col,
            y="count",
            color="outcome_label",
            orientation="v",
            title=title,
            category_orders={
                "outcome_label": category_order,
                axis_col: category_values,
            },
            color_discrete_map={
                OUTCOME_LABELS.get(k, k): v for k, v in OUTCOME_COLORS.items()
            },
            height=max(height, 360),
        )
        return _apply_compact_stacked_layout_vertical(fig)

    fig = px.bar(
        grouped,
        x="count",
        y=axis_col,
        color="outcome_label",
        orientation="h",
        title=title,
        category_orders={
            "outcome_label": category_order,
            axis_col: category_values,
        },
        color_discrete_map={
            OUTCOME_LABELS.get(k, k): v for k, v in OUTCOME_COLORS.items()
        },
        height=max(height, len(grouped[axis_col].unique()) * 30 + 120),
    )
    return _apply_compact_stacked_layout_horizontal(fig)


# ── Section 1: Outcomes by Court Type ─────────────────────────────────────────
st.subheader("Outcomes by Court Type")

type_counts = (
    df_lc_out.groupby(["court_type", "outcome_label"])
    .size()
    .reset_index(name="count")
)
type_totals = type_counts.groupby("court_type")["count"].sum().reset_index(name="total")
visible_types = type_totals[type_totals["total"] >= min_cases]["court_type"]
type_df = type_counts[type_counts["court_type"].isin(visible_types)]

if not type_df.empty:
    type_order = type_totals[type_totals["court_type"].isin(visible_types)]["court_type"].tolist()
    type_chart_height = max(520, len(type_order) * 120)
    fig_type = _stacked_bar(
        type_df,
        "court_type",
        "Case Outcomes by Court Type",
        OUTCOME_ORDER,
        orientation="v",
        category_values=type_order,
        height=type_chart_height,
    )
    st.plotly_chart(fig_type, width="stretch")
else:
    st.info("Not enough data for selected filters.")

with st.expander("Individual court breakdown by type"):
    type_pivot = (
        df_lc_out.groupby(["court_type", "court_base", "outcome_label"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in OUTCOME_ORDER:
        if col not in type_pivot.columns:
            type_pivot[col] = 0
    present_outcomes = [c for c in OUTCOME_ORDER if c in type_pivot.columns]
    type_pivot["Total"] = type_pivot[present_outcomes].sum(axis=1)
    type_pivot = type_pivot.sort_values(["court_type", "Total"], ascending=[True, False])
    st.dataframe(
        type_pivot[["court_type", "court_base"] + present_outcomes + ["Total"]].rename(
            columns={"court_type": "Court Type", "court_base": "Court"}
        ),
        width="stretch",
        hide_index=True,
    )

# ── Section 2: Outcomes by Court (grouped) ────────────────────────────────────
st.subheader("Outcomes by Court")
st.caption(
    f"Circuit Court divisions are grouped together. Courts with at least {min_cases} cases shown."
)

# Consolidate all Circuit Court sub-types into one "Circuit Court" bucket for the chart
def _chart_group(court_type: str) -> str:
    return "Circuit Court" if court_type.startswith("Circuit Court") else court_type

df_lc_out = df_lc_out.copy()
df_lc_out["court_group"] = df_lc_out["court_type"].apply(_chart_group)

group_counts = (
    df_lc_out.groupby(["court_group", "outcome_label"])
    .size()
    .reset_index(name="count")
)
group_totals = group_counts.groupby("court_group")["count"].sum().reset_index(name="total")
group_totals = group_totals.sort_values("total", ascending=False)
visible_groups = group_totals[group_totals["total"] >= min_cases]["court_group"]
group_df = group_counts[group_counts["court_group"].isin(visible_groups)]
group_order = group_totals[group_totals["court_group"].isin(visible_groups)]["court_group"].tolist()

if not group_df.empty:
    fig_court = _stacked_bar(
        group_df,
        "court_group",
        "Case Outcomes by Court",
        OUTCOME_ORDER,
        orientation="v",
        category_values=group_order,
        height=340,
    )
    st.plotly_chart(fig_court, width="stretch")

# Detail table: one row per individual court
with st.expander("Individual Circuit Court breakdown"):
    circuit_df = df_lc_out[df_lc_out["court_group"] == "Circuit Court"].copy()
    if circuit_df.empty:
        st.info("No Circuit Court data in the selected period.")
    else:
        court_pivot = (
            circuit_df.groupby(["court_base", "outcome_label"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        # Ensure outcome columns exist
        for col in OUTCOME_ORDER:
            if col not in court_pivot.columns:
                court_pivot[col] = 0
        present_outcomes = [c for c in OUTCOME_ORDER if c in court_pivot.columns]
        court_pivot["Total"] = court_pivot[present_outcomes].sum(axis=1)
        court_pivot = court_pivot.sort_values("Total", ascending=False)
        display_cols_tbl = ["court_base"] + present_outcomes + ["Total"]
        st.dataframe(
            court_pivot[display_cols_tbl].rename(columns={"court_base": "Court"}),
            width="stretch",
            hide_index=True,
        )

# ── Section 3: Outcomes by Trial Judge ────────────────────────────────────────
st.divider()
st.subheader("Outcomes by Trial Judge")
st.caption(f"Judges with at least {min_cases} cases in selected period (judge name from lower court record)")

df_judges = df_lc_out[df_lc_out["judge"].notna()].copy()

judge_counts = (
    df_judges.groupby(["judge", "outcome_label"])
    .size()
    .reset_index(name="count")
)
judge_totals = judge_counts.groupby("judge")["count"].sum().reset_index(name="total")
judge_totals = judge_totals.sort_values("total", ascending=False)
visible_judges = judge_totals[judge_totals["total"] >= min_cases]["judge"]
judge_df = judge_counts[judge_counts["judge"].isin(visible_judges)]
judge_order = judge_totals[judge_totals["judge"].isin(visible_judges)]["judge"].tolist()

if not judge_df.empty:
    fig_judge = px.bar(
        judge_df,
        x="count",
        y="judge",
        color="outcome_label",
        orientation="h",
        title="Case Outcomes by Trial Judge",
        category_orders={
            "outcome_label": OUTCOME_ORDER,
            "judge": judge_order,
        },
        color_discrete_map={
            OUTCOME_LABELS.get(k, k): v for k, v in OUTCOME_COLORS.items()
        },
        height=max(420, len(judge_order) * 30 + 120),
    )
    fig_judge = _apply_compact_stacked_layout_horizontal(fig_judge)
    st.plotly_chart(fig_judge, width="stretch")
else:
    st.info("Not enough judge data for selected filters.")

# ── Section 4: Rate table ──────────────────────────────────────────────────────
st.divider()
st.subheader("Affirmance & Reversal Rates by Judge")

if not judge_df.empty:
    rate_pivot = judge_df.pivot_table(
        index="judge", columns="outcome_label", values="count", fill_value=0
    )
    # Ensure required columns exist
    for col in ["Affirmed", "Reversed", "Reversed & Remanded", "Remanded", "Vacated", "Dismissed"]:
        if col not in rate_pivot.columns:
            rate_pivot[col] = 0

    rate_pivot["Total"] = rate_pivot.sum(axis=1)
    rate_pivot["Affirm Rate"] = (rate_pivot.get("Affirmed", 0) / rate_pivot["Total"] * 100).round(1)
    rate_pivot["Reversal Rate"] = (
        (rate_pivot.get("Reversed", 0) + rate_pivot.get("Reversed & Remanded", 0))
        / rate_pivot["Total"] * 100
    ).round(1)

    rate_table = (
        rate_pivot.reset_index()[["judge", "Total", "Affirmed", "Reversed",
                                   "Reversed & Remanded", "Remanded",
                                   "Vacated", "Dismissed",
                                   "Affirm Rate", "Reversal Rate"]]
        .sort_values("Total", ascending=False)
        .rename(columns={"judge": "Trial Judge", "Affirm Rate": "Affirm %", "Reversal Rate": "Reversal %"})
    )

    st.dataframe(
        rate_table,
        width="stretch",
        hide_index=True,
        column_config={
            "Affirm %": st.column_config.NumberColumn("Affirm %", format="%.1f%%"),
            "Reversal %": st.column_config.NumberColumn("Reversal %", format="%.1f%%"),
        },
    )

st.sidebar.download_button(
    "⬇ Download Filtered CSV",
    data=df_lc.to_csv(index=False),
    file_name="nh_sc_trial_courts_filtered.csv",
    mime="text/csv",
)
