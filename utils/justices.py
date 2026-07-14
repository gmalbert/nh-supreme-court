"""
Justice roster and historical bench helpers.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.constants import JUSTICE_DISPLAY, VOTE_NOT_PARTICIPATING

ROOT = Path(__file__).resolve().parent.parent
JUSTICES_FILE = ROOT / "data" / "justices.json"


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@lru_cache(maxsize=1)
def load_justices() -> list[dict[str, Any]]:
    """Load justice roster metadata, including tenure dates."""
    if not JUSTICES_FILE.exists():
        return []
    with open(JUSTICES_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def justice_display(key: str) -> str:
    """Return a display name for a justice key."""
    for justice in load_justices():
        if justice.get("key") == key and justice.get("display_name"):
            return str(justice["display_name"])
    return JUSTICE_DISPLAY.get(key, key.replace("_", " ").title())


def justice_role(key: str) -> str:
    """Return the justice role for a roster key."""
    for justice in load_justices():
        if justice.get("key") == key and justice.get("role"):
            return str(justice["role"])
    return "chief_justice" if "C.J." in justice_display(key) else "associate_justice"


def get_justice_keys_on_bench(bench_date: Any) -> list[str]:
    """Return roster keys for justices serving on a given date."""
    parsed_date = _parse_date(bench_date)
    if parsed_date is None:
        return []

    bench: list[str] = []
    for justice in load_justices():
        key = justice.get("key")
        appointed = _parse_date(justice.get("date_appointed"))
        retired = _parse_date(justice.get("date_retired"))
        if not key or appointed is None:
            continue
        if parsed_date < appointed:
            continue
        if retired is not None and parsed_date > retired:
            continue
        bench.append(str(key))
    return bench


def normalize_votes_for_bench(
    votes: dict[str, dict[str, Any]] | None,
    *,
    date_argued: Any = None,
    date_issued: Any = None,
) -> dict[str, dict[str, Any]]:
    """
    Limit vote records to the historical panel that sat on the case.

    Opinion JSON generated before this helper contains every known justice key,
    so historical cases can accidentally render current justices as inactive.
    Prefer the argument date because it identifies who sat on the case; fall
    back to the decision date for records without argument metadata.
    """
    if not votes:
        return {}

    panel_keys = get_justice_keys_on_bench(date_argued) or get_justice_keys_on_bench(date_issued)
    active_vote_keys = [
        key for key, record in votes.items()
        if record.get("vote") != VOTE_NOT_PARTICIPATING
    ]

    if panel_keys:
        ordered_keys = panel_keys[:]
        for key in active_vote_keys:
            if key not in ordered_keys:
                ordered_keys.append(key)
    else:
        ordered_keys = active_vote_keys[:]
        for key in votes:
            if key not in ordered_keys:
                ordered_keys.append(key)

    normalized: dict[str, dict[str, Any]] = {}
    for key in ordered_keys:
        record = dict(votes.get(key, {}))
        record.setdefault("display_name", justice_display(key))
        record.setdefault("role", justice_role(key))
        record.setdefault("vote", VOTE_NOT_PARTICIPATING)
        record.setdefault("note", None)
        normalized[key] = record
    return normalized
