"""Isolated first-phase dashboard visual and interaction checks."""
import secrets
import csv
import io
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
        page.locator('#viewsTreeButton>.share-title').click()
        expect(page.locator('#viewsDistributionRows')).to_be_visible()
        page.locator('#viewsDistribution > .distribution-collapse').click()
        expect(page.locator('#viewsTreeButton')).to_be_visible()
        expect(page.locator('#viewsDistribution > .distribution-collapse')).to_be_hidden()
        for width in [1388,390]:
            page.set_viewport_size({'width':width,'height':805})
            tile=page.locator('.views-tree-tile').first
            channel=tile.locator('.channel-brand').get_attribute('data-channel-name')
            tile.focus()
            tile.press('Enter')
            expect(page.locator('#channelDetailDialog')).to_be_visible()
            expect(page.locator('#channelDetailTitle')).to_have_text(channel)
            expected=page.evaluate('name=>reportRows.filter(r=>r.channel===name).reduce((s,r)=>s+r.views,0)',channel)
            actual=int(page.locator('.channel-detail-totals dd').first.inner_text().replace(',',''))
            assert actual==expected,('channel summary',actual,expected)
            assert page.locator('.channel-detail-table tbody tr').count()==7
            with page.expect_download() as download_info:
                page.get_by_role('button',name='Download channel CSV',exact=True).click()
            download=download_info.value
            exported=list(csv.DictReader(io.StringIO(Path(download.path()).read_text(encoding='utf-8-sig'))))
            assert len(exported)==7 and all(row['Channel']==channel for row in exported)
            assert sum(int(row['Views']) for row in exported)==expected
            assert download.suggested_filename.endswith('_2026-08-25_2026-08-31.csv')
            expect(page.locator('#channelDetailDialog')).to_be_visible()
            assert page.locator('#channelDetailDialog').evaluate('el=>el.scrollWidth<=el.clientWidth'),width
            page.screenshot(path=str(screens/f'channel-detail-{width}.png'))
            page.keyboard.press('Escape')
            expect(page.locator('#channelDetailDialog')).not_to_be_visible()
        page.set_viewport_size({'width':1388,'height':805})
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.length") == 2
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.every(d=>d.type==='bar')")
        assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.reduce((s,d)=>s+d.data.reduce((a,b)=>a+b,0),0)") == page.evaluate('reportRows.reduce((s,r)=>s+r.total,0)/100')
        assert page.locator('.full-share-row strong').first.text_content().endswith('%')
        page.locator('#revenueShareExpanded button').click()
        for metric,title in [('views','Views'),('impressions','Ad impressions'),('total','Revenue')]:
            page.locator('.overview-metric-selector [data-metric='+metric+']').click()
            expect(page.locator('.daily-revenue h2')).to_have_text(title+' over time')
            expect(page.locator('.overview-metric-selector [aria-pressed=true]')).to_have_text(title)
            assert page.evaluate('''key=>{
                const expected=reportRows.reduce((s,r)=>s+r[key],0),share=Chart.getChart('summaryShareCanvas'),trend=Chart.getChart('dailyRevenueCanvas');
                const shareSum=share.data.datasets[0].data.reduce((a,b)=>a+b,0),trendSum=trend.data.datasets.reduce((s,d)=>s+d.data.reduce((a,b)=>a+b,0),0);
                return Math.abs(shareSum-expected)<.01 && Math.abs(trendSum-expected/(key==='total'?100:1))<.01;
            }''',metric),('linked metric totals',metric)
            if metric!='total':
                assert '₹' not in page.locator('#shareSum').inner_text()
                assert page.evaluate("Chart.getChart('dailyRevenueCanvas').data.datasets.length") == 1
                page.locator('#revenueShare').click()
                expect(page.locator('#revenueShareTitle')).to_have_text(title+' by channel')
                assert '₹' not in page.locator('#fullShareRows').inner_text()
                page.locator('#revenueShareExpanded button').click()
        expect(page.locator('#performanceInsight')).to_be_visible()
        for width in [1920, 1388, 1024, 944, 900, 768, 390, 320]:
            page.set_viewport_size({'width': width, 'height': 805})
            page.wait_for_timeout(350)
            page.locator('#viewsTreeButton>.share-title').click()
            assert page.locator('#viewsDistribution').evaluate('''node=>{
                const heading=node.querySelector('h2').getBoundingClientRect(),close=node.querySelector('.distribution-collapse').getBoundingClientRect(),rows=node.querySelector('#viewsDistributionRows').getBoundingClientRect();
                return heading.right<=close.left && rows.top>=Math.max(heading.bottom,close.bottom);
            }'''),('expanded views header fit',width)
            page.locator('#viewsDistribution').screenshot(path=str(screens / f'views-expanded-{width}.png'))
            page.locator('#viewsDistribution > .distribution-collapse').click()
            if width>800:
                assert page.evaluate("()=>Math.abs(document.getElementById('revenueShare').getBoundingClientRect().height-document.querySelector('.daily-revenue').getBoundingClientRect().height)<2"),('matched chart heights',width)
            if width>=900:
                edges=page.evaluate('''()=>{const left=document.getElementById('accountMenu').getBoundingClientRect(),right=document.getElementById('export').getBoundingClientRect(),body=document.querySelector('.metrics').getBoundingClientRect();return [Math.abs(left.left-body.left),Math.abs(right.right-body.right)];}''')
                assert max(edges)<2,('header alignment',width,edges)
            if width>=900:
                assert page.locator('.metrics article').evaluate_all('(cards)=>new Set(cards.map(c=>Math.round(c.getBoundingClientRect().top))).size===1'),width
            assert page.locator('.revenue-split > .metric-topline').evaluate('(el)=>getComputedStyle(el).flexDirection==="row"')
            assert page.locator('.revenue-split .metric-changes').evaluate_all('nodes=>nodes.every(el=>el.scrollWidth<=el.clientWidth)')
            page.mouse.move(0,0)
            for card in page.locator('.metrics article').all():
                card.scroll_into_view_if_needed()
                before=card.evaluate('(el)=>[el,...el.querySelectorAll("strong,div,span")].map(n=>{const r=n.getBoundingClientRect();return [r.x+scrollX,r.y+scrollY,r.width,r.height];})')
                card.hover()
                page.wait_for_timeout(200)
                after=card.evaluate('(el)=>[el,...el.querySelectorAll("strong,div,span")].map(n=>{const r=n.getBoundingClientRect();return [r.x+scrollX,r.y+scrollY,r.width,r.height];})')
                assert before==after,('metric hover layout shift',width,before,after)
                page.mouse.move(0,0)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            assert page.locator('#revenueShare .share-centre').evaluate('''node=>{
                const chart=Chart.getChart('summaryShareCanvas'),arc=chart.getDatasetMeta(0).data[0],canvas=chart.canvas.getBoundingClientRect(),box=node.getBoundingClientRect();
                return [...node.children].every(n=>n.scrollWidth<=n.clientWidth)&&node.scrollHeight<=node.clientHeight&&
                    [box.left,box.right].every(x=>[box.top,box.bottom].every(y=>Math.hypot(x-canvas.left-arc.x,y-canvas.top-arc.y)<arc.innerRadius));
            }'''),('doughnut text inside opening',width)
            assert page.evaluate('''()=>{
                const label=document.getElementById('shareSum'),original=label.textContent,chart=Chart.getChart('summaryShareCanvas');
                const fits=['₹4,72,204','₹12,34,56,789'].every(value=>{
                    label.textContent=value;chart.draw();
                    return label.scrollWidth<=label.clientWidth && label.parentElement.scrollHeight<=label.parentElement.clientHeight;
                });
                label.textContent=original;chart.draw();return fits;
            }'''),('large doughnut totals fit',width)
            assert page.locator('.compact-share-row').evaluate_all('''rows=>rows.every(row=>{
                const name=row.querySelector('.share-channel').getBoundingClientRect(),value=row.querySelector('strong>span').getBoundingClientRect();
                return name.right<=value.left && Math.abs(name.top-value.top)<4 && row.scrollWidth<=row.clientWidth;
            })'''),('pie legend name beside value',width)
            assert page.locator('.share-content').evaluate('''node=>{
                const ring=node.querySelector('.share-ring').getBoundingClientRect(),legend=node.querySelector('#summaryShareLegend').getBoundingClientRect();
                return ring.right<=legend.left || ring.bottom<=legend.top;
            }'''),('legend beside doughnut',width)
            assert page.evaluate("Chart.getChart('summaryShareCanvas').options.plugins.visibleSharePercent===false")
            page.locator('#revenueOverview').screenshot(path=str(screens / f'revenue-overview-{width}.png'))
            page.locator('#revenueShare').screenshot(path=str(screens / f'revenue-legend-{width}.png'))
            assert page.locator('.views-tree-tile').evaluate_all('''tiles=>tiles.every(tile=>{
                const label=tile.querySelector('span'),value=tile.querySelector('strong');
                return parseFloat(getComputedStyle(label).fontSize)>=16&&parseFloat(getComputedStyle(value).fontSize)>=16&&tile.scrollHeight<=tile.clientHeight&&tile.scrollWidth<=tile.clientWidth&&label.getBoundingClientRect().bottom<=value.getBoundingClientRect().top;
            })'''),('treemap text fit',width)
            for metric in ['total', 'ad', 'other', 'views', 'impressions']:
                assert page.locator('#' + metric).evaluate('(el)=>el.hidden || el.scrollWidth<=el.clientWidth'), (width, metric)
                assert page.locator('#' + metric).evaluate('(el)=>el.closest("article").querySelector(".metric-topline").getBoundingClientRect().bottom<=el.getBoundingClientRect().top'), ('heading above value',width,metric)
            assert page.locator('.metric-value-row').evaluate_all('''rows=>rows.every(row=>{
                const value=row.querySelector('strong').getBoundingClientRect(),changes=row.querySelector('.metric-changes');
                if(!changes.getClientRects().length)return true;
                const rect=changes.getBoundingClientRect();
                return value.right<=rect.left && Math.abs((value.top+value.bottom-rect.top-rect.bottom)/2)<2;
            })'''),('comparison beside value',width)
            assert page.locator('.metric-change:not([hidden])').evaluate_all('nodes=>nodes.every(n=>parseFloat(getComputedStyle(n).fontSize)>=15)'),('readable comparison',width)
            page.locator('.metrics').screenshot(path=str(screens / f'metric-cards-{width}.png'))
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
        assert page.evaluate("Array.from(document.querySelectorAll('#channelMetrics tbody tr')).reduce((s,r)=>s+Number(r.lastElementChild.firstElementChild.textContent.replace(/[^0-9.-]/g,'')),0)") == page.evaluate("()=>{const sums={};for(const r of reportRows)sums[r.channel]=(sums[r.channel]||0)+r.total;return Object.values(sums).reduce((s,n)=>s+Math.round(n/100),0);}")
        expect(page.locator('.flatpickr-calendar')).to_be_visible()
        expect(page.locator('.flatpickr-day.flatpickr-disabled').first).to_be_visible()
        page.locator('.flatpickr-day[aria-label="August 28, 2026"]').click()
        page.locator('.flatpickr-day[aria-label="August 24, 2026"]').click()
        expect(page.locator('#start')).to_have_value('2026-08-24')
        expect(page.locator('#end')).to_have_value('2026-08-28')
        expect(page.locator('#rangeTitle')).to_contain_text('24 Aug 2026')
        page.evaluate("()=>{document.getElementById('start').value='2026-08-28';document.getElementById('end').value='2026-08-24';document.getElementById('end').dispatchEvent(new Event('change'));}")
        expect(page.locator('#start')).to_have_value('2026-08-24')
        expect(page.locator('#end')).to_have_value('2026-08-28')
        page.locator('#rangeTitle').click()
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
        page.evaluate("RevenueShare.render([{channel:'Scale check',day:'2026-08-31',views:100,impressions:50,ad:0,other:2500,total:2500}])")
        bars=page.locator('#channelMetrics .channel-value-track>span').evaluate_all('(nodes)=>nodes.map(n=>n.style.width)')
        assert bars==['100%','100%','0%','100%','100%'],bars
        page.evaluate("RevenueShare.render([1,2,3].map((n)=>({channel:'Channel '+n,day:'2026-08-31',views:n*100000,impressions:(4-n)*10,ad:n*100,other:0,total:n*100})))")
        cells=page.locator('#channelMetrics tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.querySelectorAll(".channel-value-track>span")).map(c=>parseFloat(c.style.width)))')
        assert cells[0][0]==100 and abs(cells[0][1]-100/3)<.01 and cells[0][2]==100,cells
        assert abs(cells[1][0]-200/3)<.01 and cells[1][0]==cells[1][1]==cells[1][2],cells
        page.evaluate("RevenueShare.render([{channel:'All zero',day:'2026-08-31',views:0,impressions:0,ad:0,other:0,total:0}])")
        assert page.locator('#channelMetrics .channel-value-track>span').evaluate_all('(nodes)=>nodes.every(n=>n.style.width==="0%")')
        page.evaluate('refresh()')
        print('PASS: four cards, local icons, weekly default, date change, CSV, table navigation, five responsive screenshots; no page errors.')
        browser.close()
finally:
    server.close()
