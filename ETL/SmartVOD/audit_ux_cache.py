"""Cache isolation and invalidation using disposable SQLite fixtures."""
from pathlib import Path
from contextlib import contextmanager
import json,os,sqlite3,sys,tempfile
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import server
meta=json.loads((ROOT/'data/manifest.json').read_text())
source=sqlite3.connect(ROOT/'data'/meta['database']);source.row_factory=sqlite3.Row
schema=source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='events'").fetchone()[0]
row=dict(source.execute("SELECT * FROM events WHERE day=? AND device_id!='Unknown' LIMIT 1",[meta['dates'][-1]]).fetchone());source.close()
checks=[]
def check(name,ok):
 assert ok,name
 checks.append(name)
with tempfile.TemporaryDirectory(prefix='smartvod_cache_audit_') as temp:
 paths=[Path(temp)/'v1.sqlite',Path(temp)/'v2.sqlite']
 for path,hours in zip(paths,[1.0,3.0]):
  con=sqlite3.connect(path);con.execute(schema)
  for name,cols in [('idx_day','day'),('idx_device_day','device_id,day'),('idx_cli_ip','cli_ip')]:con.execute(f'CREATE INDEX {name} ON events({cols})')
  values={**row,'hours':hours,'delivered':hours}
  con.execute('INSERT INTO events('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()));con.commit();con.close()
 active=paths[0];statements=[]
 @contextmanager
 def fixture():
  con=sqlite3.connect(active);con.row_factory=sqlite3.Row;con.set_trace_callback(statements.append)
  try:yield con
  finally:con.close()
 server.connection=fixture;server.QUERY_CACHE.clear()
 body=dict(start=row['day'],end=row['day'],timeStart='00:00',timeEnd='23:59',filters={})
 first=server.query(body);check('Cold result correct',first['kpi']['hours']==1)
 statements.clear();first['kpi']['hours']=999
 again=server.query(body)
 check('Cached response cannot be mutated by callers',again['kpi']['hours']==1)
 check('Warm query avoids event scans',not any('FROM events' in s for s in statements))
 none=server.query({**body,'filters':{'title':['__NO_MATCH__']}})
 check('Cache keys isolate filters',none['kpi']['records']==0 and server.query(body)['kpi']['records']==1)
 active=paths[1];check('New snapshot invalidates old cache',server.query(body)['kpi']['hours']==3)
 con=sqlite3.connect(active);con.execute('UPDATE events SET hours=5,delivered=5');con.commit();con.close()
 stat=active.stat();os.utime(active,ns=(stat.st_atime_ns,stat.st_mtime_ns+10000000))
 check('Changed file fingerprint invalidates cache',server.query(body)['kpi']['hours']==5)
 for i in range(10):server.query({**body,'timeStart':f'00:{i:02d}'})
 check('Cache remains bounded',len(server.QUERY_CACHE)<=server.QUERY_CACHE_LIMIT==8)
(ROOT/'audit/ux_cache.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',len(checks),'cache checks')
