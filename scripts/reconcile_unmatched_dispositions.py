"""Find exact-docket disposition records for the historical review queue.

The court's current annual 3JX listing is incomplete for older years.  This
script uses a docket-specific public case catalog solely to discover an
official courts.nh.gov PDF URL, then writes a reviewable report.  It never
matches on title or date, and it does not change the disposition corpus.
"""

from __future__ import annotations

import argparse
import csv
import re
from html import unescape
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "data" / "processed" / "unmatched_argument_review_queue.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "unmatched_disposition_reconciliation.csv"
CATALOG_URL = "https://livefreeordie.legal/judiciary/cases/{docket}/"
EVIDENCE_COLUMNS = (
    "catalog_url",
    "official_pdf_url",
    "catalog_disposition_type",
    "catalog_disposition_date",
    "reconciliation_status",
)
OFFICIAL_PDF_RE = re.compile(
    r'<a\s+href="(?P<url>https://www\.courts\.nh\.gov/[^"]+\.pdf)">PDF</a>',
    re.IGNORECASE,
)
TYPE_RE = re.compile(r'<span>(?P<kind>[^<]*(?:3JX|opinion|order)[^<]*)</span>', re.IGNORECASE)
DATE_RE = re.compile(r'case-material-date">(?P<date>[^<]+)</td>', re.IGNORECASE)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def catalog_record(docket: str) -> dict[str, str]:
    """Return catalog evidence for one docket, or a blank record if absent."""
    source_url = CATALOG_URL.format(docket=docket)
    blank = {column: "" for column in EVIDENCE_COLUMNS}
    blank["catalog_url"] = source_url
    request = Request(source_url, headers={"User-Agent": "NH-court-data-audit/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        blank["reconciliation_status"] = f"catalog_unavailable: {type(exc).__name__}"
        return blank

    official = OFFICIAL_PDF_RE.search(html)
    if not official:
        blank["reconciliation_status"] = "no_official_pdf_link"
        return blank

    # The public catalog page is docket-specific.  Still record the stated
    # material type and date so a reviewer can see exactly what was found.
    kind = TYPE_RE.search(html)
    date = DATE_RE.search(html)
    return {
        **blank,
        "official_pdf_url": _clean(official.group("url")),
        "catalog_disposition_type": _clean(kind.group("kind")) if kind else "",
        "catalog_disposition_date": _clean(date.group("date")) if date else "",
        "reconciliation_status": "exact_docket_official_pdf_found",
    }


def reconcile(
    queue_path: Path, delay_seconds: float = 0.2, offset: int = 0, limit: int | None = None
) -> list[dict[str, str]]:
    with queue_path.open(newline="", encoding="utf-8") as handle:
        queue = list(csv.DictReader(handle))

    selected = queue[offset : offset + limit if limit is not None else None]
    rows: list[dict[str, str]] = []
    for index, source in enumerate(selected, start=offset + 1):
        docket = source["case_number"].strip()
        evidence = catalog_record(docket)
        rows.append({**source, **evidence})
        print(f"{index}/{len(queue)} {docket}: {evidence['reconciliation_status']}")
        if index < offset + len(selected):
            sleep(delay_seconds)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=QUEUE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--offset", type=int, default=0, help="Zero-based queue offset for a resumable batch")
    parser.add_argument("--limit", type=int, help="Maximum rows to reconcile in this batch")
    args = parser.parse_args()

    rows = reconcile(args.queue, args.delay, args.offset, args.limit)
    columns = list(rows[0]) if rows else []
    columns.extend(EVIDENCE_COLUMNS)
    columns = list(dict.fromkeys(columns))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} reconciliation rows to {args.output}")


if __name__ == "__main__":
    main()
