"""Canonical docket extraction and source-file crosswalk helpers."""

from __future__ import annotations

import ast
import json
import re

import pandas as pd


# Newer dockets are usually YYYY-NNNN; older records also use YYYY-NNN.
DOCKET_RE = re.compile(r"\b(?:19|20)\d{2}-\d{3,4}\b")


def extract_docket_numbers(value: object) -> list[str]:
    """Return unique docket numbers in their first-seen order."""
    return list(dict.fromkeys(DOCKET_RE.findall(str(value or ""))))


def parse_docket_numbers(value: object) -> list[str]:
    """Read a stored docket list, falling back to docket extraction."""
    if isinstance(value, (list, tuple, set)):
        return list(dict.fromkeys(str(item) for item in value if str(item).strip()))
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(value)
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, (list, tuple, set)):
                return list(dict.fromkeys(str(item) for item in parsed if str(item).strip()))
    return extract_docket_numbers(value)


def apply_docket_crosswalk(
    frame: pd.DataFrame, crosswalk: pd.DataFrame, source_type: str
) -> pd.DataFrame:
    """Attach canonical docket lists while retaining the original source key.

    The source key may be a court PDF filename stem rather than a docket.  The
    crosswalk is keyed on that stable source identifier, so source URLs and
    local artifacts remain untouched.
    """
    result = frame.copy()
    if "case_number" not in result.columns:
        result["source_file_key"] = ""
        result["docket_numbers"] = [[] for _ in range(len(result))]
        return result

    result["source_file_key"] = result["case_number"].fillna("").astype(str)
    result["docket_numbers"] = result["source_file_key"].map(extract_docket_numbers)
    if crosswalk.empty:
        return result

    candidates = crosswalk[crosswalk["source_type"] == source_type]
    aliases = {
        str(row.source_file_key): parse_docket_numbers(row.docket_numbers)
        for row in candidates.itertuples(index=False)
    }
    result["docket_numbers"] = result.apply(
        lambda row: aliases.get(row["source_file_key"], row["docket_numbers"]), axis=1
    )
    return result
