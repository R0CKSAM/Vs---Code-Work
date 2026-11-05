"""Browser state, combination, keyboard, pagination and applied-export checks."""
import csv
import io
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
report={'checks':[],'errors':[]}
def check(name,ok):
    assert ok,name
    report['checks'].append(name)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.goto('http://127.0.0.1:8766')
    page.wait_for_function("document.getElementById('status').textContent.includes('matched records')")
    for field in ['video_key','title','category','os','isp','region','device_type','cli_ip','device_id']:
        page.locator('#filter-'+field).click()
        page.locator('#options input').first.wait_for()
        page.locator('#options input').first.check()
        page.locator('#done').click()
        with page.expect_response(lambda r:r.url.endswith('/api/query')) as r:page.locator('#apply').click()
        data=r.value.json()
        page.wait_for_function("!document.getElementById('apply').disabled")
        check('Browser cumulative combination '+field,data['kpi']['records']>0)
    page.locator('#filter-device_id').click()
    page.locator('#options input').first.wait_for()
    check('Selected item persists on reopen',page.locator('#options input:checked').count()==1)
    page.locator('#clearField').click()
    check('Clear current field only',page.locator('#options input:checked').count()==0)
    page.keyboard.press('Escape')
    check('Escape restores trigger focus',page.locator('#filter-device_id').evaluate('(e)=>document.activeElement===e'))
    page.locator('#reset').click()
    page.wait_for_function("!document.getElementById('apply').disabled")
    check('Reset clears all selections',page.locator('.filter-trigger.active').count()==0)
    page.locator('#filter-cli_ip').click()
    page.locator('#options input').first.wait_for()
    check('Initial high-cardinality page has 100 options',page.locator('#options input').count()==100)
    page.locator('#loadMore').click()
    page.wait_for_function("document.querySelectorAll('#options input').length===200")
    check('Load-more has no duplicate labels',len(set(page.locator('#options .option span').all_text_contents()))==200)
    page.locator('#selectVisible').click()
    check('Select shown selects all loaded options',page.locator('#options input:checked').count()==200)
    page.locator('#search').fill('not_a_real_ip')
    page.locator('#options .empty').filter(has_text='No matching').wait_for()
    check('Searching preserves hidden selections',page.locator('#selectedCount').inner_text()=='200 selected')
    page.locator('#clearField').click()
    page.locator('#done').click()
    # Export must remain tied to applied results when the draft changes.
    page.locator('#filter-os').click();page.locator('#options input').first.wait_for()
    page.locator('#options input').first.check();page.locator('#done').click()
    with page.expect_response(lambda r:r.url.endswith('/api/export')) as r:
        with page.expect_download():page.locator('#export').click()
    posted=r.value.request.post_data_json
    check('Export uses applied filters, not unapplied draft',not any(posted['filters'].values()))
    # A newer draft change while a query is in flight must remain visibly pending.
    def delay(route):
        response=route.fetch()
        page.wait_for_timeout(350)
        route.fulfill(response=response)
    page.route('**/api/query',delay)
    page.locator('#apply').click()
    page.locator('#timeStart').fill('12:00')
    page.locator('#timeStart').press('Tab')
    page.wait_for_function("!document.getElementById('apply').disabled")
    check('Newer draft remains marked pending after slow query', 'pending' in page.locator('#status').inner_text().lower())
    page.unroute('**/api/query',delay)
    page.locator('#reset').click();page.wait_for_function("!document.getElementById('apply').disabled")
    page.locator('#filter-os').click();page.locator('#options input').first.wait_for()
    page.locator('#done').focus();page.keyboard.press('Tab')
    check('Modal traps forward keyboard focus',page.locator('#closePicker').evaluate('(e)=>document.activeElement===e'))
    page.keyboard.press('Shift+Tab')
    check('Modal traps backward keyboard focus',page.locator('#done').evaluate('(e)=>document.activeElement===e'))
    page.keyboard.press('Escape')
    browser.close()
check('No JavaScript errors',not report['errors'])
report['passed']=True
(ROOT/'audit/interactions.json').write_text(json.dumps(report,indent=2))
print('PASS',len(report['checks']),'browser interaction checks')
