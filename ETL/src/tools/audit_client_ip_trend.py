"""Exercise the delivered standalone report with normal browser interactions."""
from pathlib import Path
import json, sys
from playwright.sync_api import sync_playwright

folder = Path(sys.argv[1]).resolve()
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto((folder / 'report.html').as_uri())
    check('Three complete day cards', page.locator('.kpi').count() == 3)
    check('Default overlay has three lines', page.locator('#totalChart polyline').count() == 3)
    page.locator('#continuous').click()
    check('Continuous has one 72-point line', page.locator('#totalChart polyline').count() == 1 and len(page.locator('#totalChart polyline').get_attribute('points').split()) == 72)
    page.locator('#overlay').click()
    check('Overlay restored', page.locator('#totalChart polyline').count() == 3)
    page.locator('#search').fill('B4U Music')
    check('Feed search narrows available options', page.locator('#feedSelect option').count() == 2)
    page.locator('#feedSelect').select_option(index=1)
    check('Single-feed drilldown', page.locator('#feedChart polyline').count() == 1)
    page.locator('#measure').select_option('share')
    check('Share mode labelled', 'Share of all hourly requests (%)' in page.locator('#feedChart').inner_text())
    hit = page.locator('#feedChart .hit')
    hit.hover(position={'x': 100, 'y': 60})
    check('Hover shows exact values', page.locator('#tooltip').is_visible())
    page.locator('#search').fill('there-is-no-such-feed')
    page.locator('#feedSelect').select_option('top')
    check('Empty search does not invent a feed', page.locator('#feedChart polyline').count() == 0)
    page.locator('#search').fill('')
    page.locator('#measure').select_option('requests')
    check('Top ten restored', page.locator('#feedChart polyline').count() == 10)
    check('Minute-overlap evidence chart present', page.locator('#overlapChart polyline').count() == 2)
    check('All three overlap summaries present', page.locator('#overlapSummary tbody tr').count() == 3)
    data = json.loads((folder / 'analysis.json').read_text())
    check('All charted feeds in comparison table', page.locator('#feedTable tbody tr').count() == len({(r['source'], r['reqHost'], r['candidate']) for r in data['feed_daily']}))
    page.screenshot(path=str(folder / 'report_desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    check('Mobile has no page overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    page.screenshot(path=str(folder / 'report_mobile.png'), full_page=True)
    check('No JavaScript errors', not errors)
    browser.close()
(folder / 'browser_audit.json').write_text(json.dumps({'passed': len(checks), 'checks': checks}, indent=2))
print(json.dumps({'passed': len(checks), 'checks': checks}))
