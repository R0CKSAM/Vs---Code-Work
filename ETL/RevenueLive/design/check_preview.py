"""Check the standalone KPI design without touching live data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'design/kpi-cards-redesign.html').as_uri())
    expect(page.locator('.card')).to_have_count(6)
    expect(page.locator('.icon svg')).to_have_count(6)
    expect(page.locator('.card').nth(3).locator('.value')).to_have_text('+\u20b95,459')
    assert page.evaluate('daily.reduce((a,b)=>a+b,0)===110604')
    for width in [1440,1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_timeout(300)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
        assert page.locator('.card').evaluate_all('nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth)'), width
        page.screenshot(path=str(ROOT / '.screenshots' / f'kpi-preview-{width}.png'),full_page=True)
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.card').first.evaluate("n=>getComputedStyle(n).animationName") == 'none'
    assert not errors, errors
    browser.close()
print('PASS: six cards, local icons, derived figures, five viewports and reduced motion.')
