"""Audit transcript attorney rosters against official opinion appearances.

The transcript metadata is the source for attorney profile statistics, but it
can contain stale or synthetic rosters. This script flags metadata attorneys
whose names do not appear in the official opinion appearance block.

Usage:
    python scripts/audit_attorney_rosters.py
    python scripts/audit_attorney_rosters.py --write-csv data/processed/attorney_roster_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
TRANSCRIPTS_DIR = Path("/Volumes/AI-Storage/nh-supreme-court-transcripts")
ATTORNEY_NAME_MAP_FILE = ROOT / "data" / "attorney_name_map.json"
CASE_ATTORNEY_OVERRIDES_FILE = ROOT / "data" / "case_attorney_overrides.json"


def normalize_text(value: str) -> str:
    """Normalize punctuation/spacing for loose text containment checks."""
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    value = normalize_text(value)
    suffixes = {"jr", "sr", "ii", "iii", "iv", "esq"}
    parts = [part for part in value.split() if part not in suffixes]
    return " ".join(parts)


def load_name_map() -> dict[str, str]:
    with open(ATTORNEY_NAME_MAP_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        alias: canonical
        for alias, canonical in data.items()
        if alias != "comment" and isinstance(canonical, str) and canonical.strip()
    }


def load_overridden_cases() -> set[str]:
    if not CASE_ATTORNEY_OVERRIDES_FILE.exists():
        return set()
    with open(CASE_ATTORNEY_OVERRIDES_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return {key for key, value in data.items() if key != "comment" and isinstance(value, list)}


def appearance_block(case_number: str) -> str | None:
    """Return the opinion appearance block before the opinion body starts."""
    path = DATA_DIR / "text" / f"{case_number}.txt"
    if not path.exists():
        return None

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    block: list[str] = []
    for line in lines[:80]:
        stripped = line.strip()
        if re.match(r"^[A-Z][A-Z .,'-]+,\s+(C\.J\.|J\.)", stripped):
            break
        if stripped.startswith(("I. ", "II. ")):
            break
        block.append(stripped)
    return " ".join(block)


def roster_rows(include_overridden: bool = False) -> list[dict[str, Any]]:
    name_map = load_name_map()
    overridden_cases = load_overridden_cases()
    rows: list[dict[str, Any]] = []

    for metadata_path in sorted(TRANSCRIPTS_DIR.glob("*/*/*/metadata.json")):
        with open(metadata_path, encoding="utf-8") as fh:
            metadata = json.load(fh)

        case_number = str(metadata.get("docket_number") or "").strip()
        if not case_number:
            continue
        if not include_overridden and case_number in overridden_cases:
            continue

        block = appearance_block(case_number)
        if not block:
            continue
        normalized_block = normalize_text(block)

        for attorney in metadata.get("attorneys") or []:
            raw_name = str(attorney.get("name") or "").strip()
            if not raw_name:
                continue
            canonical_name = name_map.get(raw_name, raw_name).strip()
            if not canonical_name:
                continue

            normalized_name = normalize_name(canonical_name)
            appears_in_opinion = normalized_name in normalized_block
            if appears_in_opinion:
                continue

            rows.append(
                {
                    "case_number": case_number,
                    "case_name": metadata.get("case_name") or "",
                    "metadata_name": raw_name,
                    "canonical_name": canonical_name,
                    "firm": attorney.get("firm") or "",
                    "side": attorney.get("side") or "",
                    "metadata_path": str(metadata_path),
                }
            )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-csv", type=Path, help="Optional CSV path for audit results.")
    parser.add_argument(
        "--include-overridden",
        action="store_true",
        help="Include cases that already have reviewed overrides.",
    )
    args = parser.parse_args()

    rows = roster_rows(include_overridden=args.include_overridden)
    print(f"Flagged {len(rows)} metadata attorney entries absent from opinion appearance blocks.")

    for row in rows[:50]:
        print(
            f"{row['case_number']}: {row['canonical_name']} "
            f"({row['firm'] or 'no firm'}, {row['side'] or 'no side'}) - {row['case_name']}"
        )
    if len(rows) > 50:
        print(f"... {len(rows) - 50} more rows not shown")

    if args.write_csv:
        args.write_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.write_csv, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        print(f"Wrote {args.write_csv}")


if __name__ == "__main__":
    main()
