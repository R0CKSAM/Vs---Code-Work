"""Select an unbiased distinct STREAM IP and compare observable request activity."""
from pathlib import Path
from datetime import datetime
import csv, html, ipaddress, json
from collections import Counter
from urllib.parse import parse_qs
import duckdb
import argparse

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'output/exports/ip_trend_20261107_20261109'
parser=argparse.ArgumentParser();parser.add_argument('--output-name',default='random_comparison');args=parser.parse_args()
if not args.output_name.replace('_','').isalnum():raise ValueError('Output name must be a simple folder name')
OUT = BASE/args.output_name
OUT.mkdir(parents=True,exist_ok=True)
meta=json.loads((BASE/'analysis.json').read_text())
day='2026-11-09'
files={s:json.loads(next(r['files'] for r in meta['source_files'] if r['day']==day and r['source']==s)) for s in ['stream','fast']}
start=datetime.fromisoformat(day+'T00:00:00+05:30').timestamp()
db=duckdb.connect()
db.execute('SET threads=2');db.execute("SET memory_limit='2GB'")
selection_path=OUT/'selection.json'
if not selection_path.exists():
    print('Selecting one random distinct client IP from the complete STREAM day',flush=True)
    db.execute("CREATE TABLE candidates AS SELECT DISTINCT trim(cliIP) cli_ip FROM read_parquet(?,hive_partitioning=false,union_by_name=true) WHERE nullif(trim(cliIP),'') IS NOT NULL AND lower(trim(cliIP))<>? AND try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?",[files['stream'],meta['ip'],start,start+86400])
    db.execute('SELECT setseed(0.271828)')
    selected=db.execute('SELECT cli_ip FROM candidates ORDER BY random() LIMIT 1').fetchone()[0]
    ipaddress.ip_address(selected)
    selection={'ip':selected,'date_ist':day,'pool_size':db.execute('SELECT count(*) FROM candidates').fetchone()[0],'method':'Uniform random ordering of distinct non-empty STREAM client IPs for the complete IST day, excluding the investigated IP. No device, ISP, traffic-volume or behavioural filter. First selected IP retained. DuckDB seed 0.271828.','files':files}
    selection_path.write_text(json.dumps(selection,indent=2),encoding='utf-8')
else:selection=json.loads(selection_path.read_text())
print('Selected',selection['ip'],'from',selection['pool_size'],'distinct IPs',flush=True)
cache=OUT/'selected_ip_raw.parquet'
if not cache.exists():
    for i,source in enumerate(['stream','fast']):
        print('Scanning selected IP:',source,flush=True)
        prefix='CREATE TABLE raw AS ' if i==0 else 'INSERT INTO raw '
        db.execute(prefix+"SELECT ? AS source,UA,reqTimeSec,reqHost,reqPath,queryStr,bytes,statusCode,asn,country,state,city,reqId,errorCode FROM read_parquet(?,hive_partitioning=false,union_by_name=true) WHERE trim(cliIP)=? AND try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?",[source,files[source],selection['ip'],start,start+86400])
        print(source,db.execute('SELECT count(*) FROM raw WHERE source=?',[source]).fetchone()[0],flush=True)
    db.execute('COPY raw TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(cache)])
else:db.execute('CREATE TABLE raw AS SELECT * FROM read_parquet(?)',[str(cache)])
import sys
sys.path.insert(0,str(ROOT/'src/profile'))
from vglive_core import channel_candidate_sql,resolve_channel
db.execute(f"CREATE VIEW r AS SELECT *,to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS ts,{channel_candidate_sql()} AS candidate,regexp_extract(lower(reqPath),'\\.([a-z0-9]+)(?:\\?|$)',1) AS extension FROM raw")
report={'selection':selection}
def extract(name,sql):
    cur=db.execute(sql);keys=[x[0] for x in cur.description];rows=[dict(zip(keys,r)) for r in cur.fetchall()]
    if 'candidate' in keys:
        for r in rows:r['mapped_feed']=resolve_channel(r['reqHost'],r['candidate'])
    report[name]=rows
    with (OUT/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else keys);w.writeheader()
        for row in rows:w.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()})
    return rows
