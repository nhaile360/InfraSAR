#!/usr/bin/env python3
"""Exercise the standalone site in a fresh Chromium browser context."""

import argparse
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("site", help="Path to the generated index.html or the public HTTPS URL")
    cli.add_argument("--revision", help="Expected Git SHA in the site's version.json")
    args = cli.parse_args()
    offline = not args.site.startswith("https://")
    url = Path(args.site).resolve().as_uri() if offline else args.site

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if offline:
            page.route("https://**/*", lambda route: route.abort())
        response = page.goto(url, wait_until="domcontentloaded")
        if response is None or not response.ok:
            raise RuntimeError(f"Unable to load the explorer at {url}")
        if args.revision:
            version = page.request.get(urljoin(page.url, "version.json"))
            assert version.ok and version.json()["commit"] == args.revision, "Unexpected deployed commit"

        page.wait_for_function("toolState.ready && toolState.patch?.cells.length === 108")
        expect(page.locator("#map")).to_be_visible()
        expect(page.locator("#before")).to_contain_text("Aug 2026")
        divider = page.get_by_role("slider", name="Drag to compare")
        divider.press("ArrowRight")
        expect(divider).to_have_attribute("aria-valuenow", "59")

        page.get_by_role("button", name="Change map").click()
        page.get_by_role("button", name="Agreement", exact=True).click()
        expect(page.locator("#legend")).to_contain_text("Radar change")
        page.get_by_role("button", name="Compare points").click()
        expect(page.get_by_role("heading", name="Compare two spots")).to_be_visible()
        expect(page.locator("#points")).to_contain_text("Point A")
        page.get_by_role("button", name="Timeline").click()
        expect(page.get_by_role("heading", name="Follow the observations")).to_be_visible()
        page.locator("#scrubber").press("ArrowRight")
        expect(page.locator("#time-status")).not_to_be_empty()
        page.get_by_role("button", name="Swipe dates").click()

        expect(page.locator("#pilot-score")).to_contain_text("7.68%")
        expect(page.locator("#pilot-score")).to_contain_text("0.82%")
        page.get_by_role("link", name="Investigate historical rainfall").click()
        expect(page.locator("#trend-chart")).to_be_visible()
        expect(page.locator("#trend-slope")).to_have_text("+1.52 mm/year")
        expect(page.locator("#trend-significance")).to_have_text("Inconclusive")
        page.get_by_role("button", name="Monthly estimates").click()
        page.get_by_text("Read the plotted values", exact=True).click()
        expect(page.locator("#trend-table-body tr")).to_have_count(528)
        page.locator("#trend-period").select_option("2")
        expect(page.locator("#trend-table-body tr")).to_have_count(264)
        expect(page.locator("#trend-slope")).to_have_text("+48.17 mm/year")
        assert not errors, errors
        browser.close()
    print("Browser smoke test passed for " + url)


if __name__ == "__main__":
    main()
