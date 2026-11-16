import sys
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

url, revision = sys.argv[1:3]
folder = Path('design-screenshots') / revision
folder.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 960})
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_function('toolState.ready && toolState.patch.cells.length === 108')
    page.evaluate('document.fonts.ready')
    try:
        page.wait_for_function('viewportBasemap?.image.naturalWidth > 0', timeout=10000)
    except TimeoutError:
        print('Rendered with embedded geographic context')


    def shot(name, top=True):
        if top:
            page.evaluate('window.scrollTo({top:0,behavior:"instant"})')
        page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        print(name, page.evaluate('({w:innerWidth, overflow:document.documentElement.scrollWidth-innerWidth, map:document.querySelector("#map").getBoundingClientRect().top + scrollY, chart:document.querySelector("#trend-chart").getBoundingClientRect().top + scrollY})'), flush=True)
        page.screenshot(path=folder / f'{name}.jpg', type='jpeg', quality=90, animations='disabled')

    def button(name):
        return page.get_by_role('button', name=name, exact=True)

    shot('desktop-shoreline')
    button('Map changes').click()
    button('Compare change maps').click()
    shot('desktop-change')
    button('Compare locations').click()
    button('Move Point B').press('Space')
    shot('desktop-points')
    button('Timeline').click()
    shot('desktop-timeline-map')
    page.locator('#timeline-readings').evaluate('(el) => el.scrollIntoView()')
    shot('desktop-timeline-plots', False)
    page.locator('#investigations').get_by_role('link', name='Long-term observations').click()
    shot('desktop-rainfall')
    page.locator('#trend-chart').evaluate('(el) => el.scrollIntoView({block:"center"})')
    shot('desktop-rainfall-chart', False)
    page.locator('#trend-variable').select_option('modis')
    shot('desktop-modis')
    page.get_by_text('Data and method', exact=True).click()
    page.get_by_text('Data details', exact=True).click()
    page.locator('#data-details').evaluate('(el) => el.scrollIntoView()')
    shot('desktop-sources', False)
    page.get_by_role('link', name='Return to the 2026 shoreline').click()
    button('Swipe dates').click()
    for width,height,name in [(820,1024,'tablet'), (390,844,'mobile-portrait'), (844,390,'mobile-landscape')]:
        page.set_viewport_size({'width': width, 'height': height})
        shot(f'{name}-shoreline')
    page.set_viewport_size({'width': 390, 'height': 844})
    button('Timeline').click()
    shot('mobile-timeline')
    page.locator('#investigations').get_by_role('link', name='Long-term observations').click()
    page.locator('#trend-variable').select_option('rainfall')
    shot('mobile-rainfall')
    page.locator('#trend-variable').select_option('modis')
    shot('mobile-modis')
