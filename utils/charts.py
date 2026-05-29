"""
Reusable Plotly/Streamlit chart helpers for Granite State Appeals.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.constants import VOTE_COLORS, OUTCOME_COLORS, OUTCOME_LABELS, JUSTICE_DISPLAY


NH_BLUE = "#003057"
NH_GOLD = "#C8960C"


def outcome_bar(df: pd.DataFrame) -> go.Figure:
    """Bar chart of outcome distribution."""
    counts = df["outcome"].value_counts().reset_index()
    counts.columns = ["outcome", "count"]
    counts["label"] = counts["outcome"].map(lambda x: OUTCOME_LABELS.get(x, x.title()))
    counts["color"] = counts["outcome"].map(lambda x: OUTCOME_COLORS.get(x, "#607D8B"))
    fig = px.bar(
        counts,
        x="label",
        y="count",
        color="outcome",
        color_discrete_map={k: OUTCOME_COLORS.get(k, "#607D8B") for k in counts["outcome"]},
        labels={"label": "Outcome", "count": "# Opinions"},
        title="Outcomes",
    )
    fig.update_layout(showlegend=False, plot_bgcolor="white")
    return fig


def opinions_per_year(df: pd.DataFrame) -> go.Figure:
    """Line chart of opinions per term year."""
    if "term_year" not in df.columns or df.empty:
        return go.Figure()
    by_year = df.groupby("term_year").size().reset_index(name="count")
    fig = px.line(
        by_year,
        x="term_year",
        y="count",
        markers=True,
        labels={"term_year": "Year", "count": "Opinions"},
        title="Opinions Per Year",
        color_discrete_sequence=[NH_BLUE],
    )
    min_year = int(by_year["term_year"].min())
    fig.update_layout(
        plot_bgcolor="white",
        xaxis=dict(tickmode="linear", dtick=5, tick0=min_year),
    )
    return fig


def avg_decision_time_per_year(df: pd.DataFrame) -> go.Figure:
    """Line chart of average days-to-decision by year."""
    if "term_year" not in df.columns or "days_to_decision" not in df.columns or df.empty:
        return go.Figure()

    valid = df[df["days_to_decision"].notna()].copy()
    if valid.empty:
        return go.Figure()

    avg_by_year = (
        valid.groupby("term_year")["days_to_decision"]
        .mean()
        .reset_index(name="avg_days")
    )

    fig = px.line(
        avg_by_year,
        x="term_year",
        y="avg_days",
        markers=True,
        labels={"term_year": "Year", "avg_days": "Avg Days to Decision"},
        title="Average Decision Time by Year",
        color_discrete_sequence=[NH_GOLD],
    )
    min_year = int(avg_by_year["term_year"].min())
    fig.update_layout(
        plot_bgcolor="white",
        xaxis=dict(tickmode="linear", dtick=5, tick0=min_year),
    )
    return fig


def avg_word_count_by_case_type(df: pd.DataFrame) -> go.Figure:
    """Bar chart of average word count by case type."""
    if "case_type" not in df.columns or "word_count" not in df.columns or df.empty:
        return go.Figure()

    valid = df[df["case_type"].notna() & df["word_count"].notna()].copy()
    if valid.empty:
        return go.Figure()

    valid["word_count"] = pd.to_numeric(valid["word_count"], errors="coerce")
    valid = valid[valid["word_count"].notna()]
    if valid.empty:
        return go.Figure()

    case_type_map = {
        "civil": "Civil",
        "criminal": "Criminal",
        "family/domestic": "Domestic/Family",
        "domestic/family": "Domestic/Family",
        "family": "Domestic/Family",
        "domestic": "Domestic/Family",
    }

    valid["case_type_norm"] = (
        valid["case_type"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(case_type_map)
        .fillna(valid["case_type"].astype(str).str.replace("_", " ").str.title())
    )

    avg_by_type = (
        valid.groupby("case_type_norm")["word_count"]
        .mean()
        .reindex(["Civil", "Criminal", "Domestic/Family"])
        .fillna(0)
        .reset_index(name="avg_word_count")
        .rename(columns={"case_type_norm": "case_type_label"})
    )

    fig = px.bar(
        avg_by_type,
        x="case_type_label",
        y="avg_word_count",
        labels={"case_type_label": "Case Type", "avg_word_count": "Avg Word Count"},
        title="Average Word Count by Case Type",
        color_discrete_sequence=[NH_BLUE],
    )
    fig.update_layout(plot_bgcolor="white", showlegend=False)
    return fig


def avg_word_count_by_year(df: pd.DataFrame) -> go.Figure:
    """Line chart of average word count by year."""
    if "term_year" not in df.columns or "word_count" not in df.columns or df.empty:
        return go.Figure()

    valid = df[df["term_year"].notna() & df["word_count"].notna()].copy()
    if valid.empty:
        return go.Figure()

    valid["word_count"] = pd.to_numeric(valid["word_count"], errors="coerce")
    valid = valid[valid["word_count"].notna()]
    if valid.empty:
        return go.Figure()

    avg_by_year = (
        valid.groupby("term_year")["word_count"]
        .mean()
        .reset_index(name="avg_word_count")
    )

    fig = px.line(
        avg_by_year,
        x="term_year",
        y="avg_word_count",
        markers=True,
        labels={"term_year": "Year", "avg_word_count": "Avg Word Count"},
        title="Average Word Count by Year",
        color_discrete_sequence=[NH_GOLD],
    )
    min_year = int(avg_by_year["term_year"].min())
    fig.update_layout(
        plot_bgcolor="white",
        xaxis=dict(tickmode="linear", dtick=5, tick0=min_year),
    )
    return fig


def avg_word_count_by_year_per_justice(df: pd.DataFrame) -> go.Figure:
    """Line chart of average word count by year for each justice."""
    required = {"author", "term_year", "word_count"}
    if not required.issubset(df.columns) or df.empty:
        return go.Figure()

    valid = df[
        df["author"].notna()
        & df["term_year"].notna()
        & df["word_count"].notna()
        & (df["author"].astype(str) != "per_curiam")
    ].copy()
    if valid.empty:
        return go.Figure()

    valid["word_count"] = pd.to_numeric(valid["word_count"], errors="coerce")
    valid = valid[valid["word_count"].notna()]
    if valid.empty:
        return go.Figure()

    valid["justice_display"] = valid["author"].map(
        lambda k: JUSTICE_DISPLAY.get(str(k), str(k).replace("_", " ").title())
    )

    avg_by_justice_year = (
        valid.groupby(["term_year", "justice_display"])["word_count"]
        .mean()
        .reset_index(name="avg_word_count")
    )

    fig = px.line(
        avg_by_justice_year,
        x="term_year",
        y="avg_word_count",
        color="justice_display",
        markers=True,
        labels={
            "term_year": "Year",
            "avg_word_count": "Avg Word Count",
            "justice_display": "Justice",
        },
        title="Average Word Count by Year (Each Justice)",
    )
    min_year = int(avg_by_justice_year["term_year"].min())
    fig.update_layout(
        plot_bgcolor="white",
        xaxis=dict(tickmode="linear", dtick=5, tick0=min_year),
        title=dict(x=0.01, xanchor="left"),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=70, b=95),
    )
    return fig


def avg_word_count_by_justice(df: pd.DataFrame) -> go.Figure:
    """Bar chart of average word count by justice across all opinions."""
    required = {"author", "word_count"}
    if not required.issubset(df.columns) or df.empty:
        return go.Figure()

    valid = df[
        df["author"].notna()
        & df["word_count"].notna()
        & (df["author"].astype(str) != "per_curiam")
    ].copy()
    if valid.empty:
        return go.Figure()

    valid["word_count"] = pd.to_numeric(valid["word_count"], errors="coerce")
    valid = valid[valid["word_count"].notna()]
    if valid.empty:
        return go.Figure()

    avg_by_justice = (
        valid.groupby("author")["word_count"]
        .mean()
        .reset_index(name="avg_word_count")
        .sort_values("avg_word_count", ascending=False)
    )
    avg_by_justice["justice_display"] = avg_by_justice["author"].map(
        lambda k: JUSTICE_DISPLAY.get(str(k), str(k).replace("_", " ").title())
    )

    fig = px.bar(
        avg_by_justice,
        x="justice_display",
        y="avg_word_count",
        labels={"justice_display": "Justice", "avg_word_count": "Avg Word Count"},
        title="Average Word Count by Justice",
        color_discrete_sequence=[NH_BLUE],
    )
    fig.update_layout(plot_bgcolor="white", showlegend=False, xaxis_tickangle=-25)
    return fig


def bench_diagram(votes: dict) -> go.Figure:
    """
    5-seat NH Supreme Court bench diagram.
    Each seat is a colored dot/bar representing that justice's vote.
    """
    # Prefer current court order first, then legacy/retired seats as fallback.
    bench_order = [
        "macdonald", "donovan", "hantz_marconi", "countway", "gould", "will",
        "bassett", "hicks", "lynn",
    ]

    shown_keys = [k for k in bench_order if k in votes][:5]
    if not shown_keys:
        shown_keys = list(votes.keys())[:5]

    x_positions = [1 + (i * 2.2) for i in range(len(shown_keys))]
    colors, labels, hover = [], [], []

    for key in shown_keys:
        vote_rec = votes.get(key, {"vote": "not_participating", "display_name": key})
        vote_type = vote_rec.get("vote", "not_participating")
        colors.append(VOTE_COLORS.get(vote_type, "#9E9E9E"))
        display = vote_rec.get("display_name", key)
        # Short label: everything before the first comma
        short = display.split(",")[0].strip()
        labels.append(short)
        hover.append(f"{display}<br>{vote_type.replace('_', ' ').title()}")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_positions,
            y=[1] * len(shown_keys),
            mode="markers+text",
            marker=dict(size=46, color=colors, line=dict(width=2, color="white")),
            text=labels,
            textposition="bottom center",
            textfont=dict(size=12),
            hovertext=hover,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        height=200,
        margin=dict(l=10, r=10, t=10, b=70),
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, (len(shown_keys) * 2.2) + 0.8]),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0.4, 1.5]),
        plot_bgcolor="white",
        showlegend=False,
    )
    return fig


def agreement_heatmap(agreement_df: pd.DataFrame) -> go.Figure:
    """5×5 justice agreement heatmap."""
    labels = [JUSTICE_DISPLAY.get(k, k) for k in agreement_df.index]
    fig = go.Figure(
        data=go.Heatmap(
            z=agreement_df.values,
            x=labels,
            y=labels,
            colorscale=[[0, "#FFFFFF"], [1, NH_BLUE]],
            zmin=0,
            zmax=1,
            text=[[f"{v:.0%}" for v in row] for row in agreement_df.values],
            texttemplate="%{text}",
            hoverongaps=False,
        )
    )
    fig.update_layout(
        title="Justice Agreement Rate",
        height=400,
        xaxis_tickangle=-30,
        margin=dict(l=120, r=20, t=50, b=100),
    )
    return fig


def authorship_bar(df: pd.DataFrame) -> go.Figure:
    """Bar chart of opinions authored per justice."""
    if df.empty or "author" not in df.columns:
        return go.Figure()
    counts = (
        df[df["author"] != "per_curiam"]["author"]
        .value_counts()
        .reset_index()
    )
    counts.columns = ["author_key", "count"]
    counts["display"] = counts["author_key"].map(
        lambda k: JUSTICE_DISPLAY.get(k, k)
    )
    fig = px.bar(
        counts,
        x="display",
        y="count",
        color_discrete_sequence=[NH_BLUE],
        labels={"display": "Justice", "count": "Opinions Authored"},
        title="Opinions Authored by Justice",
    )
    fig.update_layout(plot_bgcolor="white", showlegend=False)
    return fig


def rsa_citation_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Bar chart of most-cited RSA chapters."""
    import ast
    all_rsas = []
    for cell in df["rsa_citations"].dropna():
        try:
            rsas = ast.literal_eval(cell) if isinstance(cell, str) else cell
            all_rsas.extend(rsas)
        except Exception:
            pass
    if not all_rsas:
        return go.Figure()
    # Normalize to chapter level
    chapters = [r.split(":")[0].strip() for r in all_rsas]
    counts = pd.Series(chapters).value_counts().head(top_n).reset_index()
    counts.columns = ["rsa", "count"]
    fig = px.bar(
        counts,
        x="rsa",
        y="count",
        color_discrete_sequence=[NH_GOLD],
        labels={"rsa": "RSA Chapter/Section", "count": "Citations"},
        title=f"Top {top_n} Most-Cited RSA Chapters",
    )
    fig.update_layout(plot_bgcolor="white", showlegend=False)
    return fig
