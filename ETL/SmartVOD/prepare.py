"""Build the local query store from existing VOD CSV exports; never edit ETL sources."""
import argparse
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ETL=ROOT.parent

def clean(value):
    value=(value or '').strip()
    return value if value.lower() not in ('','unknown','unknown / na','unknown / unmarked','na','n/a') else 'Unknown'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--date',action='append',required=True,help='Repeat for multiple dates; replaces the local dataset')
    args=parser.parse_args()
    dates=sorted(set(args.date))
    sources=[ETL/'output/exports'/f'vod_stream_query_events_{d}.csv' for d in dates]
    for p in sources:
        if not p.is_file():raise FileNotFoundError(p)
    isp={}
    with (ETL/'data/asn/asnDecoded.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if clean(r.get('as_name'))!='Unknown':isp[r['asn'].strip()]=r['as_name'].strip()
    folder=ROOT/'data';folder.mkdir(exist_ok=True)
    tmp=folder/'smartvod.build.sqlite';tmp.unlink(missing_ok=True)
    con=sqlite3.connect(tmp)
    con.execute('CREATE TABLE events(day TEXT,clock TEXT,title TEXT,category TEXT,video_key TEXT,device_id TEXT,cli_ip TEXT,os TEXT,region TEXT,isp TEXT,device_type TEXT,hours REAL,delivered REAL,segments INTEGER,request_ist TEXT,last_request_ist TEXT,req_host TEXT,session_id TEXT,identity_source TEXT)')
    total=0;hours=0;segments=0;unknown_isp=0
    for day,p in zip(dates,sources):
        batch=[]
        with p.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if r['log_date']!=day:raise ValueError('Source date mismatch')
                asn=clean(r.get('asn'))
                provider=f'{isp[asn]} · AS{asn}' if asn in isp else ('Unknown' if asn=='Unknown' else f'Unknown ISP · AS{asn}')
                unknown_isp+=int(asn not in isp)
                h=float(r.get('request_watch_hours') or 0);s=int(r.get('segment_count') or 1)
                batch.append((day,r['minute_ist'][11:16],clean(r['content_title']),clean(r['category_name']),clean(r['content_code']),clean(r['device_id']),clean(r['cli_ip']),clean(r['decoded_os']), ' / '.join(clean(r.get(k)) for k in ('country','state','city')),provider,clean(r['decoded_form_factor']).lower(),h,float(r.get('delivered_watch_hours') or 0),s,r['request_ist'],r['last_request_ist'],r['req_host'],r['session_id'],r.get('identity_source','unavailable')))
                total+=1;hours+=h;segments+=s
                if len(batch)>=5000:
                    con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch);batch=[]
            if batch:con.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
        print('Imported',day,flush=True)
    for key in ('day','video_key','device_id','cli_ip','os','isp','region','title','category','device_type'):
        con.execute(f'CREATE INDEX idx_{key} ON events({key})')
    con.commit();con.close();tmp.replace(folder/'smartvod.sqlite')
    (folder/'manifest.json').write_text(json.dumps(dict(dates=dates,records=total,hours=hours,segments=segments,unknown_isp_records=unknown_isp,built_at=datetime.now().isoformat(),sources=[str(p) for p in sources],timezone='Asia/Kolkata'),indent=2))
    print('Ready:',total,'records',round(hours,3),'estimated hours',flush=True)

if __name__=='__main__':main()
