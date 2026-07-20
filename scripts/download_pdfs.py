"""
scripts/download_pdfs.py
------------------------
Download PDFs referenced in data/raw/index_{year}.json using a headed
Playwright browser (required to pass Akamai CDN bot detection on courts.nh.gov).

Stores PDFs in data/raw/pdfs/{year}/{filename}.pdf
Skips already-downloaded files (idempotent).

Usage:
    python scripts/download_pdfs.py --years 2024 2025 2026

Note: A visible Chromium browser window will open during downloading.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"


def _pdf_filename(pdf_url: str) -> str:
    """Derive a filename from the PDF URL basename."""
    basename = Path(urlparse(pdf_url).path).name
    return basename if basename.endswith(".pdf") else "unknown.pdf"


async def download_year(page, year: int, errors: list, source: str = "opinions") -> dict:
    if source == "orders":
        index_path = RAW_DIR / f"orders_index_{year}.json"
        dest_base = RAW_DIR / "pdfs" / "orders" / str(year)
        scraper_hint = "scrape_orders_index.py"
    else:
        index_path = RAW_DIR / f"index_{year}.json"
        dest_base = RAW_DIR / "pdfs" / str(year)
        scraper_hint = "scrape_index.py"

    if not index_path.exists():
        print(f"  No index file for {year} — run {scraper_hint} first")
        return {"downloaded": 0, "skipped": 0, "failed": 0}

    with open(index_path, encoding="utf-8", errors="replace") as fh:
        records = json.load(fh)

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    dest_dir = dest_base
    dest_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        pdf_url = rec.get("pdf_url", "")
        if not pdf_url:
            continue

        filename = _pdf_filename(pdf_url)
        dest_path = dest_dir / filename

        if dest_path.exists() and dest_path.stat().st_size > 1000:
            counts["skipped"] += 1
            continue

        try:
            # Use JS fetch() in the browser context (avoids Akamai bot detection
            # that triggers on direct page.goto() navigation to PDF URLs)
            result = await page.evaluate(
                """async (url) => {
                    const resp = await fetch(url, {credentials: 'include'});
                    if (!resp.ok) return {ok: false, status: resp.status, data: null};
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    for (let i = 0; i < bytes.byteLength; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return {ok: true, status: resp.status, data: btoa(binary)};
                }""",
                pdf_url,
            )
            if not result["ok"]:
                raise ValueError(f"HTTP {result['status']}")
            import base64
            body = base64.b64decode(result["data"])
            if body[:4] == b"%PDF":
                dest_path.write_bytes(body)
                rec["pdf_local_path"] = str(dest_path)
                counts["downloaded"] += 1
                print(f"  Downloaded {filename} ({len(body):,} bytes)")
            else:
                raise ValueError(f"Response is not a PDF (got {body[:20]})")
        except Exception as exc:
            counts["failed"] += 1
            errors.append({"url": pdf_url, "year": year, "error": str(exc)})
            print(f"  FAILED {filename}: {exc}")

        # Small delay between requests
        await asyncio.sleep(0.5)

    # Write back updated index (with local paths)
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)

    return counts


async def download_all_async(years: list[int], source: str = "opinions") -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright")
        sys.exit(1)

    errors: list = []
    total = {"downloaded": 0, "skipped": 0, "failed": 0}

    warmup_url = (
        "https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/case-orders/2025"
        if source == "orders"
        else "https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/opinions/2025"
    )

    async with async_playwright() as pw:
        print("Launching browser (a window will open — do not close it)...")
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()

        # Warm up session by visiting the relevant section first
        print("Warming up browser session...")
        await page.goto(warmup_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        for year in years:
            print(f"\n--- Year {year} ---")
            counts = await download_year(page, year, errors, source=source)
            for k in total:
                total[k] += counts[k]
            print(f"  {year}: {counts}")

        await browser.close()

    if errors:
        error_path = RAW_DIR / f"download_errors_{source}.json"
        with open(error_path, "w", encoding="utf-8") as fh:
            json.dump(errors, fh, indent=2)
        print(f"\n{len(errors)} errors logged to {error_path}")

    print(f"\nTotal: {total}")


def main():
    parser = argparse.ArgumentParser(description="Download NH Supreme Court PDFs")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2025, 2026],
    )
    parser.add_argument(
        "--source",
        choices=["opinions", "orders"],
        default="opinions",
        help="Source to download: 'opinions' (default) or 'orders'",
    )
    args = parser.parse_args()
    asyncio.run(download_all_async(args.years, source=args.source))


if __name__ == "__main__":
    main()
