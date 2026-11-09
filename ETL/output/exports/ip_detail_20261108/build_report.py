from pathlib import Path
import sys,json,csv,html
import duckdb
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/profile'))
from vglive_core import channel_candidate_sql,resolve_channel
OUT=Path(__file__).parent
IP='2400:8904::2000:b1ff:fe6b:989d'
c=duckdb.connect();c.execute("SET threads=2");c.execute("SET memory_limit='3GB'")
files=[str(p) for p in Path('Z:/Veto Logs Backup/DO NOT DELETE/source=stream/year=2026/month=11/day=08').glob('*.parquet')]
c.execute('CREATE TABLE raw AS SELECT UA,reqTimeSec,reqPath,reqHost,reqId,bytes,totalBytes,statusCode,errorCode,asn,country,state,city,serverCountry,billingRegion,rspContentType,cacheStatus,timeToFirstByte,turnAroundTimeMSec,queryStr FROM read_parquet(?,hive_partitioning=false) WHERE lower(trim(cliIP))=?',[files,IP])
print('IP records loaded',flush=True)
c.execute(f"CREATE VIEW r AS SELECT *,to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS ts,{channel_candidate_sql()} AS candidate,regexp_extract(lower(reqPath),'\\.([a-z0-9]+)(?:\\?|$)',1) AS extension FROM raw")
report={}
def query(name,sql):
 cur=c.execute(sql);cols=[d[0] for d in cur.description];rows=[dict(zip(cols,row)) for row in cur.fetchall()]
 report[name]=rows
 if rows:
  with (OUT/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 return rows
query('overview',"SELECT count(*) requests,min(ts) first_ist,max(ts) last_ist,count(distinct date_trunc('minute',ts)) active_minutes,count(distinct reqId) distinct_request_ids,count(distinct reqHost) hosts,count(distinct candidate) candidates,count(distinct UA) uas,sum(try_cast(bytes AS DOUBLE)) bytes_sum,sum(try_cast(totalBytes AS DOUBLE)) total_bytes_sum,count(*) FILTER(WHERE try_cast(statusCode AS INT)>=400) error_requests FROM r")
query('user_agents',"SELECT UA,count(*) requests,min(ts) first_ist,max(ts) last_ist,sum(try_cast(bytes AS DOUBLE)) bytes_sum FROM r GROUP BY UA ORDER BY requests DESC")
query('responses',"SELECT statusCode,errorCode,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC")
query('geography_asn',"SELECT asn,country,state,city,serverCountry,billingRegion,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC")
query('hourly',"SELECT date_trunc('hour',ts) hour_ist,count(*) requests,sum(try_cast(bytes AS DOUBLE)) bytes_sum,count(*) FILTER(WHERE try_cast(statusCode AS INT)>=400) error_requests FROM r GROUP BY 1 ORDER BY 1")
channels=query('host_candidates',"SELECT reqHost,candidate,count(*) requests,min(ts) first_ist,max(ts) last_ist FROM r GROUP BY ALL ORDER BY requests DESC")
for row in channels:row['mapped_channel']=resolve_channel(row['reqHost'],row['candidate'])
with (OUT/'host_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(channels[0]));w.writeheader();w.writerows(channels)
query('request_types',"SELECT extension,rspContentType,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC")
query('cache',"SELECT cacheStatus,count(*) requests FROM r GROUP BY 1 ORDER BY 2 DESC")
query('performance',"SELECT avg(try_cast(timeToFirstByte AS DOUBLE)) avg_ttfb_recorded,quantile_cont(try_cast(timeToFirstByte AS DOUBLE),0.95) p95_ttfb_recorded,avg(try_cast(turnAroundTimeMSec AS DOUBLE)) avg_turnaround_ms,quantile_cont(try_cast(turnAroundTimeMSec AS DOUBLE),0.95) p95_turnaround_ms FROM r")
query('peak_minute',"SELECT date_trunc('minute',ts) minute_ist,count(*) requests FROM r GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
query('query_fields',"SELECT field_name,count(*) occurrences FROM r,unnest(string_split(queryStr,'&')) t(param),LATERAL (SELECT split_part(param,'=',1) AS field_name) WHERE coalesce(queryStr,'')<>'' GROUP BY 1 ORDER BY 2 DESC")
for key in ['device_id','session_id','content_title','video_key','category_name']:
 query(key,f"SELECT try(url_decode(regexp_extract(queryStr,'(?i)(?:^|[?&]){key}=([^&]+)',1))) AS field_value,count(*) requests FROM r GROUP BY 1 ORDER BY 2 DESC")
cache=json.loads((ROOT/'data/asn/ip2location_asn_cache.json').read_text())
report['asn_decode']={str(row['asn']):cache.get(str(row['asn'])) for row in report['geography_asn']}
(OUT/'report.json').write_text(json.dumps(report,default=str,indent=2),encoding='utf-8')
parts=['<html><meta charset="utf-8"><title>Client IP activity report</title><style>body{font:15px Arial;margin:32px;color:#182435}table{border-collapse:collapse;margin-bottom:28px}td,th{border:1px solid #ccd;padding:8px;text-align:left}th{background:#eef}h1{font-size:24px}</style>',f'<h1>{IP} â€” 8 November 2026 IST</h1><p>STREAM request activity. FAST search found no matching records. Request counts are not people or video views. UA decoding does not establish physical device identity. Geography is the logged IP location; ASN names come from the current decode cache. No watch duration is inferred for this software-client traffic.</p>']
for name,rows in report.items():
 if not isinstance(rows,list) or not rows:continue
 cols=list(rows[0]);parts += [f'<h2>{html.escape(name)}</h2><table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in cols)+'</tr>']
 for row in rows[:100]:parts += ['<tr>'+''.join('<td>'+html.escape(str(row.get(k,'')))+'</td>' for k in cols)+'</tr>']
 parts+=['</table>']
parts+=['</html>'];(OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
print(json.dumps(report,default=str),flush=True)



