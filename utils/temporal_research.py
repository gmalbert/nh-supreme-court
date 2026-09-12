"""Temporal query controls that prevent future-law leakage."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable


AS_OF_RE = re.compile(
    r"\b(?:as of|on|before)\s+"
    r"(?P<year>\d{4})(?:-(?P<month>\d{1,2})(?:-(?P<day>\d{1,2}))?)?\b",
    re.IGNORECASE,
)


def parse_as_of_date(query: str) -> date | None:
    match = AS_OF_RE.search(query or "")
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month") or 12)
    day = int(match.group("day") or 31)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def result_date(result: dict[str, Any]) -> date | None:
    for field in ("date_issued", "decided_on", "date", "term", "year"):
        value = result.get(field)
        if value in (None, ""):
            continue
        text = str(value)
        try:
            if len(text) == 4 and text.isdigit():
                return date(int(text), 12, 31)
            return date.fromisoformat(text[:10])
        except ValueError:
            continue
    return None


def filter_as_of(
    results: Iterable[dict[str, Any]], as_of: date | None
) -> list[dict[str, Any]]:
    if as_of is None:
        return list(results)
    filtered = []
    for result in results:
        decided = result_date(result)
        if decided is None or decided <= as_of:
            filtered.append(result)
    return filtered


def temporal_leakage_rate(
    results: Iterable[dict[str, Any]], as_of: date
) -> float:
    rows = list(results)
    if not rows:
        return 0.0
    leaked = sum(
        1
        for row in rows
        if result_date(row) is not None and result_date(row) > as_of
    )
    return leaked / len(rows)
