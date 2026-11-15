#!/usr/bin/env python3
"""Exercise the standalone site in fresh desktop and touch Chromium contexts."""

import argparse
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright


def open_site(page, url, offline):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if offline:
        page.route("https://**/*", lambda route: route.abort())
    response = page.goto(url, wait_until="domcontentloaded")
    if response is None or not response.ok:
        raise RuntimeError(f"Unable to load the explorer at {url}")
    page.wait_for_function("toolState.ready && toolState.patch?.cells.length === 108")
    return errors


def after_draw(page):
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def check_reservoir_extent(page):
    assert page.evaluate("""() => {
        const t = transform(toolState.cam, map.clientWidth, map.clientHeight);
        return reservoir.id === 1543 && reservoir.rings.every(ring => ring.every(([x,y]) => {
            const [sx,sy] = t.xy({x,y});
            return sx > 0 && sy > 0 && sx < t.width && sy < t.height;
        }));
    }"""), "The reservoir does not fit in the overview"


def check_basemap(chromium, url):
    # A local fixture exercises the viewport requests without relying on the provider.
    pixel = bytes.fromhex("47494638396101000100800000ffffffffffff21f90401000001002c00000000010001000002024401003b")
    export = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/export?*"

    def bounds(request):
        query = parse_qs(urlsplit(request.url).query)
        assert query["bboxSR"] == query["imageSR"] == ["32636"]
        west, south, east, north = map(float, query["bbox"][0].split(","))
        width, height = map(int, query["size"][0].split(","))
        assert abs((east - west) / (north - south) - width / height) < 1e-7
        return west, east

    with chromium.new_context(viewport={"width": 1280, "height": 900}) as browser:
        page = browser.new_page()
        page.route("https://**/*", lambda route: route.abort())
        page.route(export, lambda route: route.fulfill(
            content_type="image/gif", body=pixel, headers={"access-control-allow-origin": "*"}))
        errors = open_site(page, url, offline=False)
        page.wait_for_function("viewportBasemap?.image.naturalWidth > 0")
        inlet_width = page.evaluate("viewportBasemap.bounds.east - viewportBasemap.bounds.west")

        with page.expect_request(export) as zoomed:
            page.get_by_role("button", name="Zoom in").click()
        west, east = bounds(zoomed.value)
        assert east - west < inlet_width * .8, "Zooming must request a closer view"

        with page.expect_request(export) as overview:
            page.get_by_role("button", name="Show reservoir").click()
        west, east = bounds(overview.value)
        page.wait_for_function("west => viewportBasemap?.bounds.west === west", arg=west)
        assert east - west > 40000, "The request must cover areas outside the former detail image"

        with page.expect_request(export) as panned:
            for _ in range(3):
                page.locator("#map").press("ArrowRight")
        panned_west, _ = bounds(panned.value)
        assert panned_west > west, "Panning must load basemap imagery for the new area"
        page.wait_for_function("""() => covers(
            viewportBasemap.bounds, visibleBounds(transform(toolState.cam, map.clientWidth, map.clientHeight))
        )""")
        assert not errors, errors


