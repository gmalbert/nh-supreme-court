"""Build the compact oral-argument index used by the deployed app."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.oral_arguments import has_confirmed_argument_date


DATA_DIR = ROOT / "data" / "processed"
PDF_DATE_OVERRIDES_DIR = ROOT / "data" / "oral_argument_pdf_dates"
CAPTION_OVERRIDES_PATH = ROOT / "data" / "oral_argument_caption_overrides.csv"
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


def _load_pdf_date_overrides() -> dict[str, str]:
    """Load court-PDF dates that must survive transcript-index rebuilds."""
    overrides: dict[str, str] = {}
    for path in sorted(PDF_DATE_OVERRIDES_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"PDF date override file must be an object: {path}")
        overrides.update({str(docket): str(date) for docket, date in payload.items()})
    return overrides


def _load_caption_overrides() -> dict[str, str]:
    """Load reviewed annual-roster captions for transcript records with bad titles."""
    if not CAPTION_OVERRIDES_PATH.exists():
        return {}
    with CAPTION_OVERRIDES_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    overrides: dict[str, str] = {}
    for row in rows:
        docket = str(row.get("docket", "")).strip()
        caption = str(row.get("case_name", "")).strip()
        if not docket or not caption:
            continue
        if docket in overrides:
            raise ValueError("Duplicate dockets in oral_argument_caption_overrides.csv")
        overrides[docket] = caption
    return overrides


def _normalize_case_name(case_name: str) -> str:
    return re.sub(r"^New Hampshire\s+(?:Versus|v\.?)\s+", "State v. ", case_name, flags=re.IGNORECASE)


def validate_argument_dates(records: list[dict]) -> None:
    """Reject a deployable index containing term-start fallback dates.

    The official annual oral-argument PDFs are the source of truth.  A missing
    override must fail the build rather than silently publishing October 1 as a
    hearing date.
    """
    invalid = [
        str(record.get("case_number", "unknown"))
        for record in records
        if not has_confirmed_argument_date(record)
    ]
    if invalid:
        examples = ", ".join(invalid[:10])
        suffix = " …" if len(invalid) > 10 else ""
        raise ValueError(
            f"Refusing to publish {len(invalid)} oral-argument record(s) with "
            f"missing or placeholder dates: {examples}{suffix}"
        )


def build_index(source_dir: Path) -> list[dict]:
    """Return public metadata from the per-case transcript records."""
    pdf_dates = _load_pdf_date_overrides()
    caption_overrides = _load_caption_overrides()
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
        docket = str(public_record["case_number"])
        if docket in pdf_dates:
            public_record["argument_date"] = pdf_dates[docket]
        if docket in caption_overrides:
            public_record["case_name"] = caption_overrides[docket]
        if public_record.get("case_name"):
            public_record["case_name"] = _normalize_case_name(str(public_record["case_name"]))
        records.append(public_record)

    case_numbers = [record["case_number"] for record in records]
    if len(case_numbers) != len(set(case_numbers)):
        raise ValueError("Duplicate case numbers found in oral-argument records")

    validate_argument_dates(records)

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
