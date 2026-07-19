"""Docket-based joins for oral arguments and published dispositions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
import re

import pandas as pd

from utils.dockets import parse_docket_numbers
from utils.oral_arguments import normalize_docket_numbers


RESOLUTION_LABELS = {
    "case_order": "Case order",
    "3jx_order": "3JX order",
    "opinion": "Opinion",
    "multiple": "Multiple disposition records",
    "needs_review": "Possible disposition — review needed",
    "unmatched": "No matching disposition found",
}

ASSESSMENT_LABELS = {
    "official_pdf_pending_ingestion": "Official PDF pending ingestion",
    "pending_after_oral_argument": "Pending after oral argument",
    "current_term_pending": "Current-term argument; disposition may be pending",
    "historical_no_disposition_in_corpus": "No published PDF disposition found",
}

_NON_CAPTION_PREFIXES = (
    "good morning",
    "good afternoon",
    "thank you",
    "we have",
    "for the benefit",
    "nice to see",
    "all right",
    "quite a crowd",
    "may it please",
    "why don t",
    "go good",
    "take your time",
)


def _dockets(value: object) -> set[str]:
    return set(normalize_docket_numbers(value))


def _source_dockets(frame: pd.DataFrame, source: str) -> set[str]:
    if frame.empty or "case_number" not in frame.columns:
        return set()
    if "docket_numbers" in frame.columns:
        values = frame["docket_numbers"].dropna()
        return {
            docket
            for value in values
            for docket in parse_docket_numbers(value)
        }
    values = frame["case_number"].dropna()
    return {
        docket
        for value in values
        for docket in _dockets(value)
    }


def _orders_for_source(case_orders: pd.DataFrame, source: str) -> pd.DataFrame:
    """Return a source slice, tolerating small fixture data without the column."""
    if "order_source" not in case_orders.columns:
        return case_orders if source == "case_order" else case_orders.iloc[0:0]
    return case_orders[case_orders["order_source"] == source]


def _resolution_for_dockets(
    dockets: set[str], source_dockets: Mapping[str, set[str]]
) -> str:
    matches = [source for source, values in source_dockets.items() if dockets & values]
    if not matches:
        return "unmatched"
    return matches[0] if len(matches) == 1 else "multiple"


def _title_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _has_transcript_fragment_caption(value: object) -> bool:
    """Return true when a transcript opening was saved instead of a caption."""
    return _title_key(value).startswith(_NON_CAPTION_PREFIXES)


def _review_candidate(record: Mapping[str, object], opinions: pd.DataFrame) -> bool:
    """Find a high-similarity same-date opinion without treating it as a match."""
    if opinions.empty or "date_argued" not in opinions.columns or "case_name" not in opinions.columns:
        return False
    argument_date = str(record.get("argument_date") or "")[:10]
    title = _title_key(record.get("case_name"))
    if not argument_date or not title:
        return False
    same_day = opinions[opinions["date_argued"].astype(str).str[:10] == argument_date]
    return any(
        SequenceMatcher(None, title, _title_key(candidate)).ratio() >= 0.82
        for candidate in same_day["case_name"]
    )


def argument_resolution_summary(
    oral_arguments: Iterable[Mapping[str, object]],
    case_orders: pd.DataFrame,
    opinions: pd.DataFrame,
) -> pd.DataFrame:
    """Classify each recorded argument by the disposition(s) sharing its docket.

    A combined-docket argument matches when any component docket matches.  A
    separate ``multiple`` category preserves the small number of arguments
    with more than one published disposition instead of assigning an arbitrary
    final result.
    """
    source_dockets = {
        "case_order": _source_dockets(
            _orders_for_source(case_orders, "case_order"),
            "case_order",
        ),
        "3jx_order": _source_dockets(
            _orders_for_source(case_orders, "3jx_order"),
            "3jx_order",
        ),
        "opinion": _source_dockets(opinions, "opinion"),
    }
    rows = []
    for record in oral_arguments:
        dockets = set(record.get("docket_numbers") or _dockets(record.get("case_number")))
        resolution = _resolution_for_dockets(dockets, source_dockets)
        if resolution == "unmatched" and _review_candidate(record, opinions):
            resolution = "needs_review"
        rows.append(
            {
                "case_number": record.get("case_number", ""),
                "term_year": record.get("term_year"),
                "resolution": resolution,
            }
        )
    return pd.DataFrame(rows, columns=["case_number", "term_year", "resolution"])


def assess_unmatched_arguments(
    resolutions: pd.DataFrame,
    oral_arguments: Iterable[Mapping[str, object]],
    official_pdf_gaps: set[str] | None = None,
    pending_dockets: set[str] | None = None,
) -> pd.DataFrame:
    """Explain unmatched arguments without turning a likely case into a match.

    The latest oral-argument term is treated as current and is therefore not
    called a historical corpus gap.  A verified official-PDF gap takes
    precedence over all other categories.
    """
    official_pdf_gaps = official_pdf_gaps or set()
    pending_dockets = pending_dockets or set()
    resolution_by_case = dict(zip(resolutions["case_number"], resolutions["resolution"]))
    records = [
        record for record in oral_arguments
        if resolution_by_case.get(record.get("case_number")) in {"unmatched", "needs_review"}
    ]
    terms = [int(record["term_year"]) for record in records if str(record.get("term_year", "")).isdigit()]
    current_term = max(terms) if terms else None
    rows = []
    for record in records:
        dockets = set(record.get("docket_numbers") or _dockets(record.get("case_number")))
        if dockets & pending_dockets:
            assessment = "pending_after_oral_argument"
        elif dockets & official_pdf_gaps:
            assessment = "official_pdf_pending_ingestion"
        elif current_term is not None and str(record.get("term_year")) == str(current_term):
            assessment = "current_term_pending"
        else:
            assessment = "historical_no_disposition_in_corpus"
        rows.append(
            {
                "case_number": record.get("case_number", ""),
                "argument_date": record.get("argument_date", ""),
                "term_year": record.get("term_year", ""),
                "case_name": record.get("case_name", ""),
                "assessment": assessment,
                "caption_metadata_status": (
                    "transcript_title_needs_roster_backfill"
                    if _has_transcript_fragment_caption(record.get("case_name"))
                    else "indexed"
                ),
            }
        )
    return pd.DataFrame(rows)


def disposition_source_summary(
    oral_arguments: Iterable[Mapping[str, object]],
    brief_counsel: Mapping[str, object],
    case_orders: pd.DataFrame,
    opinions: pd.DataFrame,
) -> pd.DataFrame:
    """Count unique disposition dockets associated with arguments or brief counsel.

    ``brief_counsel`` records published appearance language.  It is not used
    to infer that a case was submitted on the briefs alone.
    """
    argument_dockets = {
        docket
        for record in oral_arguments
        for docket in set(record.get("docket_numbers") or _dockets(record.get("case_number")))
    }
    brief_dockets = set(brief_counsel)
    disposition_sources = {
        "Case orders": _source_dockets(
            _orders_for_source(case_orders, "case_order"),
            "case_order",
        ),
        "3JX orders": _source_dockets(
            _orders_for_source(case_orders, "3jx_order"),
            "3jx_order",
        ),
        "Opinions": _source_dockets(opinions, "opinion"),
    }
    return pd.DataFrame(
        [
            {
                "Disposition": label,
                "With oral argument": len(dockets & argument_dockets),
                "With published brief counsel": len(dockets & brief_dockets),
            }
            for label, dockets in disposition_sources.items()
        ]
    )
