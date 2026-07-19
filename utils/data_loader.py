"""
Cached data loading utilities for Streamlit pages.
"""

from __future__ import annotations

import json
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.oral_arguments import find_argument_for_docket, normalize_docket_numbers

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "processed"
PDF_DATE_OVERRIDES_DIR = BASE_DIR / "data" / "oral_argument_pdf_dates"
RAW_DIR = BASE_DIR / "data" / "raw"
_AUTO_BUILD_ATTEMPTED = False
NON_FIRM_STATUS_PREFIX = "skipped —"


def _latest_mtime(paths) -> float | None:
    mtimes = [os.path.getmtime(p) for p in paths if p.exists()]
    return max(mtimes) if mtimes else None


def _needs_master_rebuild() -> bool:
    opinions_csv = DATA_DIR / "opinions.csv"
    all_opinions_json = DATA_DIR / "all_opinions.json"
    case_orders_csv = DATA_DIR / "case_orders.csv"

    opinion_parts = list(DATA_DIR.glob("opinions_*.json"))
    order_parts = list(DATA_DIR.glob("case_orders_*.json"))

    newest_opinion_part = _latest_mtime(opinion_parts)
    newest_order_part = _latest_mtime(order_parts)
    newest_part = _latest_mtime([p for p in [*(opinion_parts or []), *(order_parts or [])]])

    if newest_part is None:
        return False

    if newest_opinion_part is not None:
        if not opinions_csv.exists() or os.path.getmtime(opinions_csv) < newest_opinion_part:
            return True
        if not all_opinions_json.exists() or os.path.getmtime(all_opinions_json) < newest_opinion_part:
            return True

    if newest_order_part is not None:
        if not case_orders_csv.exists() or os.path.getmtime(case_orders_csv) < newest_order_part:
            return True

    return False


def _ensure_master_dataset_fresh() -> None:
    global _AUTO_BUILD_ATTEMPTED

    if _AUTO_BUILD_ATTEMPTED:
        return

    if not _needs_master_rebuild():
        return

    build_script = BASE_DIR / "scripts" / "build_dataset.py"
    if not build_script.exists():
        return

    _AUTO_BUILD_ATTEMPTED = True
    try:
        subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(BASE_DIR),
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        # Avoid breaking page loads if auto-rebuild cannot run in current context.
        pass


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
    _ensure_master_dataset_fresh()
    csv_path = DATA_DIR / "opinions.csv"
    if not csv_path.exists():
        return _empty_opinions_df()
    source_mtime = os.path.getmtime(csv_path)
    return _load_opinions_cached(str(csv_path), source_mtime)


@st.cache_data(ttl=3600)
def _load_docket_crosswalk_cached(path_str: str, source_mtime: float) -> pd.DataFrame:
    """Return generated and manually reviewed docket aliases by source file key."""
    _ = source_mtime
    return pd.read_csv(path_str, dtype=str).fillna("")


def load_docket_crosswalk() -> pd.DataFrame:
    path = DATA_DIR / "case_docket_crosswalk.csv"
    if not path.exists():
        return pd.DataFrame(columns=["source_file_key", "source_type", "docket_numbers", "source_url"])
    return _load_docket_crosswalk_cached(str(path), os.path.getmtime(path))


@st.cache_data(ttl=3600)
def _load_csv_as_strings_cached(path_str: str, source_mtime: float) -> pd.DataFrame:
    _ = source_mtime
    return pd.read_csv(path_str, dtype=str).fillna("")


def load_official_pdf_manifest_audit() -> pd.DataFrame:
    """Return official PDFs that the court lists but the local corpus lacks."""
    path = DATA_DIR / "official_pdf_manifest_audit.csv"
    if not path.exists():
        return pd.DataFrame(
            columns=["source_type", "listed_case_number", "listed_case_name", "pdf_url", "audit_status"]
        )
    return _load_csv_as_strings_cached(str(path), os.path.getmtime(path))


def load_unmatched_argument_review_queue() -> pd.DataFrame:
    """Return historical oral arguments lacking a published PDF disposition."""
    path = DATA_DIR / "unmatched_argument_review_queue.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_csv_as_strings_cached(str(path), os.path.getmtime(path))


def load_pending_oral_argument_cases() -> pd.DataFrame:
    """Return docket-specific cases known to be awaiting disposition after argument."""
    path = BASE_DIR / "data" / "pending_oral_argument_cases.csv"
    if not path.exists():
        return pd.DataFrame(columns=["case_number", "case_name", "argument_date", "notes"])
    return _load_csv_as_strings_cached(str(path), os.path.getmtime(path))


def load_unmatched_disposition_reconciliation() -> pd.DataFrame:
    """Return exact-docket research evidence for unresolved arguments."""
    path = DATA_DIR / "unmatched_disposition_reconciliation.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_csv_as_strings_cached(str(path), os.path.getmtime(path))


