"""Exercise the actual generated page and validate selected geography numbers."""
import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright

path=Path(sys.argv[1]).resolve()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(path.as_uri(),wait_until='load',timeout=180000)
    page.locator('#sourceSelect').select_option('stream')
    page.locator('#startDate').fill('2026-11-11');page.locator('#startDate').blur()
    page.locator('#endDate').fill('2026-11-11');page.locator('#endDate').blur()
    page.locator('#geoDeviceSection').scroll_into_view_if_needed()
    page.wait_for_function("document.getElementById('geoTable').innerText.includes('63,496 (exact)')",timeout=60000)
    row=page.locator('#geoTable tr').filter(has_text='BD').inner_text()
    assert '14,580.7' in row and '14,555.2' in row and '63,496 (exact)' in row,row
    checks={'BD_all_channels':row}
    page.locator('#channelToggle').click()
    page.locator('#channelMenu input[data-value="Weightlifting (dreamboat-ch01)"]').check()
    page.locator('#geoDeviceSection').scroll_into_view_if_needed()
    page.wait_for_function("document.getElementById('geoTable').innerText.includes('63,454 (exact)')",timeout=60000)
    row=page.locator('#geoTable tr').filter(has_text='BD').inner_text()
    assert '14,566.7' in row and '63,454 (exact)' in row,row
    checks['BD_weightlifting']=row
    page.evaluate("state.channel='all';state.start='2026-11-10';filterCache=new WeakMap();renderGeoDevice()")
    row=page.locator('#geoTable tr').filter(has_text='BD').inner_text()
    assert 'Unavailable: overlapping groups' in row,row
    checks['multi_day_no_false_unique']=row
    page.evaluate("state.start='2026-11-10';state.end='2026-11-10';filterCache=new WeakMap();renderGeoDevice()")
    row=page.evaluate("geoIpValue([DATA.geo_daily.find(r=>r.source==='stream' && r.log_date==='2026-11-10' && r.country==='BD')]).label")
    assert '(approx.)' in row,row
    checks['historical_estimate_label']=row
    page.evaluate("state.start='2026-11-11';state.end='2026-11-11';filterCache=new WeakMap();renderGeoDevice()")
    page.locator('#geoDeviceSection').screenshot(path=str(path.with_suffix('.audit.png')))
    checks['browser_errors']=errors
    assert not errors,errors
    path.with_suffix('.audit.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks,indent=2))
    browser.close()
