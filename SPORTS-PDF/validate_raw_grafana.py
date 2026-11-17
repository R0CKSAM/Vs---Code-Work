"""Resumable local GZIP audit and exact raw-log aggregates for Grafana parity.

No ETL jobs, lake writes, log deletion, network access or credentials.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
import gzip,hashlib,json,os,re,time,traceback
from pathlib import Path
from functools import lru_cache
from urllib.parse import parse_qs,unquote
import orjson

VERSION=1
PATTERN=re.compile(r'[-_](\d+)\.ts$')
MASTERS=('main.m3u8','satsangmaster.m3u8','sanskarmaster.m3u8','index.m3u8','shubhmaster.m3u8','playlist.m3u8','master.m3u8')
COLS=('time_us','host','ip','device','session','ip_ua','country','state','city','status','bytes','is_ts','eligible_ts','master','line_hash')

@lru_cache(maxsize=65536)
def query_ids(rawquery):
    if '=' not in rawquery and '%3d' in rawquery.lower():rawquery=unquote(rawquery)
    q=parse_qs(rawquery.lstrip('?'),keep_blank_values=True)
    return next(iter(q.get('device_id',q.get('deviceid',['']))),''),next(iter(q.get('session_id',q.get('sessionid',['']))),'')

@lru_cache(maxsize=100000)
def ip_ua_key(ip,ua):return hashlib.blake2b(orjson.dumps([ip,ua]),digest_size=16).digest()

def atomic(path,data):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8');tmp.replace(path)

def stamp():return datetime.now(timezone.utc).isoformat()

def parse_record(r,raw):
    try:t=float(r['reqTimeSec']);time_us=round(t*1_000_000)
    except (ValueError,TypeError,KeyError,OverflowError):raise ValueError('Missing/invalid reqTimeSec')
    if not 946684800000000<=time_us<=4102444800000000:raise ValueError('reqTimeSec outside supported range')
    def string(k):return '' if r.get(k) is None else str(r[k])
    def integer(k):
        try:return int(r.get(k) or 0)
        except (ValueError,TypeError):raise ValueError('Invalid numeric '+k)
    path=string('reqPath');is_ts=path.endswith('.ts');status=integer('statusCode');eligible=is_ts and status in (200,206) and PATTERN.search(path) is not None
    rawquery=string('queryStr');dev=ses=''
    if 'device' in rawquery.lower() or 'session' in rawquery.lower():
        dev,ses=query_ids(rawquery)
    ip=string('cliIP');ua=string('UA')
    pair=ip_ua_key(ip,ua)
    return (time_us,string('reqHost'),ip,dev,ses,pair,string('country'),string('state'),string('city'),status,integer('bytes'),is_ts,eligible,'.m3u8' in path and any(x in path for x in MASTERS),hashlib.blake2b(raw.rstrip(b'\r\n'),digest_size=16).digest())

def schema():
    import pyarrow as pa
    return pa.schema([(k,pa.int64() if k in ('time_us','bytes') else pa.int32() if k=='status' else pa.bool_() if k in ('is_ts','eligible_ts','master') else pa.binary(16) if k in ('ip_ua','line_hash') else pa.string()) for k in COLS])

def process_chunk(task):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x00004000)
    chunk,files,base,digest=task;base=Path(base);part=base/f'part_{chunk:06}.parquet';receipt=base/f'part_{chunk:06}.json'
    if part.exists() and receipt.exists():
        old=json.loads(receipt.read_text())
        if old.get('digest')==digest and old.get('version')==VERSION and old.get('errors',0)==0:return old
    tmp=part.with_suffix('.parquet.tmp');sch=schema();writer=pq.ParquetWriter(tmp,sch,compression='zstd',compression_level=1)
    values=[[] for _ in COLS];stats={'chunk':chunk,'files':len(files),'rows':0,'blank_lines':0,'errors':0,'bad_files':[],'bad_rows':0,'digest':digest,'version':VERSION,'min_us':None,'max_us':None}
    def flush():
        if not values[0]:return
        table=pa.Table.from_arrays([pa.array(v,type=f.type) for v,f in zip(values,sch)],schema=sch);writer.write_table(table,row_group_size=50000)
        for v in values:v.clear()
    try:
        for filename,size,mtime in files:
            st=os.stat(filename)
            if st.st_size!=size or st.st_mtime_ns!=mtime:raise RuntimeError('Source file changed during scan: '+filename)
            try:
                with gzip.open(filename,'rb') as f:
                    for raw in f:
                        if not raw.strip():stats['blank_lines']+=1;continue
                        try:
                            obj=orjson.loads(raw)
                            if not isinstance(obj,dict):raise ValueError('Expected NDJSON object')
                            row=parse_record(obj,raw)
                        except (orjson.JSONDecodeError,ValueError,TypeError,OverflowError):stats['bad_rows']+=1;continue
                        for v,item in zip(values,row):v.append(item)
                        stats['rows']+=1;t=row[0];stats['min_us']=t if stats['min_us'] is None else min(t,stats['min_us']);stats['max_us']=t if stats['max_us'] is None else max(t,stats['max_us'])
                        if len(values[0])>=50000:flush()
                after=os.stat(filename)
                if after.st_size!=size or after.st_mtime_ns!=mtime:raise RuntimeError('Source file changed during scan: '+filename)
            except (OSError,EOFError) as e:
                stats['errors']+=1
                if len(stats['bad_files'])<10:stats['bad_files'].append({'file':Path(filename).name,'error':type(e).__name__})
        flush();writer.close();tmp.replace(part);atomic(receipt,stats);return stats
    finally:
        writer.close()

def epoch_us(s):return round(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1_000_000)

def aggregate(parts,out,date):
    import duckdb
    c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='3GB'");c.execute("SET TimeZone='UTC'");scratch=out/'scratch';scratch.mkdir(exist_ok=True);c.execute("SET temp_directory='"+str(scratch).replace('\\','/').replace("'","''")+"'")
    folders=parts if isinstance(parts,list) else [parts]
    c.read_parquet([str(folder/'part_*.parquet') for folder in folders]).create_view('r')
    def q(sql):
        x=c.execute(sql);names=[d[0] for d in x.description];return [dict(zip(names,row)) for row in x.fetchall()]
    start=epoch_us(date+'T00:00:00+05:30');end=start+86400_000000
    utc=epoch_us(date+'T00:00:00Z')
    metrics="""count(*) AS raw_rows,count(distinct line_hash) AS distinct_raw_lines,
      count(distinct ip) AS users_including_blank,count(distinct ip) filter(where trim(ip) NOT IN ('','-')) AS users_nonblank,
      count(distinct ip) filter(where is_ts) AS users_all_ts,count(distinct ip) filter(where eligible_ts) AS users_eligible_ts,
      count(distinct device) AS device_ids_including_blank,count(distinct device) filter(where device NOT IN ('','-','null','none','unknown')) AS device_ids_nonblank,
      count(distinct session) AS session_ids_including_blank,count(distinct session) filter(where session NOT IN ('','-','null','none','unknown')) AS session_ids_nonblank,
      count(distinct ip_ua) AS ip_ua_pairs,count(*) filter(where master) AS master_manifest_requests,
      count(*) filter(where is_ts) AS ts_all_status,count(*) filter(where eligible_ts) AS ts_eligible,
      count(*) filter(where eligible_ts)*0.6/3600 AS hours_0_6,count(*) filter(where eligible_ts)*6.0/3600 AS hours_6,
      coalesce(sum(bytes) filter(where is_ts and status IN (200,206)),0) AS video_bytes,
      min(time_us) AS min_us,max(time_us) AS max_us"""
    windows={
        'target_full_ist_day':(start,end),
        'covered_ist_day_from_utc_midnight':(utc,end),
        'utc_day':(utc,utc+86400_000000),
    }
    summary={'createdAt':stamp(),'dateIST':date,'definitions':{'hours':'Eligible TS requests * seconds / 3600; 0.6s and 6s both reported.','eligible_ts':"reqPath ends .ts, status 200/206, regex [-_](digits).ts at end; raw path is not URL-decoded.",'identifiers':'Device/session query parameters decoded once; counts with and without blanks provided. Grafana uniq() is approximate; these local counts are exact.','duplicates':'Exact repeated NDJSON lines are detected but NOT removed.','master':'Request path contains one of the master-manifest names in the existing exporter.'},'windows':{}}
    for name,(lo,hi) in windows.items():
        print('Aggregating '+name,flush=True);where=f' WHERE time_us>={lo} AND time_us<{hi}'
        summary['windows'][name]={'fromUtc':datetime.fromtimestamp(lo/1e6,timezone.utc).isoformat(),'toUtcExclusive':datetime.fromtimestamp(hi/1e6,timezone.utc).isoformat(),'metrics':q('SELECT '+metrics+' FROM r'+where)[0]}
    summary['hourly_utc']=q("SELECT strftime(to_timestamp(time_us/1000000.0),'%Y-%m-%dT%H:00:00Z') AS hour_utc,count(*) AS requests,count(*) filter(where eligible_ts) AS ts_eligible FROM r GROUP BY 1 ORDER BY 1")
    summary['hosts']=q(f'SELECT host,count(*) AS requests,count(distinct ip) AS users,count(*) filter(where eligible_ts) AS ts_eligible FROM r WHERE time_us>={start} AND time_us<{end} GROUP BY 1 ORDER BY requests DESC')
    summary['http_status']=q('SELECT status,count(*) AS requests FROM r GROUP BY 1 ORDER BY 1')
    atomic(out/'local_summary.json',summary)
    import csv
    for key in ['hourly_utc','hosts','http_status']:
        rows=summary[key]
        if rows:
            with (out/(key+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    c.close();return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,action='append',required=True);p.add_argument('--date',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--max-minutes',type=float,default=15);p.add_argument('--chunk-files',type=int,default=1000);a=p.parse_args()
    datetime.strptime(a.date,'%Y-%m-%d');out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);parts=out/'parts';parts.mkdir(exist_ok=True)
    roots=[x.resolve() for x in a.folder]
    if len(set(roots))!=len(roots):raise ValueError('Duplicate source folder')
    if any(out==x or out in x.parents or x in out.parents for x in roots):raise ValueError('Keep output separate from input folders')
    if not 1<=a.workers<=8 or a.chunk_files<1 or a.max_minutes<=0:raise ValueError('Invalid worker, chunk or time limit')
    started=time.monotonic();print('INVENTORY: '+', '.join(map(str,roots)),flush=True);inventory=[]
    for root in roots:
        if not root.is_dir():raise FileNotFoundError(root)
        for base,dirs,files in os.walk(root):
            for name in files:
                if name.lower().endswith('.gz'):
                    file=Path(base)/name;st=file.stat();inventory.append((str(file),st.st_size,st.st_mtime_ns))
    inventory.sort();fingerprint=hashlib.sha256(orjson.dumps(inventory)).hexdigest();settings={'version':VERSION,'date':a.date,'inventory_sha256':fingerprint,'files':len(inventory),'bytes':sum(x[1] for x in inventory),'roots':list(map(str,roots)),'chunk_files':a.chunk_files}
    if not inventory:raise ValueError('No .gz files found')
    config=out/'input_manifest.json'
    if config.exists() and json.loads(config.read_text())!=settings:raise RuntimeError('Inventory/settings changed. Use a new output folder; completed prior parts remain intact.')
    atomic(config,settings);receipts=[];tasklist=[]
    for i in range(0,len(inventory),a.chunk_files):
        subset=inventory[i:i+a.chunk_files];chunk=i//a.chunk_files;digest=hashlib.sha256(orjson.dumps(subset)).hexdigest();receipt=parts/f'part_{chunk:06}.json'
        if receipt.exists() and (parts/f'part_{chunk:06}.parquet').exists():
            old=json.loads(receipt.read_text())
            if old.get('digest')==digest and old.get('version')==VERSION and old.get('errors')==0:receipts.append(old);continue
        tasklist.append((chunk,subset,str(parts),digest))
    def progress(phase,**extra):
        elapsed=time.monotonic()-started;files=sum(r['files'] for r in receipts);rows=sum(r['rows'] for r in receipts)
        data={'phase':phase,'updatedAt':stamp(),'pid':os.getpid(),'files_completed':files,'files_total':len(inventory),'rows_parsed':rows,'elapsed_seconds':round(elapsed,1),'errors':sum(r['errors'] for r in receipts),'bad_rows':sum(r['bad_rows'] for r in receipts),'percent':round(files/len(inventory)*100,2),**extra};atomic(out/'progress.json',data)
        print(f"{phase}: {files:,}/{len(inventory):,} files ({data['percent']}%) | {rows:,} rows | {elapsed:.0f}s",flush=True)
    progress('parsing');iterator=iter(tasklist);pending={};timed_out=False
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for _ in range(a.workers*2):
            task=next(iterator,None)
            if task is not None:pending[pool.submit(process_chunk,task)]=task[0]
        while pending:
            ready,_=wait(pending,timeout=5,return_when=FIRST_COMPLETED)
            for f in ready:
                pending.pop(f);receipts.append(f.result())
                if time.monotonic()-started<a.max_minutes*60:
                    task=next(iterator,None)
                    if task is not None:pending[pool.submit(process_chunk,task)]=task[0]
                else:timed_out=True
            progress('parsing')
    if timed_out and sum(x['files'] for x in receipts)<len(inventory):progress('time_limit_resume_required');return
    if sum(r['files'] for r in receipts)!=len(inventory):raise RuntimeError('File inventory not fully processed')
    progress('aggregating');summary=aggregate(parts,out,a.date)
    start_hour=epoch_us(a.date+'T00:00:00+05:30')//3600_000000
    required={datetime.fromtimestamp((start_hour+h)*3600,timezone.utc).strftime('%Y-%m-%dT%H:00:00Z') for h in range(25)}
    present={x['hour_utc'] for x in summary['hourly_utc']}
    missing=not required.issubset(present)
    progress('complete_local_with_input_errors' if any(r['errors'] or r['bad_rows'] for r in receipts) else 'complete_local',missing_hour_bins_for_ist_day=missing,coverage_note='Hourly presence and min/max are boundary checks only, not proof every source delivery file is present.',source_files_unchanged=True)
    print('LOCAL RESULT: '+str(out/'local_summary.json'),flush=True)

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc();raise
