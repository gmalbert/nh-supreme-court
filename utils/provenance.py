"""Field-level extraction provenance and impact-ranked review queues."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS field_observation (
  record_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  value_json TEXT,
  source_url TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  page_number INTEGER,
  confidence REAL,
  method TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  reviewed_value_json TEXT,
  reviewed_at TEXT,
  PRIMARY KEY (record_id, field_name, source_sha256, extractor_version)
);
CREATE INDEX IF NOT EXISTS idx_field_observation_review
ON field_observation (confidence, field_name);
"""


@dataclass(frozen=True)
class FieldObservation:
    record_id: str
    field_name: str
    value_json: str
    source_url: str
    source_sha256: str
    page_number: int | None
    confidence: float
    method: str
    extractor_version: str
    observed_at: str


def confidence_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return {
        "high": 0.95,
        "medium": 0.70,
        "low": 0.35,
        "unknown": 0.50,
    }.get(str(value or "unknown").strip().lower(), 0.50)


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def observation_from_record(
    record: dict[str, Any],
    field_name: str,
    *,
    record_id_field: str = "case_number",
    method: str = "opinion-pdf-parser",
    extractor_version: str | None = None,
    observed_at: str | None = None,
) -> FieldObservation:
    source_url = str(record.get("pdf_url") or record.get("source_url") or "local-corpus")
    source_hash = str(record.get("source_sha256") or sha256_text(source_url))
    return FieldObservation(
        record_id=str(record.get(record_id_field) or record.get("docket") or "unknown"),
        field_name=field_name,
        value_json=json.dumps(record.get(field_name), ensure_ascii=False, default=str),
        source_url=source_url,
        source_sha256=source_hash,
        page_number=record.get("source_page") or record.get("page_number"),
        confidence=confidence_value(
            record.get(
                f"{field_name}_confidence",
                record.get("parse_confidence", record.get("confidence")),
            )
        ),
        method=method,
        extractor_version=str(
            extractor_version
            or record.get("parse_version")
            or record.get("parser_version")
            or "unknown"
        ),
        observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
    )


def initialize_database(path: str | Path) -> Path:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
    return db_path


def upsert_observations(
    path: str | Path, observations: Iterable[FieldObservation]
) -> int:
    db_path = initialize_database(path)
    rows = [asdict(item) for item in observations]
    if not rows:
        return 0
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO field_observation (
              record_id, field_name, value_json, source_url, source_sha256,
              page_number, confidence, method, extractor_version, observed_at
            ) VALUES (
              :record_id, :field_name, :value_json, :source_url, :source_sha256,
              :page_number, :confidence, :method, :extractor_version, :observed_at
            )
            ON CONFLICT(record_id, field_name, source_sha256, extractor_version)
            DO UPDATE SET value_json=excluded.value_json,
                          confidence=excluded.confidence,
                          observed_at=excluded.observed_at
            """,
            rows,
        )
    return len(rows)


def load_observations(path: str | Path) -> pd.DataFrame:
    db_path = Path(path)
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as connection:
        return pd.read_sql_query("SELECT * FROM field_observation", connection)


def rank_review_queue(
    observations: pd.DataFrame,
    downstream_impact: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Rank uncertainty by confidence loss multiplied by downstream impact."""
    if observations.empty:
        return observations.copy()
    impacts = downstream_impact or {
        "outcome": 8,
        "date_issued": 8,
        "votes": 7,
        "author": 6,
        "topics": 5,
        "attorney_canonical": 5,
        "speaker": 4,
        "summary_paragraph": 3,
    }
    frame = observations.copy()
    frame["confidence"] = pd.to_numeric(
        frame["confidence"], errors="coerce"
    ).fillna(0.5)
    frame["downstream_impact"] = frame["field_name"].map(impacts).fillna(1)
    frame["review_priority"] = (
        (1.0 - frame["confidence"]) * frame["downstream_impact"]
    )
    return frame.sort_values(
        ["review_priority", "confidence"], ascending=[False, True]
    ).reset_index(drop=True)


def record_review(
    path: str | Path,
    *,
    record_id: str,
    field_name: str,
    source_sha256: str,
    extractor_version: str,
    reviewed_value: Any,
) -> None:
    with sqlite3.connect(initialize_database(path)) as connection:
        connection.execute(
            """
            UPDATE field_observation
               SET reviewed_value_json = ?, reviewed_at = ?
             WHERE record_id = ? AND field_name = ?
               AND source_sha256 = ? AND extractor_version = ?
            """,
            (
                json.dumps(reviewed_value, ensure_ascii=False, default=str),
                datetime.now(timezone.utc).isoformat(),
                record_id,
                field_name,
                source_sha256,
                extractor_version,
            ),
        )
