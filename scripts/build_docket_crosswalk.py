"""Build the docket-to-source-file crosswalk used for disposition matching."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.dockets import extract_docket_numbers


DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
TEXT_DIR = PROCESSED_DIR / "text"
ALIASES_PATH = DATA_DIR / "case_docket_aliases.csv"
OUTPUT_PATH = PROCESSED_DIR / "case_docket_crosswalk.csv"
HEADER_CHAR_LIMIT = 1800


def _header_dockets(source_file_key: str, case_name: object) -> list[str]:
    text_path = TEXT_DIR / f"{source_file_key}.txt"
    if text_path.exists():
        return extract_docket_numbers(text_path.read_text(encoding="utf-8")[:HEADER_CHAR_LIMIT])
    return extract_docket_numbers(case_name)


def _load_aliases() -> dict[tuple[str, str], dict[str, str]]:
    if not ALIASES_PATH.exists():
        return {}
    with ALIASES_PATH.open(newline="", encoding="utf-8") as fh:
        return {
            (row["source_file_key"], row["source_type"]): row
            for row in csv.DictReader(fh)
            if row.get("review_status", "").lower() == "approved"
        }


def _records_for_file(filename: str, source_type: str) -> list[dict[str, str]]:
    path = PROCESSED_DIR / filename
    if not path.exists():
        return []
    records = []
    for row in pd.read_csv(path, low_memory=False).fillna("").to_dict("records"):
        source_file_key = str(row.get("case_number", "")).strip()
        if not source_file_key:
            continue
        source_dockets = extract_docket_numbers(source_file_key)
        caption_dockets = _header_dockets(source_file_key, row.get("case_name"))
        dockets = list(dict.fromkeys([*source_dockets, *caption_dockets]))
        if not dockets:
            continue
        records.append({
            "source_file_key": source_file_key,
            "source_type": source_type,
            "docket_numbers": json.dumps(dockets),
            "source_url": str(row.get("pdf_url", "")),
            "match_method": "source_case_number_and_caption" if source_dockets and caption_dockets else ("source_case_number" if source_dockets else "caption_text"),
            "confidence": "high",
            "review_status": "generated",
        })
    return records


def main() -> None:
    aliases = _load_aliases()
    rows = []
    for filename, source_type in [
        ("opinions.csv", "opinion"),
        ("case_orders.csv", "case_order"),
        ("3jx_orders.csv", "3jx_order"),
    ]:
        rows.extend(_records_for_file(filename, source_type))

    for row in rows:
        alias = aliases.get((row["source_file_key"], row["source_type"]))
        if alias:
            row.update({
                "docket_numbers": alias["docket_numbers"],
                "source_url": alias.get("source_url") or row["source_url"],
                "match_method": alias.get("match_method") or "manual_review",
                "confidence": alias.get("confidence") or "high",
                "review_status": "approved",
            })

    columns = ["source_file_key", "source_type", "docket_numbers", "source_url", "match_method", "confidence", "review_status"]
    output = pd.DataFrame(rows, columns=columns).drop_duplicates(
        ["source_file_key", "source_type"], keep="last"
    )
    output.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"Wrote {len(output)} crosswalk rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