def check_swipe(page, offline):
    expect(page.locator("#before")).to_contain_text("Left · NISAR HH · 29 Aug 2026")
    expect(page.locator("#after")).to_contain_text("Right · NISAR HH · 16 Oct 2026")
    divider = page.get_by_role("slider", name="Drag to compare")
    divider.press("ArrowRight")
    expect(divider).to_have_attribute("aria-valuenow", "59")

    if offline:
        page.locator("#radar-rendering").select_option("raw")

    for key, value in [("End", "100"), ("Home", "0")]:
        divider.press(key)
        expect(divider).to_have_attribute("aria-valuenow", value)
        after_draw(page)
        if offline:
            assert page.evaluate("""(value) => {
                const t = transform(toolState.cam, map.clientWidth, map.clientHeight);
                const i = indexAt(t.location(t.width*.38,t.height*.38));
                const [x,y] = t.xy(pointFrom(i));
                const date = value === "100" ? 0 : 1;
                const image = rasterImage(pilotRadar()[date].raw, "radar");
                const rgba = image.getContext("2d").getImageData(i%grid.width,Math.floor(i/grid.width),1,1).data;
                const actual = context.getImageData(Math.floor(x*map.width/t.width),Math.floor(y*map.height/t.height),1,1).data;
                return rgba.every((channel,index)=>channel===actual[index]);
            }""", value), "The visible radar pixels do not match the fully revealed date"

    divider.scroll_into_view_if_needed()
    handle = divider.bounding_box()
    map_box = page.locator("#map").bounding_box()
    page.mouse.move(handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2)
    page.mouse.down()
    page.mouse.move(map_box["x"] + map_box["width"] + 2, handle["y"] + handle["height"] / 2, steps=8)
    page.mouse.up()
    expect(divider).to_have_attribute("aria-valuenow", "100")
    expect(page.locator("#zoom-in")).to_be_visible()
    page.locator("#zoom-in").click()
    page.locator("#map").press("ArrowRight")
    after_draw(page)
    assert page.evaluate("""() => {
        const patch = toolState.patch;
        const t = transform(toolState.cam,map.clientWidth,map.clientHeight);
        const i = patch.cells[patch.cells.length >> 1];
        return indexAt(t.location(...t.xy(pointFrom(i)))) === i;
    }""")

    page.get_by_role("button", name="Water map", exact=True).click()
    expect(page.locator("#before")).to_contain_text("26 Aug 2026")
    expect(page.locator("#after")).to_contain_text("15 Oct 2026")
    page.get_by_role("button", name="Radar vs optical change").click()
    expect(page.locator("#before")).to_contain_text("NISAR candidates")
    expect(page.locator("#after")).to_contain_text("Sentinel‑2 change")
    expect(page.locator("#legend")).to_contain_text("threshold-based")
    expect(page.get_by_role("button", name="Rule: local")).to_be_visible()
    page.get_by_role("button", name="Rule: local").click()
    expect(page.get_by_role("button", name="Rule: fixed")).to_be_visible()

    page.get_by_role("button", name="Show reservoir").click()
    check_reservoir_extent(page)
    page.get_by_role("button", name="Hide study layers").click()
    expect(divider).to_be_hidden()
    expect(page.locator("#legend")).to_contain_text("Historical shoreline · HydroLAKES")
    page.get_by_role("button", name="Show study layers").click()
    expect(divider).to_be_visible()
    page.get_by_role("button", name="Show inlet").click()
    if offline:
        assert page.evaluate("""() => {
            const data = new Float32Array(size);
            data[0] = NaN;
            const radar = rasterImage(data,"radar");
            const classes = new Uint8Array(size);
            classes.set([5,9,6]);
            const optical = rasterImage(classes,"water");
            const alpha = (image,x) => image.getContext("2d").getImageData(x,0,1,1).data[3];
            return !!radar.observed && alpha(radar,0) === 0 && alpha(radar,1) === 255 &&
                alpha(optical,0) === 0 && alpha(optical,1) === 0 && alpha(optical,2) === 255;
        }"""), "No-data cells must be transparent and observed cloud must remain visible"


def check_other_views(page):
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


def check_touch(chromium, url, offline):
    with chromium.new_context(viewport={"width": 390, "height": 844},
                              device_scale_factor=2, has_touch=True, is_mobile=True) as mobile:
        page = mobile.new_page()
        errors = open_site(page, url, offline)
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), "Horizontal overflow on mobile"
        canvas = page.locator("#map")
        canvas.scroll_into_view_if_needed()
        divider = page.get_by_role("slider", name="Drag to compare")
        cdp = mobile.new_cdp_session(page)

        def touch(kind, *positions):
            points = [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(positions)]
            cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

        box, handle = canvas.bounding_box(), divider.bounding_box()
        x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
        touch("touchStart", (x, y))
        touch("touchMove", (box["x"] + 70, y))
        touch("touchMove", (box["x"] - 2, y))
        touch("touchEnd")
        expect(divider).to_have_attribute("aria-valuenow", "0")

        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        original = page.evaluate("({x:toolState.cam.x,span:toolState.cam.span})")
        touch("touchStart", (x, y))
        touch("touchMove", (x+55, y))
        touch("touchEnd")
        assert page.evaluate("toolState.cam.x") < original["x"], "Touch pan did not move the camera"
        touch("touchStart", (x-35, y), (x+35, y))
        touch("touchMove", (x-80, y), (x+80, y))
        touch("touchEnd")
        assert page.evaluate("toolState.cam.span") < original["span"] * .8, "Pinch did not zoom"

        page.get_by_role("button", name="Show reservoir").tap()
        check_reservoir_extent(page)
        page.get_by_role("button", name="Water map", exact=True).tap()
        expect(page.locator("#after")).to_contain_text("Sentinel‑2")
        assert not errors, errors


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
        errors = open_site(page, url, offline)
        if args.revision:
            version = page.request.get(urljoin(page.url, "version.json"))
            assert version.ok and version.json()["commit"] == args.revision, "Unexpected deployed commit"

        check_swipe(page, offline)
        check_other_views(page)
        assert not errors, errors
        check_touch(browser, url, offline)
        if offline:
            check_basemap(browser, url)
        browser.close()
    print("Desktop, keyboard, mouse and mobile touch smoke tests passed for " + url)


if __name__ == "__main__":
    main()
