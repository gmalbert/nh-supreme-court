"""Build the normalized case corpus used by every retrieval backend.

Output: data/retrieval/case_documents.parquet

Each row is one case with:
    case_id            — stable sha-1 of href/term:name
    name, normalized_name
    href, term, docket_number, citation
    facts, question, holding, description
    retrieval_text     — combined label:text for retrieval
    decisions_json     — JSON-encoded Oyez decisions list
    oral_argument_audio — raw Oyez audio list (for transcript->case mapping)
    raw_metadata_json  — JSON-encoded timeline, lower_court, advocates, ...
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "case_detail.parquet"
OUT_DIR = ROOT / "data" / "retrieval"
OUT = OUT_DIR / "case_documents.parquet"


def clean(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, (list, dict)) and isinstance(value, float) and pd.isna(value):
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def normalize_case_name(value: str) -> str:
    if not value:
        return ""
    v = value.casefold().replace("versus", " v ")
    v = re.sub(r"\bvs?\.?\b", " v ", v)
    v = re.sub(r"[^a-z0-9]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def canonical_citation(value: object) -> str:
    """Parse an Oyez citation blob and return ''volume' u.s. 'page'' lowercased."""
    if value is None:
        return ""
    try:
        records = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return ""
    if isinstance(records, list):
        records = records[0] if records else {}
    if not isinstance(records, dict):
        return ""
    volume = str(records.get("volume") or "").strip()
    page = str(records.get("page") or "").strip()
    if not volume:
        return ""
    if not page:
        return f"{volume} u.s."
    return f"{volume} u.s. {page}".casefold()


def stable_case_id(href: str, name: str, term: str) -> str:
    key = (href or f"{term}:{name}").strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def main() -> None:
    columns = [
        "name", "href", "term", "docket_number", "citation",
        "facts_of_the_case", "question", "conclusion", "description",
        "decisions", "timeline", "lower_court", "advocates",
        "oral_argument_audio", "related_cases",
    ]
    df = pd.read_parquet(SOURCE, columns=columns)
    rows = []
    for record in df.to_dict("records"):
        name = clean(record.get("name"))
        href = clean(record.get("href"))
        term = clean(record.get("term"))
        fields = {
            "name": name,
            "facts": clean(record.get("facts_of_the_case")),
            "question": clean(record.get("question")),
            "holding": clean(record.get("conclusion")),
            "description": clean(record.get("description")),
        }
        retrieval_text = "\n".join(
            f"{label}: {value}" for label, value in fields.items() if value
        )
        rows.append(
            {
                "case_id": stable_case_id(href, name, term),
                "name": name,
                "normalized_name": normalize_case_name(name),
                "href": href,
                "term": term,
                "docket_number": clean(record.get("docket_number")),
                "citation": canonical_citation(record.get("citation")),
                **fields,
                "retrieval_text": retrieval_text,
                "decisions_json": json.dumps(record.get("decisions") or [], default=str),
                "oral_argument_audio": json.dumps(
                    record.get("oral_argument_audio") or [], default=str
                ),
                "raw_metadata_json": json.dumps(
                    {
                        key: record.get(key)
                        for key in (
                            "timeline",
                            "lower_court",
                            "advocates",
                            "oral_argument_audio",
                            "related_cases",
                        )
                    },
                    default=str,
                ),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False, compression="zstd")
    print(f"Wrote {len(rows)} cases -> {OUT}")


if __name__ == "__main__":
    main()