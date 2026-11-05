import json
import math
import sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from playwright.sync_api import sync_playwright
from journey import build_sessions

ROOT=Path(__file__).resolve().parent
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
def event(clock,key='a',host='one',session='s',**kwargs):
    return dict(request_ist='2026-11-04 '+clock,last_request_ist='2026-11-04 '+clock,video_key=key,req_host=host,session_id=session,title=key,category='test',hours=0.1,segments=60,identity_source='segment_query',**kwargs)
rows=[event('10:00:00'),event('10:30:00'),event('11:00:01'),event('11:01:00','b'),event('11:02:00','a'),event('11:03:00',host='two'),event('11:04:00',host='two',session='new')]
s=build_sessions(rows,{})
check('Exactly 30 minute gap groups; longer gap splits',len(s)==6 and s[0]['segments']==120)
check('Repeat title after different content stays separate',s[2]['video_key']=='b' and s[3]['video_key']=='a')
check('Host and known session changes split',s[4]['host']=='two' and s[5]['session_id']=='new')
check('Session hours reconcile',math.isclose(sum(r['hours'] for r in s),.7))
highlight=build_sessions(rows,{'video_key':['b']})
check('Content filtering highlights without dropping neighbors',len(highlight)==6 and sum(r['matched'] for r in highlight)==1)
overlap=event('10:00:00');overlap['last_request_ist']='2026-11-04 10:02:00'
check('Overlapping content activity is flagged',all(r['overlap'] for r in build_sessions([overlap,event('10:01:00','b')],{})))
with sqlite3.connect(ROOT/'data/smartvod.sqlite') as con:
    device=con.execute("SELECT device_id FROM events WHERE device_id!='Unknown' GROUP BY device_id HAVING count(DISTINCT video_key)>5 ORDER BY count(*) DESC LIMIT 1").fetchone()[0]
    total=con.execute('SELECT sum(hours),sum(segments) FROM events WHERE device_id=?',[device]).fetchone()
def api(filters):
    b=dict(start='2026-11-04',end='2026-11-04',timeStart='00:00',timeEnd='23:59',filters=filters)
    return json.load(urlopen(Request('http://127.0.0.1:8766/api/journey',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})))
data=api({'device_id':[device]})
check('Real device returns chronological sessions',len(data['sessions'])>5 and [s['start'] for s in data['sessions']]==sorted(s['start'] for s in data['sessions']))
check('Real journey hours reconcile',math.isclose(sum(s['hours'] for s in data['sessions']),total[0],rel_tol=1e-10))
check('Real journey segments reconcile',sum(s['segments'] for s in data['sessions'])==total[1])
for filters in ({},{'device_id':['Unknown']},{'device_id':[device,'other']}):
    check('No blended or missing-device journey '+str(filters),not api(filters)['sessions'])
target=data['sessions'][3]['video_key']
highlight=api({'device_id':[device],'video_key':[target]})
check('Real content filter preserves adjacent sessions',len(highlight['sessions'])==len(data['sessions']) and all(s['matched']==(s['video_key']==target) for s in highlight['sessions']))
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8766')
    page.wait_for_function("document.getElementById('status').textContent.includes('matched records')")
    page.locator('#filter-device_id').click();page.locator('#search').fill(device)
    page.locator('#options .option').filter(has_text=device).locator('input').check()
    page.locator('#done').click();page.locator('#apply').click()
    page.locator('#journeyContent').wait_for(state='visible')
    check('Browser journey follows applied device',device in page.locator('#journeyStatus').inner_text())
    page.locator('#journeyNextMatch').click()
    check('Next session navigation', 'Session 2 of' in page.locator('#journeyPosition').inner_text())
    page.locator('#journeyPrevMatch').click()
    check('Previous session navigation','Session 1 of' in page.locator('#journeyPosition').inner_text())
    page.locator('.journey-panel').screenshot(path=str(ROOT/'audit/journey.png'))
    page.set_viewport_size({'width':390,'height':844})
    check('Journey fits mobile width',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.locator('#reset').click()
    page.wait_for_function("document.getElementById('journeyStatus').textContent.includes('Select exactly one')")
    check('Reset clears prior device journey',page.locator('#journeyContent').is_hidden())
    browser.close()
check('No journey JavaScript errors',not errors)
(ROOT/'audit/journey.json').write_text(json.dumps(dict(passed=True,checks=checks,session_count=len(data['sessions'])),indent=2))
print('PASS',len(checks),'journey checks;',len(data['sessions']),'real-device sessions')
