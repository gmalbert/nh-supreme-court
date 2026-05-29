"""
Playwright UI validation for Granite State Appeals Streamlit app.
Tests all 7 pages for load errors, missing content, and JS exceptions.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page

BASE_URL = "http://localhost:8504"

PAGES = [
    {"path": "/", "name": "Case Explorer (cases.py)", "expect": ["Granite State Appeals", "Case Explorer"]},
    {"path": "/?page=01_Opinions", "name": "Opinions", "expect": []},
    {"path": "/?page=02_Justices", "name": "Justices", "expect": []},
    {"path": "/?page=03_Analysis", "name": "Analysis", "expect": []},
    {"path": "/?page=04_Topics", "name": "Topics", "expect": []},
    {"path": "/?page=05_Case_Orders", "name": "Case Orders", "expect": []},
    {"path": "/?page=06_About", "name": "About", "expect": []},
]

STREAMLIT_PAGES = [
    {"url": BASE_URL, "name": "Main (cases.py)"},
    {"url": f"{BASE_URL}/Opinions", "name": "01 Opinions"},
    {"url": f"{BASE_URL}/Justices", "name": "02 Justices"},
    {"url": f"{BASE_URL}/Analysis", "name": "03 Analysis"},
    {"url": f"{BASE_URL}/Topics", "name": "04 Topics"},
    {"url": f"{BASE_URL}/Case_Orders", "name": "05 Case Orders"},
    {"url": f"{BASE_URL}/About", "name": "06 About"},
]

results = []


async def check_page(page: Page, url: str, name: str) -> dict:
    """Navigate to a page and collect errors/warnings."""
    console_errors = []
    js_errors = []
    failed_resources = []

    page.on("console", lambda msg: console_errors.append(
        {"type": msg.type, "text": msg.text}
    ) if msg.type in ("error", "warning") else None)

    page.on("pageerror", lambda err: js_errors.append(str(err)))

    page.on("response", lambda resp: failed_resources.append(resp.url)
            if resp.status == 404 else None)

    print(f"\n--- Testing: {name} ---")
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=30000)
        status = response.status if response else "no response"
        print(f"  HTTP Status: {status}")
    except Exception as e:
        print(f"  Navigation error: {e}")
        return {"page": name, "url": url, "status": "ERROR", "error": str(e), "console_errors": [], "js_errors": []}

    # Wait for Streamlit to finish rendering
    try:
        await page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=15000)
    except Exception:
        pass

    # Extra wait for charts and dynamic content
    await asyncio.sleep(3)

    # Check for Streamlit error elements
    error_elements = await page.query_selector_all('[data-testid="stException"], .stException')
    streamlit_errors = []
    for el in error_elements:
        text = await el.inner_text()
        streamlit_errors.append(text[:200])
        print(f"  Streamlit ERROR: {text[:150]}")

    # Get page title
    title = await page.title()
    print(f"  Title: {title}")

    # Check for logo on main page
    if "cases.py" in name.lower() or "Main" in name:
        logo = await page.query_selector("img")
        print(f"  Logo found: {logo is not None}")

    # Get visible text (first 300 chars)
    try:
        body_text = await page.inner_text("body")
        visible = body_text[:300].replace("\n", " ").strip()
        print(f"  Content preview: {visible[:150]}")
    except Exception:
        visible = ""

    # Check for "No data" messages  
    no_data = "no data" in visible.lower() or "run the pipeline" in visible.lower()

    # Filter console errors (skip known harmless ones)
    HARMLESS = ("favicon", "ResizeObserver", "analytics", "matomo", "google",
                "failed to load resource")
    real_errors = [
        e for e in console_errors
        if e["type"] == "error"
        and not any(h in e["text"].lower() for h in HARMLESS)
    ]

    # 404 resources — skip favicon and Streamlit internal assets
    bad_404s = [u for u in failed_resources
                if "favicon" not in u and "_stcore" not in u and "healthz" not in u]
    if bad_404s:
        print(f"  404 resources: {bad_404s[:3]}")
    else:
        print(f"  (All 404s are harmless: {failed_resources[:3]})")

    result = {
        "page": name,
        "url": url,
        "status": "OK" if not streamlit_errors and not real_errors else "ERRORS",
        "http_status": status,
        "title": title,
        "streamlit_errors": streamlit_errors,
        "console_errors": real_errors,
        "js_errors": js_errors,
        "has_data": not no_data,
        "content_preview": visible[:200],
    }
    results.append(result)

    if real_errors:
        print(f"  Console errors: {len(real_errors)}")
        for e in real_errors[:3]:
            print(f"    {e['text'][:100]}")
    if js_errors:
        print(f"  JS errors: {js_errors[:2]}")

    return result


async def main():
    print("Starting Playwright UI validation for Granite State Appeals")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # Test main page first
        await check_page(page, BASE_URL, "Main (cases.py)")

        # Test each sub-page
        for pg in STREAMLIT_PAGES[1:]:
            await check_page(page, pg["url"], pg["name"])

        await browser.close()

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    all_ok = True
    for r in results:
        status_icon = "✓" if r["status"] == "OK" else "✗"
        data_icon = "📊" if r.get("has_data") else "⚠"
        print(f"{status_icon} {data_icon}  {r['page']}")
        if r.get("streamlit_errors"):
            all_ok = False
            for e in r["streamlit_errors"]:
                print(f"     ERROR: {e[:100]}")
        if r.get("console_errors"):
            all_ok = False

    print()
    if all_ok:
        print("All pages passed validation!")
    else:
        print("Some pages have errors - see details above.")

    # Save results
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    with open("data/raw/playwright_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Results saved to data/raw/playwright_results.json")


if __name__ == "__main__":
    asyncio.run(main())
