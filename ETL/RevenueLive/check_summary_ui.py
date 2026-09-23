"""Isolated first-phase dashboard visual and interaction checks."""
import secrets
import sqlite3
import sys
import threading
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
from werkzeug.security import generate_password_hash
from app import create_app, parse_upload
from demo_data import seed_demo

data = ROOT / '.test-data' / secrets.token_hex(8)
app = create_app(data)
password = secrets.token_urlsafe(18)
with closing(sqlite3.connect(data / 'revenuelive.db')) as db, db:
    db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')", ('smarth-test', generate_password_hash(password)))
    for row in parse_upload((ROOT / 'Upload File.xls').read_bytes(), '.xls'):
        db.execute('INSERT OR IGNORE INTO channels(name) VALUES (?)', (row['channel'],))
seed_demo(data)
server = create_server(app, host='127.0.0.1', port=0)
threading.Thread(target=server.run, daemon=True).start()
screens = ROOT / '.screenshots'
screens.mkdir(exist_ok=True)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1388, 'height': 805})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.effective_port}')
        page.locator('#loginForm [name=username]').fill('smarth-test')
        page.locator('#loginForm [name=password]').fill(password)
        page.locator('#loginForm button.primary').click()
        expect(page.locator('#filterState')).to_have_text('Updated')
        expect(page.locator('#start')).to_have_value('2026-08-25')
        expect(page.locator('#end')).to_have_value('2026-08-31')
        expect(page.locator('.metric-icon svg')).to_have_count(4)
        expect(page.locator('.metrics article')).to_have_count(4)
        expect(page.locator('#channelAnalysis')).not_to_be_visible()
        expect(page.locator('#summaryShareLegend .compact-share-row')).to_have_count(6)
        page.locator('#revenueShare').click()
        expect(page.locator('#revenueShareExpanded')).to_be_visible()
        expect(page.locator('#fullShareRows .full-share-row')).to_have_count(28)
        expect(page.locator('#viewsDistributionRows .full-share-row')).to_have_count(28)
        expect(page.locator('.tree-legend-item')).to_have_count(28)
        assert page.locator('.views-tree-tile').count()==page.evaluate('new Set(reportRows.filter(r=>r.views>0).map(r=>r.channel)).size')
        expect(page.locator('#viewsDistributionRows')).not_to_be_visible()
        page.locator('#viewsTreeButton').click()
        expect(page.locator('#viewsDistributionRows')).to_be_visible()
        page.locator('#viewsDistribution > .distribution-collapse').click()
        expect(page.locator('#viewsTreeButton')).to_be_visible()
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.length") == 2
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.every(d=>d.type==='bar')")
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.reduce((s,d)=>s+d.data.reduce((a,b)=>a+b,0),0)") == page.evaluate('reportRows.reduce((s,r)=>s+r.total,0)/100')
        assert page.locator('.full-share-row strong').first.text_content().endswith('%')
        page.locator('#revenueShareExpanded button').click()
        for width in [1388, 1024, 768, 390, 320]:
            page.set_viewport_size({'width': width, 'height': 805})
            page.wait_for_timeout(350)
            page.mouse.move(0,0)
            for card in page.locator('.metrics article').all():
                before=card.evaluate('(el)=>[el,...el.querySelectorAll("strong,div,span")].map(n=>{const r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height];})')
                card.hover()
                page.wait_for_timeout(200)
                after=card.evaluate('(el)=>[el,...el.querySelectorAll("strong,div,span")].map(n=>{const r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height];})')
                assert before==after,('metric hover layout shift',width,before,after)
                page.mouse.move(0,0)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            for metric in ['total', 'ad', 'other', 'views', 'impressions']:
                assert page.locator('#' + metric).evaluate('(el)=>el.hidden || el.scrollWidth<=el.clientWidth'), (width, metric)
            page.screenshot(path=str(screens / f'summary-{width}.png'), full_page=True)
        page.locator('#rangeTitle').click()
        page.locator('#chooseCalendarYear').click()
        page.locator('.calendar-choices button',has_text='2026').click()
        page.locator('#chooseCalendarMonth').click()
        page.locator('.calendar-choices button',has_text='Aug').click()
        expect(page.locator('.flatpickr-months')).not_to_be_visible()
        expect(page.locator('#channelMetrics tbody tr')).to_have_count(28)
        expect(page.locator('#channelMetrics tbody tr:visible')).to_have_count(5)
        page.locator('.metrics-toggle').click()
        expect(page.locator('#channelMetrics tbody tr:visible')).to_have_count(28)
        page.locator('.metrics-toggle').click()
        page.locator('#rangeTitle').click()
        assert page.evaluate("Array.from(document.querySelectorAll('#channelMetrics tbody tr')).reduce((s,r)=>s+Number(r.lastElementChild.textContent.replace(/[^0-9.-]/g,'')),0)") == page.evaluate("()=>{const sums={};for(const r of reportRows)sums[r.channel]=(sums[r.channel]||0)+r.total;return Object.values(sums).reduce((s,n)=>s+Math.round(n/100),0);}")
        expect(page.locator('.flatpickr-calendar')).to_be_visible()
        expect(page.locator('.flatpickr-day.flatpickr-disabled').first).to_be_visible()
        page.locator('.flatpickr-day[aria-label="August 26, 2026"]').click()
        page.locator('.flatpickr-day[aria-label="August 26, 2026"]').click()
        expect(page.locator('#rangeTitle')).to_contain_text('26 Aug 2026')
        expect(page.locator('#end')).to_have_value('2026-08-26')
        page.locator('#channelSummary').click()
        expect(page.locator('#selectVisible')).not_to_be_visible()
        page.locator('#channelSearch').fill('NDTV')
        page.locator('#clearChannels').click()
        assert page.locator('#channelOptions label:not([hidden]) input:checked').count()==0
        assert page.locator('#channelOptions label[hidden] input:checked').count()>0
        page.locator('#selectAllChannels').click()
        assert page.locator('#channelOptions label:not([hidden]) input:not(:checked)').count()==0
        page.locator('#channelSearch').fill('')
        page.locator('#clearChannels').click()
        page.locator('#channelOptions input').first.check()
        expect(page.locator('#filterState')).to_have_text('Updated')
        expect(page.locator('#totalLabel')).to_contain_text(page.locator('#channelOptions label').first.text_content())
        page.locator('#channelOptions input').nth(1).check()
        expect(page.locator('#totalLabel')).to_have_text('TOTAL REVENUE (2 Channels)')
        expect(page.locator('#summaryShareLegend .compact-share-row')).to_have_count(2)
        page.locator('#selectAllChannels').click()
        expect(page.locator('#filterState')).to_have_text('Updated')
        page.locator('#channelSummary').click()
        page.keyboard.press('Escape')
        with page.expect_download() as download:
            page.locator('#export').click()
        assert download.value.failure() is None
        page.locator('#accountMenu > summary').click()
        page.locator('[data-view=tabular]').click()
        expect(page.locator('#records tr').first).to_be_visible()
        page.evaluate('overview()')
        for width in [1388, 768, 390, 320]:
            page.set_viewport_size({'width':width,'height':950})
            for count in [1, 2, 28]:
                for first,last in [('2026-08-27','2026-08-27'),('2026-08-27','2026-08-31'),('2026-08-25','2026-08-31'),('2026-08-01','2026-08-31')]:
                    page.evaluate('''async ([count,first,last])=>{selectedChannels=new Set(me.channels.slice(0,count).map(c=>String(c.id)));renderChannelOptions();document.getElementById('start').value=first;document.getElementById('end').value=last;await refresh();}''',[count,first,last])
                    page.wait_for_timeout(320)
                    result=page.evaluate('''()=>{const c=Chart.getChart('dailyRevenueCanvas'),a=c.chartArea;return {bad:c.config.type==='bar'&&c.data.datasets.some((_,i)=>c.getDatasetMeta(i).data.some(b=>b.x-b.width/2<a.left-1||b.x+b.width/2>a.right+1||Math.min(b.y,b.base)<a.top-1||Math.max(b.y,b.base)>a.bottom+1)),overflow:document.documentElement.scrollWidth>innerWidth};}''')
                    assert not result['bad'] and not result['overflow'],(width,count,first,last,result)
        assert not errors, errors
        print('PASS: four cards, local icons, weekly default, date change, CSV, table navigation, five responsive screenshots; no page errors.')
        browser.close()
finally:
    server.close()
