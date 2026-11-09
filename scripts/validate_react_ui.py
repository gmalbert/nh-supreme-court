"""Smoke-test the React routes and FastAPI endpoints through the frontend proxy."""

import asyncio
import os

from playwright.async_api import async_playwright


BASE_URL = os.environ.get("NHSC_UI_BASE_URL", "http://127.0.0.1:4173").rstrip("/")
API_ENDPOINTS = (
    "/api/health",
    "/api/site-status",
    "/api/dashboard",
    "/api/opinions/filters",
)
APP_ROUTES = (
    "/",
    "/opinions",
    "/about",
    "/oral-arguments",
    "/topics",
    "/case-orders",
    "/justices",
    "/analysis",
    "/legal-intelligence",
    "/case-explorer",
    "/trial-courts",
)


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        for endpoint in API_ENDPOINTS:
            response = await page.request.get(f"{BASE_URL}{endpoint}")
            assert response.ok, f"{endpoint} returned HTTP {response.status}"

        for route in APP_ROUTES:
            response = await page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
            assert response and response.ok, f"{route} did not load successfully"
            await page.locator("#root > *").wait_for(timeout=10000)
            text = await page.locator("#root").inner_text()
            assert text.strip(), f"{route} rendered an empty React root"

        await browser.close()
        assert not page_errors, "React page errors: " + "; ".join(page_errors)
        print(f"React routes and FastAPI endpoints passed at {BASE_URL}")


if __name__ == "__main__":
    asyncio.run(main())
