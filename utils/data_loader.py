"""
Cached data loading utilities for Streamlit pages.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "processed"
RAW_DIR = BASE_DIR / "data" / "raw"


@st.cache_data(ttl=3600)
def _load_opinions_cached(csv_path_str: str, source_mtime: float) -> pd.DataFrame:
    """Load all opinions as a flat DataFrame (cache keyed by source mtime)."""
    _ = source_mtime
    df = pd.read_csv(
        csv_path_str,
        parse_dates=["date_argued", "date_issued"],
        low_memory=False,
    )
    # Ensure list-like columns are strings (CSV flattens them)
    for col in ("topics", "rsa_citations"):
        if col in df.columns:
            df[col] = df[col].fillna("[]")
    return df


def load_opinions() -> pd.DataFrame:
    """Load all opinions as a flat DataFrame."""
    csv_path = DATA_DIR / "opinions.csv"
    if not csv_path.exists():
        return _empty_opinions_df()
    source_mtime = os.path.getmtime(csv_path)
    return _load_opinions_cached(str(csv_path), source_mtime)


@st.cache_data(ttl=3600)
def load_opinions_json() -> list[dict]:
    """Load all opinions as raw JSON (includes nested vote dicts)."""
    json_path = DATA_DIR / "all_opinions.json"
    if not json_path.exists():
        return []
    with open(json_path, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data
def load_justices() -> dict:
    """Return justice metadata keyed by justice key."""
    path = BASE_DIR / "data" / "justices.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)
    return {j["key"]: j for j in items}


@st.cache_data
def load_topic_taxonomy() -> dict:
    path = BASE_DIR / "data" / "topic_taxonomy.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(ttl=3600)
def _load_case_orders_cached(case_orders_mtime: float | None, jx3_mtime: float | None) -> pd.DataFrame:
    _ = (case_orders_mtime, jx3_mtime)
    case_orders_path = DATA_DIR / "case_orders.csv"
    jx3_path = DATA_DIR / "3jx_orders.csv"

    frames: list[pd.DataFrame] = []

    if case_orders_path.exists():
        case_df = pd.read_csv(case_orders_path, parse_dates=["date_issued"], low_memory=False)
        case_df["order_source"] = "case_order"
        frames.append(case_df)

    if jx3_path.exists():
        jx_df = pd.read_csv(jx3_path, low_memory=False)
        # Normalize 3JX schema to align with case orders.
        if "year" in jx_df.columns and "term_year" not in jx_df.columns:
            jx_df["term_year"] = jx_df["year"]
        if "opinion_type" in jx_df.columns:
            jx_df["order_source"] = jx_df["opinion_type"].fillna("3jx_order")
        else:
            jx_df["order_source"] = "3jx_order"
        jx_df["date_issued"] = pd.to_datetime(jx_df.get("date_issued"), errors="coerce")
        frames.append(jx_df)

    if not frames:
        return _empty_orders_df()

    merged = pd.concat(frames, ignore_index=True, sort=False)
    # Hide transcript placeholders in both feeds.
    merged = merged[merged["case_name"].fillna("").str.lower() != "request a transcript"]
    merged = merged[merged["case_number"].fillna("").str.lower() != "transcript-instructions"]
    return merged


def load_case_orders() -> pd.DataFrame:
    case_orders_path = DATA_DIR / "case_orders.csv"
    jx3_path = DATA_DIR / "3jx_orders.csv"

    case_orders_mtime = os.path.getmtime(case_orders_path) if case_orders_path.exists() else None
    jx3_mtime = os.path.getmtime(jx3_path) if jx3_path.exists() else None

    return _load_case_orders_cached(case_orders_mtime, jx3_mtime)


@st.cache_data
def load_opinion_text(case_number: str) -> str:
    path = DATA_DIR / "text" / f"{case_number}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _empty_opinions_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "case_number", "citation", "case_name", "date_issued",
            "date_argued", "author", "outcome", "vote_string",
            "is_unanimous", "has_dissent", "topics", "term_year",
            "lower_court", "appeal_type", "word_count",
        ]
    )


def _empty_orders_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["case_number", "case_name", "date_issued", "order_type", "term_year", "order_source"]
    )


def data_last_updated() -> str:
    """Return a human-readable last-updated timestamp from the CSV mtime."""
    csv_path = DATA_DIR / "opinions.csv"
    if not csv_path.exists():
        return "No data yet — run the pipeline"
    mtime = os.path.getmtime(csv_path)
    return pd.Timestamp(mtime, unit="s").strftime("%B %d, %Y %I:%M %p")
