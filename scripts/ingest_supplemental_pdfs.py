"""Download and ingest verified official PDFs outside the normal court indexes.

This is deliberately limited to ``data/official_pdf_manifest_supplement.csv``.
It does not use captions or filenames to infer an identity: every row must
already contain a reviewed docket, source type, and official PDF URL.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.parse_opinions import parse_pdf


SUPPLEMENT_PATH = ROOT / "data" / "official_pdf_manifest_supplement.csv"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def _rows() -> list[dict[str, str]]:
    with SUPPLEMENT_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("pdf_url") and row.get("case_number")]


def _pdf_path(row: dict[str, str]) -> Path:
    year = row["case_number"][:4]
    source_dir = "orders" if row.get("source_type") == "case_order" else "supplemental"
    filename = Path(urlparse(row["pdf_url"]).path).name
    return RAW_DIR / "pdfs" / source_dir / year / filename


async def _download(page, row: dict[str, str]) -> Path:
    path = _pdf_path(row)
    if path.exists() and path.stat().st_size > 1000:
        return path
    result = await page.evaluate(
        """async (url) => {
            const response = await fetch(url, {credentials: 'include'});
            if (!response.ok) return {ok: false, status: response.status};
            const bytes = new Uint8Array(await response.arrayBuffer());
            let binary = '';
            for (const byte of bytes) binary += String.fromCharCode(byte);
            return {ok: true, data: btoa(binary)};
        }""",
        row["pdf_url"],
    )
    if not result.get("ok"):
        raise RuntimeError(f"HTTP {result.get('status')} for {row['pdf_url']}")
    body = base64.b64decode(result["data"])
    if body[:4] != b"%PDF":
        raise RuntimeError(f"Official URL did not return a PDF: {row['pdf_url']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _merge_record(row: dict[str, str], path: Path) -> None:
    source_type = row.get("source_type", "opinion")
    year = row["case_number"][:4]
    metadata = {
        "case_number": row["case_number"],
        "case_name": row.get("case_name", ""),
        "pdf_url": row["pdf_url"],
        "pdf_local_path": str(path),
        "opinion_type": source_type,
        "date_issued": None,
    }
    parsed = parse_pdf(path, metadata)
    if not parsed:
        raise RuntimeError(f"Could not parse {path}")
    filename = f"case_orders_{year}.json" if source_type == "case_order" else f"opinions_{year}.json"
    target = PROCESSED_DIR / filename
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    merged = [
        record for record in existing
        if record.get("case_number") != parsed["case_number"] and record.get("pdf_url") != parsed["pdf_url"]
    ]
    merged.append(parsed)
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")


async def ingest() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is required; install requirements and Chromium first.") from exc
    rows = _rows()
    if not rows:
        print("No supplemental official PDFs to ingest.")
        return
    async with async_playwright() as playwright:
        # The court's CDN rejects headless PDF fetches; match the project's
        # ordinary downloader, which uses a visible Chromium context.
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.courts.nh.gov", wait_until="domcontentloaded")
        for row in rows:
            path = await _download(page, row)
            _merge_record(row, path)
            print(f"Ingested {row['case_number']} from {row['pdf_url']}")
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(ingest())


if __name__ == "__main__":
    main()
