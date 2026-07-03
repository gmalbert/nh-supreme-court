"""Build the compact oral-argument index used by the deployed app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
PUBLIC_FIELDS = (
    "case_number",
    "case_name",
    "argument_date",
    "term_year",
    "vimeo_url",
    "duration_seconds",
    "segment_count",
    "language",
    "model",
    "speaker_label_status",
    "exported_at",
)


def build_index(source_dir: Path) -> list[dict]:
    """Return public metadata from the per-case transcript records."""
    records: list[dict] = []
    for path in sorted(source_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        public_record = {
            field: record[field]
            for field in PUBLIC_FIELDS
            if record.get(field) not in (None, "")
        }
        if not public_record.get("case_number"):
            raise ValueError(f"Missing case_number in {path}")
        records.append(public_record)

    case_numbers = [record["case_number"] for record in records]
    if len(case_numbers) != len(set(case_numbers)):
        raise ValueError("Duplicate case numbers found in oral-argument records")

    return sorted(
        records,
        key=lambda record: (
            str(record.get("argument_date", "")),
            str(record["case_number"]),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DATA_DIR / "oral_arguments",
        help="Directory containing one JSON metadata record per argument",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "oral_arguments.json",
        help="Path for the compact deployable index",
    )
    args = parser.parse_args()

    records = build_index(args.source_dir)
    if not records:
        raise SystemExit(f"No per-case JSON records found in {args.source_dir}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(records, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
