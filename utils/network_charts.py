"""
Network chart visualizations: co-counsel networks, citation graphs.
Uses Plotly for interactive network charts.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from typing import Optional


def build_co_counsel_network(
    opinions_df: pd.DataFrame,
    min_cases: int = 2,
) -> go.Figure:
    """
    Build network chart of co-counsel relationships.
    
    Args:
        opinions_df: Opinions DataFrame with attorney data
        min_cases: Minimum shared cases for edge
    
    Returns:
        Plotly Figure with network chart
    """
    # Build co-occurrence matrix
    co_counsel_pairs = []
    
    attorney_cols = [
        "petitioner_attorney",
        "respondent_attorney",
        "appellant_attorney",
        "appellee_attorney",
    ]
    
    available_cols = [col for col in attorney_cols if col in opinions_df.columns]
    
    for _, row in opinions_df.iterrows():
        attorneys = []
        for col in available_cols:
            attorney = row.get(col)
            if attorney and pd.notna(attorney):
                attorneys.append(attorney)
        
        # Record pairs
        for i in range(len(attorneys)):
            for j in range(i + 1, len(attorneys)):
                co_counsel_pairs.append((attorneys[i], attorneys[j]))
    
    # Count pairs
    pair_counts = pd.Series(co_counsel_pairs).value_counts()
    pair_counts = pair_counts[pair_counts >= min_cases]
    
    if pair_counts.empty:
        # Return empty figure
        fig = go.Figure()
        fig.update_layout(title="No co-counsel relationships found")
        return fig
    
    # Build node list
    nodes = set()
    for (a1, a2), count in pair_counts.items():
        nodes.add(a1)
        nodes.add(a2)
    
    nodes = sorted(nodes)
    node_indices = {node: i for i, node in enumerate(nodes)}
    
    # Build edges
    edge_x = []
    edge_y = []
    edge_weights = []
    
    for (a1, a2), count in pair_counts.items():
        idx1 = node_indices[a1]
        idx2 = node_indices[a2]
        
        # Simple circular layout
        import math
        angle1 = 2 * math.pi * idx1 / len(nodes)
        angle2 = 2 * math.pi * idx2 / len(nodes)
        
        x1, y1 = math.cos(angle1), math.sin(angle1)
        x2, y2 = math.cos(angle2), math.sin(angle2)
        
        edge_x.extend([x1, x2, None])
        edge_y.extend([y1, y2, None])
        edge_weights.append(count)
    
    # Create edge trace
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="#888"),
        hoverinfo="none",
        mode="lines",
    )
    
    # Create node positions
    import math
    node_x = []
    node_y = []
    node_text = []
    
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / len(nodes)
        x, y = math.cos(angle), math.sin(angle)
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
    
    # Create node trace
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        hoverinfo="text",
        marker=dict(
            size=10,
            color="lightblue",
            line=dict(width=2, color="darkblue"),
        ),
    )
    
    # Create figure
    fig = go.Figure(data=[edge_trace, node_trace])
    
    fig.update_layout(
        title="Co-Counsel Network",
        showlegend=False,
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="white",
    )
    
    return fig


def build_citation_network(
    citation_graph: dict,
    focus_case: Optional[str] = None,
    max_depth: int = 2,
) -> go.Figure:
    """
    Build network chart of citation relationships.
    
    Args:
        citation_graph: Dict mapping case_number -> list of cited cases
        focus_case: Optional case to center network on
        max_depth: Maximum citation depth from focus case
    
    Returns:
        Plotly Figure with citation network
    """
    if not citation_graph:
        fig = go.Figure()
        fig.update_layout(title="No citation data available")
        return fig
    
    # Build nodes and edges
    if focus_case and focus_case in citation_graph:
        # BFS from focus case
        nodes = {focus_case}
        edges = []
        queue = [(focus_case, 0)]
        visited = set()
        
        while queue:
            case, depth = queue.pop(0)
            
            if case in visited or depth >= max_depth:
                continue
            
            visited.add(case)
            
            cited_cases = citation_graph.get(case, [])
            for cited in cited_cases:
                if cited in citation_graph:  # Only include if we have data
                    nodes.add(cited)
                    edges.append((case, cited))
                    
                    if depth + 1 < max_depth:
                        queue.append((cited, depth + 1))
    else:
        # Show all (limited for performance)
        nodes = set(citation_graph.keys())
        edges = []
        
        for case, cited_cases in list(citation_graph.items())[:100]:  # Limit for performance
            for cited in cited_cases:
                if cited in citation_graph:
                    edges.append((case, cited))
    
    nodes = sorted(nodes)
    node_indices = {node: i for i, node in enumerate(nodes)}
    
    # Layout nodes (circular for simplicity)
    import math
    node_x = []
    node_y = []
    node_text = []
    
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / len(nodes)
        x, y = math.cos(angle), math.sin(angle)
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
    
    # Build edge traces
    edge_x = []
    edge_y = []
    
    for source, target in edges:
        if source in node_indices and target in node_indices:
            idx1 = node_indices[source]
            idx2 = node_indices[target]
            
            edge_x.extend([node_x[idx1], node_x[idx2], None])
            edge_y.extend([node_y[idx1], node_y[idx2], None])
    
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="#888"),
        hoverinfo="none",
        mode="lines",
    )
    
    # Node colors (focus case is different)
    node_colors = ["red" if n == focus_case else "lightblue" for n in nodes]
    
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers",
        text=node_text,
        hoverinfo="text",
        marker=dict(
            size=8,
            color=node_colors,
            line=dict(width=1, color="darkblue"),
        ),
    )
    
    # Create figure
    fig = go.Figure(data=[edge_trace, node_trace])
    
    fig.update_layout(
        title=f"Citation Network{' for ' + focus_case if focus_case else ''}",
        showlegend=False,
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="white",
    )
    
    return fig
