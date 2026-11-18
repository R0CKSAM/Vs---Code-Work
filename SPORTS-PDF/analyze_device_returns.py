"""Daily distinct device returns and aggregate IP/device relationships.

Reads the supplied sports Parquet only. Exports no raw IPs or device IDs.
"""
import argparse,csv,json
from datetime import datetime,timezone
from pathlib import Path
import duckdb

def analyze(source,out):
    source=Path(source).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    before=source.stat();con=duckdb.connect();con.execute("SET threads=4");con.execute("SET memory_limit='2GB'")
    con.read_parquet(str(source)).create_view('raw')
    fields=[r[0] for r in con.execute('DESCRIBE raw').fetchall()]
    con.execute("""CREATE TEMP TABLE base AS SELECT cast(ist_date AS DATE) dt,
      CASE WHEN lower(trim(coalesce(device_id,''))) IN ('','unknown','null','none','nan','-','0','na','n/a') THEN NULL ELSE trim(device_id) END dev,
      CASE WHEN lower(trim(coalesce(cli_ip,''))) IN ('','unknown','null','none','nan','-','0','na','n/a') THEN NULL ELSE trim(cli_ip) END ip,
      raw_ts_requests FROM raw""")
    def query(sql):
        r=con.execute(sql);names=[x[0] for x in r.description];return [dict(zip(names,row)) for row in r.fetchall()]
    def write_csv(name,rows):
        if not rows:return
        with (out/name).open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    con.execute('CREATE TEMP TABLE dd AS SELECT DISTINCT dt,dev FROM base WHERE dev IS NOT NULL')
    con.execute('CREATE TEMP TABLE first_seen AS SELECT dev,min(dt) first_dt,count(*) n_dates FROM dd GROUP BY 1')
    daily=query("""WITH dates AS (SELECT DISTINCT dt FROM base), counts AS (
      SELECT d.dt,count(*) total_device_ids,count(*) FILTER(WHERE d.dt>f.first_dt) returning_device_ids,
      count(*) FILTER(WHERE d.dt=f.first_dt) first_observed_device_ids
      FROM dd d JOIN first_seen f USING(dev) GROUP BY 1)
      SELECT strftime(d.dt,'%Y-%m-%d') date_ist,coalesce(c.total_device_ids,0) total_device_ids,
      coalesce(c.returning_device_ids,0) returning_device_ids,coalesce(c.first_observed_device_ids,0) first_observed_device_ids,
      round(100.0*c.returning_device_ids/nullif(c.total_device_ids,0),2) returning_device_pct
      FROM dates d LEFT JOIN counts c USING(dt) ORDER BY d.dt""")
    if 'Match Name' in fields and 'Event Name' in fields:
        labels=query('SELECT ist_date AS date_ist,list(DISTINCT "Match Name") AS matches,list(DISTINCT "Event Name") AS events FROM raw GROUP BY 1')
        context={x['date_ist']:{'Match Name':' | '.join(sorted({str(v).strip() for v in x['matches'] if v is not None and str(v).strip()})),'Event Name':' | '.join(sorted({str(v).strip() for v in x['events'] if v is not None and str(v).strip()}))} for x in labels}
        for row in daily:row.update(context.get(row['date_ist'],{'Match Name':'','Event Name':''}))
    con.execute('CREATE TEMP TABLE dip AS SELECT DISTINCT dt,dev,ip FROM base WHERE dev IS NOT NULL AND ip IS NOT NULL')
    con.execute('CREATE TEMP TABLE first_pair AS SELECT dev,ip,min(dt) first_pair_dt FROM dip GROUP BY 1,2')
    linkage=query("""WITH a AS (SELECT dt,count(distinct dev) device_ids_with_ip,count(distinct ip) ips_with_device_id,count(*) device_ip_pairs FROM dip GROUP BY 1),
      multi AS (SELECT dt,count(*) devices_on_multiple_ips_same_day FROM (SELECT dt,dev,count(*) n FROM dip GROUP BY 1,2 HAVING n>1) GROUP BY 1),
      changed AS (SELECT d.dt,count(distinct d.dev) returning_devices_with_new_ip FROM dip d JOIN first_seen f USING(dev) JOIN first_pair p USING(dev,ip) WHERE d.dt>f.first_dt AND d.dt=p.first_pair_dt GROUP BY 1)
      SELECT strftime(a.dt,'%Y-%m-%d') date_ist,a.device_ids_with_ip,a.ips_with_device_id,a.device_ip_pairs,
      coalesce(multi.devices_on_multiple_ips_same_day,0) devices_on_multiple_ips_same_day,
      coalesce(changed.returning_devices_with_new_ip,0) returning_devices_with_new_ip
      FROM a LEFT JOIN multi USING(dt) LEFT JOIN changed USING(dt) ORDER BY a.dt""")
    assoc=query("""SELECT CASE WHEN n=1 THEN '1 device ID' WHEN n=2 THEN '2 device IDs' WHEN n BETWEEN 3 AND 5 THEN '3-5 device IDs' WHEN n BETWEEN 6 AND 10 THEN '6-10 device IDs' ELSE '11+ device IDs' END device_ids_per_ip,count(*) distinct_ips
      FROM (SELECT ip,count(distinct dev) n FROM dip GROUP BY 1) GROUP BY 1 ORDER BY min(n)""")
    ipmobility=query("""SELECT CASE WHEN n=1 THEN '1 client IP' WHEN n=2 THEN '2 client IPs' WHEN n BETWEEN 3 AND 5 THEN '3-5 client IPs' WHEN n BETWEEN 6 AND 10 THEN '6-10 client IPs' ELSE '11+ client IPs' END ips_per_device_id,count(*) distinct_device_ids
      FROM (SELECT dev,count(distinct ip) n FROM dip GROUP BY 1) GROUP BY 1 ORDER BY min(n)""")
    quality=query("""SELECT count(*) rows_total,count(*) FILTER(WHERE dev IS NULL) rows_without_valid_device_id,
      count(distinct dev) valid_distinct_device_ids,count(distinct ip) valid_distinct_ips,
      count(*) FILTER(WHERE dev IS NOT NULL AND raw_ts_requests>0) valid_device_rows_with_positive_ts,
      count(distinct dev) FILTER(WHERE raw_ts_requests>0) valid_device_ids_with_positive_ts,
      min(dt) first_date,max(dt) last_date,count(distinct dt) represented_dates FROM base""")[0]
    returns=query('SELECT count(*) unique_devices,count(*) FILTER(WHERE n_dates>1) devices_seen_on_multiple_dates FROM first_seen')[0]
    after=source.stat();assert before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns,'Source changed during analysis'
    for row in daily:assert row['total_device_ids']==row['returning_device_ids']+row['first_observed_device_ids']
    assert sum(x['first_observed_device_ids'] for x in daily)==quality['valid_distinct_device_ids']
    assert sum(x['distinct_device_ids'] for x in ipmobility)==con.execute('SELECT count(distinct dev) FROM dip').fetchone()[0]
    write_csv('daily_device_returns.csv',daily);write_csv('daily_device_ip_relationship.csv',linkage);write_csv('devices_per_ip_distribution.csv',assoc);write_csv('ips_per_device_distribution.csv',ipmobility)
    result={'createdAt':datetime.now(timezone.utc).isoformat(),'source':str(source),'source_bytes':before.st_size,'source_mtime_ns':before.st_mtime_ns,'quality':quality,'repeat_device_summary':returns,'ua_available':'UA' in fields,'definitions':{'total_device_ids':'Distinct trimmed valid device_id per IST date, all events/hosts/rows combined. No positive-TS filter.','returning_device_ids':'Device IDs present today whose first observed date in this file is earlier than today. Counted once per date regardless of events/IPs.','first_observed_device_ids':'First appearance inside this file, not proof the device is new in its lifetime.','returning_devices_with_new_ip':'Previously observed device IDs with at least one client IP not linked to that ID on an earlier date in this file.','invalid_ids':"Null/empty or case-insensitive unknown,null,none,nan,-,0,na,n/a excluded. Other IDs retained exactly after trimming.",'relationship_scope':'Only records where both device_id and cli_ip are present. One ID does not prove one physical device.','ua':'Device Type and OS Type are classifications, not a raw UA string. UA cannot be compared from this file.'},'daily':daily,'daily_ip_relationship':linkage,'devices_per_ip':assoc,'ips_per_device':ipmobility,'source_unchanged':True}
    (out/'analysis.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    notes='''DEVICE RETURN COUNTS - ALL SPORTS EVENTS COMBINED

daily_device_returns.csv is the requested primary table.
Returning device = present on this date AND observed on an earlier date in THIS file.
A device is counted once per date even if seen under multiple IPs or events.
First-observed is not a lifetime/new-customer claim. The first represented date has
zero returning IDs because the file contains no earlier baseline.

All rows are used, including zero-TS rows. The supplied aggregate dataset mostly
stores device identifiers on rows separate from positive TS request counts.
Filtering to positive TS requests would discard almost all identifiable devices.
Missing/placeholder IDs are excluded; no IDs are guessed from IP addresses.

Other CSV files describe IP/device relationships only where both values exist.
One IP may cover many devices (shared networks/NAT), and an ID may use many IPs
(mobility, dynamic addresses, VPNs or shared/reused IDs). Counts alone cannot
prove which mechanism caused a relationship.

This file has no raw UA column; Device Type and OS Type are not substitutes.
No raw identifiers are exported. The input Parquet is unchanged.
'''
    (out/'READ ME.txt').write_text(notes,encoding='utf-8');con.close();print(json.dumps({'quality':quality,'repeat_device_summary':returns,'daily':daily,'devices_per_ip':assoc,'ips_per_device':ipmobility},indent=2,default=str))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();analyze(a.source,a.out)
