"""Privacy-preserving product telemetry for research-quality signals."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable


ALLOWED_EVENTS = {
    "zero_result_search",
    "citation_click",
    "correction_submission",
    "answer_abstention",
    "verified_research_task",
}
SENSITIVE_KEYS = {
    "query",
    "query_text",
    "answer",
    "source_span",
    "email",
    "name",
    "note",
}
_LOCK = Lock()


def sanitize_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in (properties or {}).items():
        if key.lower() in SENSITIVE_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
    return clean


def record_event(
    event: str,
    properties: dict[str, Any] | None = None,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Record an allowlisted event; raw query text is never accepted."""
    if event not in ALLOWED_EVENTS:
        raise ValueError(f"Unsupported telemetry event: {event}")
    payload = {
        "event": event,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "properties": sanitize_properties(properties),
    }
    if path is not None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(event.get("event", "unknown") for event in events))
