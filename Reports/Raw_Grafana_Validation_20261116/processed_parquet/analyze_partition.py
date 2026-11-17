from pathlib import Path
import duckdb,json,time,pyarrow.parquet as pq
r=Path(r'D:\Vs - Code Work\Reports\Raw_Grafana_Validation_20261116');out=r/'processed_parquet';src=Path(r'Y:\Veto Logs Backup\DO NOT DELETE\source=stream\year=2026\month=11\day=16');files=sorted(src.glob('*.parquet'));inventory=[{'name':f.name,'bytes':f.stat().st_size,'mtime_ns':f.stat().st_mtime_ns,'rows':pq.ParquetFile(f).metadata.num_rows} for f in files]
c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='3GB'");c.execute("SET TimeZone='UTC'");(out/'scratch').mkdir(exist_ok=True);c.execute("SET temp_directory='"+str(out/'scratch').replace('\\','/')+"'")
c.read_parquet([str(f) for f in files],hive_partitioning=False).create_view('p');c.execute("CREATE VIEW v AS SELECT *,try_cast(reqTimeSec AS DOUBLE) AS epoch,try_cast(statusCode AS INTEGER) status,try_cast(bytes AS BIGINT) byte_count,ends_with(reqPath,'.ts') is_ts,ends_with(reqPath,'.ts') AND try_cast(statusCode AS INTEGER) IN (200,206) AND regexp_matches(reqPath,'[-_]([0-9]+)\\.ts$') AS eligible_ts FROM p")
def q(sql):
 t=time.monotonic();x=c.execute(sql);cols=[f[0] for f in x.description];rows=[dict(zip(cols,a)) for a in x.fetchall()];print('QUERY COMPLETE',len(rows),'groups',round(time.monotonic()-t,1),'s',flush=True);return rows
where=' WHERE epoch>=1794767400 AND epoch<1794853800'
metrics=q('SELECT reqHost host,count(*) requests,count(distinct cliIP) users,count(distinct cliIP) filter(where eligible_ts) ts_users,count(*) filter(where eligible_ts) ts_eligible,coalesce(sum(byte_count) filter(where is_ts and status IN (200,206)),0) video_bytes FROM v'+where+' GROUP BY 1 ORDER BY requests DESC')
quality=q('SELECT count(*) partition_rows,count(*) filter(where epoch is null) invalid_timestamps,count(*) filter(where status is null) invalid_statuses,count(*) filter(where byte_count is null) invalid_bytes,min(epoch) min_epoch,max(epoch) max_epoch,count(*) filter(where epoch<1794767400 OR epoch>=1794853800) outside_ist_day FROM v')[0]
summary=q('SELECT count(*) requests,count(distinct cliIP) users,count(distinct cliIP) filter(where eligible_ts) ts_users,count(*) filter(where eligible_ts) ts_eligible,coalesce(sum(byte_count) filter(where is_ts and status IN (200,206)),0) video_bytes FROM v'+where)[0]
status=q('SELECT status,is_ts,count(*) requests FROM v'+where+' GROUP BY 1,2 ORDER BY 1,2')
hour=q('SELECT cast(floor(epoch/3600)*3600 AS BIGINT) hour_epoch,count(*) requests,count(*) filter(where eligible_ts) ts_eligible FROM v'+where+' GROUP BY 1 ORDER BY 1')
for f,old in zip(files,inventory):
 st=f.stat();assert st.st_size==old['bytes'] and st.st_mtime_ns==old['mtime_ns'],'Source partition changed during audit'
result={'source':str(src),'input_files':inventory,'window':{'fromUtc':'2026-11-15T18:30:00Z','toUtcExclusive':'2026-11-16T18:30:00Z'},'quality':quality,'summary':summary,'hosts':metrics,'status':status,'hourly':hour};(out/'processed_metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps({'quality':quality,'summary':summary,'top_hosts':metrics[:5]},indent=2))
