"""
Playwright UI validation for Granite State Appeals Streamlit app.
Tests all pages for load errors, missing content, JS exceptions,
mobile responsiveness, and accessibility.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page

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
    {"url": f"{BASE_URL}/about", "name": "06 About", "expect": []},
    {"url": f"{BASE_URL}/oral-arguments", "name": "08 Oral Arguments", "expect": ["Search transcripts", "Statistics", "47"]},
    {"url": f"{BASE_URL}/oral-arguments?argument=2025-0344", "name": "Oral Argument Reader", "expect": ["Machine-generated beta transcript", "Download text", "Download Markdown"]},
]

results = []


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
    body_text = ""
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


async def check_accessibility(page: Page, name: str) -> dict:
    """Check basic accessibility features on the page."""
    accessibility_issues = []
    
    # Check for semantic headings
    hccessibility_results = []
    responsive_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Test each viewport size
        for viewport_name, viewport_config in VIEWPORTS.items():
            print(f"\n{'='*60}")
            print(f"Testing {viewport_config['name']} ({viewport_config['width']}x{viewport_config['height']})")
            print(f"{'='*60}")
            
            context = await browser.new_context(
                viewport={"width": viewport_config["width"], "height": viewport_config["height"]}
            )
            page = await context.new_page()

            # Test main page first
            main_page = STREAMLIT_PAGES[0]
            await check_page(page, BASE_URL, "Main (cases.py)", main_page.get("expect", []))

            # Test each sub-page
            for pg in STREAMLIT_PAGES[1:]:
                await check_page(page, pg["url"], pg["name"], pg.get("expect", []))
            
            # Run accessibility checks (only once on desktop)
            if viewport_name == "desktop":
                print(f"\n{'='*60}")
                print("Running Accessibility Checks")
                print(f"{'='*60}")
                for pg in STREAMLIT_PAGES:
                    print(f"\n--- Checking accessibility: {pg['name']} ---")
                    await page.goto(pg["url"], wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)
                    a11y_result = await check_accessibility(page, pg["name"])
                    accessibility_results.append(a11y_result)
                    
                    if a11y_result["accessibility_issues"]:
                        print(f"  Issues found: {len(a11y_result['accessibility_issues'])}")
                        for issue in a11y_result["accessibility_issues"][:3]:
                            print(f"    - {issue}")
                    else:
                        print("  No accessibility issues detected")
            
            # Run responsive layout checks
            print(f"\n{'='*60}")
            print({
            "page_tests": results,
            "accessibility": accessibility_results,
            "responsive": responsive_results,
        }, f, indent=2, default=str)
    print("Results saved to data/raw/playwright_results.json")
    
    # Print accessibility summary
    if accessibility_results:
        print("\n" + "=" * 60)
        print("ACCESSIBILITY SUMMARY")
        print("=" * 60)
        total_issues = sum(len(r["accessibility_issues"]) for r in accessibility_results)
        if total_issues == 0:
            print("No accessibility issues detected!")
        else:
            print(f"Total accessibility issues: {total_issues}")
            for r in accessibility_results:
                if r["accessibility_issues"]:
                    print(f"\n{r['page']}:")
                    for issue in r["accessibility_issues"][:3]:
                        print(f"  - {issue}")
    
    # Print responsive summary
    if responsive_results:
        print("\n" + "=" * 60)
        print("RESPONSIVE LAYOUT SUMMARY")
        print("=" * 60)
        for viewport in VIEWPORTS.keys():
            viewport_results = [r for r in responsive_results if r["viewport"] == viewport]
            total_issues = sum(len(r["responsive_issues"]) for r in viewport_results)
            print(f"\n{viewport.upper()}: {total_issues} issues")
            for r in viewport_results:
                if r["responsive_issues"]:
                    print(f"  {r['page']}: {', '.join(r['responsive_issues'])}
            for pg in STREAMLIT_PAGES[:5]:  # Check first 5 pages
                print(f"\n--- Checking layout: {pg['name']} ---")
                await page.goto(pg["url"], wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                responsive_result = await check_responsive_layout(page, pg["name"], viewport_name)
                responsive_results.append(responsive_result)
                
                if responsive_result["responsive_issues"]:
                    print(f"  Issues: {', '.join(responsive_result['responsive_issues'])}")
                else:
                    print("  Layout looks good")
            
            await context.close(
    # Check for buttons/links with accessible names
    buttons = await page.query_selector_all("button, [role='button']")
    for btn in buttons[:10]:  # Sample first 10 buttons
        aria_label = await btn.get_attribute("aria-label")
        text = await btn.inner_text()
        title = await btn.get_attribute("title")
        if not aria_label and not text.strip() and not title:
            accessibility_issues.append("Button without accessible name found")
    
    # Check for sufficient color contrast (basic check via computed styles)
    # Note: This is a simplified check; full contrast analysis requires more sophisticated tools
    links = await page.query_selector_all("a")
    for link in links[:5]:  # Sample first 5 links
        color = await link.evaluate("el => window.getComputedStyle(el).color")
        bg_color = await link.evaluate("el => window.getComputedStyle(el).backgroundColor")
        # Just verify that colors are defined (full contrast calculation is complex)
        if not color or not bg_color:
            pass  # Skip this check for now
    
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # Test main page first
        main_page = STREAMLIT_PAGES[0]
        await check_page(page, BASE_URL, "Main (cases.py)", main_page.get("expect", []))

        # Test each sub-page
        for pg in STREAMLIT_PAGES[1:]:
            await check_page(page, pg["url"], pg["name"], pg.get("expect", []))

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
