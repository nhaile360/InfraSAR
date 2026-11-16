#!/usr/bin/env python3
"""Exercise the standalone site in fresh desktop and touch Chromium contexts."""

import argparse
from hashlib import sha256
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

        page.get_by_role("button", name="Show reservoir").click()
        with page.expect_request(export) as overview:
            page.get_by_role("button", name="Zoom in").click()
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
    expect(page.locator("#before")).to_contain_text("26 Aug 2026")
    radar = page.get_by_role("button", name="Radar image", exact=True)
    radar.press("Enter")
    expect(radar).to_be_focused()
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

    page.get_by_role("button", name="Optical water map", exact=True).click()
    expect(page.locator("#before")).to_contain_text("26 Aug 2026")
    expect(page.locator("#after")).to_contain_text("15 Oct 2026")
    page.get_by_role("button", name="Map changes").click()
    page.get_by_role("button", name="Compare change maps").click()
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


def check_points(page):
    page.get_by_role("button", name="Compare the inlet with nearby dry land").click()
    expect(page.get_by_role("heading", name="Location readings")).to_be_visible()
    a, b = (page.locator(f'[data-point-card="{key}"]') for key in ("A", "B"))
    expect(a).to_contain_text("Land → Water")
    expect(b).to_contain_text("Land → Land")
    expect(a).to_contain_text("NISAR HH")
    expect(b).to_contain_text("Radar change")
    a_index = page.evaluate("toolState.points.A")
    b_index = page.evaluate("toolState.points.B")
    move = page.get_by_role("button", name="Move Point B", exact=True)
    move.press("Enter")
    expect(move).to_have_attribute("aria-pressed", "true")
    expect(b).to_have_attribute("data-active", "true")
    pin = page.get_by_role("button", name="Point B marker")
    expect(pin).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("button", name="Point A marker")).to_be_visible()

    canvas = page.locator("#map")
    box = canvas.bounding_box()
    canvas.click(position={"x": box["width"] * .35, "y": box["height"] * .58})
    expect(page.locator("#point-status")).to_contain_text("Point B moved")
    changed = page.evaluate("toolState.points.B")
    assert changed != b_index and page.evaluate("toolState.points.A") == a_index
    assert page.evaluate("""() => {
        const cell = toolState.points.B;
        const [before, after] = pilotRadar();
        const reading = dbText(after.raw[cell] - before.raw[cell], 2);
        return document.querySelector('[data-point-card="B"]').textContent.includes(reading);
    }"""), "The card must show the new cell's radar change"
    pin.press("ArrowRight")
    assert page.evaluate("toolState.points.B") == changed + 1

    pin.scroll_into_view_if_needed()
    handle = pin.bounding_box()
    x, y = handle["x"] + handle["width"] / 2, handle["y"] + handle["height"] / 2
    expected = page.evaluate("Math.round(60 / (cell * (map.clientWidth / toolState.cam.span)))")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y, steps=6)
    page.mouse.up()
    assert abs(page.evaluate("toolState.points.B") - (changed + 1) - expected) <= 1

    page.get_by_role("button", name="Show reservoir").click()
    canvas.click(position={"x": 13, "y": canvas.bounding_box()["height"] * .75})
    expect(page.locator("#point-status")).to_contain_text("inside the dashed study boundary")
    page.get_by_role("button", name="Show both").click()
    expect(pin).to_be_visible()
    expect(page.get_by_role("button", name="Point A marker")).to_be_visible()
    page.get_by_role("button", name="Reset examples").click()
    expect(page.locator("#point-status")).to_contain_text("Example locations restored")
    assert page.evaluate("toolState.points.A === toolState.examples.A && toolState.points.B === toolState.examples.B")
    expect(a).to_have_attribute("data-active", "true")


