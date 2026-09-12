"""Directed NH opinion citation graph helpers."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import plotly.graph_objects as go


DOCKET_RE = re.compile(r"\b\d{4}-\d{3,4}\b")


def extract_citations(text: str) -> list[str]:
    return list(dict.fromkeys(DOCKET_RE.findall(text or "")))


def build_citation_graph(opinions: pd.DataFrame) -> dict[str, list[str]]:
    """Return a serializable adjacency map, avoiding a runtime NetworkX dependency."""
    available = set(opinions["case_number"].astype(str))
    graph: dict[str, list[str]] = {}
    for _, row in opinions.iterrows():
        docket = str(row.get("case_number", ""))
        text = str(row.get("opinion_text") or "")
        graph[docket] = [
            cited
            for cited in extract_citations(text)
            if cited != docket and cited in available
        ]
    return graph


def landmark_cases(graph: dict[str, list[str]], top_n: int = 20) -> pd.DataFrame:
    counts: dict[str, int] = {}
    for cited_cases in graph.values():
        for case_id in cited_cases:
            counts[case_id] = counts.get(case_id, 0) + 1
    return pd.DataFrame(
        [
            {"case_number": case_id, "in_degree": degree}
            for case_id, degree in sorted(
                counts.items(), key=lambda item: item[1], reverse=True
            )[:top_n]
        ]
    )


def render_citation_graph(
    graph: dict[str, list[str]],
    top_n: int = 50,
    focus_case: str | None = None,
) -> go.Figure:
    """Delegate rendering to the application's maintained interactive chart."""
    from utils.network_charts import build_citation_network

    if focus_case:
        return build_citation_network(graph, focus_case=focus_case)
    landmarks = set(landmark_cases(graph, top_n)["case_number"])
    subgraph = {
        source: [target for target in targets if target in landmarks]
        for source, targets in graph.items()
        if source in landmarks
    }
    return build_citation_network(subgraph)
