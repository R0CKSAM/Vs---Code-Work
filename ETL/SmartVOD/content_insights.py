"""Content-first decision support. Asset identity is (host, video key), never title."""
from collections import OrderedDict,defaultdict
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from threading import Lock
import json
from insight_store import analytical_connection
from insights import dates,change,geography
CACHE=OrderedDict();LOCK=Lock()
def action(row,comparable,minimum,days):
    if row['quality_rank']>=2:return ('Verify content label','The asset label is missing or unverified. Title changes and SEO aliases alone do not trigger this check.')
    if row['device_hours'] and row['avg_device_minutes'] is not None and row['avg_device_minutes']>days*1440:return ('Review request activity','Estimated activity per known ID exceeds the calendar capacity of this window. Check retries, shared IDs or parallel activity.')
    if row['hours']>0 and row['identity_coverage_pct']<20:return ('Review identity coverage','Most estimated hours lack a Device ID. Do not interpret low known-ID reach as weak audience demand.')
    if row['hours']>=1 and row['delivery_pct'] is not None and row['delivery_pct']<98:return ('Investigate delivery','Fewer than 98% of estimated segment hours have 2xx delivery. Check response codes before interpreting the demand movement.')
    if not comparable:return ('Establish comparison','A complete preceding calendar period is unavailable. Current rank is observable; growth or decline is not established.')
    if row['previous_hours']==0 and row['hours']>=minimum:return ('Monitor newly observed demand','This asset has activity in the selected range and none in the complete prior range. This is not evidence of its release date.')
    if row['delta_hours'] is not None and row['delta_hours']<=-minimum and row['pct_hours'] is not None and row['pct_hours']<=-20:return ('Investigate demand decline','Material request-derived hours declined. Check event timing, availability, placement changes and delivery; the logs do not establish the cause.')
    if row['delta_hours'] is not None and row['delta_hours']>=minimum and row['pct_hours'] is not None and row['pct_hours']>=20 and row['devices']>=50 and row['identity_coverage_pct']>=50:return ('Test additional promotion','Observed hours are rising materially with at least 50 known IDs and 50% ID-hour coverage. Run a controlled placement test; this does not prove conversion or ROI.')
    return ('Monitor measured demand','Use the asset trend and audience mix to monitor performance. There is no strong rule-based action beyond the checks above.')

