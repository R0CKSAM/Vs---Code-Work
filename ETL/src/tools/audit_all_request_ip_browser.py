"""Validate the visible all-request card against SQL distinct counts."""
import json,sys
from pathlib import Path
import duckdb
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
path=Path(sys.argv[1]).resolve()
con=duckdb.connect()
con.execute('CREATE TABLE members AS SELECT * FROM read_parquet(?)',[str(ROOT/'output/watch_hours/daily_tables/channel_ip_all_requests_daily.parquet')])
def expected(source,channels=None):
    sql="SELECT count(DISTINCT nullif(trim(cliIP),'')) FROM members WHERE source=? AND log_date='2026-11-11'"
    args=[source]
    if channels:sql+=' AND channel_name IN ('+','.join('?' for _ in channels)+')';args+=channels
    return con.execute(sql,args).fetchone()[0]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(path.as_uri(),wait_until='load',timeout=180000)
    results={}
    for source in ['fast','stream']:
        page.locator('#sourceSelect').select_option(source)
        page.locator('#startDate').fill('2026-11-11');page.locator('#startDate').blur()
        page.locator('#endDate').fill('2026-11-11');page.locator('#endDate').blur()
        page.wait_for_function("document.querySelector('#allRequestIpCard .kpi span').textContent !== 'Not Available'")
        number=int(page.locator('#allRequestIpCard .kpi span').inner_text().replace(',',''))
        assert number==expected(source),(source,number,expected(source))
        results[source+'_all_channels']=number
    page.locator('#channelToggle').click()
    page.locator('#channelMenu input[data-value="Weightlifting (dreamboat-ch01)"]').check()
    page.wait_for_function("state.channel!=='all'")
    number=int(page.locator('#allRequestIpCard .kpi span').inner_text().replace(',',''))
    assert number==expected('stream',['Weightlifting (dreamboat-ch01)'])
    results['stream_weightlifting']=number
    channels=['Weightlifting (dreamboat-ch01)','Veto VOD']
    page.evaluate('(channels)=>setChannelValues(channels)',channels)
    number=int(page.locator('#allRequestIpCard .kpi span').inner_text().replace(',',''))
    assert number==expected('stream',channels)
    results['two_channel_union']=number
    page.evaluate("state.platform='not-a-real-platform';renderAllRequestIps()")
    assert int(page.locator('#allRequestIpCard .kpi span').inner_text().replace(',',''))==number
    results['platform_ignored']=True
    page.evaluate("state.start='2026-11-10';renderAllRequestIps()")
    assert page.locator('#allRequestIpCard .kpi span').inner_text()=='Not Available'
    page.evaluate("state.start='2026-11-11';state.end='2026-11-12';renderAllRequestIps()")
    assert page.locator('#allRequestIpCard .kpi span').inner_text()=='Not Available'
    results['historical_and_missing_days_guarded']=True
    page.evaluate("state.start='2026-11-11';state.end='2026-11-11';state.platform='all';setChannelValues([]);renderAllRequestIps()")
    page.locator('#allRequestIpCard').scroll_into_view_if_needed()
    page.locator('#allRequestIpCard').screenshot(path=str(path.with_suffix('.audit.png')))
    assert not errors,errors
    results['browser_errors']=errors
    path.with_suffix('.audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
    browser.close()
