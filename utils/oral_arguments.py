"""Pure helpers for oral-argument search, docket matching, and statistics."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from statistics import median


DOCKET_RE = re.compile(r"\d{4}-\d{4}")
SEARCH_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]{1,}")


def normalize_docket_numbers(value: object) -> list[str]:
    """Extract one or more canonical docket numbers from an export key."""
    return list(dict.fromkeys(DOCKET_RE.findall(str(value or ""))))


def format_duration(seconds: object) -> str:
    """Format a duration as a compact hours/minutes label."""
    try:
        total_minutes = round(float(seconds) / 60)
    except (TypeError, ValueError):
        return "Unknown"
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"
    return f"{minutes} min"


def make_search_snippet(text: str, query: str, radius: int = 150) -> str:
    """Return a compact transcript excerpt around the first useful match."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return ""
    terms = SEARCH_TOKEN_RE.findall((query or "").lower())
    lowered = cleaned.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    position = min(positions) if positions else 0
    start = max(0, position - radius)
    end = min(len(cleaned), position + radius)
    if start:
        start = cleaned.find(" ", start) + 1
    if end < len(cleaned):
        boundary = cleaned.rfind(" ", 0, end)
        end = boundary if boundary > start else end
    prefix = "..." if start else ""
    suffix = "..." if end < len(cleaned) else ""
    return f"{prefix}{cleaned[start:end].strip()}{suffix}"


def search_oral_arguments(
    records: Iterable[Mapping[str, object]], query: str
) -> list[dict[str, object]]:
    """Rank oral arguments using metadata and full transcript text."""
    query = (query or "").strip().lower()
    prepared = [dict(record) for record in records]
    if not query:
        return sorted(
            prepared,
            key=lambda row: (str(row.get("argument_date", "")), str(row.get("case_name", ""))),
            reverse=True,
        )

    tokens = SEARCH_TOKEN_RE.findall(query)
    ranked: list[dict[str, object]] = []
    for record in prepared:
        docket = str(record.get("case_number", "")).lower()
        name = str(record.get("case_name", "")).lower()
        argument_date = str(record.get("argument_date", "")).lower()
        transcript = str(record.get("transcript_text", ""))
        transcript_lower = transcript.lower()
        score = 0
        if query == docket:
            score += 100
        if query in name:
            score += 45
        if query in docket:
            score += 35
        if query in argument_date:
            score += 30
        if query in transcript_lower:
            score += 12
        for token in tokens:
            score += 12 if token in name else 0
            score += 10 if token in docket else 0
            score += 6 if token in argument_date else 0
            score += min(transcript_lower.count(token), 5)
        if score:
            record["_score"] = score
            record["_snippet"] = make_search_snippet(transcript, query)
            ranked.append(record)

    return sorted(
        ranked,
        key=lambda row: (
            int(row.get("_score", 0)),
            str(row.get("argument_date", "")),
            str(row.get("case_name", "")),
        ),
        reverse=True,
    )


def find_argument_for_docket(
    records: Iterable[Mapping[str, object]], docket_number: object
) -> dict[str, object] | None:
    """Find an oral argument that contains the requested docket number."""
    docket = str(docket_number or "").strip()
    for record in records:
        dockets = record.get("docket_numbers") or normalize_docket_numbers(record.get("case_number"))
        if docket in dockets:
            return dict(record)
    return None


def collection_statistics(records: Iterable[Mapping[str, object]]) -> dict[str, float | int]:
    """Calculate public collection-level transcript statistics."""
    rows = list(records)
    durations = [float(row["duration_seconds"]) for row in rows if row.get("duration_seconds") is not None]
    word_counts = [int(row["word_count"]) for row in rows if row.get("word_count") is not None]
    return {
        "argument_count": len(rows),
        "total_duration_seconds": sum(durations),
        "median_duration_seconds": median(durations) if durations else 0,
        "total_word_count": sum(word_counts),
        "median_word_count": median(word_counts) if word_counts else 0,
    }
