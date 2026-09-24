"""Deterministic DIY insight audit using isolated synthetic data only."""
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
from werkzeug.security import generate_password_hash
from app import create_app
from insight_presets import install

data = ROOT / '.test-data' / secrets.token_hex(8)
app = create_app(data)
password = secrets.token_urlsafe(18)
with closing(sqlite3.connect(data / 'revenuelive.db')) as db, db:
    db.execute("INSERT INTO users(id,username,password,role) VALUES (1,'insight-test',?,'admin')", (generate_password_hash(password),))
    db.executemany('INSERT INTO channels(id,name) VALUES (?,?)', [(1,'Alpha'),(2,'Beta with a long channel name')])
    db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?)', [
        ('2026-09-20',1,100,10,10000,0,10000,'synthetic'),
        ('2026-09-20',2,100,20,15000,5000,20000,'synthetic'),
        ('2026-09-21',1,300,30,20000,0,20000,'synthetic'),
        ('2026-09-21',2,100,10,15000,5000,20000,'synthetic'),
        ('2026-09-23',1,0,0,0,0,0,'synthetic'),
        ('2026-09-23',2,0,0,5000,0,5000,'synthetic'),
    ])
assert install(data / 'revenuelive.db','insight-test') == 4
assert install(data / 'revenuelive.db','insight-test') == 0
server = create_server(app,host='127.0.0.1',port=0)
threading.Thread(target=server.run,daemon=True).start()
screens = ROOT / '.screenshots'
screens.mkdir(exist_ok=True)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:'+str(server.effective_port))
        page.locator('#loginForm [name=username]').fill('insight-test')
        page.locator('#loginForm [name=password]').fill(password)
        page.locator('#loginForm button.primary').click()
        page.locator('#shell').wait_for(state='visible')
        page.wait_for_function("()=>!!Chart.getChart('metricSpark-total')")
        assert page.evaluate("Chart.getChart('metricSpark-total').data.datasets[0].data")==[30000,40000,None,5000]
        assert page.evaluate("Chart.getChart('metricSpark-views').data.datasets[0].data")==[200,400,None,0]
        expect(page.locator('#insightsView')).to_be_hidden()
        page.locator('#accountMenu summary').click()
        page.locator('[data-view=insightsView]').click()
        expect(page.locator('#dashboard')).to_be_hidden()
        expect(page.locator('#revenueHeader')).to_be_visible()
        expect(page.locator('#quickInsights')).to_be_visible()
        page.wait_for_function("()=>document.getElementById('insightNote').textContent!== 'Comparing with the preceding period...'")
        assert page.locator('.metric-change').evaluate_all('nodes=>nodes.every(n=>n.hidden && !n.textContent)'), 'Incomplete comparison must be silent'
        assert page.locator('#insightList article').count()>0
        checks=page.evaluate("""()=>{
          const row=(day,id,views,ad,other=0)=>({day,channel_id:id,channel:id===1?'Alpha':'Beta',views,impressions:views/2,ad,other,total:ad+other});
          const q='start=2026-09-21&end=2026-09-21&channel=1&channel=2';
          const current={rows:[row('2026-09-21',1,200,20000),row('2026-09-21',2,200,20000)]};
          const previous={rows:[row('2026-09-20',1,100,10000),row('2026-09-20',2,100,20000)]};
          const insights=QuickInsights.build(current,q,previous,'ready');
          const partial=QuickInsights.build({rows:current.rows.slice(0,1)},q,previous,'ready');
          const negative=QuickInsights.build({rows:[row('2026-09-21',1,0,-100),row('2026-09-21',2,0,200)]},q,previous,'ready');
          const missing=QuickInsights.build(current,q,null,'unavailable');
          return {insights,partial,negative,missing,empty:QuickInsights.build({rows:[]},q)};
        }""")
        findings={row['id']:row for row in checks['insights']}
        assert '+33.3%' in findings['change-total']['evidence']
        assert findings['change-total']['kpi']['value']=='\u20b9400'
        assert [row['value'] for row in findings['change-total']['kpi']['pairs']]==[40000,30000]
        assert findings['change-total']['kpi']['badge']=='+33.3%'
        assert findings['gainer']['kpi']['channel']=='Alpha'
        assert '+100.0%' in findings['change-views']['evidence']
        assert '-33.3%' in findings['yield-change']['evidence']
        assert 'Alpha, Beta' in findings['leader']['evidence']
        assert '50.0%' in findings['leader']['evidence']
        assert 'coverage' in [row['id'] for row in checks['partial']]
        assert not any(row['id'].startswith('change-') for row in checks['partial'])
        assert 'negative' in [row['id'] for row in checks['negative']]
        assert not any(row['id'] in ['leader','mix','yield'] for row in checks['negative'])
        assert checks['missing'][0]['id']=='comparison'
        assert not checks['empty']
        matrix=page.evaluate("""()=>{
          let tested=0;
          for(const count of [1,2,5,28])for(const duration of [1,7,21])for(const mode of ['normal','equal','zero','negative','missing']){
            const current=[],previous=[];
            for(let day=1;day<=duration;day++)for(let id=1;id<=count;id++){
              const value=mode==='zero'?0:mode==='negative'&&id===1?-100:mode==='equal'?100:id*100+day;
              const row={channel_id:id,channel:'Channel '+id,views:100,impressions:50,ad:value,other:0,total:value};
              if(!(mode==='missing'&&day===1&&id===count))current.push({...row,day:'2026-08-'+String(day).padStart(2,'0')});
              previous.push({...row,day:'2026-07-'+String(31-duration+day).padStart(2,'0')});
            }
            const q='start=2026-08-01&end=2026-08-'+String(duration).padStart(2,'0')+Array.from({length:count},(_,i)=>'&channel='+(i+1)).join('');
            const result=QuickInsights.build({rows:current},q,{rows:previous},'ready'),ids=result.map(item=>item.id);
            const check=(condition,message)=>{if(!condition)throw new Error(JSON.stringify({count,duration,mode,message,ids}));};
            if(count===1){check(!ids.some(id=>['leader','concentration','pair-gap','gainer','decliner'].includes(id)),'single channel ranking');if(current.length)check(ids.includes('channel-summary'),'single channel summary');}
            if(mode==='missing'){check(!ids.includes('leader')&&!ids.includes('peak')&&!ids.some(id=>id.startsWith('change-')),'incomplete comparison');}
            if(mode==='equal'){check(!ids.includes('concentration'),'balanced concentration');if(duration>1)check(ids.includes('steady-days'),'flat daily revenue');if(count>1)check(result.find(item=>item.id==='leader').title.includes('tied'),'tied leader');check(!result.some(item=>item.title.includes('rose')),'flat yield rose');}
            if(mode==='zero')check(!ids.includes('leader')&&!ids.includes('yield')&&!ids.includes('peak'),'zero total division');
            if(mode==='negative')check(!ids.includes('leader')&&!ids.includes('mix')&&!ids.includes('yield-change'),'negative share');
            check(!JSON.stringify(result).includes('NaN')&&!JSON.stringify(result).includes('Infinity'),'invalid number');
            check(new Set(ids).size===ids.length,'duplicate insights');tested++;
          }
          return tested;
        }""")
        assert matrix==60
        expect(page.locator('#quickInsights button')).to_have_count(0)
        priorities=page.locator('#insightList article').evaluate_all('nodes=>nodes.map(node=>Number(node.dataset.priority))')
        assert priorities==sorted(priorities,reverse=True)
        expect(page.locator('#insightList article')).to_have_count(4)
        assert page.evaluate("()=>{const rows=QuickInsights.curate([{id:'coverage',priority:100},{id:'comparison',priority:90,evidence:'Incomplete prior period'},{id:'concentration',priority:84},{id:'leader',priority:80},{id:'yield-change',priority:85},{id:'yield',priority:40}]);return rows.length===3&&!rows.some(r=>['comparison','leader','yield'].includes(r.id));}")
        for width in [1440,944,390,320]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#quickInsights').screenshot(path=str(screens/f'quick-insights-{width}.png'))
        page.evaluate("async()=>{selectedChannels=new Set(['1']);document.getElementById('start').value='2026-09-21';document.getElementById('end').value='2026-09-21';await refresh();}")
        page.wait_for_function("()=>document.getElementById('insightNote').textContent!== 'Comparing with the preceding period...'")
        expect(page.locator('#insightScope')).to_contain_text('1 selected channel')
        expect(page.locator('#insightScope')).to_contain_text('21 Sept 2026')
        assert page.locator('.metric-spark').evaluate_all('nodes=>nodes.every(n=>n.hidden)'), 'Single-day cards must not show isolated dots'
        assert page.evaluate("!Chart.getChart('metricSpark-total')"), 'Single-day trend chart should be removed'
        expect(page.locator('#change-total')).to_have_text('+100%')
        assert not page.locator('#change-total').evaluate('node=>node.hidden')
        assert page.locator('#change-other').evaluate('node=>node.hidden')
        assert 'Beta' not in page.locator('#insightList').inner_text()
        expect(page.locator('[data-insight="change-total"] .insight-value')).to_have_text('\u20b9200')
        assert page.locator('#insightList .kpi-icon svg').count()==page.locator('#insightList article').count()
        for width in [1440,1024,390,320]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('production-kpi',width)
            assert page.locator('#insightList article').evaluate_all('nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth)'),width
            page.screenshot(path=str(screens/f'production-kpi-{width}.png'),full_page=True)
        page.evaluate("()=>{document.getElementById('end').value='2026-09-23';dirty();}")
        expect(page.locator('#insightList article')).to_have_count(0)
        page.wait_for_function("()=>document.getElementById('insightScope').textContent.includes('23 Sept 2026')")
        page.locator('#accountMenu summary').click()
        page.locator('[data-view=diyGraphs]').click()
        expect(page.locator('#diySaved option')).to_have_count(9)
        page.locator('#diyStart').click()
        page.evaluate("()=>{document.getElementById('diyStart')._flatpickr.close();}")
        for first,last in [('2026-09-23','2026-09-20'),('2026-09-20','2026-09-23'),('2026-09-21','2026-09-21')]:
            page.locator('#diyAllDates').click()
            page.evaluate("([first,last])=>{document.getElementById('diyStart')._flatpickr.setDate(first,true);document.getElementById('diyEnd')._flatpickr.setDate(last,true);}",[first,last])
            expect(page.locator('#diyStart')).to_have_value(min(first,last))
            expect(page.locator('#diyEnd')).to_have_value(max(first,last))
            assert 'must be' not in page.locator('#diyStatus').inner_text()
        page.locator('#diyAllDates').click()
        page.evaluate("()=>{document.getElementById('diyEnd')._flatpickr.setDate('2026-09-20',true);document.getElementById('diyStart')._flatpickr.setDate('2026-09-23',true);}")
        expect(page.locator('#diyStart')).to_have_value('2026-09-20')
        expect(page.locator('#diyEnd')).to_have_value('2026-09-23')
        page.locator('#diyAllDates').click()
        page.locator('#diySaved').select_option('insight-views')
        values=page.evaluate("(()=>{const c=Chart.getChart('diyCanvas');return {labels:c.data.labels,data:c.data.datasets.map(d=>d.data),axes:c.data.datasets.map(d=>d.yAxisID)};})()")
        assert values['data']==[[200,400,None,0],[300,400,None,50]],values
        assert values['axes']==['y','right'],values
        expect(page.locator('#diyData tbody tr').nth(1)).to_contain_text('+100.0%')
        expect(page.locator('#diyData tbody tr').nth(1)).to_contain_text('+33.3%')
        expect(page.locator('#diyData tbody tr').last).to_contain_text('N/A')
        for width in [1440,944,390]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(screens/f'insight-relation-{width}.png'),full_page=True)
        page.locator('#diySaved').select_option('insight-leader')
        assert page.evaluate("Chart.getChart('diyCanvas').data.datasets[0].data")==[200,200,None,50]
        expect(page.locator('#diyData tbody tr').first).to_contain_text('Beta with a long channel name')
        expect(page.locator('#diyData tbody tr').first).to_contain_text('66.7%')
        expect(page.locator('#diyData tbody tr').nth(1)).to_contain_text('Alpha, Beta')
        expect(page.locator('#diyData tbody tr').nth(1)).to_contain_text('50.0%')
        expect(page.locator('#diyData tbody tr').nth(2)).to_contain_text('No records')
        page.screenshot(path=str(screens/'insight-leader-mobile.png'),full_page=True)
        page.locator('#diyChannels summary').click()
        page.locator('#diyChannelOptions input').nth(1).uncheck()
        page.locator('#diyChannels summary').click()
        expect(page.locator('#diyData tbody tr').first).to_contain_text('Alpha')
        assert page.evaluate("Chart.getChart('diyCanvas').data.datasets[0].data")==[100,200,None,0]
        page.locator('#diyName').fill('Single channel daily leader')
        page.locator('#diySave').click()
        expect(page.locator('#diyStatus')).to_have_text('Preset saved.')
        page.locator('#diySaved').select_option(label='Single channel daily leader')
        expect(page.locator('#diyChannelOptions input:checked')).to_have_count(1)
        for value in ['insight-mix','insight-share']:
            page.locator('#diySaved').select_option(value)
            assert page.evaluate("!!Chart.getChart('diyCanvas')")
        with closing(sqlite3.connect(data / 'revenuelive.db')) as db, db:
            db.execute("UPDATE records SET ad=-30000,total=-30000 WHERE day='2026-09-20' AND channel_id=1")
        page.evaluate('window.DIYGraphs.load()')
        page.locator('#diySaved').select_option('insight-share')
        expect(page.locator('#diyStatus')).to_contain_text('Negative values')
        page.locator('#diySaved').select_option('insight-leader')
        assert page.evaluate("Chart.getChart('diyCanvas').data.datasets[0].data")[0]==-300
        assert not errors,errors
        page.evaluate("RevenueShare.render([{channel:'9X Tashan',day:'2026-09-21',views:100,impressions:50,ad:100,other:0,total:100},{channel:'Unknown Channel',day:'2026-09-21',views:10,impressions:5,ad:10,other:0,total:10}])")
        page.wait_for_function("()=>document.querySelector('.channel-brand[data-channel-name=\"9X Tashan\"] img')?.naturalWidth>0")
        assert page.locator('.channel-brand[data-channel-name="9X Tashan"]').first.evaluate("node=>node.style.backgroundColor==='rgb(24, 54, 77)'")
        expect(page.locator('.channel-brand[data-channel-name="Unknown Channel"]').first).to_have_text('UC')
        page.locator('.channel-brand[data-channel-name="9X Tashan"] img').first.evaluate("image=>image.dispatchEvent(new Event('error'))")
        expect(page.locator('.channel-brand[data-channel-name="9X Tashan"]').first).to_have_text('9T')
        page.evaluate("signOutView('')")
        assert page.evaluate("!Chart.getChart('metricSpark-total')")
        expect(page.locator('#insightList article')).to_have_count(0)
        expect(page.locator('#insightScope')).to_be_empty()
        print(json.dumps({'presets':4,'daily_totals':True,'separate_axes':True,'ties':True,'missing_dates':True,'zero_views':True,'negative_values':True,'scope':True,'saved_reload':True,'overflow':False,'errors':errors}))
        browser.close()
finally:
    server.close()
