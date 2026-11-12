"""All-request exact IP membership must include playlists/errors and union selections."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import duckdb
import pandas as pd

ROOT=Path(__file__).parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_all_request_extraction_and_browser_union(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'src/profile'))
    profile=load('all_ip_profile',ROOT/'src/profile/vglive_deep_profile.py')
    gen=load('all_ip_generator',ROOT/'src/dashboards/audienceOpsDashboard/generate_audience_ops.py')
    host=next(iter(profile.HOST_MAP))
    rows=[]
    for day,ip,path,status in [(10,'old','/a.ts','200'),(11,' same ','/a.m3u8','404'),(11,'same','/a.ts','200'),(11,'only-error','/other','500'),(11,'','/b.ts','200'),(11,None,'/b.ts','200'),(12,'same','/a.m3u8','200'),(12,'new','/a.ts','206')]:
        rows.append(dict(year=2026,month=11,day=day,source='stream',cliIP=ip,reqHost=host,reqPath=path,statusCode=status,reqTimeSec=0,UA='',country='BD',state='',city='',queryStr=''))
    con=duckdb.connect();con.register('lake_rows',pd.DataFrame(rows));profile.register_maps(con)
    out=tmp_path/'profile'
    profile.write_daily_tables(con,out,'TRUE',"'ts'","'mapped'",only_tables={'channel_ip_all_requests_daily'})
    membership=pd.read_parquet(tmp_path/'daily_tables/channel_ip_all_requests_daily.parquet')
    assert set(membership.log_date)=={'2026-11-11','2026-11-12'}
    assert set(membership.cliIP.dropna())=={'same','only-error','new'}
    # Same IP on another channel must still count once in a combined selection.
    extra=membership[(membership.log_date=='2026-11-11')&(membership.cliIP=='same')].copy()
    extra.channel_name='Second channel'
    extra.city='Dhaka'
    moved=extra.copy();moved.state='Second state';moved.city='Transit'
    membership.loc[membership.cliIP=='only-error','city']='Error-only city'
    pd.concat([membership,extra,moved],ignore_index=True).to_parquet(tmp_path/'daily_tables/channel_ip_all_requests_daily.parquet',index=False)
    payload=gen.build_all_request_ip_membership(tmp_path/'daily_tables','2026-11-12')
    geo_payload=gen.build_all_request_ip_membership(tmp_path/'daily_tables','2026-11-12',geography=True)
    assert 'only-error' not in json.dumps(payload)
    template=(ROOT/'src/dashboards/audienceOpsDashboard/template.html').read_text(encoding='utf-8')
    funcs=[]
    for name in ['addIsoDays','exactAllRequestIps','exactRegionalAllRequestIps']:
        funcs.append(re.search(r'^function '+name+r'\(.*?(?=^function |\Z)',template,re.M|re.S).group(0))
    js='\n'.join(funcs)+'\nconst assert=require("node:assert/strict");const payload='+json.dumps(payload)+';const gp='+json.dumps(geo_payload)+';\n'+'''
assert.equal(exactAllRequestIps(payload,'stream','2026-11-11','2026-11-11',[]).value,2);
assert.equal(exactAllRequestIps(payload,'stream','2026-11-11','2026-11-12',[]).value,3);
assert.equal(exactAllRequestIps(payload,'stream','2026-11-11','2026-11-12',['Second channel']).value,1);
assert.equal(exactAllRequestIps(payload,'stream','2026-11-11','2026-11-11',['absent']).value,0);
assert.equal(exactAllRequestIps(payload,'stream','2026-11-10','2026-11-11',[]).value,null);
assert.equal(exactAllRequestIps(payload,'stream','2026-11-11','2026-11-13',[]).value,null);
assert.equal(exactAllRequestIps(payload,'fast','2026-11-11','2026-11-11',[]).value,null);
const geo=exactRegionalAllRequestIps(gp,'stream','2026-11-11','2026-11-12',[]);
assert.equal(geo.regions.get('BD / Unknown'),3);
assert.equal(geo.regions.get('BD / Second state'),1);
assert.equal(geo.cities.get('BD / Unknown / Error-only city'),1);
assert.equal(geo.cities.get('BD / Unknown / Dhaka'),1);
assert.equal(exactRegionalAllRequestIps(gp,'stream','2026-11-11','2026-11-12',['Second channel']).regions.get('BD / Unknown'),1);
assert.equal(exactRegionalAllRequestIps(gp,'stream','2026-11-10','2026-11-12',[]).available,false);
assert.equal(exactRegionalAllRequestIps(gp,'stream','2026-11-11','2026-11-13',[]).available,false);
'''
    subprocess.run(['node','-e',js],check=True,capture_output=True,text=True)
