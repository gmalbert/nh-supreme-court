"""
scripts/scrape_orders_index.py
-------------------------------
Build the NH Supreme Court case-orders index by scraping per-year pages
using a headed Playwright browser (required to pass Akamai CDN bot detection).

URL pattern:
    https://www.courts.nh.gov/our-courts/supreme-court/
        orders-and-opinions/case-orders/{year}

The page uses the same Tabulator.js pagination as the opinions pages.
Each entry has format: "CASE-NUMBER, Case Name" with a PDF link and a date.

Outputs: data/raw/orders_index_{year}.json

Usage:
    python scripts/scrape_orders_index.py --years 2024 2025 2026
    python scripts/scrape_orders_index.py --years 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_ORDERS_URL = (
    "https://www.courts.nh.gov/our-courts/supreme-court/"
    "orders-and-opinions/case-orders"
)

# Case number format: "2024-0358, Case Name"
CASE_NUMBER_RE = re.compile(r"^(\d{4}-\d+),\s*(.+)$")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_order_text(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    m = CASE_NUMBER_RE.match(raw_text)
    if m:
        return {"case_number": m.group(1), "case_name": m.group(2).strip()}
    return {"case_number": None, "case_name": raw_text}


async def scrape_year(page, year: int) -> list[dict]:
    """Navigate to case orders page for a year and collect all records."""
    url = f"{BASE_ORDERS_URL}/{year}"
    print(f"  Loading {url}")

    await page.goto(url, wait_until="networkidle", timeout=30000)
    # Wait for Tabulator to finish rendering (older year pages can be slower)
    await page.wait_for_timeout(6000)

    orders = []
    page_num = 1

    while True:
        # Collect order PDFs — same filter as opinions
        links = await page.eval_on_selector_all(
            "a[href]",
            """els => els
                .filter(e =>
                    e.href.includes('/files/documents/') &&
                    e.href.endsWith('.pdf')
                )
                .map(e => ({url: e.href, text: e.innerText.trim()}))""",
        )

        new_orders = [
            l for l in links
            if l["text"] and not l["text"].startswith("http")
        ]

        print(f"    Page {page_num}: {len(new_orders)} orders")
        orders.extend(new_orders)

        # Advance Tabulator pagination
        next_btn = await page.query_selector('[data-page="next"]:not([disabled])')
        if not next_btn:
            break
        page_num += 1
        await next_btn.evaluate("el => el.click()")
        await page.wait_for_timeout(1500)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_orders = []
    for o in orders:
        if o["url"] not in seen_urls:
            seen_urls.add(o["url"])
            unique_orders.append(o)

    # Build records
    records = []
    for o in unique_orders:
        parsed = parse_order_text(o["text"])
        records.append({
            "year": year,
            "pdf_url": o["url"],
            "case_name": parsed["case_name"],
            "case_number": parsed["case_number"],
            "citation": None,
            "opinion_type": "case_order",
            "date_issued": None,
            "pdf_local_path": None,
        })

    return records


async def scrape_years_async(years: list[int]) -> dict[int, list[dict]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright")
        sys.exit(1)

    results: dict[int, list[dict]] = {}

    async with async_playwright() as pw:
        print("Launching browser (a window will open — do not close it)...")
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()

        for year in sorted(years):
            print(f"\nScraping orders {year}...")
            try:
                records = await scrape_year(page, year)
                results[year] = records
                print(f"  → {len(records)} orders found for {year}")
            except Exception as exc:
                print(f"  ERROR scraping {year}: {exc}")
                results[year] = []

        await browser.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Build NH Supreme Court case-orders index via Playwright scraping"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(range(2014, datetime.now().year + 1)),
        help="Years to index (default: 2014 to current year)",
    )
    args = parser.parse_args()

    results = asyncio.run(scrape_years_async(args.years))

    total = 0
    for year in sorted(args.years):
        records = results.get(year, [])
        out_path = RAW_DIR / f"orders_index_{year}.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
        print(f"  {year}: {len(records)} orders → {out_path}")
        total += len(records)

    print(f"\nTotal: {total} case order records across {len(args.years)} years")


if __name__ == "__main__":
    main()
