from pathlib import Path
import duckdb,json
root=Path(r'D:\Vs - Code Work\Reports\Veto_Sports_Sponsor_Deck_20261117_v2')
c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='2GB'")
c.execute("CREATE TEMP TABLE s AS SELECT *,trim(cli_ip) ip FROM read_parquet('Y:/Veto Logs Backup/Chinmoy/sports_all_dates_12_columns.parquet') WHERE raw_ts_requests>0 AND trim(cli_ip)<>''")
def q(sql):
 r=c.execute(sql);return [dict(zip([d[0] for d in r.description],row)) for row in r.fetchall()]
d={}
d['overall']=q('SELECT count(distinct ip) users,sum(raw_ts_requests) requests,sum(raw_ts_requests)/6000.0 watch_hours,count(distinct ist_date) recorded_dates,min(ist_date) first_date,max(ist_date) last_date FROM s')[0]
d['events']=q('SELECT "Event Name" property,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours,count(distinct ist_date) recorded_dates,min(ist_date) first_date,max(ist_date) last_date FROM s GROUP BY 1 ORDER BY watch_hours DESC')
d['daily']=q('SELECT ist_date dt,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours FROM s GROUP BY 1 ORDER BY 1')
d['states']=q("SELECT state region,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours FROM s WHERE country='IN' GROUP BY 1 ORDER BY watch_hours DESC LIMIT 10")
d['devices']=q('SELECT "Device Type" category,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours FROM s GROUP BY 1 ORDER BY watch_hours DESC')
d['countries']=q('SELECT country category,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours FROM s GROUP BY 1 ORDER BY watch_hours DESC LIMIT 12')
c.execute('CREATE TEMP TABLE identities AS SELECT ip,count(distinct ist_date) n_dates,count(distinct "Event Name") n_events,bool_or("Event Name" IN (\'ODI Tri Series\',\'Pak-Sl T20 Series\')) cricket,bool_or("Event Name" NOT IN (\'ODI Tri Series\',\'Pak-Sl T20 Series\')) noncricket,sum(raw_ts_requests) requests FROM s GROUP BY 1')
d['repeat']=q('SELECT CASE WHEN n_dates>1 THEN \'Returning across dates\' ELSE \'One recorded date\' END cohort,count(*) users,sum(requests)/6000.0 watch_hours FROM identities GROUP BY 1')
d['sports_overlap']=q('SELECT cricket,noncricket,count(*) users,sum(requests)/6000.0 watch_hours FROM identities GROUP BY 1,2')
d['exclusive']=q('WITH x AS (SELECT ip,min("Event Name") property,count(distinct "Event Name") ne FROM s GROUP BY 1) SELECT property,count(*) users FROM x WHERE ne=1 GROUP BY 1 ORDER BY users DESC')
d['overlap']=q('WITH x AS (SELECT DISTINCT ip,"Event Name" property FROM s) SELECT a.property property_a,b.property property_b,count(*) users FROM x a JOIN x b USING(ip) WHERE a.property<b.property GROUP BY 1,2 ORDER BY users DESC')
d['matches']=q('SELECT "Event Name" property,"Match Name" match_label,ist_date dt,count(distinct ip) users,sum(raw_ts_requests)/6000.0 watch_hours FROM s GROUP BY 1,2,3 ORDER BY 5 DESC')
d['new_by_date']=q('WITH f AS (SELECT ip,min(ist_date) first_date FROM s GROUP BY 1) SELECT s.ist_date dt,count(distinct s.ip) users,count(distinct s.ip) filter(where f.first_date=s.ist_date) first_observed_users FROM s JOIN f USING(ip) GROUP BY 1 ORDER BY 1')
(root/'insights.json').write_text(json.dumps(d,indent=2));print(json.dumps({k:v for k,v in d.items() if k not in ['daily','matches','new_by_date','devices','countries']},indent=2))
