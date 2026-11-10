"""Deterministic, filter-scoped stakeholder insights over read-only snapshots."""
from collections import OrderedDict,defaultdict
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from statistics import median
from threading import Lock
import json,math
from insight_store import analytical_connection

CACHE=OrderedDict();LOCK=Lock();LIMIT=6
METRICS={'hours':('Estimated watch hours','sum(hours)',1.0),
         'devices':('Known Device IDs',"count(DISTINCT nullif(device_id,'Unknown'))",10.0),
         'ips':('Known client IPs',"count(DISTINCT nullif(cli_ip,'Unknown'))",10.0)}
DIMENSIONS={'device_type','os','isp','title','category'}
def dates(start,end):
    return [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
def geography(value,level):
    parts=[s.strip() or 'Unknown' for s in str(value or '').split(' / ')]
    parts=(parts+['Unknown']*3)[:3]
    return ' / '.join(parts[:{'country':1,'state':2,'city':3}[level]])
def unknown(label):return any(p.strip().lower() in {'unknown','unknown / na','n/a',''} for p in label.split(' / '))
def change(current,previous):
    delta=current-previous
    return dict(current=current,previous=previous,delta=delta,pct=delta/previous*100 if previous else None,
                change_type='New activity' if previous==0 and current>0 else 'No activity' if not previous and not current else 'Increase' if delta>0 else 'Decrease' if delta<0 else 'Unchanged')
def anomaly(value,history,floor):
    if len(history)<4:return None
    base=median(history);mad=median(abs(v-base) for v in history)
    scale=max(1.4826*mad,abs(base)*.1,floor/3)
    score=abs(value-base)/scale
    if abs(value-base)<floor or score<3 or (base and abs(value-base)/base<.3):return None
    return dict(**change(value,base),score=score,baseline_median=base,baseline_mad=mad,baseline_days=len(history),direction='Rise' if value>base else 'Drop')

def analyze(body,connection,where):
    w,_=where(body)
    metric=body.get('insight_metric','hours');level=body.get('geo_level','state');dimension=body.get('insight_dimension','device_type');basis=body.get('viewer_basis','device_id')
    if metric not in METRICS or level not in {'country','state','city'} or dimension not in DIMENSIONS or basis not in {'device_id','cli_ip'}:raise ValueError('Invalid insight controls')
    title,aggregate,min_abs=METRICS[metric]
    start=date.fromisoformat(body['start']);end=date.fromisoformat(body['end']);length=(end-start).days+1
    if length>366:raise ValueError('Choose up to 366 days for an insight report')
    prev_end=start-timedelta(days=1);prev_start=start-timedelta(days=length);history_start=end-timedelta(days=7)
    with analytical_connection(connection) as con:
        canonical=dict(start=body['start'],end=body['end'],timeStart=body.get('timeStart','00:00'),timeEnd=body.get('timeEnd','23:59'),filters={k:sorted(set(v)) for k,v in body.get('filters',{}).items() if v},metric=metric,level=level,dimension=dimension,basis=basis)
        db=Path(con.execute('PRAGMA database_list').fetchone()[2]);stat=db.stat();key=(str(db),stat.st_size,stat.st_mtime_ns,json.dumps(canonical,sort_keys=True))
        with LOCK:
            if key in CACHE:CACHE.move_to_end(key);return deepcopy(CACHE[key])
        loaded={r[0] for r in con.execute('SELECT DISTINCT day FROM events INDEXED BY idx_day WHERE day BETWEEN ? AND ?',[min(prev_start,history_start,start).isoformat(),end.isoformat()])}
        current_days=dates(start,end);previous_days=dates(prev_start,prev_end);history_days=dates(history_start,end-timedelta(days=1))
        current_complete=all(d in loaded for d in current_days);previous_complete=all(d in loaded for d in previous_days);comparable=current_complete and previous_complete
        def scope(a,b):return where({**body,'start':a.isoformat(),'end':b.isoformat()})
        columnar=getattr(con,'columnar',False)
        if not columnar:con.create_function('insight_geo',1,lambda v:geography(v,level),deterministic=True)
        def period(a,b,group=None):
            clause,params=scope(a,b)
            cols=(group+' AS label,' if group else '')+aggregate+' AS "value",sum(hours) AS hours,sum(segments) AS segments,'+"count(DISTINCT nullif(device_id,'Unknown')) AS devices,count(DISTINCT nullif(cli_ip,'Unknown')) AS ips"
            if not group:cols+=",coalesce(sum(CASE WHEN device_id!='Unknown' THEN hours ELSE 0 END),0) AS device_hours,coalesce(sum(CASE WHEN cli_ip!='Unknown' THEN hours ELSE 0 END),0) AS ip_hours"
            return [dict(r) for r in con.execute('SELECT '+cols+' FROM events'+clause+(' GROUP BY 1' if group else ''),params)]
        overall=period(start,end)[0];prior=period(prev_start,prev_end)[0] if comparable else None
        overall={k:(v or 0) for k,v in overall.items()}
        geo="concat_ws(' / ',"+','.join(f"coalesce(nullif(trim(split_part(region,' / ',{i})),''),'Unknown')" for i in range(1,{'country':1,'state':2,'city':3}[level]+1))+')' if columnar else 'insight_geo(region)'
        regions=period(start,end,geo);previous={r['label']:r for r in period(prev_start,prev_end,geo)} if comparable else {}
        current={r['label']:r for r in regions}
        region_rows=[]
        for label in current.keys()|previous.keys():
            row=current.get(label,{});old=previous.get(label,{})
            region_rows.append(dict(label=label,**change(row.get('value',0),old.get('value',0)),hours=row.get('hours',0),devices=row.get('devices',0),ips=row.get('ips',0),unknown=unknown(label),comparison_available=comparable))
        region_rows.sort(key=lambda r:(-r['current'],r['label']))
        material=max(min_abs,overall['value']*.005)
        movers=[r for r in region_rows if comparable and not r['unknown'] and abs(r['delta'])>=material and (r['pct'] is None or abs(r['pct'])>=20)]
        movers.sort(key=lambda r:-abs(r['delta']))
        clause,params=scope(min(start,history_start),end)
        daily=[dict(r) for r in con.execute('SELECT day,'+geo+' AS label,'+aggregate+' AS "value" FROM events'+clause+' GROUP BY 1,2 ORDER BY 1,2',params)]
        per_region=defaultdict(dict)
        for row in daily:per_region[row['label']][row['day']]=row['value']
        valid_history=[d for d in history_days if d in loaded]
        alerts=[]
        if end.isoformat() in loaded:
            for label,values in per_region.items():
                if unknown(label):continue
                found=anomaly(values.get(end.isoformat(),0),[values.get(d,0) for d in valid_history],min_abs)
                if found:alerts.append(dict(label=label,day=end.isoformat(),**found))
        alerts.sort(key=lambda r:-abs(r['delta']))
        current_dimension=period(start,end,dimension);old_dimension={r['label']:r['value'] for r in period(prev_start,prev_end,dimension)} if comparable else {}
        drivers=[dict(label=r['label'],**change(r['value'],old_dimension.get(r['label'],0)),comparison_available=comparable) for r in current_dimension]
        current_labels={r['label'] for r in drivers}
        for label,value in old_dimension.items():
            if label not in current_labels:drivers.append(dict(label=label,**change(0,value),comparison_available=comparable))
        drivers.sort(key=lambda r:-abs(r['delta']) if comparable else -r['current'])
        clause,params=scope(start,end)
        leaders=[dict(r) for r in con.execute(f"SELECT {basis} AS identifier,sum(hours) AS hours,sum(segments) AS segments,count(DISTINCT day) AS active_days,count(DISTINCT video_key) AS titles,count(DISTINCT nullif(cli_ip,'Unknown')) AS ips,count(DISTINCT nullif(device_id,'Unknown')) AS devices FROM events"+clause+f" AND {basis}!='Unknown' GROUP BY 1 ORDER BY hours DESC,identifier LIMIT 100",params)]
        for row in leaders:row.update(share=row['hours']/overall['hours']*100 if overall['hours'] else 0,high_activity=row['hours']>24*row['active_days'])
        coverage={k:overall[k] for k in ('device_hours','ip_hours')}
        unknown_hours=sum(r['hours'] for r in regions if unknown(r['label']))
        selected={r['label'] for r in region_rows[:100]}|{r['label'] for r in movers[:100]}|{r['label'] for r in alerts[:100]}
        series=[dict(label=label,points=[dict(day=d,value=per_region[label].get(d,0) if d in loaded else None) for d in dates(min(start,history_start),end)]) for label in sorted(selected)]
        if metric=='hours':
            overall_daily=defaultdict(float)
            for r in daily:overall_daily[r['day']]+=r['value']
        else:
            clause,params=scope(min(start,history_start),end)
            overall_daily={r['day']:r['value'] for r in con.execute('SELECT day,'+aggregate+' AS "value" FROM events'+clause+' GROUP BY 1',params)}
        trend=[dict(day=d,value=overall_daily.get(d,0) if d in loaded else None) for d in dates(min(start,history_start),end)]
    summary=change(overall['value'],prior['value'] or 0) if comparable else dict(current=overall['value'] if any(d in loaded for d in current_days) else None,previous=None,delta=None,pct=None,change_type='Comparison unavailable')
    result=dict(backend='columnar' if columnar else 'sqlite',metric=metric,metric_label=title,geo_level=level,dimension=dimension,viewer_basis=basis,
        period=dict(start=start.isoformat(),end=end.isoformat(),days=length,loaded_days=sum(d in loaded for d in current_days),complete=current_complete),
        previous_period=dict(start=prev_start.isoformat(),end=prev_end.isoformat(),days=length,loaded_days=sum(d in loaded for d in previous_days),complete=previous_complete),
        comparison_available=comparable,summary=summary,totals=overall,trend=trend,regions=region_rows[:100],region_count=len(region_rows),region_series=series,
        movers=movers[:100],mover_count=len(movers),alerts=alerts[:100],alert_count=len(alerts),anomaly_available=end.isoformat() in loaded and len(valid_history)>=4,drivers=drivers[:100],leaders=leaders,
        quality=dict(unknown_geo_hours=unknown_hours,unknown_geo_pct=unknown_hours/overall['hours']*100 if overall['hours'] else 0,**coverage),
        rules=dict(material_change_minimum=material,period_percent=20,anomaly_percent=30,anomaly_score=3,anomaly_minimum=min_abs,anomaly_history_days=len(valid_history),anomaly_required_days=4),
        limitations=['Request-derived estimates, not measured playback or verified people.','Distinct IDs and IPs are not additive across dates or regions.','Movement describes an association; it does not establish a cause.','Anomaly rules are screening thresholds, not significance tests or predictions; they do not adjust for weekdays or event schedules.','Loaded-day coverage checks snapshot presence; it does not prove complete source logs or normal delivery.','Identity inference, shared IPs, automated traffic and incomplete geography can affect results.'])
    # Missing periods never become fabricated zero baselines in the response.
    if not comparable:
        for row in result['regions']+result['drivers']:row.update(previous=None,delta=None,pct=None,change_type='Comparison unavailable')
    with LOCK:
        CACHE[key]=deepcopy(result);CACHE.move_to_end(key)
        while len(CACHE)>LIMIT:CACHE.popitem(last=False)
    return result