def load_orphan_official_pdf_recovery_candidates() -> pd.DataFrame:
    """Return caption-verified checks of standard official PDF candidates."""
    path = DATA_DIR / "orphan_official_pdf_recovery_candidates.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_csv_as_strings_cached(str(path), os.path.getmtime(path))


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
    if "case_name" in merged.columns:
        merged = merged[merged["case_name"].fillna("").str.lower() != "request a transcript"]
    if "case_number" in merged.columns:
        merged = merged[merged["case_number"].fillna("").str.lower() != "transcript-instructions"]
    return merged


def load_case_orders() -> pd.DataFrame:
    _ensure_master_dataset_fresh()
    case_orders_path = DATA_DIR / "case_orders.csv"
    jx3_path = DATA_DIR / "3jx_orders.csv"

    case_orders_mtime = os.path.getmtime(case_orders_path) if case_orders_path.exists() else None
    jx3_mtime = os.path.getmtime(jx3_path) if jx3_path.exists() else None

    return _load_case_orders_cached(case_orders_mtime, jx3_mtime)


@st.cache_data
def load_opinion_text(case_number: str) -> str:
    path = DATA_DIR / "text" / f"{case_number}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@st.cache_data(ttl=3600)
def _load_oral_arguments_cached(
    index_path_str: str,
    stats_path_str: str,
    index_mtime: float,
    stats_mtime: float,
    transcript_mtime: float,
    pdf_date_overrides_mtime: float,
) -> list[dict]:
    """Load oral-argument metadata, public statistics, and searchable text."""
    _ = (index_mtime, stats_mtime, transcript_mtime, pdf_date_overrides_mtime)
    index_path = Path(index_path_str)
    stats_path = Path(stats_path_str)
    with open(index_path, encoding="utf-8") as fh:
        records = json.load(fh)
    with open(stats_path, encoding="utf-8") as fh:
        stats_by_case = {row["case_number"]: row for row in json.load(fh)}
    pdf_dates: dict[str, str] = {}
    for path in sorted(PDF_DATE_OVERRIDES_DIR.glob("*.json")):
        pdf_dates.update(json.loads(path.read_text(encoding="utf-8")))

    oral_argument_dir = DATA_DIR / "oral_arguments"
    prepared: list[dict] = []
    for source in records:
        case_number = str(source.get("case_number", "")).strip()
        if not case_number:
            continue
        record = {
            key: value
            for key, value in source.items()
            if not key.startswith("granite_export_")
        }
        source_date = source.get("argument_date")
        record.update(stats_by_case.get(case_number, {}))
        if source_date:
            record["argument_date"] = source_date
        if case_number in pdf_dates:
            record["argument_date"] = str(pdf_dates[case_number])
        record["case_name"] = re.sub(
            r"^New Hampshire\s+(?:Versus|v\.?)\s+",
            "State v. ",
            str(record.get("case_name", "")),
            flags=re.IGNORECASE,
        )
        record["docket_numbers"] = normalize_docket_numbers(case_number)
        text_path = oral_argument_dir / "text" / f"{case_number}.txt"
        record["transcript_text"] = (
            text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        )
        prepared.append(record)
    return prepared


def load_oral_arguments() -> list[dict]:
    """Return the deployable oral-argument collection with public statistics."""
    index_path = DATA_DIR / "oral_arguments.json"
    stats_path = DATA_DIR / "oral_argument_stats.json"
    if not index_path.exists() or not stats_path.exists():
        return []
    transcript_paths = list((DATA_DIR / "oral_arguments" / "text").glob("*.txt"))
    transcript_mtime = _latest_mtime(transcript_paths) or 0
    pdf_date_overrides_mtime = _latest_mtime(list(PDF_DATE_OVERRIDES_DIR.glob("*.json"))) or 0
    return _load_oral_arguments_cached(
        str(index_path),
        str(stats_path),
        os.path.getmtime(index_path),
        os.path.getmtime(stats_path),
        transcript_mtime,
        pdf_date_overrides_mtime,
    )


