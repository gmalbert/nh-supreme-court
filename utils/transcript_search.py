"""Timestamp-aware search over oral-argument transcript segments."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = ROOT / "data" / "processed" / "oral_arguments"
INDEX_COLUMNS = [
    "docket",
    "case_name",
    "argument_date",
    "speaker",
    "text",
    "start_sec",
    "end_sec",
    "audio_url",
]


def build_transcript_index(
    transcripts_dir: str | Path = TRANSCRIPTS_DIR,
) -> pd.DataFrame:
    """Read exported transcript JSON files into a segment-level index."""
    rows: list[dict] = []
    for path in sorted(Path(transcripts_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        docket = str(data.get("case_number") or data.get("docket_number") or path.stem)
        for segment in data.get("segments", []):
            start = float(segment.get("start") or 0)
            rows.append(
                {
                    "docket": docket,
                    "case_name": data.get("case_name", ""),
                    "argument_date": data.get("argument_date", ""),
                    "speaker": segment.get("display_speaker") or segment.get("speaker") or "Unknown",
                    "text": str(segment.get("text") or "").strip(),
                    "start_sec": start,
                    "end_sec": float(segment.get("end") or start),
                    "audio_url": data.get("vimeo_url", ""),
                }
            )
    return pd.DataFrame(rows, columns=INDEX_COLUMNS)


def timestamp_url(url: str, start_sec: float) -> str:
    """Create the most portable timestamp link supported by Vimeo."""
    if not url:
        return ""
    seconds = max(0, int(start_sec))
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={seconds}s"


def _context(text: str, match: re.Match, radius: int = 150) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def search_transcripts(
    query: str,
    index: pd.DataFrame,
    case_filter: str | None = None,
    *,
    limit: int = 100,
) -> pd.DataFrame:
    """Search literal words or phrases and return playable result segments."""
    query = (query or "").strip()
    if not query or index.empty:
        return pd.DataFrame(
            columns=[
                "docket",
                "case_name",
                "argument_date",
                "speaker",
                "context",
                "start_sec",
                "timestamp_url",
            ]
        )
    working = index
    if case_filter:
        working = working[working["docket"].astype(str) == str(case_filter)]
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = working[working["text"].fillna("").str.contains(pattern, na=False)].copy()
    matches = matches.head(max(1, limit))
    matches["context"] = matches["text"].map(
        lambda text: _context(str(text), pattern.search(str(text)))
    )
    matches["timestamp_url"] = matches.apply(
        lambda row: timestamp_url(str(row.get("audio_url", "")), float(row["start_sec"])),
        axis=1,
    )
    return matches[
        [
            "docket",
            "case_name",
            "argument_date",
            "speaker",
            "context",
            "start_sec",
            "timestamp_url",
        ]
    ].reset_index(drop=True)


def search_transcript_corpus(
    query: str,
    *,
    transcripts_dir: str | Path = TRANSCRIPTS_DIR,
    case_filter: str | None = None,
    limit: int = 100,
) -> pd.DataFrame:
    """Search the full corpus without holding every transcript segment in RAM.

    The compact text export identifies matching dockets.  Only matching JSON
    files are then opened to recover speaker and exact timestamp evidence.
    """
    query = (query or "").strip()
    if not query:
        return search_transcripts(query, pd.DataFrame())
    root = Path(transcripts_dir)
    text_root = root / "text"
    lowered = query.casefold()
    rows: list[dict] = []
    candidates = (
        [text_root / f"{case_filter}.txt"]
        if case_filter
        else sorted(text_root.glob("*.txt"))
    )
    for text_path in candidates:
        if len(rows) >= limit:
            break
        try:
            transcript_text = text_path.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        if lowered not in transcript_text.casefold():
            continue
        json_path = root / f"{text_path.stem}.json"
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        matching_segments = [
            segment
            for segment in data.get("segments", [])
            if lowered in str(segment.get("text") or "").casefold()
        ]
        if not matching_segments:
            character_index = transcript_text.casefold().find(lowered)
            duration = float(data.get("duration_seconds") or 0)
            approximate_start = (
                duration * character_index / max(len(transcript_text), 1)
            )
            excerpt_start = max(0, character_index - 150)
            excerpt_end = min(
                len(transcript_text), character_index + len(query) + 150
            )
            rows.append(
                {
                    "docket": text_path.stem,
                    "case_name": data.get("case_name", text_path.stem),
                    "argument_date": data.get("argument_date", ""),
                    "speaker": "Cross-segment match",
                    "context": transcript_text[
                        excerpt_start:excerpt_end
                    ].strip(),
                    "start_sec": approximate_start,
                    "timestamp_url": timestamp_url(
                        str(data.get("vimeo_url", "")), approximate_start
                    ),
                }
            )
            continue
        for segment in matching_segments:
            segment_text = str(segment.get("text") or "")
            match = re.search(re.escape(query), segment_text, re.IGNORECASE)
            start_sec = float(segment.get("start") or 0)
            rows.append(
                {
                    "docket": text_path.stem,
                    "case_name": data.get("case_name", text_path.stem),
                    "argument_date": data.get("argument_date", ""),
                    "speaker": segment.get("display_speaker")
                    or segment.get("speaker")
                    or "Unknown",
                    "context": _context(segment_text, match)
                    if match
                    else segment_text[:320],
                    "start_sec": start_sec,
                    "timestamp_url": timestamp_url(
                        str(data.get("vimeo_url", "")), start_sec
                    ),
                }
            )
            if len(rows) >= limit:
                break
    return pd.DataFrame(
        rows,
        columns=[
            "docket",
            "case_name",
            "argument_date",
            "speaker",
            "context",
            "start_sec",
            "timestamp_url",
        ],
    )
