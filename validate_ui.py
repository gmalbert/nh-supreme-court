"""
Playwright UI validation for Granite State Appeals Streamlit app.
Tests all pages for load errors, missing content, JS exceptions,
mobile responsiveness, and accessibility.
"""
import asyncio
import json
import os
import shutil
from pathlib import Path
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright

BASE_URL = "http://localhost:8504"

# Viewport configurations for responsive testing
VIEWPORTS = {
    "mobile": {"width": 375, "height": 667, "name": "Mobile (iPhone SE)"},
    "tablet": {"width": 768, "height": 1024, "name": "Tablet (iPad)"},
    "desktop": {"width": 1920, "height": 1080, "name": "Desktop (1080p)"},
}

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
    {"url": BASE_URL, "name": "Main (cases.py)", "expect": ["Granite State Appeals", "Oral Arguments"]},
    {"url": f"{BASE_URL}/opinions", "name": "01 Opinions", "expect": ["Opinions Browser"]},
    {"url": f"{BASE_URL}/justices", "name": "02 Justices", "expect": []},
    {"url": f"{BASE_URL}/analysis", "name": "03 Analysis", "expect": ["oral-argument statistics"]},
    {"url": f"{BASE_URL}/topics", "name": "04 Topics", "expect": []},
    {"url": f"{BASE_URL}/case-orders", "name": "05 Case Orders", "expect": []},
    {"url": f"{BASE_URL}/trial-courts", "name": "07 Trial Courts", "expect": []},
    {
        "url": f"{BASE_URL}/legal-intelligence",
        "name": "13 Legal Intelligence",
        "expect": [
            "Legal Intelligence Lab",
            "Research & Authority",
            "Open Data & Quality",
        ],
    },
    {"url": f"{BASE_URL}/about", "name": "06 About", "expect": []},
    {
        "url": f"{BASE_URL}/oral-arguments",
        "name": "08 Oral Arguments",
        "expect": ["Search and read machine-generated transcripts", "Statistics", "Transcripts"],
    },
    {"url": f"{BASE_URL}/oral-arguments?argument=2025-0344", "name": "Oral Argument Reader", "expect": ["Machine-generated beta transcript", "Download text", "Download Markdown"]},
]

results = []


def _printable(value: str) -> str:
    """Keep Windows CI consoles from choking on page emoji or smart punctuation."""
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _installed_browser_candidates() -> list[str]:
    """Return explicit local browser paths for developer machines.

    CI installs Playwright's pinned Chromium.  A source checkout can still run
    the same validator with an already-installed Chrome or Edge when that
    optional browser download has not happened yet.
    """
    configured = os.environ.get("PLAYWRIGHT_EXECUTABLE_PATH", "").strip()
    candidates = [configured] if configured else []
    for command in ("chrome", "google-chrome", "chromium", "msedge"):
        discovered = shutil.which(command)
        if discovered:
            candidates.append(discovered)
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ]
        )
    return list(dict.fromkeys(path for path in candidates if path and Path(path).is_file()))


async def launch_validation_browser(playwright):
    """Launch pinned Chromium, with a deterministic system-browser fallback."""
    try:
        return await playwright.chromium.launch(headless=True)
    except PlaywrightError as original_error:
        for executable in _installed_browser_candidates():
            try:
                print(f"Bundled Chromium unavailable; using {executable}")
                return await playwright.chromium.launch(
                    headless=True, executable_path=executable
                )
            except PlaywrightError:
                continue
        raise original_error
