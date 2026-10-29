"""Optional headless browser check. Requires Playwright + its Chromium browser."""
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright


def check(path):
    path = Path(path).resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors, external = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: external.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        page.goto(path.as_uri())
        page.wait_for_selector('.chunk')
        assert page.evaluate("unicodeSlice('A🙂B',1,2)") == '🙂'
        assert page.locator('#doc option').count() == 6
        assert page.locator('#page').input_value() == '4'
        assert page.locator('.chunk').count() == 2  # EDF accounting policy + methodology
        page.locator('#byPage').click()
        assert page.locator('.chunk').count() == 1
        page.locator('#bySection').click()
        page.locator('.meta button').first.click()
        assert page.locator('#source mark').count() == 1
        assert page.locator('#source mark').inner_text().startswith('## **ACCOUNTING STANDARDS**')
        page.locator('#page').select_option('3')
        assert page.locator('#source table').count() == 1
        assert page.locator('#chunks table').count() == 1
        assert page.locator('#chunks [rowspan="2"]').count() > 0
        page.locator('#page').select_option('6')
        assert page.locator('.context').count() >= 1
        page.locator('#allPages').check()
        page.locator('#query').fill('hedging')
        assert page.locator('.chunk').count() >= 1
        page.locator('#query').fill('zzzznotfound')
        assert page.locator('.chunk').count() == 0
        assert page.locator('.empty').count() == 1
        page.locator('#query').fill('')
        page.locator('#allPages').uncheck()
        for document in ['hippodrome_2025', 'rolls_royce_2026h1_release', 'peterborough_2025', 'cvs_2025q2', 'rolls_royce_2026h1_presentation']:
            page.locator('#doc').select_option(document)
            assert page.locator('.chunk').count() >= 1
        page.locator('#doc').select_option('edf_2024')
        screenshots = path.parents[2] / 'artifacts'
        screenshots.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshots / 'preview-desktop.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        page.screenshot(path=str(screenshots / 'preview-mobile.png'))
        assert not errors, errors
        assert not external, external
        browser.close()
        return dict(browser='Chromium headless', documents=6, page_errors=errors,
                    external_requests=external, desktop_and_mobile=True, controls_and_source_navigation=True)


if __name__ == '__main__':
    print(json.dumps(check(sys.argv[1]), indent=2))