extract('overview',"SELECT count(*) requests,min(ts) first_ist,max(ts) last_ist,count(distinct date_trunc('minute',ts)) active_minutes,count(distinct (reqHost,candidate)) feeds,count(distinct UA) uas,sum(try_cast(bytes AS DOUBLE)) bytes,count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 400 AND 599) http_errors FROM r")
extract('sources','SELECT source,count(*) requests FROM r GROUP BY source ORDER BY source')
extract('user_agents','SELECT UA,count(*) requests FROM r GROUP BY UA ORDER BY requests DESC')
extract('geography_asn','SELECT country,state,city,asn,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC')
extract('feed_activity','SELECT reqHost,candidate,count(*) requests,min(ts) first_ist,max(ts) last_ist FROM r GROUP BY ALL ORDER BY requests DESC')
extract('ua_feed_activity','SELECT UA,reqHost,candidate,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC')
extract('hourly',"SELECT extract('hour' FROM ts)::INT AS \"hour\",count(*) requests FROM r GROUP BY 1 ORDER BY 1")
extract('minute_activity',"SELECT date_trunc('minute',ts) minute_ist,count(*) requests,count(distinct (reqHost,candidate)) feeds,count(distinct (reqHost,candidate)) FILTER(WHERE extension='ts' AND try_cast(statusCode AS INT) BETWEEN 200 AND 299 AND try_cast(bytes AS DOUBLE)>0) successful_ts_feeds FROM r GROUP BY 1 ORDER BY 1")
extract('request_types','SELECT source,UA,extension,statusCode,count(*) requests,sum(try_cast(bytes AS DOUBLE)) bytes FROM r GROUP BY ALL ORDER BY requests DESC')
extract('errors','SELECT statusCode,errorCode,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC')
extract('repeated_playlists',"SELECT UA,reqHost,reqPath,count(*) requests,min(ts) first_ist,max(ts) last_ist,quantile_cont(try_cast(bytes AS DOUBLE),.5) median_logged_bytes FROM r WHERE extension='m3u8' GROUP BY ALL ORDER BY requests DESC LIMIT 20")
extract('query_keys',"SELECT split_part(param,'=',1) key_name,count(*) occurrences FROM r,unnest(string_split(queryStr,'&')) t(param) WHERE coalesce(queryStr,'')<>'' AND param<>'' GROUP BY 1 ORDER BY occurrences DESC")
# Do not publish query parameter values: report only identifier coverage.
extract('identifier_coverage',"SELECT count(*) FILTER(WHERE regexp_matches(queryStr,'(?i)(?:^|[?&])device_id=[^&]+')) device_id_requests,count(*) FILTER(WHERE regexp_matches(queryStr,'(?i)(?:^|[?&])session_id=[^&]+')) session_id_requests FROM r")
descriptions=Counter()
reported_ids={'device_id':set(),'session_id':set()}
for (raw_query,) in db.execute('SELECT queryStr FROM r').fetchall():
    fields=parse_qs((raw_query or '').lstrip('?'))
    for field in reported_ids:
        value=fields.get(field,[''])[0].strip()
        if value.lower() not in {'','null','undefined','unknown','na','n/a','none','0'} and set(value.replace('-',''))!={'0'}:reported_ids[field].add(value)
    values=tuple(fields.get(k,[''])[0] for k in ['platform','device','content_title','content_type'])
    if any(values):descriptions[values]+=1
report['descriptive_query_metadata']=[dict(zip(['platform','device_label','title','content_type','requests'],[*values,n])) for values,n in descriptions.most_common()]
report['reported_identifier_counts']={field:len(values) for field,values in reported_ids.items()}
asn=json.loads((ROOT/'data/asn/ip2location_asn_cache.json').read_text());report['asn_decode']={str(r['asn']):asn.get(str(r['asn'])) for r in report['geography_asn']}
uas={r['UA'] for r in report['user_agents']};report['ua_decode']=[]
with (ROOT/'output/device_decode/ua_decode_lookup_both_all.csv').open(encoding='utf-8-sig',newline='') as f:
    for row in csv.DictReader(f):
        if row['UA'] in uas:report['ua_decode'].append(row)
n=report['overview'][0]['requests'];assert n>0
for k in ['sources','user_agents','geography_asn','feed_activity','hourly','minute_activity','request_types','errors']:assert sum(r['requests'] for r in report[k])==n,k
report['validation']={'all_breakdowns_reconcile':True,'original_selection_retained':True,'both_sources_scanned':True}
(OUT/'analysis.json').write_text(json.dumps(report,default=str,indent=2),encoding='utf-8')
print('READY',json.dumps({'ip':selection['ip'],'overview':report['overview'],'top_5_ua':report['user_agents'][:5],'geography_asn':report['geography_asn'],'asn_decode':report['asn_decode'],'reported_identifier_counts':report['reported_identifier_counts'],'report_json':str(OUT/'analysis.json')},default=str),flush=True)
