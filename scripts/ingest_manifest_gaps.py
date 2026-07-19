"""Parse approved official-PDF audit gaps from already downloaded court files.

Each record is keyed by the official manifest's docket and URL.  This is a
backfill adapter for documents that have reached the raw PDF cache but were
not promoted by a bulk year parser.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.parse_opinions import parse_pdf


RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
AUDIT_PATH = PROCESSED_DIR / "official_pdf_manifest_audit.csv"


def _cached_pdf(row: dict[str, str]) -> Path | None:
    filename = Path(urlparse(row["pdf_url"]).path).name
    if row["source_type"] == "case_order":
        matches = sorted((RAW_DIR / "pdfs" / "orders").glob(f"*/{filename}"))
    else:
        matches = sorted((RAW_DIR / "pdfs").glob(f"*/{filename}"))
        matches.extend(sorted((RAW_DIR / "pdfs" / "supplemental").glob(f"*/{filename}")))
    return next((path for path in matches if path.stat().st_size > 1000), None)


def _merge(row: dict[str, str], pdf_path: Path) -> None:
    source_type = row["source_type"]
    docket = row["listed_case_number"]
    metadata = {
        "case_number": docket,
        "case_name": row["listed_case_name"],
        "pdf_url": row["pdf_url"],
        "pdf_local_path": str(pdf_path),
        "opinion_type": source_type,
        "date_issued": None,
    }
    parsed = parse_pdf(pdf_path, metadata)
    if not parsed:
        raise RuntimeError(f"Could not parse {pdf_path}")
    year = docket[:4]
    filename = f"case_orders_{year}.json" if source_type == "case_order" else f"opinions_{year}.json"
    target = PROCESSED_DIR / filename
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    existing = [
        record for record in existing
        if record.get("case_number") != docket and record.get("pdf_url") != row["pdf_url"]
    ]
    existing.append(parsed)
    target.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    if not AUDIT_PATH.exists():
        raise SystemExit("Run audit_official_pdf_manifest.py before ingesting manifest gaps.")
    with AUDIT_PATH.open(newline="", encoding="utf-8") as handle:
        gaps = [
            row for row in csv.DictReader(handle)
            if row.get("audit_status") == "missing_from_local_corpus"
        ]
    ingested = 0
    missing_cache = []
    for row in gaps:
        if not row.get("listed_case_number", "").strip():
            missing_cache.append(f"unkeyed official record: {row.get('listed_case_name', 'unknown')}")
            continue
        pdf_path = _cached_pdf(row)
        if pdf_path is None:
            missing_cache.append(row["listed_case_number"])
            continue
        _merge(row, pdf_path)
        ingested += 1
        print(f"Promoted {row['listed_case_number']} from {pdf_path.name}")
    print(f"Promoted {ingested} official PDF gap(s).")
    if missing_cache:
        print("Still requires download: " + ", ".join(missing_cache))


if __name__ == "__main__":
    main()
