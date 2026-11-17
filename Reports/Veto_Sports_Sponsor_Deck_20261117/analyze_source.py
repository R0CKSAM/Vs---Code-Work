import duckdb,json
from pathlib import Path
out=Path(r'D:\Vs - Code Work\Reports\Veto_Sports_Sponsor_Deck_20261117')
c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='2GB'")
c.execute("CREATE VIEW s AS SELECT *,nullif(trim(cli_ip),'') ip,nullif(trim(device_id),'') dev FROM read_parquet('Y:/Veto Logs Backup/Chinmoy/sports_all_dates_12_columns.parquet')")
def q(sql):
 r=c.execute(sql);return [dict(zip([d[0] for d in r.description],row)) for row in r.fetchall()]
d={}
d['overall']=q('SELECT count(*) AS row_count,min(ist_date) first_date,max(ist_date) finish,count(distinct ist_date) day_count,count(distinct "Event Name") events,count(distinct "Match Name") matches,count(distinct ip) ips,count(distinct dev) devices,sum(raw_ts_requests) requests,count(*) filter(where raw_ts_requests>0) positive_rows,count(*) filter(where raw_ts_requests<0) negative_rows,count(*) filter(where ip is null) missing_ips,count(*) filter(where dev is null) missing_devices FROM s')
d['events']=q('SELECT "Event Name" event_label,count(*) AS row_count,count(distinct "Match Name") matches,min(ist_date) first_date,max(ist_date) finish,count(distinct ist_date) day_count,count(distinct ip) ips,count(distinct dev) devices,sum(raw_ts_requests) requests,count(distinct dev) filter(where raw_ts_requests>0) active_devices FROM s GROUP BY 1 ORDER BY devices DESC')
d['devices']=q('SELECT "Device Type" category,count(distinct dev) devices,count(*) AS row_count,sum(raw_ts_requests) requests FROM s GROUP BY 1 ORDER BY devices DESC')
d['countries']=q('SELECT country category,count(distinct dev) devices,count(distinct ip) ips FROM s GROUP BY 1 ORDER BY devices DESC LIMIT 15')
d['states']=q("SELECT state category,count(distinct dev) devices FROM s WHERE country='IN' GROUP BY 1 ORDER BY devices DESC LIMIT 15")
d['daily']=q('SELECT ist_date date_label,count(distinct dev) devices,count(distinct ip) ips,sum(raw_ts_requests) requests FROM s GROUP BY 1 ORDER BY 1')
d['matches']=q('SELECT "Event Name" event_label,"Match Name" match_label,count(distinct dev) devices FROM s GROUP BY 1,2 ORDER BY devices DESC LIMIT 20')
d['engagement']=q('WITH x AS (SELECT dev,count(distinct ist_date) day_count,count(distinct "Event Name") events FROM s WHERE dev IS NOT NULL GROUP BY 1) SELECT count(*) devices,count(*) filter(where day_count>1) repeat_devices,count(*) filter(where events>1) cross_event_devices,avg(day_count) avg_days FROM x')
d['quality']=q('SELECT country,count(*) AS row_count FROM s GROUP BY 1 ORDER BY row_count DESC LIMIT 10')
(out/'analysis.json').write_text(json.dumps(d,indent=2,default=str),encoding='utf-8')
print(json.dumps(d,indent=2,default=str))
