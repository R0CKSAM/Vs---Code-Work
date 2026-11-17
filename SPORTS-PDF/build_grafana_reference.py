"""Create a small, aggregate-only reference for Smart Export's validator."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import duckdb

def build(source, output):
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output: raise ValueError('Output must not overwrite the Parquet source.')
    con=duckdb.connect();con.execute("SET threads=4");con.execute("SET memory_limit='2GB'")
    con.execute("CREATE TEMP TABLE s AS SELECT *,nullif(trim(cli_ip),'') ip,nullif(trim(device_id),'') dev FROM read_parquet(?)",[str(source)])
    def rows(sql):
        r=con.execute(sql); names=[x[0] for x in r.description]; return [dict(zip(names,v)) for v in r.fetchall()]
    metric="count(distinct ip) AS users_all,count(distinct ip) filter(where raw_ts_requests>0) AS users_positive_ts,count(distinct dev) AS device_ids,sum(raw_ts_requests) AS ts_requests,sum(raw_ts_requests)*0.6/3600 AS hours_0_6,sum(raw_ts_requests)*6.0/3600 AS hours_6"
    scopes=[{'id':'portfolio','name':'Entire sports portfolio','where':''}]+[{'id':x['name'],'name':x['name'],'where':" WHERE \"Event Name\"='"+x['name'].replace("'","''")+"'"} for x in rows('SELECT DISTINCT "Event Name" AS name FROM s ORDER BY 1')]
    result=[]
    for scope in scopes:
        where=scope.pop('where')
        scope['summary']=rows('SELECT '+metric+' FROM s'+where)[0]
        scope['daily']=rows('SELECT ist_date AS date,'+metric+' FROM s'+where+' GROUP BY 1 ORDER BY 1')
        scope['hosts']=rows('SELECT ist_date AS date,ReqHost AS host FROM s'+where+' GROUP BY 1,2 ORDER BY 1,2')
        scope['geo']=rows('SELECT ist_date AS date,country,state,sum(raw_ts_requests) AS ts_requests,sum(raw_ts_requests)*0.6/3600 AS hours_0_6,sum(raw_ts_requests)*6.0/3600 AS hours_6 FROM s'+where+' GROUP BY 1,2,3 ORDER BY 1,2,3')
        result.append(scope)
    stat=source.stat()
    packet={'schema':'smart-export-parquet-reference/v1','createdAt':datetime.now(timezone.utc).isoformat(),'source':{'name':source.name,'bytes':stat.st_size,'modifiedNs':stat.st_mtime_ns},'timezone':'Asia/Kolkata','secondsPerTs':0.6,'definitions':{'users_positive_ts':'Distinct trimmed nonblank cli_ip on raw_ts_requests > 0 rows; the sponsor deck user definition.','users_all':'Distinct trimmed nonblank cli_ip across supplied rows; not necessarily all source traffic.','device_ids':'Distinct trimmed nonblank device_id; not comparable to Grafana approximate uniq including blank IDs.','ts_requests':'SUM(raw_ts_requests). No HTTP status, segment path or duration columns exist in this file.','hours_0_6':'SUM(raw_ts_requests) * 0.6 / 3600','hours_6':'SUM(raw_ts_requests) * 6 / 3600'},'unsupported':['city','session_id','user_agent','URL / reqPath','statusCode','bytes','player duration','ad impressions'],'warnings':['Only dates represented in Parquet are included; absent dates are not zero.','ReqHost names are reused across events. Host filters alone do not certify event mapping.','HTTP status and TS path rules cannot be checked from this Parquet.','Distinct daily users must not be summed to calculate period users.'],'scopes':result}
    output.parent.mkdir(parents=True,exist_ok=True);tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(packet,ensure_ascii=False),encoding='utf-8');tmp.replace(output)
    con.close();print(f'Reference ready: {output} ({output.stat().st_size:,} bytes); {len(result)} scopes; no raw identifiers exported.')
    return packet

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.source,a.output)
