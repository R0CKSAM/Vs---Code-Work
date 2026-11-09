"""Current SmartVOD API audit: independent SQL/source checks and filter coverage."""
import csv,io,itertools,json,math,sqlite3,string,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from server import FIELDS,csv_bytes,connection
BASE='http://127.0.0.1:8766';checks=[]
def check(name,ok):
 assert ok,name
 checks.append(name)
def raw(path,b):
 with urlopen(Request(BASE+path,data=json.dumps(b).encode(),headers={'Content-Type':'application/json'}),timeout=120) as r:return r.read()
def api(path,b):return json.loads(raw(path,b))
meta=json.load(urlopen(BASE+'/api/meta'));day=meta['dates'][-1]
B=dict(start=day,end=day,timeStart='00:00',timeEnd='23:59',filters={})
con=sqlite3.connect(ROOT/'data'/meta['database']);con.row_factory=sqlite3.Row
anchor=dict(con.execute("SELECT * FROM events WHERE day=? AND device_id!='Unknown' AND cli_ip!='Unknown' LIMIT 1",[day]).fetchone())
def expected(body):
 clauses=['day>=?','day<=?'];args=[body['start'],body['end']]
 lo,hi=body['timeStart'],body['timeEnd']
 clauses.append('clock BETWEEN ? AND ?' if lo<=hi else '(clock>=? OR clock<=?)');args += [lo,hi]
 for f,vs in body['filters'].items():
  if vs:clauses.append('('+ ' OR '.join(f'{f}=?' for _ in vs)+')');args += vs
 w=' WHERE '+' AND '.join(clauses)
 row=dict(con.execute("SELECT count(*) records,coalesce(sum(hours),0) hours,coalesce(sum(delivered),0) delivered,coalesce(sum(segments),0) segments,count(DISTINCT nullif(device_id,'Unknown')) devices,count(DISTINCT nullif(cli_ip,'Unknown')) ips,count(DISTINCT nullif(video_key,'Unknown')) videos,sum(CASE WHEN device_id!='Unknown' THEN hours ELSE 0 END) device_hours,sum(CASE WHEN cli_ip!='Unknown' THEN hours ELSE 0 END) ip_hours FROM events"+w,args).fetchone())
 for f in ['device','ip']:
  count=row['devices' if f=='device' else 'ips'];row['average_'+f+'_minutes']=row[f+'_hours']*60/count if count else None
 return row

def reconcile(name,body):
 result=api('/api/query',body);truth=expected(body)
 for k in ['records','hours','delivered','segments','devices','ips','videos','average_device_minutes','average_ip_minutes']:
  a,b=result['kpi'][k],truth[k]
  check(name+' '+k,(a is None and b is None) or (a is not None and b is not None and math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-8)))
 check(name+' hourly sum',math.isclose(sum(r['hours'] for r in result['hourly']),truth['hours'],rel_tol=1e-8,abs_tol=1e-8))
 return result
baseline=reconcile('Baseline',B)
source=ROOT.parent/'output/exports'/f'vod_stream_query_events_{day}.csv'
if source.exists():
 count=0;hours=0
 with source.open(encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):count+=1;hours+=float(row['request_watch_hours'])
 check('Source CSV record reconciliation',count==baseline['kpi']['records'])
 check('Source CSV hours reconciliation',math.isclose(hours,baseline['kpi']['hours'],rel_tol=1e-8))
print('Baseline/source reconciliation passed',flush=True)
ascii_lower=str.maketrans(string.ascii_uppercase,string.ascii_lowercase)
for field in FIELDS:
 rows=[dict(r) for r in con.execute(f'SELECT {field} value,sum(segments) segments,sum(hours) hours FROM events WHERE day=? GROUP BY 1',[day])]
 for sort in ['segments','hours','alpha_asc','alpha_desc']:
  actual=api('/api/facet',{**B,'field':field,'sort':sort})
  ranked=sorted(rows,key=(lambda r:(r[sort],r['value'])) if sort in ['segments','hours'] else (lambda r:(r['value'].translate(ascii_lower),r['value'])),reverse=sort!='alpha_asc')
  check(field+' '+sort+' ordering',[r['value'] for r in actual['options']]==[r['value'] for r in ranked[:100]])
  check(field+' '+sort+' pagination flag',actual['more']==(len(rows)>100))
  if sort=='segments' and len(rows)>100:
   following=api('/api/facet',{**B,'field':field,'offset':100})['options']
   check(field+' second page no duplicates',not set(r['value'] for r in actual['options'])&set(r['value'] for r in following))
   check(field+' second page ordering',[r['value'] for r in following]==[r['value'] for r in ranked[100:200]])
 # A facet ignores its own selection while respecting the other selected field.
 other='device_id' if field!='device_id' else 'cli_ip'
 scoped={field:[anchor[field]],other:[anchor[other]]}
 a=api('/api/facet',{**B,'field':field,'filters':scoped})
 e=con.execute(f'SELECT {field},sum(segments) n FROM events WHERE day=? AND {other}=? GROUP BY 1 ORDER BY n DESC,1 DESC LIMIT 100',[day,anchor[other]]).fetchall()
 check(field+' self exclusion and cross-filtering',[r['value'] for r in a['options']]==[r[0] for r in e])
 for search in ['%','_']:
  a=api('/api/facet',{**B,'field':field,'search':search})['options']
  e=sorted([r for r in rows if search in r['value']],key=lambda r:(r['segments'],r['value']),reverse=True)
  check(field+' literal search '+search,[r['value'] for r in a]==[r['value'] for r in e[:100]])
 vals=[r['value'] for r in sorted(rows,key=lambda r:r['segments'],reverse=True)[:2]]
 reconcile(field+' multiselect OR',{**B,'filters':{field:vals}})
 print('Facet and multi-select passed:',field,flush=True)
