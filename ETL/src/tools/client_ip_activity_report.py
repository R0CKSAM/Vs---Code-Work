"""Read-only client IP investigation across completed STREAM/FAST IST partitions."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from urllib.parse import unquote
import argparse,csv,html,ipaddress,json,sys
import duckdb
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src/profile'))
from src.common.lake_partitions import partition_for_date,resolve_lake_roots
from vglive_core import channel_candidate_sql,resolve_channel

def run(ip,day):
    ip=str(ipaddress.ip_address(ip));target=date.fromisoformat(day);out=ROOT/'output/exports'/('ip_detail_'+target.strftime('%Y%m%d'));out.mkdir(exist_ok=True,parents=True)
    start=datetime.combine(target,datetime.min.time(),timezone(timedelta(hours=5,minutes=30))).timestamp();end=start+86400
    con=duckdb.connect();con.execute('SET threads=2');con.execute("SET memory_limit='2GB'")
    report=dict(ip=ip,date_ist=day,generated_at_ist=datetime.now(timezone(timedelta(hours=5,minutes=30))).isoformat(),source_partitions=[])
    columns='UA,reqTimeSec,reqPath,reqHost,reqId,bytes,totalBytes,statusCode,errorCode,asn,country,state,city,serverCountry,billingRegion,rspContentType,cacheStatus,timeToFirstByte,turnAroundTimeMSec,queryStr'
    roots=resolve_lake_roots(ROOT/'data/lake',[Path('Z:/Veto Logs Backup/DO NOT DELETE')])
    for index,source in enumerate(['stream','fast']):
        partition=partition_for_date(roots,source,day)
        if not partition:raise FileNotFoundError(f'No completed {source} partition for {day}')
        files=[str(p) for p in partition.files]
        report['source_partitions'].append(dict(source=source,files=files))
        print(f'Scanning {source}: {len(files)} unique partition files',flush=True)
        query=('CREATE TABLE raw AS ' if index==0 else 'INSERT INTO raw ')+f"SELECT ? AS source,{columns} FROM read_parquet(?,hive_partitioning=false,union_by_name=true) WHERE lower(trim(cliIP))=? AND try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?"
        con.execute(query,[source,files,ip,start,end]);print(source,con.execute('SELECT count(*) FROM raw WHERE source=?',[source]).fetchone()[0],'matching requests',flush=True)
    con.execute(f"CREATE VIEW r AS SELECT *,to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS ts,{channel_candidate_sql()} AS candidate,regexp_extract(lower(reqPath),'\\.([a-z0-9]+)(?:\\?|$)',1) AS extension FROM raw")
    def query(name,sql):
        cur=con.execute(sql);names=[c[0] for c in cur.description];rows=[dict(zip(names,row)) for row in cur.fetchall()];report[name]=rows
        with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(names)
            for row in rows:w.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for v in row.values()])
        return rows
    query('overview',"SELECT count(*) AS requests,min(ts) AS first_ist,max(ts) AS last_ist,count(distinct date_trunc('minute',ts)) AS active_minutes,count(distinct nullif(trim(cast(reqId AS VARCHAR)),'')) AS distinct_request_ids,count(distinct reqHost) AS hosts,count(distinct (reqHost,candidate)) AS host_candidate_pairs,count(distinct UA) AS uas,coalesce(sum(try_cast(bytes AS DOUBLE)),0) AS bytes_sum,coalesce(sum(try_cast(totalBytes AS DOUBLE)),0) AS total_bytes_sum,count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 400 AND 599) AS http_error_requests FROM r")
    query('sources',"SELECT source,count(*) AS requests,min(ts) AS first_ist,max(ts) AS last_ist FROM r GROUP BY source ORDER BY source")
    query('user_agents',"SELECT UA,count(*) AS requests,min(ts) AS first_ist,max(ts) AS last_ist,sum(try_cast(bytes AS DOUBLE)) AS bytes_sum FROM r GROUP BY UA ORDER BY requests DESC")
    query('status_codes',"SELECT statusCode,count(*) AS requests FROM r GROUP BY statusCode ORDER BY requests DESC")
    query('responses',"SELECT statusCode,errorCode,count(*) AS requests FROM r GROUP BY ALL ORDER BY requests DESC")
    query('geography_asn',"SELECT asn,country,state,city,serverCountry,billingRegion,count(*) AS requests FROM r GROUP BY ALL ORDER BY requests DESC")
    query('hourly',"SELECT date_trunc('hour',ts) AS hour_ist,count(*) AS requests,sum(try_cast(bytes AS DOUBLE)) AS bytes_sum,count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 400 AND 599) AS http_error_requests FROM r GROUP BY 1 ORDER BY 1")
    channels=query('host_candidates',"SELECT source,reqHost,candidate,count(*) AS requests,min(ts) AS first_ist,max(ts) AS last_ist FROM r GROUP BY ALL ORDER BY requests DESC")
    for row in channels:row['mapped_channel']=resolve_channel(row['reqHost'],row['candidate'])
    if channels:
        with (out/'host_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(channels[0]));w.writeheader();w.writerows(channels)
    query('request_types',"SELECT extension,rspContentType,count(*) AS requests FROM r GROUP BY ALL ORDER BY requests DESC")
    query('cache',"SELECT cacheStatus,count(*) AS requests FROM r GROUP BY 1 ORDER BY requests DESC")
    query('performance',"SELECT avg(try_cast(timeToFirstByte AS DOUBLE)) AS avg_ttfb_recorded,quantile_cont(try_cast(timeToFirstByte AS DOUBLE),0.95) AS p95_ttfb_recorded,avg(try_cast(turnAroundTimeMSec AS DOUBLE)) AS avg_turnaround_ms,quantile_cont(try_cast(turnAroundTimeMSec AS DOUBLE),0.95) AS p95_turnaround_ms FROM r")
    query('peak_minutes',"SELECT date_trunc('minute',ts) AS minute_ist,count(*) AS requests FROM r GROUP BY 1 ORDER BY requests DESC LIMIT 10")
    query('top_paths',"SELECT reqHost,reqPath,count(*) AS requests FROM r GROUP BY ALL ORDER BY requests DESC LIMIT 100")
    query('query_fields',"SELECT split_part(param,'=',1) AS field_name,count(*) AS occurrences FROM r,unnest(string_split(queryStr,'&')) t(param) WHERE coalesce(queryStr,'')<>'' AND param<>'' GROUP BY 1 ORDER BY occurrences DESC")
    for key in ['device_id','session_id','content_title','video_key','category_name','content_type','platform','channel']:
        query(key,f"SELECT nullif(try(url_decode(regexp_extract(queryStr,'(?i)(?:^|[?&]){key}=([^&]+)',1))),'') AS field_value,count(*) AS requests FROM r GROUP BY 1 ORDER BY requests DESC")
    uas={r['UA'] for r in report['user_agents']};lookup={}
    with (ROOT/'output/device_decode/ua_decode_lookup_both_all.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['UA'] in uas:lookup[row['UA']]=row
    report['ua_decode']=[dict(UA=row['UA'],requests=row['requests'],decoded=lookup.get(row['UA'])) for row in report['user_agents']]
    asn_cache=json.loads((ROOT/'data/asn/ip2location_asn_cache.json').read_text());report['asn_decode']={str(r['asn']):asn_cache.get(str(r['asn'])) for r in report['geography_asn']}
    prior=ROOT/'output/exports'/('ip_detail_'+(target-timedelta(days=1)).strftime('%Y%m%d'))/'report.json'
    if prior.exists():
        old=json.loads(prior.read_text());previous=old['overview'][0];current=report['overview'][0]
        report['previous_day_comparison']=dict(date_ist=(target-timedelta(days=1)).isoformat(),previous_requests=previous['requests'],current_requests=current['requests'],change_requests=current['requests']-previous['requests'],change_pct=(current['requests']/previous['requests']-1)*100 if previous['requests'] else None)
    n=report['overview'][0]['requests'];checks={}
    for key in ['sources','user_agents','status_codes','responses','geography_asn','hourly','host_candidates','request_types','cache']:
        checks[key+'_requests_reconcile']=sum(r['requests'] for r in report[key])==n
    checks['timestamps_within_ist_date']=all(str(r['hour_ist']).startswith(day) for r in report['hourly']);report['validation']=checks
    if not all(checks.values()):raise RuntimeError('Breakdown totals did not reconcile')
    (out/'report.json').write_text(json.dumps(report,default=str,indent=2),encoding='utf-8')
    summary=report['overview'][0];parts=['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Client IP activity</title><style>body{font:15px/1.7 system-ui,sans-serif;max-width:1300px;margin:auto;padding:24px;color:#244334;background:#f4f8f4}section{background:white;padding:18px;border:1px solid #c2d9c9;border-radius:10px;margin:18px 0;overflow:auto}table{border-collapse:collapse;min-width:600px;width:100%}td,th{border-bottom:1px solid #dce8df;text-align:left;padding:10px;font-size:12px;overflow-wrap:anywhere}h1{font-size:23px}a{color:#176b43}</style></head><body>',f'<h1>{html.escape(ip)}</h1><p>{day} / 00:00-23:59 IST / STREAM + FAST</p>',f'<section><h2>Activity summary</h2><p>{n:,} requests; {summary["active_minutes"]:,} active minutes; {summary["hosts"]} hosts; {summary["uas"]} UA strings. HTTP 4xx/5xx: {summary["http_error_requests"]:,}.</p><p>Request counts are not views or people. Software UA decoding does not identify a physical device or owner. No watch duration is inferred from this IP. ASN names are from the local decode cache; logged geography and ASN registration country are separate fields. Bytes and totalBytes are separate counters and must not be added. TTFB is shown in recorded units; turnaround is the explicitly named millisecond field.</p></section>']
    parts+=['<section><h2>User-agent decode</h2>']
    for row in report['ua_decode']:
        decoded=row['decoded'];parts+=['<p><b>'+html.escape(str(row['UA']))+'</b> / '+f'{row["requests"]:,}'+' requests<br>'+html.escape(json.dumps({k:decoded.get(k) for k in ['decode_status','decoder_method','device_type','form_factor','os_name','app_player','is_bot','notes']} if decoded else {'decode_status':'not found in current lookup'}))+'</p>']
    parts+=['</section>','<section><h2>ASN decode</h2><pre>'+html.escape(json.dumps(report['asn_decode'],indent=2))+'</pre></section>']
    for name,rows in report.items():
        if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict) or name in {'source_partitions','ua_decode'}:continue
        keys=list(rows[0]);parts+=['<section><h2>'+html.escape(name.replace('_',' '))+'</h2><p><a href="'+name+'.csv">Download CSV</a></p><table><thead><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr></thead><tbody>']
        for row in rows[:100]:parts+=['<tr>'+''.join('<td>'+html.escape(str(row.get(k,'')))+'</td>' for k in keys)+'</tr>']
        parts+=['</tbody></table></section>']
    parts+=['</body></html>'];(out/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    con.close();print(json.dumps(dict(report=str(out/'report.html'),overview=summary,comparison=report.get('previous_day_comparison'),validation=checks),default=str),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ip',required=True);parser.add_argument('--date',required=True);args=parser.parse_args();run(args.ip,args.date)
