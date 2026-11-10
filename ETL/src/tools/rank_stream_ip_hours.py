"""Rank all STREAM IPs by the explicit six-second TS-request estimate."""
from pathlib import Path
from datetime import datetime
import csv,json
import duckdb

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'output/exports/ip_trend_20261107_20261109'
OUT=BASE/'highest_hours_comparison';OUT.mkdir(exist_ok=True,parents=True)
meta=json.loads((BASE/'analysis.json').read_text());day='2026-11-09'
files={s:json.loads(next(r['files'] for r in meta['source_files'] if r['day']==day and r['source']==s)) for s in ['stream','fast']}
start=datetime.fromisoformat(day+'T00:00:00+05:30').timestamp()
c=duckdb.connect(str(OUT/'ranking.duckdb'));c.execute('SET threads=2');c.execute("SET memory_limit='2GB'")
exists=c.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='ip_ranking'").fetchone()[0]
if not exists:
    print('Ranking every STREAM client IP by TS request estimate for the full IST day',flush=True)
    c.execute("""CREATE TABLE ip_ranking AS SELECT trim(cliIP) cli_ip,count(*) ts_requests,
      count(*)/600.0 estimated_request_hours,
      count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 200 AND 299) successful_http_ts_requests,
      count(*) FILTER(WHERE try_cast(statusCode AS INT)=200) http_200_ts_requests,
      count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 400 AND 599) http_error_ts_requests
      FROM read_parquet(?,hive_partitioning=false,union_by_name=true)
      WHERE try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?
       AND lower(reqPath) LIKE '%.ts' AND nullif(trim(cliIP),'') IS NOT NULL
      GROUP BY 1""",[files['stream'],start,start+86400])
cur=c.execute('SELECT row_number() OVER(ORDER BY ts_requests DESC,cli_ip) AS rank,* FROM ip_ranking ORDER BY ts_requests DESC,cli_ip LIMIT 50');keys=[r[0] for r in cur.description];rows=[dict(zip(keys,row)) for row in cur.fetchall()]
with (OUT/'top_50_ip_hours.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
picked=next(r for r in rows if r['cli_ip']!=meta['ip'])
selection={'ip':picked['cli_ip'],'date_ist':day,'pool_size':c.execute('SELECT count(*) FROM ip_ranking').fetchone()[0], 'selection_kind':'highest estimated TS-request hours excluding the investigated cloud IP','rank':picked['rank'],'estimated_request_hours':picked['estimated_request_hours'],'method':'Rank all non-empty STREAM client IPs for 9 November IST by logged .ts request rows multiplied by 6 seconds / 3600. No bot, ISP, device or activity filter. Select the highest-ranked IP other than the investigated IP. This is aggregate requested-media time, not measured human watch time; retries, partial transfers and overlapping feeds may inflate it. HTTP-success counts shown separately; no URL/request-ID deduplication applied. FAST is checked separately for the selected IP.','files':files}
(OUT/'selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
(OUT/'ranking_summary.json').write_text(json.dumps({'date':day,'metric':selection['method'],'top_50':rows,'selected':selection},indent=2),encoding='utf-8')
print('READY',json.dumps({'pool_size':selection['pool_size'],'top_10':rows[:10],'selected':selection}),flush=True)
c.close()
