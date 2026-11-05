"""Independent CSV oracle for filter subsets, multi-select, facets and exports."""
import csv
import io
import itertools
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
BASE='http://127.0.0.1:8766'
FIELDS=['title','category','video_key','device_id','cli_ip','os','region','isp','device_type']
B=dict(start='2026-11-04',end='2026-11-04',timeStart='00:00',timeEnd='23:59',filters={})
report={'passed':False,'cases':0,'groups':{},'failures':[],'started':time.strftime('%Y-%m-%dT%H:%M:%S')}
def normalize(v):
    s=(v or '').strip()
    return 'Unknown' if s.lower() in ('','unknown','unknown / na','unknown / unmarked','na','n/a') else s
def post(path,b):
    with urlopen(Request(BASE+path,data=json.dumps(b).encode(),headers={'Content-Type':'application/json'}),timeout=60) as r:
        return r.read()
def get(path,b):return json.loads(post(path,b))
with (ROOT.parent/'data/asn/asnDecoded.csv').open(encoding='utf-8-sig',newline='') as f:
    providers={r['asn'].strip():r['as_name'].strip() for r in csv.DictReader(f) if normalize(r['as_name'])!='Unknown'}
rows=[]
with (ROOT.parent/'output/exports/vod_stream_query_events_2026-11-04.csv').open(encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        asn=normalize(r['asn'])
        rows.append(dict(title=normalize(r['content_title']),category=normalize(r['category_name']),video_key=normalize(r['content_code']),device_id=normalize(r['device_id']),cli_ip=normalize(r['cli_ip']),os=normalize(r['decoded_os']),region=' / '.join(normalize(r[k]) for k in ('country','state','city')),isp=f'{providers[asn]} · AS{asn}' if asn in providers else 'Unknown' if asn=='Unknown' else f'Unknown ISP · AS{asn}',device_type=normalize(r['decoded_form_factor']).lower(),day=r['log_date'],clock=r['minute_ist'][11:16],hours=float(r['request_watch_hours']),delivered=float(r['delivered_watch_hours']),segments=int(r['segment_count'])))
indexes={k:defaultdict(set) for k in FIELDS}
for i,r in enumerate(rows):
    for k in FIELDS:indexes[k][r[k]].add(i)
ALL=set(range(len(rows)))
def selected(b,omit=None):
    result=None
    for k,vs in b['filters'].items():
        if k==omit or not vs:continue
        union=set().union(*(indexes[k].get(v,set()) for v in vs))
        result=union if result is None else result&union
    result=ALL if result is None else result
    lo,hi=b['timeStart'],b['timeEnd']
    return [rows[i] for i in sorted(result) if b['start']<=rows[i]['day']<=b['end'] and
            (lo<=rows[i]['clock']<=hi if lo<=hi else rows[i]['clock']>=lo or rows[i]['clock']<=hi)]
def near(a,b):return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-7)
def verify(name,b,group):
    expected=selected(b);actual=get('/api/query',b)
    k=actual['kpi']
    assert k['records']==len(expected),(name,'records',k['records'],len(expected))
    for key in ('hours','delivered','segments'):
        assert near(k[key],sum(r[key] for r in expected)),(name,key)
    for metric,col in [('ips','cli_ip'),('devices','device_id'),('videos','video_key')]:
        assert k[metric]==len({r[col] for r in expected if r[col]!='Unknown'}),(name,metric)
    hourly=defaultdict(float)
    for r in expected:hourly[r['clock'][:2]]+=r['hours']
    assert set(hourly)=={r['hour'] for r in actual['hourly']},(name,'hour buckets')
    assert all(near(r['hours'],hourly[r['hour']]) for r in actual['hourly']),(name,'hour totals')
    for field,groups in actual['breakdown'].items():
        sums=defaultdict(float)
        for r in expected:sums[r[field]]+=r['hours']
        assert len(groups)==min(5,len(sums)),(name,'breakdown size',field)
        assert all(near(r['hours'],sums[r['label']]) for r in groups),(name,'breakdown',field)
    grouped=defaultdict(list)
    for r in expected:grouped[(r['video_key'],r['title'])].append(r)
    assert len(actual['table'])==min(100,len(grouped)),(name,'table count')
    for entry in actual['table']:
        rs=grouped[(entry['video_key'],entry['title'])]
        assert near(entry['hours'],sum(r['hours'] for r in rs)),(name,'table hours')
        assert entry['ips']==len({r['cli_ip'] for r in rs if r['cli_ip']!='Unknown'}),(name,'table IPs')
        assert entry['devices']==len({r['device_id'] for r in rs if r['device_id']!='Unknown'}),(name,'table devices')
    report['cases']+=1;report['groups'][group]=report['groups'].get(group,0)+1