@st.cache_data(ttl=3600)
def load_speaker_statistics() -> list[dict]:
    """Load speaker statistics (Justice vs Counsel speaking time, words, pace)."""
    stats_path = DATA_DIR / "oral_arguments_speaker_stats.json"
    if not stats_path.exists():
        return []
    with open(stats_path, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(ttl=3600)
def _load_attorney_statistics_cached(path_str: str, source_mtime: float) -> dict:
    """Load attorney statistics, keyed by source modification time."""
    _ = source_mtime
    with open(path_str, encoding="utf-8") as fh:
        return json.load(fh)


def load_attorney_statistics() -> dict:
    """Load attorney and firm statistics, invalidating when the file changes."""
    stats_path = DATA_DIR / "oral_arguments_attorney_stats.json"
    if not stats_path.exists():
        return {"case_attorneys": {}, "attorney_stats": [], "firm_stats": []}
    return _load_attorney_statistics_cached(str(stats_path), stats_path.stat().st_mtime)


@st.cache_data(ttl=3600)
def _load_brief_counsel_cached(path_str: str, source_mtime: float) -> dict:
    """Load published brief-counsel facts, keyed by source modification time."""
    _ = source_mtime
    with open(path_str, encoding="utf-8") as fh:
        return json.load(fh)


def load_brief_counsel() -> dict[str, list[dict]]:
    """Return brief counsel grouped by docket from official decisions."""
    path = DATA_DIR / "brief_counsel.json"
    if not path.exists():
        return {}
    payload = _load_brief_counsel_cached(str(path), path.stat().st_mtime)
    grouped: dict[str, list[dict]] = {}
    for fact in payload.get("facts", []):
        docket = str(fact.get("docket") or "")
        if docket:
            grouped.setdefault(docket, []).append(fact)
    return grouped


@st.cache_data(ttl=3600)
def load_attorney_justice_interactions() -> dict:
    """Load attorney-justice interaction data."""
    interactions_path = DATA_DIR / "attorney_justice_interactions.json"
    if not interactions_path.exists():
        return {"attorney_interactions": [], "justice_interactions": [], "summary": {}}
    with open(interactions_path, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(ttl=3600)
def load_enhanced_statistics() -> dict:
    """Load enhanced oral arguments statistics (temporal, complexity, networks)."""
    enhanced_path = DATA_DIR / "oral_arguments_enhanced_stats.json"
    if not enhanced_path.exists():
        return {
            "temporal_trends": {},
            "complexity_analysis": {},
            "attorney_networks": {},
            "case_parties": {}
        }
    with open(enhanced_path, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(ttl=3600)
def load_firm_metadata() -> dict:
    """Load firm metadata from the canonical reviewed-firm CSV."""
    source_path = DATA_DIR.parent / "nh_supreme_court_firms_enriched_v7.csv"
    if not source_path.exists():
        return {"firms": []}
    with open(source_path, newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(fh)
        firms_lookup = {}
        for row in rows:
            short_name = row.get("short_name", "").strip()
            full_name = row.get("full_name", "").strip()
            review_status = row.get("review_status", "").strip().lower()
            if (
                not short_name
                or not full_name
                or review_status.startswith(NON_FIRM_STATUS_PREFIX)
            ):
                continue
            firms_lookup.setdefault(short_name, {
                "short_name": short_name,
                "full_name": full_name,
                "website": row.get("website", "").strip(),
                "description": None,
            })
        return {"firms": list(firms_lookup.values()), "lookup": firms_lookup}


@st.cache_data(ttl=3600)
def _load_oral_argument_artifact(path_str: str, source_mtime: float) -> str:
    _ = source_mtime
    return Path(path_str).read_text(encoding="utf-8")


def _oral_argument_artifact(case_number: str, folder: str, suffix: str) -> str:
    path = DATA_DIR / "oral_arguments" / folder / f"{case_number}{suffix}"
    if not path.exists():
        return ""
    return _load_oral_argument_artifact(str(path), os.path.getmtime(path))


def load_oral_argument_text(case_number: str) -> str:
    """Load the plain-text transcript for one docket key."""
    return _oral_argument_artifact(case_number, "text", ".txt")


def load_oral_argument_markdown(case_number: str) -> str:
    """Load the readable Markdown transcript for one docket key."""
    return _oral_argument_artifact(case_number, "markdown", ".md")


def load_oral_argument(case_number: str) -> dict | None:
    """Find an oral argument by a primary or combined docket number."""
    return find_argument_for_docket(load_oral_arguments(), case_number)


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
        return "Unknown"
    mtime = os.path.getmtime(csv_path)
    return pd.Timestamp(mtime, unit="s").strftime("%B %d, %Y %I:%M %p")


@st.cache_data(ttl=3600)
def _load_argument_dispositions_cached(path_str: str, source_mtime: float) -> pd.DataFrame:
    """Load argument dispositions fact table, keyed by source modification time."""
    _ = source_mtime
    return pd.read_csv(
        path_str,
        parse_dates=["argument_date", "disposition_date"],
        low_memory=False,
    )


def load_argument_dispositions() -> pd.DataFrame:
    """Load the canonical argument dispositions fact table."""
    path = DATA_DIR / "argument_dispositions.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_argument_dispositions_cached(str(path), os.path.getmtime(path))


@st.cache_data(ttl=3600)
def _load_simple_csv_cached(path_str: str, source_mtime: float) -> pd.DataFrame:
    """Load a simple CSV file, keyed by source modification time."""
    _ = source_mtime
    return pd.read_csv(path_str)


def load_argument_participants() -> pd.DataFrame:
    """Load the argument participants bridge table."""
    path = DATA_DIR / "argument_participants.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_simple_csv_cached(str(path), os.path.getmtime(path))


def load_argument_topics() -> pd.DataFrame:
    """Load the argument topics bridge table."""
    path = DATA_DIR / "argument_topics.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_simple_csv_cached(str(path), os.path.getmtime(path))


def load_argument_disposition_links() -> pd.DataFrame:
    """Load the argument disposition links bridge table."""
    path = DATA_DIR / "argument_disposition_links.csv"
    if not path.exists():
        return pd.DataFrame()
    return _load_simple_csv_cached(str(path), os.path.getmtime(path))


@st.cache_data(ttl=3600)
def load_argument_dispositions_metadata() -> dict:
    """Load the argument dispositions metadata and data dictionary."""
    path = DATA_DIR / "argument_dispositions_metadata.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