def analyze_content(body,connection,where):
    where(body);start=date.fromisoformat(body['start']);end=date.fromisoformat(body['end']);length=(end-start).days+1
    if length>366:raise ValueError('Choose up to 366 days for a content report')
    old_end=start-timedelta(days=1);old_start=start-timedelta(days=length)
    host=body.get('content_host','');key=body.get('content_key','')
    if not isinstance(host,str) or not isinstance(key,str) or len(host)>500 or len(key)>500 or bool(host)!=bool(key):raise ValueError('Choose both asset host and video key')
    level=body.get('geo_level','state')
    if level not in {'country','state','city'}:raise ValueError('Invalid geography level')
    with analytical_connection(connection) as con:
        columnar=getattr(con,'columnar',False);db=Path(con.execute('PRAGMA database_list').fetchone()[2]);stat=db.stat()
        cache_key=(str(db),stat.st_size,stat.st_mtime_ns,json.dumps(dict(start=body['start'],end=body['end'],timeStart=body.get('timeStart','00:00'),timeEnd=body.get('timeEnd','23:59'),filters={k:sorted(set(v)) for k,v in body.get('filters',{}).items() if v},host=host,key=key,level=level),sort_keys=True))
        with LOCK:
            if cache_key in CACHE:CACHE.move_to_end(cache_key);return deepcopy(CACHE[cache_key])
        loaded={r[0] for r in con.execute('SELECT DISTINCT day FROM events INDEXED BY idx_day WHERE day BETWEEN ? AND ?',[min(old_start,end-timedelta(days=7)).isoformat(),end.isoformat()])}
        current_dates=dates(start,end);previous_dates=dates(old_start,old_end);complete=all(d in loaded for d in current_dates);prior_complete=all(d in loaded for d in previous_dates);comparable=complete and prior_complete
        def scope(a,b):return where({**body,'start':a.isoformat(),'end':b.isoformat()})
        def assets(a,b):
            clause,params=scope(a,b)
            sql="SELECT req_host AS host,video_key AS video_key,min(title) AS title,min(title_status) AS title_status,count(DISTINCT nullif(raw_title,'Unknown')) AS title_labels,max(CASE WHEN raw_title IS NOT NULL AND raw_title!='Unknown' AND raw_title!='' THEN request_ist || '|' || raw_title END) AS latest_observed_label,max(CASE title_status WHEN 'Verified override' THEN 0 WHEN 'Consistent log title' THEN 1 WHEN 'Unverified log title' THEN 2 WHEN 'Conflicting log titles' THEN 1 WHEN 'Title history / SEO aliases' THEN 1 WHEN 'Multiple canonical log labels' THEN 1 ELSE 4 END) AS quality_rank,sum(hours) AS hours,sum(delivered) AS delivered,sum(segments) AS segments,count(DISTINCT nullif(device_id,'Unknown')) AS devices,count(DISTINCT nullif(cli_ip,'Unknown')) AS ips,coalesce(sum(CASE WHEN device_id!='Unknown' THEN hours ELSE 0 END),0) AS device_hours,count(DISTINCT day) AS active_days,min(day) AS first_observed,max(day) AS last_observed,sum(CASE WHEN category='Unknown' THEN hours ELSE 0 END) AS missing_category_hours FROM events"
            return [dict(r) for r in con.execute(sql+clause+' GROUP BY req_host,video_key',params)]
        current=assets(start,end);previous=assets(old_start,old_end) if comparable else [];prior={(r['host'],r['video_key']):r for r in previous}
        total_hours=sum(r['hours'] for r in current);prior_hours=sum(r['hours'] for r in previous) if comparable else None;minimum=max(1,total_hours*.005)
        repeat={}
        if length>=2:
            clause,params=scope(start,end)
            repeat={(r['host'],r['video_key']):r['repeated_ids'] for r in con.execute("SELECT host,video_key,count(*) AS repeated_ids FROM (SELECT req_host AS host,video_key,device_id FROM events"+clause+" AND device_id!='Unknown' GROUP BY req_host,video_key,device_id HAVING count(DISTINCT day)>=2) grouped_ids GROUP BY host,video_key",params)}
        rows=[]
        for r in current:
            r['snapshot_title']=r['title']
            observed=r.pop('latest_observed_label',None)
            if observed and r['quality_rank']!=0:r['title']=observed.split('|',1)[1]
            r['label_source']='Verified snapshot override' if r['quality_rank']==0 else 'Latest observed request label in selected data' if observed else 'Snapshot asset label'
            if r['title_status'] in {'Conflicting log titles','Multiple canonical log labels','Title history / SEO aliases'} or (r['title_labels']>1 and r['quality_rank']==1):r['title_status']='Title history / SEO aliases'
            identity=(r['host'],r['video_key']);old=prior.get(identity);delta=change(r['hours'],old['hours'] if old else 0)
            r.update(previous_hours=delta['previous'] if comparable else None,delta_hours=delta['delta'] if comparable else None,pct_hours=delta['pct'] if comparable else None,previous_devices=old['devices'] if old else 0 if comparable else None,
                avg_device_minutes=r['device_hours']*60/r['devices'] if r['devices'] else None,identity_coverage_pct=r['device_hours']/r['hours']*100 if r['hours'] else 0,
                delivery_pct=r['delivered']/r['hours']*100 if r['hours'] else None,share_hours=r['hours']/total_hours*100 if total_hours else 0,
                repeat_ids=repeat.get(identity,0) if length>=2 else None,repeat_id_pct=repeat.get(identity,0)/r['devices']*100 if length>=2 and r['devices'] else None,
                hours_per_active_day=r['hours']/r['active_days'] if r['active_days'] else None)
            r['action'],r['reason']=action(r,comparable,minimum,length);rows.append(r)
        rows.sort(key=lambda r:(-r['hours'],r['host'],r['video_key']))
        # Disappeared assets remain visible in the decision worklist.
        current_keys={(r['host'],r['video_key']) for r in rows}
        disappeared=[]
        for old in previous:
            if (old['host'],old['video_key']) not in current_keys and old['hours']>=minimum:
                disappeared.append(dict(host=old['host'],video_key=old['video_key'],title=old['title'],title_status=old['title_status'],hours=0,previous_hours=old['hours'],delta_hours=-old['hours'],pct_hours=-100,action='Check disappeared activity',reason='No matching requests in the complete current period. Check availability and event lifecycle before treating this as content failure.'))
        disappeared.sort(key=lambda r:r['delta_hours'])
        focus=next((r for r in rows if r['host']==host and r['video_key']==key),None) if host else (rows[0] if rows else None)
        details=None
        if focus:
            def focused(a,b):
                clause,params=scope(a,b);return clause+' AND req_host=? AND video_key=?',params+[focus['host'],focus['video_key']]
            context_start=min(start,end-timedelta(days=7),old_start if comparable else start)
            clause,params=focused(context_start,end)
            points={r['day']:r['hours'] for r in con.execute('SELECT day,sum(hours) AS hours FROM events'+clause+' GROUP BY day',params)}
            daily=[dict(day=d,value=points.get(d,0) if d in loaded else None) for d in dates(context_start,end)]
            clause,params=focused(start,end)
            if columnar:geo="concat_ws(' / ',"+','.join(f"coalesce(nullif(trim(split_part(region,' / ',{i})),''),'Unknown')" for i in range(1,{'country':1,'state':2,'city':3}[level]+1))+')'
            else:con.create_function('content_geo',1,lambda v:geography(v,level),deterministic=True);geo='content_geo(region)'
            mix={}
            for field,expression in [('region',geo),('device_type','device_type'),('os','os'),('isp','isp'),('source_category','category')]:
                mix[field]=[dict(r) for r in con.execute('SELECT '+expression+' AS label,sum(hours) AS hours FROM events'+clause+' GROUP BY 1 ORDER BY hours DESC,label LIMIT 5',params)]
            history=[dict(r) for r in con.execute("SELECT raw_title AS title,min(request_ist) AS first_seen,max(request_ist) AS last_seen FROM events WHERE req_host=? AND video_key=? AND day<=? AND raw_title IS NOT NULL AND raw_title!='Unknown' AND raw_title!='' GROUP BY raw_title ORDER BY last_seen DESC,title LIMIT 100",[focus['host'],focus['video_key'],end.isoformat()])]
            details=dict(asset=focus,daily=daily,mix=mix,title_history=history)
        quality=dict(label_review_hours=sum(r['hours'] for r in rows if r['quality_rank']>=2),missing_category_hours=sum(r['missing_category_hours'] for r in rows),missing_device_hours=sum(r['hours']-r['device_hours'] for r in rows))
        action_counts={name:sum(r['action']==name for r in rows) for name in sorted({r['action'] for r in rows})}
        opportunities=sorted([r for r in rows if r['action']=='Test additional promotion'],key=lambda r:-r['delta_hours'])[:10]
        declines=sorted([r for r in rows if r['delta_hours'] is not None and r['delta_hours']<=-minimum],key=lambda r:r['delta_hours'])[:10]
        worklist={(r['host'],r['video_key']):r for r in rows[:100]+opportunities+declines}
        shortlist=sorted(worklist.values(),key=lambda r:(-r['hours'],r['host'],r['video_key']))
        result=dict(kind='content',backend='columnar' if columnar else 'sqlite',metric='hours',metric_label='Estimated watch hours',comparison_available=comparable,
            period=dict(start=start.isoformat(),end=end.isoformat(),days=length,loaded_days=sum(d in loaded for d in current_dates),complete=complete),
            previous_period=dict(start=old_start.isoformat(),end=old_end.isoformat(),days=length,loaded_days=sum(d in loaded for d in previous_dates),complete=prior_complete),
            summary=change(total_hours,prior_hours) if comparable else dict(current=total_hours if any(d in loaded for d in current_dates) else None,previous=None,delta=None,pct=None,change_type='Comparison unavailable'),
            asset_count=len(rows),assets=shortlist,action_counts=action_counts,opportunities=opportunities,declines=declines,disappeared=disappeared[:50],focus=details,
            quality={**quality,**{k.replace('_hours','_pct'):v/total_hours*100 if total_hours else None for k,v in quality.items()}},
            rules=dict(material_hours=minimum,change_percent=20,promotion_min_ids=50,promotion_min_identity_pct=50,review_identity_below_pct=20,delivery_review_below_pct=98),
            limitations=['Assets are host plus video key; titles are log-derived labels.','Watch hours and minutes per known ID are request-based estimates, not actual session duration or completion.','Repeat IDs means activity on two or more selected dates, not verified repeat views or people.','First observed date is not publication date; per-active-day hours are not availability-normalised.','Source category can be a placement or campaign tag, not a verified genre.','The VOD export classification is not a substitute for an authoritative VOD/live/replay catalogue.','No impressions, clicks, content runtime, publication schedule, costs or revenue are available here; CTR, completion, ROI and acquisition causality cannot be determined.','Promotion candidates are hypotheses for controlled tests, not automatic budget or catalogue decisions.'])
    with LOCK:
        CACHE[cache_key]=deepcopy(result);CACHE.move_to_end(cache_key)
        while len(CACHE)>6:CACHE.popitem(last=False)
    return result
