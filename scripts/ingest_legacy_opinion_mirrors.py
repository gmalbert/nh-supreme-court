"""Ingest caption-verified orphaned NH Supreme Court dispositions from mirrors.

Use only for a published opinion missing from the current court archive index.
Each row must identify a specific docket and a stable public PDF mirror.  The
PDF's caption, rather than its title or filename, must contain that docket.
Records retain external-mirror provenance and are never represented as part of
the current official court index.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.parse_opinions import parse_pdf


MANIFEST_PATH = ROOT / "data" / "legacy_opinion_mirrors.csv"
RAW_DIR = ROOT / "data" / "raw" / "pdfs" / "legacy_mirrors"
PROCESSED_DIR = ROOT / "data" / "processed"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("case_number") and row.get("pdf_url")]


def _download(row: dict[str, str]) -> Path:
    docket = row["case_number"]
    filename = Path(urlparse(row["pdf_url"]).path).name or f"{docket}.pdf"
    path = RAW_DIR / docket[:4] / filename
    if path.exists() and path.stat().st_size > 1000:
        return path
    request = Request(row["pdf_url"], headers={"User-Agent": "NH-court-data-audit/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            content = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not download {docket}: {exc}") from exc
    if not content.startswith(b"%PDF"):
        raise RuntimeError(f"Mirror did not return a PDF for {docket}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _merge(row: dict[str, str], pdf_path: Path) -> None:
    docket = row["case_number"]
    parsed = parse_pdf(
        pdf_path,
        {
            "case_number": docket,
            "case_name": row.get("case_name", ""),
            "pdf_url": row["pdf_url"],
            "pdf_local_path": str(pdf_path),
            "opinion_type": row.get("source_type", "opinion") or "opinion",
        },
    )
    if not parsed:
        raise RuntimeError(f"Could not parse {pdf_path}")
    if docket not in set(parsed.get("docket_numbers") or []):
        raise RuntimeError(f"Caption verification failed for {docket}: {parsed.get('docket_numbers')}")
    parsed["source_provenance"] = "external_mirror_verified_caption"
    parsed["source_url"] = row.get("source_url", "")
    parsed["source_notes"] = row.get("notes", "")

    source_type = row.get("source_type", "opinion") or "opinion"
    target_prefix = "case_orders" if source_type == "case_order" else "opinions"
    target = PROCESSED_DIR / f"{target_prefix}_{docket[:4]}.json"
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    existing = [
        record for record in existing
        if docket not in set(record.get("docket_numbers") or [])
        and record.get("case_number") != docket
    ]
    existing.append(parsed)
    target.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()
    for row in _rows(args.manifest):
        pdf_path = _download(row)
        _merge(row, pdf_path)
        print(f"Ingested verified legacy opinion: {row['case_number']}")


if __name__ == "__main__":
    main()
