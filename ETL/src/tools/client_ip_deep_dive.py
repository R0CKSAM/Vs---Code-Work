"""Inspect logged software behaviours; do not infer ownership or human viewing."""
from pathlib import Path
import csv, html, json, sys
import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/profile'))
from vglive_core import channel_candidate_sql, resolve_channel

OUT = ROOT / 'output/exports/ip_trend_20261107_20261109/deep_dive'
OUT.mkdir(parents=True, exist_ok=True)
BASE = OUT.parent
meta = json.loads((BASE / 'analysis.json').read_text())
db = duckdb.connect(str(BASE / 'activity.duckdb'), read_only=True)
db.execute('SET threads=2')
db.execute("SET memory_limit='2GB'")
result = {'ip': meta['ip'], 'period': meta['days'], 'raw_day': '2026-11-09'}

def extract(name, sql, connection=db):
    cur = connection.execute(sql)
    keys = [r[0] for r in cur.description]
    rows = [dict(zip(keys, row)) for row in cur.fetchall()]
    result[name] = rows
    if 'reqHost' in keys and 'candidate' in keys:
        for row in rows:
            row['mapped_feed'] = resolve_channel(row['reqHost'], row['candidate'])
    with (OUT / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k,v in row.items()})
    return rows

extract('software_roles', "SELECT UA,extension,count(*) requests,sum(bytes) bytes,count(*) FILTER(WHERE status BETWEEN 400 AND 599) http_errors,count(distinct (reqHost,candidate)) feeds FROM activity GROUP BY ALL ORDER BY UA,requests DESC")
extract('software_feed_status', 'SELECT UA,reqHost,candidate,status,count(*) requests,sum(bytes) bytes FROM activity GROUP BY ALL ORDER BY requests DESC')
extract('software_payload_sizes', "SELECT UA,extension,count(*) requests,min(bytes) min_bytes,quantile_cont(bytes,.5) median_bytes,quantile_cont(bytes,.95) p95_bytes,max(bytes) max_bytes,count(*) FILTER(WHERE bytes=65536) exactly_65536_bytes FROM activity GROUP BY ALL ORDER BY UA,extension")
extract('software_cadence', "WITH t AS (SELECT *,epoch(ts-lag(ts) OVER(PARTITION BY day,UA,reqHost,candidate,extension ORDER BY ts)) gap FROM activity) SELECT UA,extension,count(*) positive_intervals,quantile_cont(gap,.5) median_gap_s,quantile_cont(gap,.9) p90_gap_s,quantile_cont(gap,.99) p99_gap_s FROM t WHERE gap>0 GROUP BY ALL ORDER BY UA,extension")
extract('second_overlap', "SELECT day,max(feeds) max_feeds_same_second,max(ts_feeds) max_successful_ts_feeds_same_second,count(*) FILTER(WHERE ts_feeds>1) seconds_with_multiple_ts_feeds FROM (SELECT day,date_trunc('second',ts) s,count(distinct (reqHost,candidate)) feeds,count(distinct (reqHost,candidate)) FILTER(WHERE extension='ts' AND status BETWEEN 200 AND 299 AND bytes>0) ts_feeds FROM activity GROUP BY ALL) GROUP BY day ORDER BY day")
files = json.loads(db.execute("SELECT files FROM scanned WHERE day='2026-11-09' AND source='stream'").fetchone()[0])
db.close()
raw_path = OUT / 'raw_ip_20261109.parquet'
con = duckdb.connect()
con.execute('SET threads=2')
con.execute("SET memory_limit='2GB'")
if not raw_path.exists():
    print('Reading additional raw fields for 9 November; preserving only this IP', flush=True)
    con.execute("CREATE TABLE raw AS SELECT UA,reqTimeSec,reqHost,reqPath,queryStr,reqId,bytes,rspContentLen,objSize,statusCode,errorCode,cmcd,startupError,tlsVersion,version,reqEndTimeMSec,transferTimeMSec FROM read_parquet(?,hive_partitioning=false,union_by_name=true) WHERE lower(trim(cliIP))=? AND try_cast(reqTimeSec AS DOUBLE)>=1794162600 AND try_cast(reqTimeSec AS DOUBLE)<1794249000", [files, meta['ip']])
    # Verify the epoch boundaries using DuckDB, rather than trusting hand-entered values.
    bounds = con.execute("SELECT epoch(TIMESTAMPTZ '2026-11-09 00:00:00+05:30'),epoch(TIMESTAMPTZ '2026-11-10 00:00:00+05:30')").fetchone()
    if bounds != (1794162600.0, 1794249000.0):
        raise AssertionError(('epoch boundaries', bounds))
    if con.execute('SELECT count(*) FROM raw').fetchone()[0] != 865770:
        raise AssertionError('Raw sample does not reconcile with the completed IP report')
    con.execute('COPY raw TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(raw_path)])
else:
    con.execute('CREATE TABLE raw AS SELECT * FROM read_parquet(?)', [str(raw_path)])
con.execute(f"CREATE VIEW r AS SELECT *,{channel_candidate_sql()} AS candidate,regexp_extract(lower(reqPath),'\\.([a-z0-9]+)(?:\\?|$)',1) AS extension FROM raw")
extract('raw_field_coverage', "SELECT count(*) requests,count(*) FILTER(WHERE nullif(trim(cmcd),'') IS NOT NULL) cmcd_present,count(*) FILTER(WHERE nullif(trim(queryStr),'') IS NOT NULL) query_present,count(distinct reqId) request_ids,count(*) FILTER(WHERE nullif(trim(startupError),'') IS NOT NULL) startup_error_field_present FROM r", con)
extract('protocols', 'SELECT UA,tlsVersion,version,count(*) requests FROM r GROUP BY ALL ORDER BY UA,requests DESC', con)
extract('payload_vs_object', "SELECT UA,extension,count(*) requests,quantile_cont(try_cast(bytes AS DOUBLE),.5) median_bytes,quantile_cont(try_cast(rspContentLen AS DOUBLE),.5) median_rsp_content_length,quantile_cont(try_cast(objSize AS DOUBLE),.5) median_object_size,count(*) FILTER(WHERE try_cast(bytes AS DOUBLE)=65536) bytes_exact_64k,count(*) FILTER(WHERE try_cast(bytes AS DOUBLE)<try_cast(objSize AS DOUBLE)) logged_bytes_less_than_object FROM r GROUP BY ALL ORDER BY UA,extension", con)
extract('software_errors', 'SELECT UA,statusCode,errorCode,count(*) requests FROM r GROUP BY ALL ORDER BY requests DESC', con)
extract('url_repetition', 'SELECT UA,reqHost,candidate,reqPath,count(*) requests,count(distinct reqId) request_ids,count(distinct queryStr) query_variants FROM r GROUP BY ALL ORDER BY requests DESC LIMIT 100', con)
extract('repeated_object_summary', 'WITH t AS (SELECT UA,reqHost,reqPath,count(*) n FROM r GROUP BY ALL) SELECT UA,count(*) distinct_host_paths,sum(n) requests,sum(n-1) requests_beyond_first,max(n) max_requests_one_host_path FROM t GROUP BY UA ORDER BY UA', con)
extract('shared_ts_objects', "WITH t AS (SELECT reqHost,candidate,reqPath,bool_or(UA='Lavf/60.16.100') ffmpeg,bool_or(UA='python-requests/2.31.0') python FROM r WHERE extension='ts' GROUP BY ALL) SELECT reqHost,candidate,count(*) distinct_ts_paths,count(*) FILTER(WHERE ffmpeg) ffmpeg_ts_paths,count(*) FILTER(WHERE python) python_ts_paths,count(*) FILTER(WHERE ffmpeg AND python) shared_ts_paths FROM t GROUP BY ALL ORDER BY distinct_ts_paths DESC", con)
extract('query_keys', "SELECT split_part(param,'=',1) key_name,count(*) occurrences FROM r,unnest(string_split(queryStr,'&')) t(param) WHERE coalesce(queryStr,'')<>'' AND param<>'' GROUP BY 1 ORDER BY occurrences DESC", con)
# Keep query values and CMCD values out of the published profile; field presence is enough.
result['limitations'] = ['UA strings are client-supplied identifiers, not proof of software ownership.', 'No request headers, Referer, cookies, account IDs, forwarded IPs, range header or client ports in the available lake schema.', 'Logged bytes smaller than object size does not by itself establish an HTTP Range request.', 'No request response bodies; cannot inspect playlist text or segment contents.', 'Same-second/minute requests are evidence of overlapping fetching, not measured concurrent playback.', 'No ownership or maliciousness established.']
result['validation'] = {'raw_day_requests': con.execute('SELECT count(*) FROM r').fetchone()[0], 'three_day_requests': sum(r['requests'] for r in result['software_roles'])}
assert result['validation']=={'raw_day_requests':865770,'three_day_requests':2644496}
(OUT/'analysis.json').write_text(json.dumps(result,default=str,indent=2),encoding='utf-8')
parts=['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IP software behaviour evidence</title><style>body{font:15px/1.6 system-ui;max-width:1450px;margin:auto;padding:24px;color:#183b30;background:#f2f7f4}section{background:white;padding:20px;border:1px solid #c9decf;border-radius:12px;margin:20px 0;overflow:auto}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:9px;border-bottom:1px solid #dce8df;font-size:12px;overflow-wrap:anywhere}a{color:#007c55}h1{overflow-wrap:anywhere}</style></head><body><h1>Deep investigation: '+html.escape(meta['ip'])+'</h1><p>7–9 November 2026 IST: software behaviour. Additional raw-field checks cover 9 November only. Requests are not human views or watch duration.</p><p><a href="../report.html">Back to three-day trend report</a></p><section><h2>Evidence and interpretation</h2><p>The pattern is consistent with automated multi-feed fetching: FFmpeg retrieves substantial media payloads; Python makes near-periodic 15-second checks and almost always logs exactly 64 KiB for segment requests; AdFlag requests playlists across many feed candidates. This supports a combination of sustained fetching and monitoring/sampling. It does not establish whether the operator is an internal service, a vendor, or another party.</p><p>Nearly all HTTP errors belong to AdFlag playlist requests. Error counts alone do not mean every media-fetching process is failing. The same-second overlap table demonstrates multiple successful feed fetches within one-second buckets; this is not measured concurrent human playback.</p><p>Evidence for HTTP Range headers, account identity, request referrer, physical hardware, and ownership is unavailable in this lake schema. UA labels can be spoofed. A decoder flag saying is_bot=False does not override the observed automation pattern.</p></section>']
for name,rows in result.items():
    if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict):continue
    keys=list(rows[0]);parts+=['<section><h2>'+html.escape(name.replace('_',' '))+'</h2><a href="'+name+'.csv">CSV</a><table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr>']
    for row in rows:parts+=['<tr>'+''.join('<td>'+html.escape(str(row.get(k,'')))+'</td>' for k in keys)+'</tr>']
    parts+=['</table></section>']
parts+=['<section><h2>Limits of attribution</h2><ul>'+''.join('<li>'+html.escape(s)+'</li>' for s in result['limitations'])+'</ul></section></body></html>']
(OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
print('Complete',str(OUT/'report.html'),json.dumps(result['software_payload_sizes']),json.dumps(result['payload_vs_object']),flush=True)
