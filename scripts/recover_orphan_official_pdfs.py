"""Recover court PDFs omitted from annual listings, with caption verification.

A docket-derived URL is only a retrieval candidate.  A result is retained only
when the first-page caption contains the requested docket; filename, title, and
date never establish a legal-case match.
"""
from __future__ import annotations

import argparse, asyncio, base64, csv, io, re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "processed" / "unmatched_argument_review_queue.csv"
OUTPUT = ROOT / "data" / "processed" / "orphan_official_pdf_recovery_candidates.csv"
BASE = "https://www.courts.nh.gov/sites/g/files/ehbemt471/files/documents/2021-08/{stem}.pdf"


def _kind(text: str) -> str:
    if re.search(r"Opinion\s+Issued", text, re.I):
        return "opinion"
    if re.search(r"issued the following order", text, re.I):
        return "3jx_order"
    return "unclassified"


def _issued(text: str) -> str:
    match = re.search(r"(?:Opinion Issued:|court on)\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    return match.group(1) if match else ""


async def main_async(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    from playwright.async_api import async_playwright
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.courts.nh.gov", wait_until="domcontentloaded")
        for row in rows:
            docket = row["case_number"]
            if not re.fullmatch(r"\d{4}-\d{4}", docket):
                results.append({**row, "candidate_url": "", "recovery_status": "nonstandard_docket", "document_type": "", "issued_date": ""})
                continue
            url = BASE.format(stem=docket.replace("-", ""))
            result = await page.evaluate("""async (url) => { const r=await fetch(url); if (!r.ok) return {ok:false,status:r.status}; const b=new Uint8Array(await r.arrayBuffer()); let s=''; for (const x of b) s+=String.fromCharCode(x); return {ok:true,data:btoa(s)}; }""", url)
            if not result.get("ok"):
                results.append({**row, "candidate_url": url, "recovery_status": f"not_found_http_{result.get('status')}", "document_type": "", "issued_date": ""})
                continue
            body = base64.b64decode(result["data"])
            if not body.startswith(b"%PDF"):
                results.append({**row, "candidate_url": url, "recovery_status": "not_a_pdf", "document_type": "", "issued_date": ""})
                continue
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                text = pdf.pages[0].extract_text() or ""
            if docket not in text:
                results.append({**row, "candidate_url": url, "recovery_status": "caption_docket_mismatch", "document_type": "", "issued_date": ""})
                continue
            results.append({**row, "candidate_url": url, "recovery_status": "caption_verified", "document_type": _kind(text), "issued_date": _issued(text)})
            print(f"Verified {docket}: {_kind(text)}")
        await browser.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with QUEUE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    results = asyncio.run(main_async(rows))
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]) if results else [])
        writer.writeheader(); writer.writerows(results)
    print(f"Wrote {len(results)} recovery checks to {OUTPUT}")


if __name__ == "__main__":
    main()