for n,(a,b) in enumerate(itertools.combinations(FIELDS,2),1):
 reconcile('Pair '+a+'/'+b,{**B,'filters':{a:[anchor[a]],b:[anchor[b]]}})
 if n%10==0:print('Pair combinations passed:',n,flush=True)
reconcile('All eleven together',{**B,'filters':{f:[anchor[f]] for f in FIELDS}})
reconcile('Zero result',{**B,'filters':{'title':['__NO_SUCH_TITLE_AUDIT__']}})
reconcile('One inclusive minute',{**B,'timeStart':'09:00','timeEnd':'09:00'})
reconcile('Overnight window',{**B,'timeStart':'23:30','timeEnd':'00:30'})
reconcile('Two dates',{**B,'start':meta['dates'][-2]})
for basis in ['device_id','cli_ip']:
 q=api('/api/query',{**B,'identity_basis':basis})
 check(basis+' legacy average compatibility',q['kpi']['average_watch_minutes']==q['kpi']['average_device_minutes' if basis=='device_id' else 'average_ip_minutes'])
 value=baseline['explorers'][basis][0]['identity_value'];body={**B,'identity_basis':basis,'filters':{basis:[value]}}
 j=api('/api/journey',body);export=list(csv.DictReader(io.StringIO(raw('/api/journey-export',body).decode('utf-8-sig'))))
 check(basis+' journey sum',math.isclose(sum(r['hours'] for r in j['sessions']),expected(body)['hours'],rel_tol=1e-8))
 check(basis+' journey export identity',bool(export) and all(r['identity_basis']==basis and r['identity_value']==value for r in export))
 check(basis+' journey export minutes',math.isclose(sum(float(r['watch_minutes_estimated']) for r in export),sum(r['hours']*60 for r in j['sessions']),abs_tol=1e-4))
 for values in [[value,'__OTHER__'],['Unknown'],[]]:
  check(basis+' invalid/multiple identifiers not blended '+str(len(values)),not api('/api/journey',{**body,'filters':{basis:values}})['sessions'])
content_export=list(csv.DictReader(io.StringIO(raw('/api/export',B).decode('utf-8-sig'))))
check('Content CSV hours reconcile',math.isclose(sum(float(r['watch_hours_estimated']) for r in content_export),baseline['kpi']['hours'],rel_tol=1e-8))
check('Content CSV both average columns',all('average_device_minutes' in r and 'average_ip_minutes' in r for r in content_export))
check('CSV formula escaping',"'=1+1" in csv_bytes(['value'],[['=1+1']]).decode('utf-8-sig'))
invalid=[[],None,{**B,'start':'20261104'},{**B,'start':'2026-99-99'},{**B,'start':day,'end':'2020-01-01'},{**B,'timeStart':'25:00'},{**B,'filters':{'invalid':['x']}},{**B,'filters':{'title':[1]}},{**B,'identity_basis':'bad'}]
for i,body in enumerate(invalid):
 try:raw('/api/query',body);raise AssertionError('invalid accepted '+str(i))
 except HTTPError as e:check('Invalid request '+str(i)+' returns 400',e.code==400)
try:raw('/api/facet',{**B,'field':'title','filters':{'title':[1]}});raise AssertionError('invalid own facet accepted')
except HTTPError as e:check('Invalid own-facet values rejected',e.code==400)
with connection() as c:c.execute('SELECT 1')
try:c.execute('SELECT 1');raise AssertionError('Database connection remains open')
except sqlite3.ProgrammingError:check('Database connection closes deterministically',True)
con.close()
report={'passed':True,'checks':checks,'coverage':{'from':meta['dates'][0],'through':day,'dates':len(meta['dates']),'pairwise_combinations':55,'fields':len(FIELDS)}}
(ROOT/'audit/comprehensive_api.json').write_text(json.dumps(report,indent=2));print('PASS',len(checks),'API checks',flush=True)