try:
    anchor=next(r for r in rows if all(r[k] not in ('Unknown','unknown') for k in FIELDS))
    for n in range(1,10):
        for fields in itertools.combinations(FIELDS,n):
            verify('subset:'+','.join(fields),{**B,'filters':{k:[anchor[k]] for k in fields}},'all_nonempty_dimension_subsets')
        print('Verified subsets with',n,'filters;',report['cases'],'cases',flush=True)
    rng=random.Random(20261105)
    for fields in itertools.combinations(FIELDS,2):
        sample=rng.sample(rows,3)
        verify('multi pair:'+','.join(fields),{**B,'filters':{k:list({r[k] for r in sample}) for k in fields}},'all_multiselect_field_pairs')
    for i in range(80):
        fields=rng.sample(FIELDS,rng.randint(1,9));sample=rng.sample(rows,rng.randint(1,4))
        verify('random:'+str(i),{**B,'filters':{k:list({r[k] for r in sample}) for k in fields},'timeStart':rng.choice(['00:00','12:00','23:00']),'timeEnd':rng.choice(['23:59','12:30','01:00'])},'random_multiselect_and_time')
    for field in FIELDS:
        verify('unknown:'+field,{**B,'filters':{field:['unknown' if field=='device_type' else 'Unknown']}},'unknown_values')
        verify('absent:'+field,{**B,'filters':{field:["not-real-' OR 1=1 --"]}},'absent_and_literal_sql_values')
    for lo,hi in [('00:00','00:00'),('23:59','23:59'),('12:15','12:15'),('00:00','23:59'),('23:59','00:00')]:
        verify('time:'+lo+hi,{**B,'timeStart':lo,'timeEnd':hi},'time_boundaries')
    for start,end in [('2026-11-03','2026-11-05'),('2026-11-03','2026-11-03'),('2026-11-05','2026-11-05')]:
        verify('dates:'+start+end,{**B,'start':start,'end':end},'date_coverage')
    for field in FIELDS:
        b={**B,'filters':{k:[anchor[k]] for k in FIELDS}}
        facet=get('/api/facet',{**b,'field':field,'search':''})
        weights=defaultdict(int)
        for row in selected(b,omit=field):weights[row[field]]+=row['segments']
        expected=sorted(weights,key=lambda value:(weights[value],value),reverse=True)
        assert [r['value'] for r in facet['options']]==expected[:100],('cascade self exclusion',field)
        report['cases']+=1
    for field in ('video_key','device_id','cli_ip'):
        first=get('/api/facet',{**B,'field':field,'search':'','offset':0})
        second=get('/api/facet',{**B,'field':field,'search':'','offset':100})
        vals=sorted(indexes[field],key=lambda value:(sum(rows[i]['segments'] for i in indexes[field][value]),value),reverse=True)
        assert [r['value'] for r in first['options']]==vals[:100]
        assert [r['value'] for r in second['options']]==vals[100:200]
        assert first['more'] is True
        for search in [vals[-1],'%','_',"'",'zzzz_absent']:
            found=get('/api/facet',{**B,'field':field,'search':search})
            assert [r['value'] for r in found['options']]==[v for v in vals if search.lower() in v.lower()][:100],(field,'search',search)
            report['cases']+=1
    for b in [B,{**B,'filters':{k:[anchor[k]] for k in FIELDS}},{**B,'filters':{'video_key':['absent']}},{**B,'timeStart':'23:00','timeEnd':'01:00'}]:
        export=list(csv.DictReader(io.StringIO(post('/api/export',b).decode('utf-8-sig'))))
        rs=selected(b)
        assert near(sum(float(r['watch_hours_estimated']) for r in export),sum(r['hours'] for r in rs))
        assert near(sum(float(r['delivered_hours_estimated']) for r in export),sum(r['delivered'] for r in rs))
        report['cases']+=1
    for invalid in [{**B,'start':'2026-11-06'},{**B,'timeStart':'25:00'},{**B,'filters':{'invalid':['a']}},{**B,'filters':{'os':'Android'}},{**B,'filters':{'os':[None]}}]:
        try:post('/api/query',invalid);raise AssertionError('Invalid input accepted')
        except HTTPError as e:assert e.code==400
        report['cases']+=1
    report['passed']=True
finally:
    report['finished']=time.strftime('%Y-%m-%dT%H:%M:%S')
    (ROOT/'audit/combinations.json').write_text(json.dumps(report,indent=2))
print('PASS',report['cases'],'data combination checks',flush=True)
