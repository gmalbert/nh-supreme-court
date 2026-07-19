"""Compare freshly scraped court PDF indexes with the local disposition corpus.

Run the opinion and case-order index scrapers first.  This audit does not
infer a case identity from a title or filename: it flags official PDF URLs that
are absent from the local corpus for review and ingestion.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "official_pdf_manifest_audit.csv"
SUPPLEMENTAL_MANIFEST_PATH = ROOT / "data" / "official_pdf_manifest_supplement.csv"
VERIFIED_3JX_ORDERS_PATH = ROOT / "data" / "verified_3jx_orders.csv"


def _file_key(url: object) -> str:
    return Path(urlparse(str(url or "")).path).stem.lower()


def _read_index_records(pattern: str, source_type: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(RAW_DIR.glob(pattern)):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in records:
            url = str(record.get("pdf_url") or "")
            if not url:
                continue
            rows.append(
                {
                    "source_type": source_type,
                    "source_index": path.name,
                    "source_file_key": _file_key(url),
                    "listed_case_number": record.get("case_number") or "",
                    "listed_case_name": record.get("case_name") or "",
                    "pdf_url": url,
                }
            )
    return rows


def _read_supplemental_records() -> list[dict[str, object]]:
    """Load verified official PDFs omitted from the court's year listing."""
    if not SUPPLEMENTAL_MANIFEST_PATH.exists():
        return []
    records = []
    for row in pd.read_csv(SUPPLEMENTAL_MANIFEST_PATH, dtype=str).fillna("").to_dict("records"):
        url = str(row.get("pdf_url") or "")
        if not url:
            continue
        records.append(
            {
                "source_type": row.get("source_type") or "unknown",
                "source_index": "official_pdf_manifest_supplement.csv",
                "source_file_key": _file_key(url),
                "listed_case_number": row.get("case_number") or "",
                "listed_case_name": row.get("case_name") or "",
                "pdf_url": url,
            }
        )
    return records


def _read_verified_3jx_records() -> list[dict[str, object]]:
    """Load exact-docket 3JX recoveries from the incomplete annual archive."""
    if not VERIFIED_3JX_ORDERS_PATH.exists():
        return []
    records = []
    for row in pd.read_csv(VERIFIED_3JX_ORDERS_PATH, dtype=str).fillna("").to_dict("records"):
        url = str(row.get("pdf_url") or "")
        if not url:
            continue
        records.append(
            {
                "source_type": "3jx_order",
                "source_index": "verified_3jx_orders.csv",
                "source_file_key": _file_key(url),
                "listed_case_number": row.get("case_number") or "",
                "listed_case_name": row.get("case_name") or "",
                "pdf_url": url,
            }
        )
    return records


def _local_url_indexes() -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    file_keys: set[str] = set()
    for filename in ("opinions.csv", "case_orders.csv", "3jx_orders.csv"):
        path = PROCESSED_DIR / filename
        if not path.exists():
            continue
        for url in pd.read_csv(path, usecols=["pdf_url"], dtype=str).fillna("")["pdf_url"]:
            normalized = str(url).strip()
            if normalized:
                urls.add(normalized)
                file_keys.add(_file_key(normalized))
    # Some legitimate source records are deliberately excluded from the flat
    # case-explorer tables (for example, administrative redistricting orders).
    # They are still present in the parsed corpus and should not be reported as
    # acquisition gaps.
    for pattern in ("opinions_*.json", "case_orders_*.json"):
        for path in PROCESSED_DIR.glob(pattern):
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for record in records:
                normalized = str(record.get("pdf_url") or "").strip()
                if normalized:
                    urls.add(normalized)
                    file_keys.add(_file_key(normalized))
    return urls, file_keys


def build_audit() -> pd.DataFrame:
    """Return one deduplicated manifest row per official PDF URL."""
    manifest = _read_index_records("index_*.json", "opinion")
    manifest.extend(_read_index_records("orders_index_*.json", "case_order"))
    # 3JX final orders are a separate disposition channel.  They must be in
    # the inventory audit as well; otherwise the audit can wrongly describe a
    # docket as having no published disposition merely because it is not an
    # opinion or a case order.
    manifest.extend(_read_index_records("3jx_*.json", "3jx_order"))
    manifest.extend(_read_verified_3jx_records())
    manifest.extend(_read_supplemental_records())
    if not manifest:
        return pd.DataFrame()

    local_urls, local_file_keys = _local_url_indexes()
    frame = pd.DataFrame(manifest).drop_duplicates("pdf_url", keep="last")
    frame["local_url_present"] = frame["pdf_url"].isin(local_urls)
    frame["local_file_key_present"] = frame["source_file_key"].isin(local_file_keys)
    frame["audit_status"] = frame.apply(
        lambda row: "present" if row.local_url_present else (
            "possible_url_change" if row.local_file_key_present else "missing_from_local_corpus"
        ),
        axis=1,
    )
    return frame.sort_values(["audit_status", "source_type", "pdf_url"])


def main() -> None:
    audit = build_audit()
    audit.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"Wrote {len(audit)} official PDF manifest rows to {OUTPUT_PATH}")
    if not audit.empty:
        print(audit["audit_status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