def check_other_views(page):
    page.get_by_role("button", name="Map changes").click()
    page.get_by_role("button", name="Agreement", exact=True).click()
    expect(page.locator("#legend")).to_contain_text("Radar change")
    page.get_by_role("button", name="Radar change", exact=True).click()
    expect(page.locator("#legend")).to_contain_text("October minus August")
    page.get_by_role("button", name="Optical change", exact=True).click()
    expect(page.locator("#legend")).to_contain_text("Land in August, water in October")
    check_points(page)
    page.get_by_role("button", name="Timeline").click()
    expect(page.get_by_role("heading", name="Observation readings")).to_be_visible()
    expect(page.get_by_role("button", name="Compare these dates")).to_be_hidden()
    scrubber = page.get_by_role("slider", name="Timeline date")
    scrubber.press("ArrowRight")
    expect(page.locator("#time-status")).not_to_be_empty()
    assert page.locator("#before").inner_text() == scrubber.get_attribute("aria-valuetext")
    canvas = page.locator("#radar-chart")
    canvas.click(position={"x": 50, "y": 22})
    assert scrubber.input_value() == "0"
    page.get_by_role("button", name="Play", exact=True).click()
    expect(page.get_by_role("button", name="Pause", exact=True)).to_be_enabled()
    stage = page.locator("#investigations").get_by_role("link", name="Long-term observations")
    stage.press("Enter")
    expect(stage).to_have_attribute("aria-current", "location")
    expect(page.locator("#shoreline")).to_be_hidden()
    expect(page.get_by_role("heading", name="Has rainfall changed near Roseires?")).to_be_focused()
    assert page.evaluate("toolState.timer === null")
    page.go_back()
    expect(page.locator("#timeline")).to_be_visible()
    page.get_by_role("button", name="Swipe dates").click()

    expect(page.locator("#pilot-score")).to_contain_text("7.68%")
    expect(page.locator("#pilot-score")).to_contain_text("0.82%")
    page.get_by_role("link", name="Explore long-term observations").click()
    expect(page.locator("#trend-chart")).to_be_visible()
    expect(page.locator("#trend-slope")).to_have_text("+1.52 mm/year")
    expect(page.locator("#trend-significance")).to_have_text("Inconclusive")
    page.get_by_role("button", name="Monthly estimates").click()
    page.get_by_text("Read the plotted values", exact=True).click()
    expect(page.locator("#trend-table-body tr")).to_have_count(528)
    page.locator("#trend-period").select_option("2")
    expect(page.locator("#trend-table-body tr")).to_have_count(264)
    expect(page.locator("#trend-slope")).to_have_text("+48.17 mm/year")
    variable = page.get_by_role("combobox", name="Variable", exact=True)
    variable.select_option("modis")
    expect(page.locator("#trend-shift")).to_have_text("+164.07 km²")
    expect(page.locator("#trend-shift-ci")).to_have_text("95% CI 107.55 to 220.59 km²")
    expect(page.locator("#trend-slope")).to_have_text("-1.26 km²/year")
    expect(page.locator("#trend-post-ci")).to_have_text("95% CI -3.34 to 0.82 km²/year")
    expect(page.locator("#trend-significance")).to_have_text("Inconclusive")
    expect(page.locator("#trend-chart-unit")).to_have_text("Monthly reservoir surface area (km²)")
    expect(page.locator("#trend-table-body tr")).to_have_count(317)
    for month, status in [("2000-06", "NASA fill value"), ("2022-01", "No granule")]:
        row = page.locator("#trend-table-body tr").filter(has_text=month)
        expect(row.get_by_role("cell", name="—", exact=True)).to_be_visible()
        expect(row.get_by_role("cell", name=status, exact=True)).to_be_visible()
    assert page.evaluate("""() => {
        const events = [];
        const tracer = {beginPath(){}, stroke(){},
            moveTo(x, y){events.push(["move", x, y])}, lineTo(x, y){events.push(["line", x, y])}};
        const rows = seed.modis.monthly.slice(0, 10).map((row, time) => ({time, value: row.area_km2}));
        drawTrendLine(tracer, rows, x => x, y => y);
        return events.some(([action, time]) => action === "line" && time === 2)
            && events.some(([action, time]) => action === "move" && time === 7)
            && !events.some(([, time]) => rows[time].value === null);
    }"""), "The plotted line must restart after a gap"
    variable.select_option("rainfall")
    expect(page.locator("#trend-slope")).to_have_text("+48.17 mm/year")
    expect(page.locator("#trend-table-body tr")).to_have_count(264)
    page.get_by_role("link", name="Return to the 2026 shoreline").click()
    expect(page.locator("#shoreline")).to_be_visible()
    expect(page.get_by_role("button", name="Swipe dates")).to_have_attribute("aria-pressed", "true")


