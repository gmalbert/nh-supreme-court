"""
scripts/scrape_index.py
-----------------------
Build the NH Supreme Court opinion index by scraping the per-year opinions
pages using a headed Playwright browser (required to pass Akamai CDN bot
detection).

Strategy
--------
1. Launch headed Chromium via Playwright.
2. For each requested year, navigate to:
       https://www.courts.nh.gov/our-courts/supreme-court/
           orders-and-opinions/opinions/{year}
3. Click through all Tabulator.js pagination pages to collect every opinion
   PDF link and its case name.
4. Emit one index record per opinion.

Outputs: data/raw/index_{year}.json

Usage:
    python scripts/scrape_index.py --years 2022 2023 2024 2025 2026
    python scripts/scrape_index.py              # defaults to current + last 3 years

Note: A visible Chromium browser window will open during scraping.
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

BASE_OPINIONS_URL = (
    "https://www.courts.nh.gov/our-courts/supreme-court/"
    "orders-and-opinions/opinions"
)

# Extract citation number from case name for 2024+ format:
# "2024 N.H. 71, Some Case Name" → citation="2024 N.H. 71"
# For 2023 and earlier: "2022-0523, Case Name" → case_number="2022-0523"
CITATION_RE = re.compile(r"^(\d{4}\s+N\.H\.\s+\d+),\s*(.+)$")
CASE_NUMBER_RE = re.compile(r"^(\d{4}-\d+),\s*(.+)$")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_case_name(raw_text: str, year: int) -> dict:
    """Parse the link text into structured fields."""
    raw_text = raw_text.strip()

    m = CITATION_RE.match(raw_text)
    if m:
        return {
            "citation": m.group(1),
            "case_name": m.group(2).strip(),
            "case_number": None,
        }

    m = CASE_NUMBER_RE.match(raw_text)
    if m:
        return {
            "citation": None,
            "case_name": m.group(2).strip(),
            "case_number": m.group(1),
        }

    return {"citation": None, "case_name": raw_text, "case_number": None}


async def scrape_year(page, year: int) -> list[dict]:
    """
    Navigate to the opinions page for a year, click through all Tabulator
    pagination pages, and return a list of opinion index records.
    """
    url = f"{BASE_OPINIONS_URL}/{year}"
    print(f"  Loading {url}")

    await page.goto(url, wait_until="networkidle", timeout=30000)
    # Wait for Tabulator to finish rendering (older year pages can be slower)
    await page.wait_for_timeout(6000)

    opinions = []
    page_num = 1

    while True:
        # Collect opinion PDFs from current Tabulator page
        links = await page.eval_on_selector_all(
            "a[href]",
            """els => els
                .filter(e =>
                    e.href.includes('/files/documents/') &&
                    e.href.endsWith('.pdf') &&
                    !e.href.includes('transcript-instructions') &&
                    !e.href.includes('neutral-citation')
                )
                .map(e => ({url: e.href, text: e.innerText.trim()}))""",
        )

        new_opinions = [
            l for l in links
            if l["text"]
            and not l["text"].startswith("http")
            and "Transcript" not in l["text"]
            and "transcript" not in l["text"].lower()
        ]

        print(f"    Page {page_num}: {len(new_opinions)} opinions")
        opinions.extend(new_opinions)

        # Try to advance to the next Tabulator page
        next_btn = await page.query_selector('[data-page="next"]:not([disabled])')
        if not next_btn:
            break

        page_num += 1
        await next_btn.evaluate("el => el.click()")
        await page.wait_for_timeout(1500)

        if page_num > 30:  # safety limit
            print("  WARNING: hit page limit (30), stopping")
            break

    # Deduplicate by URL and build structured records
    seen_urls: set[str] = set()
    records: list[dict] = []

    for link in opinions:
        pdf_url = link["url"]
        if pdf_url in seen_urls:
            continue
        seen_urls.add(pdf_url)

        parsed = parse_case_name(link["text"], year)
        records.append(
            {
                "year": year,
                "pdf_url": pdf_url,
                "case_name": parsed["case_name"],
                "case_number": parsed["case_number"],
                "citation": parsed["citation"],
                "opinion_type": "opinion",
                # date_issued is extracted by parse_opinions.py from the PDF
                "date_issued": None,
            }
        )

    return records


async def scrape_years_async(years: list[int]) -> dict[int, list[dict]]:
    """Scrape all requested years using a single browser session."""
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
            print(f"\nScraping {year}...")
            try:
                records = await scrape_year(page, year)
                results[year] = records
                print(f"  → {len(records)} opinions found for {year}")
            except Exception as exc:
                print(f"  ERROR scraping {year}: {exc}")
                results[year] = []

        await browser.close()

    return results


def main():
    current_year = datetime.now().year
    default_years = list(range(current_year - 3, current_year + 1))

    parser = argparse.ArgumentParser(
        description="Build NH Supreme Court opinion index via Playwright scraping"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=default_years,
        help=f"Years to index (default: {default_years})",
    )
    args = parser.parse_args()

    results = asyncio.run(scrape_years_async(args.years))

    total = 0
    for year in sorted(args.years):
        records = results.get(year, [])
        out_path = RAW_DIR / f"index_{year}.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
        print(f"  {year}: {len(records)} opinions → {out_path}")
        total += len(records)

    out_all = RAW_DIR / "index_all.json"
    all_records = [r for year_records in results.values() for r in year_records]
    with open(out_all, "w", encoding="utf-8") as fh:
        json.dump(all_records, fh, indent=2, ensure_ascii=False)

    print(f"\nTotal: {total} opinion index records across {len(args.years)} years")
    print(f"Combined index: {out_all}")


if __name__ == "__main__":
    main()
