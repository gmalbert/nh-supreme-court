"""Read-only REST API for versioned NH Supreme Court public data."""

from __future__ import annotations

import ast
from datetime import date
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from utils.authority_graph import controlling_treatments, load_treatments, treatment_to_dict
from utils.data_loader import load_opinions


app = FastAPI(
    title="Granite State Appeals API",
    version="1.0.0",
    description="Read-only public research data; not legal advice.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _json_value(value: Any) -> Any:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, str) and value.startswith(("[", "{")):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {column: _json_value(value) for column, value in row.items()}
        for row in frame.to_dict("records")
    ]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/opinions")
def get_opinions(
    year: int | None = None,
    topic: str | None = None,
    disposition: str | None = None,
    query: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    frame = load_opinions().copy()
    if year is not None:
        frame = frame[pd.to_numeric(frame["term_year"], errors="coerce") == year]
    if topic:
        frame = frame[frame["topics"].astype(str).str.contains(topic, case=False, na=False)]
    if disposition:
        frame = frame[frame["outcome"].astype(str).str.casefold() == disposition.casefold()]
    if query:
        searchable = (
            frame["case_name"].fillna("").astype(str)
            + " "
            + frame["summary_paragraph"].fillna("").astype(str)
            + " "
            + frame["case_number"].fillna("").astype(str)
        )
        frame = frame[searchable.str.contains(query, case=False, na=False, regex=False)]
    return _records(frame.iloc[offset : offset + limit])


@app.get("/opinions/{docket_number}")
def get_opinion(docket_number: str) -> dict[str, Any]:
    frame = load_opinions()
    row = frame[frame["case_number"].astype(str) == str(docket_number)]
    if row.empty:
        raise HTTPException(status_code=404, detail="Opinion not found")
    return _records(row.head(1))[0]


@app.get("/stats/topics")
def get_topic_stats() -> list[dict[str, Any]]:
    frame = load_opinions()
    rows: list[str] = []
    for value in frame["topics"].fillna("[]"):
        try:
            parsed = ast.literal_eval(str(value))
            rows.extend(str(item).replace("_", " ").title() for item in parsed)
        except (ValueError, SyntaxError):
            if str(value).strip():
                rows.append(str(value))
    return [
        {"topic": topic, "count": count}
        for topic, count in pd.Series(rows).value_counts().items()
    ]


@app.get("/authority/{case_id}")
def get_authority_status(
    case_id: str,
    as_of: date = Query(default_factory=date.today),
) -> dict[str, Any]:
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "processed" / "authority_treatments.json"
    treatments = controlling_treatments(load_treatments(path), case_id, as_of)
    return {
        "case_id": case_id,
        "as_of": as_of.isoformat(),
        "treatments": [treatment_to_dict(item) for item in treatments],
    }