async def check_page(page: Page, url: str, name: str, expected: list[str] | None = None) -> dict:
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
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        status = response.status if response else "no response"
        print(f"  HTTP Status: {status}")
    except Exception as e:
        print(f"  Navigation error: {e}")
        result = {
            "page": name,
            "url": url,
            "status": "ERROR",
            "error": str(e),
            "streamlit_errors": [],
            "console_errors": [],
            "js_errors": [],
            "missing_expected": list(expected or []),
            "has_data": False,
        }
        results.append(result)
        return result

    # Wait for Streamlit to finish rendering
    try:
        await page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=15000)
    except Exception:
        pass

    # Extra wait for charts and dynamic content
    try:
        await page.wait_for_function(
            "document.body && document.body.innerText.length > 100",
            timeout=30000,
        )
        for expected_text in expected or []:
            await page.get_by_text(expected_text, exact=False).first.wait_for(
                state="visible", timeout=30000
            )
    except Exception:
        # Missing content is reported below with the full set of diagnostics.
        pass
    await asyncio.sleep(1)

    # Check for Streamlit error elements
    error_elements = await page.query_selector_all('[data-testid="stException"], .stException')
    streamlit_errors = []
    for el in error_elements:
        text = await el.inner_text()
        streamlit_errors.append(text[:200])
        print(f"  Streamlit ERROR: {_printable(text[:150])}")

    # Get page title
    title = await page.title()
    print(f"  Title: {title}")

    # Check for logo on main page
    if "cases.py" in name.lower() or "Main" in name:
        logo = await page.query_selector("img")
        print(f"  Logo found: {logo is not None}")

    # Get visible text (first 300 chars)
    body_text = ""
    try:
        body_text = await page.inner_text("body")
        visible = body_text[:300].replace("\n", " ").strip()
        print(f"  Content preview: {_printable(visible[:150])}")
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

    missing_expected = [text for text in (expected or []) if text.lower() not in body_text.lower()]
    result = {
        "page": name,
        "url": url,
        "status": "OK" if not streamlit_errors and not real_errors and not js_errors and not missing_expected else "ERRORS",
        "http_status": status,
        "title": title,
        "streamlit_errors": streamlit_errors,
        "console_errors": real_errors,
        "js_errors": js_errors,
        "missing_expected": missing_expected,
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


async def check_legal_intelligence_interactions(page: Page) -> list[str]:
    """Exercise every top-level Legal Intelligence section with Playwright."""
    errors: list[str] = []
    steps = [
        ("Issue Lifecycles", "Doctrinal issue lifecycle"),
        ("Predictive Analytics", "Explainable case outcome estimate"),
        ("Dockets & Media", "Keyword or exact phrase"),
        ("Research Workspace", "Local auditable research workspace"),
        ("Open Data & Quality", "Open-access historical dataset"),
        ("Research & Authority", "Semantic case search"),
    ]
    for section, expected_text in steps:
        try:
            await page.get_by_role("radio", name=section).click()
            await page.get_by_text(expected_text, exact=False).first.wait_for(
                state="visible", timeout=30000
            )
        except Exception as error:
            errors.append(f"{section}: {error}")

    try:
        await page.get_by_role("radio", name="Predictive Analytics").click()
        await page.get_by_role("button", name="Estimate outcome").click()
        await page.get_by_text("Estimated P(affirmed)", exact=False).first.wait_for(
            state="visible", timeout=30000
        )
    except Exception as error:
        errors.append(f"Outcome predictor interaction: {error}")

    try:
        await page.get_by_role("radio", name="Dockets & Media").click()
        await page.get_by_role("tab", name="PDF & readability").click()
        await page.get_by_text("Flesch ease", exact=False).first.wait_for(
            state="visible", timeout=30000
        )
    except Exception as error:
        errors.append(f"PDF/readability interaction: {error}")

    try:
        await page.get_by_role("radio", name="Open Data & Quality").click()
        await page.get_by_role("tab", name="Quality review").click()
        await page.get_by_text(
            "Impact-ranked extraction review", exact=False
        ).first.wait_for(state="visible", timeout=30000)
    except Exception as error:
        errors.append(f"Quality review interaction: {error}")

    streamlit_errors = await page.query_selector_all(
        '[data-testid="stException"], .stException'
    )
    for element in streamlit_errors:
        errors.append("Streamlit exception: " + (await element.inner_text())[:200])
    return errors


async def check_accessibility(page: Page, name: str) -> dict:
    """Check basic accessibility features on the page."""
    accessibility_issues = []

    headings = await page.query_selector_all("h1, h2, h3, h4, h5, h6")
    if not headings:
        accessibility_issues.append("No semantic headings found")

    images = await page.query_selector_all("img")
    for image in images:
        if await image.get_attribute("alt") is None:
            accessibility_issues.append("Image without alt text found")

    # Check for buttons/links with accessible names
    buttons = await page.query_selector_all("button, [role='button']")
    for btn in buttons[:10]:  # Sample first 10 buttons
        aria_label = await btn.get_attribute("aria-label")
        text = await btn.inner_text()
        title = await btn.get_attribute("title")
        if not aria_label and not text.strip() and not title:
            accessibility_issues.append("Button without accessible name found")
    
    # Check for keyboard focus indicators
    # This requires actually tabbing through the page, so we'll do a basic check
    focusable = await page.query_selector_all("a, button, input, select, textarea, [tabindex]")
    if len(focusable) == 0:
        accessibility_issues.append("No focusable elements found")
    
    return {
        "page": name,
        "accessibility_issues": accessibility_issues,
        "heading_count": len(headings),
        "image_count": len(images),
        "button_count": len(buttons),
        "focusable_count": len(focusable),
    }


async def check_responsive_layout(page: Page, name: str, viewport: str) -> dict:
    """Check for responsive layout issues at different viewport sizes."""
    issues = []
    
    # Check for horizontal scrollbars (excluding data tables which may scroll)
    scroll_width = await page.evaluate("() => document.documentElement.scrollWidth")
    client_width = await page.evaluate("() => document.documentElement.clientWidth")
    
    if scroll_width > client_width + 20:  # Allow 20px tolerance
        # Check if it's just data tables
        tables = await page.query_selector_all("table, [data-testid='stDataFrame']")
        if len(tables) == 0:
            issues.append(f"Horizontal scroll detected ({scroll_width}px > {client_width}px)")
    
    # Check for elements that extend beyond viewport
    wide_elements = await page.evaluate("""() => {
        const elements = Array.from(document.querySelectorAll('*'));
        return elements.filter(el => {
            const rect = el.getBoundingClientRect();
            return rect.width > window.innerWidth && !el.matches('table, [data-testid="stDataFrame"]');
        }).length;
    }""")
    
    if wide_elements > 0:
        issues.append(f"{wide_elements} elements extend beyond viewport")
    
    # Check minimum tap target size (mobile only)
    if viewport == "mobile":
        small_targets = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            return buttons.filter(el => {
                const rect = el.getBoundingClientRect();
                return (rect.width > 0 && rect.width < 44) || (rect.height > 0 && rect.height < 44);
            }).length;
        }""")
        
        if small_targets > 5:  # Allow a few small elements
            issues.append(f"{small_targets} tap targets smaller than 44px")
    
    return {
        "page": name,
        "viewport": viewport,
        "responsive_issues": issues,
        "scroll_width": scroll_width,
        "client_width": client_width,
    }


async def main():
    print("Starting Playwright UI validation for Granite State Appeals")
    print(f"Target: {BASE_URL}")
    print("=" * 60)
    async with async_playwright() as p:
        browser = await launch_validation_browser(p)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        for pg in STREAMLIT_PAGES:
            page = await context.new_page()
            result = await check_page(
                page, pg["url"], pg["name"], pg.get("expect", [])
            )
            if pg["name"] == "13 Legal Intelligence" and result["status"] == "OK":
                interaction_errors = await check_legal_intelligence_interactions(page)
                result["interaction_errors"] = interaction_errors
                if interaction_errors:
                    result["status"] = "ERRORS"
            await page.close()

        await browser.close()

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    all_ok = True
    for r in results:
        status_label = "PASS" if r["status"] == "OK" else "FAIL"
        data_label = "DATA" if r.get("has_data") else "NO DATA"
        print(f"[{status_label}] [{data_label}] {r['page']}")
        if r["status"] != "OK":
            all_ok = False
        if r.get("error"):
            print(f"     NAVIGATION ERROR: {r['error'][:100]}")
        if r.get("streamlit_errors"):
            all_ok = False
            for e in r["streamlit_errors"]:
                print(f"     ERROR: {e[:100]}")
        if r.get("console_errors"):
            all_ok = False
        if r.get("js_errors"):
            all_ok = False
            print(f"     JS ERROR: {r['js_errors'][0][:100]}")
        if r.get("missing_expected"):
            all_ok = False
            print(f"     MISSING: {', '.join(r['missing_expected'])}")
        if r.get("interaction_errors"):
            all_ok = False
            for error in r["interaction_errors"]:
                print(f"     INTERACTION ERROR: {_printable(error[:150])}")

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
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
