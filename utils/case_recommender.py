"""Case similarity recommendations backed by the maintained app scorer."""

from __future__ import annotations

import ast
from typing import Any

import pandas as pd


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or str(value).strip() in {"", "nan", "[]"}:
        return []
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (ValueError, SyntaxError):
        pass
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _normalized(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in ("topics", "rsa_citations"):
        if column in output.columns:
            output[column] = output[column].map(_as_list)
    return output


def get_similar_cases(
    docket: str,
    opinions: pd.DataFrame,
    top_k: int = 5,
    *,
    exclude_future: bool = True,
) -> pd.DataFrame:
    """Return related cases with an auditable score and explanation."""
    from utils.similar_cases import find_similar_cases

    frame = _normalized(opinions)
    results = find_similar_cases(
        docket,
        frame,
        limit=top_k,
        exclude_future=exclude_future,
    )
    if not results:
        return pd.DataFrame(
            columns=[
                "case_number",
                "case_name",
                "year",
                "outcome",
                "similarity_score",
                "reasons",
            ]
        )
    output = pd.DataFrame(results)
    output["reasons"] = output["reasons"].map(
        lambda reasons: "; ".join(reasons) if isinstance(reasons, list) else str(reasons)
    )
    return output
