"""Browser/data reconciliation for the synthetic month, isolated from production."""
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from contextlib import closing

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
from werkzeug.security import generate_password_hash
from app import create_app, parse_upload
from demo_data import seed_demo

data=ROOT/'.test-data'/secrets.token_hex(8)
app=create_app(data)
password=secrets.token_urlsafe(18)
with closing(sqlite3.connect(data/'revenuelive.db')) as db,db:
    db.execute("INSERT INTO users(username,password,role) VALUES (?,?,'admin')",('test-admin',generate_password_hash(password)))
    for r in parse_upload((ROOT/'Upload File.xls').read_bytes(),'.xls'):
        db.execute('INSERT OR IGNORE INTO channels(name) VALUES (?)',(r['channel'],))
seed_demo(data)
server=create_server(app,host='127.0.0.1',port=0)
threading.Thread(target=server.run,daemon=True).start()
screens=ROOT/'.screenshots';screens.mkdir(exist_ok=True)
checks=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1050})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:'+str(server.effective_port))
        page.locator('#loginForm [name=username]').fill('test-admin')
        page.locator('#loginForm [name=password]').fill(password)
        page.locator('#loginForm button').click()
        try:
            expect(page.locator('#rowCount')).to_have_text('868 records')
        except AssertionError:
            print('LOGIN ERROR:',page.locator('#loginError').text_content(), 'JS ERRORS:',errors,flush=True)
            raise
        def apply():
            with page.expect_response(lambda r:'/api/report?' in r.url) as response:
                page.locator('#filters button.primary').click()
            result=response.value.json()
            assert response.value.status==200,result
            expect(page.locator('#filterState')).to_have_text('Filters applied')
            return result
        def reconcile(label):
            metrics=page.evaluate('''() => {
                const c=RevenueCharts.charts;
                return {rows:reportRows.length,total:reportRows.reduce((n,r)=>n+r.total,0)/100,
                    trend:c.trendChart?.data.datasets[0].data.reduce((n,v)=>n+v,0)||0,
                    share:c.shareChart?.data.datasets[0].data.reduce((n,v)=>n+v,0)||0,
                    mix:c.mixChart?.data.datasets.reduce((n,d)=>n+d.data.reduce((n,v)=>n+v,0),0)||0,
                    scatter:c.scatterChart?.data.datasets[0].data.reduce((n,v)=>n+v.y,0)||0};
            }''')
            for key in ['trend','share','mix','scatter']:
                assert abs(metrics[key]-metrics['total'])<.000001,(label,key,metrics)
            checks.append({'case':label,**metrics})
        reconcile('all channels / whole month')
        page.screenshot(path=str(screens/'analytics-desktop.png'),full_page=True)
        # Search and select only the visible NDTV options.
        page.locator('#channelSummary').click();page.locator('#clearChannels').click()
        page.locator('#channelSearch').fill('NDTV');page.locator('#selectVisible').click()
        page.locator('#datePreset').select_option('custom')
        page.locator('#start').fill('2026-08-05');page.locator('#end').fill('2026-08-18')
        result=apply();assert len(result['rows'])==6*14
        assert all(r['channel'].startswith('NDTV') for r in result['rows'])
        reconcile('six searched channels / 14 days')
        for interval in ['week','month','day']:
            page.locator('#interval').select_option(interval);reconcile(interval+' aggregation')
        page.locator('#shareType').select_option('pie');reconcile('pie')
        page.locator('#shareType').select_option('doughnut')
        page.locator('#rankLimit').select_option('all')
        rank=page.evaluate('() => RevenueCharts.charts.rankChart.data.datasets[0].data.reduce((a,b)=>a+b,0)')
        assert abs(rank-result['totals']['total']/100)<.000001
        # Draft filter changes must not silently change the export selection.
        applied=page.evaluate('() => appliedQuery')
        page.locator('#start').fill('2026-08-10')
        assert page.evaluate('() => appliedQuery')==applied
        exported=page.request.get('http://127.0.0.1:'+str(server.effective_port)+'/api/export?'+applied)
        assert exported.status==200 and len(exported.text().splitlines())==85
        page.locator('#start').fill('2026-08-05');apply()
        # Pointer hover exposes actual values; expanded chart must render real pixels.
        location=page.evaluate('''() => {const c=RevenueCharts.charts.trendChart,e=c.getDatasetMeta(0).data[0],r=c.canvas.getBoundingClientRect();return {x:r.x+e.x,y:r.y+e.y};}''')
        page.mouse.move(location['x'],location['y']);page.wait_for_timeout(150)
        assert page.evaluate('() => RevenueCharts.charts.trendChart.tooltip.opacity')>0
        for id in ['trendChart','shareChart','rankChart','mixChart','scatterChart']:
            page.locator(f'[data-expand={id}]').click()
            expect(page.locator('#chartDialog')).to_be_visible()
            page.wait_for_timeout(100)
            pixels=page.locator('#expandedChart').evaluate('(c)=>{const p=c.getContext("2d").getImageData(0,0,c.width,c.height).data;let count=0;for(let i=3;i<p.length;i+=4)if(p[i])count++;return count;}')
            assert pixels>1000,(id,pixels)
            page.locator('#closeChart').click()
        # A zero-valued record is distinct from an empty selection.
        page.locator('#channelSummary').click();page.locator('#clearChannels').click();page.locator('#channelSearch').fill('9X Jalwa');page.locator('#selectVisible').click()
        page.locator('#datePreset').select_option('single');page.locator('#start').fill('2026-08-12');page.locator('#start').press('Tab')
        result=apply();assert len(result['rows'])==1 and result['totals']['total']==0,result;reconcile('single channel / zero day')
        page.locator('#channelSummary').click();page.locator('#clearChannels').click();result=apply();assert result['rows']==[];reconcile('no channels')
        expect(page.locator('#chartsEmpty')).to_be_visible()
        page.locator('#reset').click();expect(page.locator('#rowCount')).to_have_text('868 records')
        for preset,count in [('7',196),('30',840),('month',868)]:
            page.locator('#datePreset').select_option(preset);result=apply();assert len(result['rows'])==count;reconcile(preset+' date preset')
        for metric in ['views','impressions','ad','total']:
            page.locator('#trendMetric').select_option(metric)
            value=page.evaluate('() => RevenueCharts.charts.trendChart.data.datasets[0].data.reduce((a,b)=>a+b,0)')
            expected=result['totals'][metric]/(100 if metric in ['ad','total'] else 1)
            assert abs(value-expected)<.000001
        for width in [1440,768,390,320]:
            page.set_viewport_size({'width':width,'height':950})
            page.wait_for_timeout(200)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            page.screenshot(path=str(screens/f'analytics-{width}.png'),full_page=True)
            page.locator('#channelSummary').click()
            assert page.locator('.channel-menu').bounding_box()['width']<=width
            page.locator('#channelSummary').click()
        assert not errors,errors
        report={'passed':True,'checks':checks,'page_errors':errors,'viewports':[1440,768,390,320]}
        (screens/'analytics-validation.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        browser.close()
finally:
    server.close()
