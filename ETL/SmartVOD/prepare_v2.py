"""Build a private database version; atomically publish its manifest on success."""
import argparse,csv,json,sqlite3,shutil,os,io
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import parse_qs
ROOT=Path(__file__).resolve().parent
ETL=ROOT.parent
SCHEMA=4

def status_code(value):
    try:
        number=float(str(value or '').strip())
        if number.is_integer() and 100<=number<=599:return str(int(number))
    except ValueError:pass
    return 'Unknown'
def clean(v):
    v=(v or '').strip()
    return v if v.lower() not in ('','null','undefined','unknown','unknown / na','unknown / unmarked','na','n/a') else 'Unknown'
def identity(r):
    if clean(r.get('device_id'))=='Unknown':return 'Missing Device ID'
    if r.get('identity_source')=='same_cli_manifest':return 'Manifest-inferred Device ID'
    direct=parse_qs(r.get('query_string','').lstrip('?')).get('device_id',[''])[0]
    return 'Direct Device ID' if r.get('identity_source')=='segment_query' and direct==r.get('device_id') else 'Unverified Device ID'
def publish(dates,incremental=False):
    folder=ROOT/'data';folder.mkdir(exist_ok=True)
    lock=(folder/'refresh.lock').open('a+')
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write('0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _publish(dates,incremental,folder)
    finally:lock.close()
def _publish(dates,incremental,folder):
    prev=json.loads((folder/'manifest.json').read_text()) if (folder/'manifest.json').exists() else {}
    compatible=incremental and prev.get('schema')==SCHEMA
    paths={d:ETL/'output/exports'/f'vod_stream_query_events_{d}.csv' for d in dates}
    for d,p in list(paths.items()):
        if not p.exists():paths[d]=folder/'sources'/p.name
        if not paths[d].is_file():raise FileNotFoundError(paths[d])
    signatures={d:dict(path=str(p),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for d,p in paths.items()}
    changed=[d for d in dates if not compatible or prev.get('inputs',{}).get(d)!=signatures[d]]
    asn=ETL/'data/asn/asnDecoded.csv';asn_sig=dict(size=asn.stat().st_size,mtime_ns=asn.stat().st_mtime_ns)
    overrides=ROOT/'title_overrides.csv';override_rows=list(csv.DictReader(io.StringIO(overrides.read_text(encoding='utf-8-sig')))) if overrides.exists() else [];override_text=json.dumps(override_rows,sort_keys=True) if override_rows else ''
    if compatible and not changed and prev.get('asn_signature')==asn_sig and prev.get('overrides')==override_text:
        print('No changed completed exports; snapshot retained.',flush=True);return prev
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f');db=folder/f'smartvod_{stamp}.sqlite'
    if compatible:shutil.copy2(folder/prev['database'],db)
    con=sqlite3.connect(db);con.execute('PRAGMA journal_mode=OFF');con.execute('PRAGMA synchronous=OFF')
    if not compatible:con.execute('CREATE TABLE events(day TEXT,clock TEXT,title TEXT,category TEXT,video_key TEXT,device_id TEXT,cli_ip TEXT,os TEXT,region TEXT,isp TEXT,device_type TEXT,hours REAL,delivered REAL,segments INTEGER,request_ist TEXT,last_request_ist TEXT,req_host TEXT,session_id TEXT,identity_source TEXT,identity_confidence TEXT,raw_title TEXT,title_status TEXT,asn TEXT,mapping_evidence INTEGER,status_code TEXT)')
    for day in changed:
        con.execute('DELETE FROM events WHERE day=?',[day]);before=paths[day].stat();batch=[]
        with paths[day].open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['log_date']!=day:raise ValueError('Source date mismatch')
                title=clean(r['content_title'])
                batch.append((day,r['minute_ist'][11:16],title,clean(r['category_name']),clean(r['content_code']),clean(r['device_id']),clean(r['cli_ip']),clean(r['decoded_os']),' / '.join(clean(r.get(k)) for k in ('country','state','city')),'Unknown',clean(r['decoded_form_factor']).lower(),float(r.get('request_watch_hours') or 0),float(r.get('delivered_watch_hours') or 0),int(r.get('segment_count') or 1),r['request_ist'],r.get('last_request_ist') or r['request_ist'],r['req_host'].lower(),r.get('session_id',''),r.get('identity_source','unavailable'),identity(r),title,'Pending',clean(r.get('asn')),int(r.get('content_mapping_evidence') or 0),status_code(r.get('status_code'))))
                if len(batch)==5000:con.executemany('INSERT INTO events VALUES ('+','.join(['?']*25)+')',batch);batch=[]
            if batch:con.executemany('INSERT INTO events VALUES ('+','.join(['?']*25)+')',batch)
        after=paths[day].stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Source changed during import')
        con.commit();print('Imported',day,flush=True)
    con.execute('CREATE TABLE IF NOT EXISTS isp_lookup(asn TEXT PRIMARY KEY,name TEXT)');con.execute('DELETE FROM isp_lookup')
    with asn.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if clean(r.get('as_name'))!='Unknown':con.execute('INSERT OR REPLACE INTO isp_lookup VALUES (?,?)',[r['asn'].strip(),r['as_name'].strip()])
    con.execute("UPDATE events SET isp=CASE WHEN asn='Unknown' THEN 'Unknown' ELSE coalesce((SELECT name FROM isp_lookup WHERE isp_lookup.asn=events.asn),'Unknown ISP') || ' · AS' || asn END")
    con.execute('CREATE TABLE IF NOT EXISTS titles(host TEXT,video_key TEXT,title TEXT,status TEXT,variants INTEGER,PRIMARY KEY(host,video_key))');con.execute('DELETE FROM titles')
    groups={}
    for host,key,title,weight,evidence in con.execute("SELECT req_host,video_key,raw_title,sum(segments),max(mapping_evidence) FROM events WHERE raw_title!='Unknown' GROUP BY 1,2,3"):
        groups.setdefault((host,key),[]).append((title,weight,evidence))
    review=[]
    for (host,key),values in groups.items():
        ranked=sorted(values,key=lambda v:(v[2]>0,v[1],v[0]),reverse=True)
        status='Conflicting log titles' if len(values)>1 else 'Consistent log title' if ranked[0][2]>0 else 'Unverified log title'
        con.execute('INSERT INTO titles VALUES (?,?,?,?,?)',[host,key,ranked[0][0],status,len(values)])
        if status!='Consistent log title':review.append(dict(host=host,video_key=key,selected_title=ranked[0][0],status=status,variants=values))
    if overrides.exists():
        with overrides.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if not all(r.get(k,'').strip() for k in ('host','video_key','title','evidence')):raise ValueError('Title overrides require host, video_key, title and evidence')
                con.execute('INSERT OR REPLACE INTO titles VALUES (?,?,?,?,?)',[r['host'].strip().lower(),r['video_key'].strip(),r['title'].strip(),'Verified override',1])
    con.execute("UPDATE events SET title=coalesce((SELECT title FROM titles WHERE host=events.req_host AND titles.video_key=events.video_key),'Unknown'),title_status=coalesce((SELECT status FROM titles WHERE host=events.req_host AND titles.video_key=events.video_key),'Unknown title')")
    for key in ('day','video_key','device_id','cli_ip','os','isp','region','title','category','device_type','identity_confidence','title_status'):
        con.execute(f'CREATE INDEX IF NOT EXISTS idx_{key} ON events({key})')
    con.execute('CREATE INDEX IF NOT EXISTS idx_device_day ON events(device_id,day)')
    stats=con.execute('SELECT count(*),sum(hours),sum(segments) FROM events').fetchone()
    dates=[r[0] for r in con.execute('SELECT DISTINCT day FROM events ORDER BY day')]
    quality=dict(con.execute('SELECT title_status,count(*) FROM events GROUP BY title_status'))
    confidence=dict(con.execute('SELECT identity_confidence,count(*) FROM events GROUP BY identity_confidence'))
    con.commit();con.close()
    review_path=folder/f'title_review_{stamp}.json';review_path.write_text(json.dumps(review,indent=2),encoding='utf-8')
    manifest=dict(schema=SCHEMA,database=db.name,dates=dates,records=stats[0],hours=stats[1],segments=stats[2],built_at=datetime.now().isoformat(),inputs={**(prev.get('inputs',{}) if compatible else {}),**signatures},timezone='Asia/Kolkata',title_quality=quality,identity_confidence=confidence,title_review=review_path.name,asn_signature=asn_sig,overrides=override_text)
    tmp=folder/'manifest.tmp.json';tmp.write_text(json.dumps(manifest,indent=2),encoding='utf-8');tmp.replace(folder/'manifest.json')
    # Keep current and previous version; a locked in-flight reader is left intact.
    versions=sorted(folder.glob('smartvod_*.sqlite'),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in versions[2:]:
        if old.name==db.name:continue
        try:old.unlink()
        except OSError:pass
    print('Published',len(dates),'days',stats[0],'records',flush=True)
    try:
        from insight_store import build
        build(ROOT)
    except Exception as exc:print('Analysis acceleration was not refreshed:',str(exc),flush=True)
    return manifest
def main():
    p=argparse.ArgumentParser();p.add_argument('--date',action='append');p.add_argument('--history-days',type=int);p.add_argument('--incremental',action='store_true');a=p.parse_args();dates=sorted(set(a.date or []))
    if a.history_days:
        available=sorted(x.stem[-10:] for x in (ETL/'output/exports').glob('vod_stream_query_events_????-??-??.csv'))
        cutoff=(datetime.fromisoformat(available[-1])-timedelta(days=a.history_days-1)).date().isoformat();dates=[d for d in available if d>=cutoff]
    if not dates:p.error('Provide --date or --history-days')
    publish(dates,a.incremental)
if __name__=='__main__':main()