def check_imported_dates(page):
    # Exercise the import UI with a test-only bundle on the original grid.
    payload = page.evaluate("""() => {
        const bundle = structuredClone(seed.bundles.find(item => item.pair === "pilot"));
        bundle.pair = "holdout";
        bundle.optical_sources = {};
        bundle.radar.radar[0].datetime = "2026-08-18T03:20:00Z";
        bundle.radar.radar[1].datetime = "2026-10-02T03:20:00Z";
        return '<script type="application/json" id="data">'+JSON.stringify(bundle)+'</script>';
    }""")
    page.get_by_text("Data details", exact=True).click()
    page.locator("#add-data").set_input_files({
        "name": "test-holdout.html", "mimeType": "text/html", "buffer": payload.encode()
    })
    expect(page.locator("#import-status")).to_contain_text("usable water or land class")
    assert page.evaluate("loaded.radar.size === 4")
    page.get_by_role("button", name="Timeline").click()
    scrubber = page.get_by_role("slider", name="Timeline date")
    select = page.get_by_role("button", name="Select this date")
    compare = page.get_by_role("button", name="Compare these dates")

    def seek(date):
        index = page.evaluate("(day) => toolState.events.findIndex(event => event.record?.time.startsWith(day))", date)
        assert index >= 0
        scrubber.press("Home")
        for _ in range(index):
            scrubber.press("ArrowRight")

    seek("2026-10-02")
    select.press("Enter")
    expect(select).to_be_disabled()
    expect(compare).to_be_disabled()
    seek("2026-08-26")
    expect(select).to_be_disabled()
    seek("2026-08-18")
    select.press("Enter")
    expect(compare).to_be_focused()
    compare.press("Enter")
    expect(page.locator("#before")).to_contain_text("18 Aug 2026")
    expect(page.locator("#after")).to_contain_text("2 Oct 2026")
    expect(page.get_by_role("slider",name="Drag to compare")).to_be_visible()


def check_single_observation(page):
    # An isolated browser fixture reuses a frozen plane. No fixture goes into the site data.
    payload = page.evaluate("""() => {
        const bundle = seed.bundles.find(item => item.pair === "pilot");
        return JSON.stringify({
            id:"NISAR_L2_PR_GCOV_030_057_A_007_2005_DHDH_A_20260910T031900_20260910T031935_P05023_N_F_J_001",
            datetime:"2026-09-10T03:19:00Z", maturity:"PROVISIONAL", version:"1.0.11", release:"P05023",
            mode:"DHDH", grid:seed.grid, hh_db:bundle.arrays.hh_before
        });
    }""")
    page.get_by_text("Data details", exact=True).click()
    page.locator("#add-data").set_input_files({
        "name": "test-observation.json", "mimeType": "application/json", "buffer": payload.encode()
    })
    page.wait_for_function("loaded.radar.size === 3 && toolState.events.some(e => e.date.startsWith('2026-09-10'))")
    assert page.evaluate("loaded.water.size === 2 && toolState.patch.cells.length === 108")
    page.get_by_role("button", name="Timeline").click()
    slider = page.get_by_role("slider", name="Timeline date")
    index = page.evaluate("toolState.events.findIndex(event => event.date.startsWith('2026-09-10'))")
    slider.press("Home")
    for _ in range(index):
        slider.press("ArrowRight")
    expect(page.locator("#before")).to_contain_text("10 Sep")
    status = page.locator("#time-status")
    for label in ("PROVISIONAL", "Radar only", "Point A HH", "Point B HH"):
        expect(status).to_contain_text(label)
    assert page.evaluate("""() => {
        const row = toolState.events[toolState.time].record;
        const index = toolState.points.A;
        return row.raw[index] === pilotRadar()[0].raw[index]
            && !comparable(row, {...row, maturity:"VALIDATED"})
            && !comparable(row, {...row, mode:"SHSH"});
    }""")


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
        page.get_by_role("button", name="Optical water map", exact=True).tap()
        expect(page.locator("#after")).to_contain_text("Sentinel‑2")
        page.get_by_role("button", name="Show inlet").tap()
        page.get_by_role("button", name="Compare locations").tap()
        page.get_by_role("button", name="Move Point B",exact=True).tap()
        canvas.tap(position={"x": 80, "y": 170})
        expect(page.locator("#point-status")).to_contain_text("Point B moved")
        expect(page.locator('[data-point-card="B"]')).to_have_attribute("data-active","true")
        page.locator("#investigations").get_by_role("link", name="Long-term observations").tap()
        expect(page.locator("#trend-chart")).to_be_visible()
        page.get_by_role("combobox", name="Variable", exact=True).select_option("modis")
        expect(page.locator("#trend-shift")).to_have_text("+164.07 km²")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), "Horizontal overflow on mobile trends"
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
            data = page.request.get(urljoin(page.url, "roseires_modis_monthly_surface_area.csv"))
            assert data.ok and sha256(data.body()).hexdigest() == page.evaluate("seed.modis.source.sha256"), "Unexpected deployed MODIS CSV"

        check_swipe(page, offline)
        check_other_views(page)
        assert not errors, errors
        check_touch(browser, url, offline)
        if offline:
            single = browser.new_page(viewport={"width": 1280, "height": 900})
            single_errors = open_site(single, url, offline)
            check_single_observation(single)
            assert not single_errors, single_errors
            check_imported_dates(page)
            assert not errors, errors
            check_basemap(browser, url)
        browser.close()
    print("Desktop, keyboard, mouse and mobile touch smoke tests passed for " + url)


if __name__ == "__main__":
    main()
