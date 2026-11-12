"""Compare every rendered regional/city all-request count with a SQL union."""
import json,sys
from pathlib import Path
import duckdb
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
path=Path(sys.argv[1]).resolve()
con=duckdb.connect()
con.execute('CREATE TABLE members AS SELECT * FROM read_parquet(?)',[str(ROOT/'output/watch_hours/daily_tables/channel_ip_all_requests_daily.parquet')])
def expected(source,channels,city=False):
    fields=["coalesce(nullif(country,''),'Unknown')","coalesce(nullif(state,''),'Unknown')"]
    if city:fields.append("coalesce(nullif(city,''),'Unknown / NA')")
    where="source=? AND log_date='2026-11-11'";params=[source]
    if channels:where+=' AND channel_name IN ('+','.join('?' for _ in channels)+')';params+=channels
    rows=con.execute('SELECT '+','.join(fields)+",count(DISTINCT nullif(trim(cliIP),'')) FROM members WHERE "+where+' GROUP BY ALL',params).fetchall()
    return {' / '.join(r[:-1]):r[-1] for r in rows}

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(path.as_uri(),wait_until='load',timeout=180000)
    results={}
    cases=[('fast',[]),('stream',[]),('stream',['Weightlifting (dreamboat-ch01)']),('stream',['Weightlifting (dreamboat-ch01)','Veto VOD'])]
    for source,channels in cases:
        page.locator('#sourceSelect').select_option(source)
        page.evaluate('(channels)=>setChannelValues(channels)',channels)
        page.locator('#geoDeviceSection').scroll_into_view_if_needed()
        page.evaluate('renderGeoDevice()')
        result={}
        where="source=? AND log_date='2026-11-11'";params=[source]
        if channels:where+=' AND channel_name IN ('+','.join('?' for _ in channels)+')';params+=channels
        total=con.execute("SELECT count(DISTINCT nullif(trim(cliIP),'')) FROM members WHERE "+where,params).fetchone()[0]
        assert int(page.locator('#allRequestIpCard .kpi span').inner_text().replace(',',''))==total
        result['overall_card_verified']=total
        for table,city in [('geoTable',False),('cityTable',True)]:
            rows=page.locator('#'+table+' tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.cells,c=>c.textContent))')
            exp=expected(source,channels,city)
            actual={r[0]:int(r[5].split(' ')[0].replace(',','')) for r in rows}
            for key,count in actual.items():assert count==exp.get(key,0),(source,channels,table,key,count,exp.get(key))
            assert set(exp).issubset(actual),(table,'all-request-only location missing')
            result[table+'_rows_checked']=len(rows)
            if source=='stream' and len(channels)==1:
                result[table+'_examples']=[r for r in rows if r[0].startswith(('BD /','IN / West Bengal /')) or r[0]=='IN / West Bengal']
        results[source+'|'+','.join(channels)]=result
    page.evaluate("state.start='2026-11-10';renderGeoDevice()")
    assert 'Not Available' in page.locator('#geoTable').inner_text()
    results['pre_cutoff_guard']=True
    page.evaluate("state.start='2026-11-11';setChannelValues(['Weightlifting (dreamboat-ch01)']);renderGeoDevice()")
    page.locator('#geoTable').screenshot(path=str(path.with_suffix('.audit.png')))
    assert not errors,errors
    results['browser_errors']=errors
    path.with_suffix('.audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2));browser.close()
