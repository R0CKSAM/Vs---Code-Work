"""Additive category attribution: each source row contributes to exactly one tag."""
from collections import OrderedDict,defaultdict
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from threading import Lock
import json,re
from insight_store import analytical_connection
from insights import dates,change

CACHE=OrderedDict();LOCK=Lock()
EDITORIAL={'sports','kids','podcast','entertainment','music','documentaries','news','lifestyle','dharam','bhajan','motor_sports'}
def normalize(value):
    value=re.sub(r'[\s_]+','_',str(value or '').strip().lower())
    return 'unknown' if value in {'','unknown','null','undefined','n/a','na'} else value
def label(key):return 'Unknown / untagged' if key=='unknown' else key.replace('_',' ')
def tag_type(key):return 'Unknown' if key=='unknown' else 'Content-category label' if key in EDITORIAL else 'Placement / collection / campaign label'

def analyze_categories(body,connection,where,export=False):
    where(body);start=date.fromisoformat(body['start']);end=date.fromisoformat(body['end']);length=(end-start).days+1
    if length>366:raise ValueError('Choose up to 366 days')
    old_start=start-timedelta(days=length);old_end=start-timedelta(days=1)
    focus=body.get('category_focus','');search=body.get('category_title_search','');page=body.get('category_page',0)
    host=body.get('category_asset_host','');key=body.get('category_asset_key','')
    if not all(isinstance(v,str) and len(v)<=500 for v in [focus,search,host,key]) or bool(host)!=bool(key):raise ValueError('Invalid category or asset selection')
    search=search.strip()
    if not isinstance(page,int) or isinstance(page,bool) or not 0<=page<=10000:raise ValueError('Invalid title page')
    with analytical_connection(connection) as con:
        columnar=getattr(con,'columnar',False)
        if columnar:expr="CASE WHEN category IS NULL OR lower(trim(category)) IN ('','unknown','null','undefined','n/a','na') THEN 'unknown' ELSE lower(regexp_replace(trim(category),'[\\s_]+','_','g')) END"
        else:con.create_function('category_key',1,normalize,deterministic=True);expr='category_key(category)'
        db=Path(con.execute('PRAGMA database_list').fetchone()[2]);stat=db.stat();cache_key=(str(db),stat.st_mtime_ns,json.dumps(body,sort_keys=True),export)
        with LOCK:
            if cache_key in CACHE:CACHE.move_to_end(cache_key);return deepcopy(CACHE[cache_key])
        loaded={r[0] for r in con.execute('SELECT DISTINCT day FROM events WHERE day BETWEEN ? AND ?',[old_start.isoformat(),end.isoformat()])}
        current_dates=dates(start,end);previous_dates=dates(old_start,old_end);complete=all(d in loaded for d in current_dates);prior_complete=all(d in loaded for d in previous_dates);comparable=complete and prior_complete
        def scope(a,b):return where({**body,'start':a.isoformat(),'end':b.isoformat()})
        def aggregate(a,b):
            w,p=scope(a,b)
            return [dict(r) for r in con.execute("SELECT "+expr+" AS category_key,sum(hours) AS hours,sum(delivered) AS delivered,sum(segments) AS segments,count(DISTINCT CASE WHEN video_key!='Unknown' THEN req_host || '|' || video_key END) AS assets FROM events"+w+' GROUP BY 1',p)]
        current=aggregate(start,end);prior={r['category_key']:r for r in aggregate(old_start,old_end)} if comparable else {}
        total=sum(r['hours'] for r in current);prior_total=sum(r['hours'] for r in prior.values()) if comparable else None
        categories=[];cur={r['category_key']:r for r in current}
        for cat in set(cur)|set(prior):
            row=cur.get(cat,dict(category_key=cat,hours=0,delivered=0,segments=0,assets=0));delta=change(row['hours'],prior.get(cat,{}).get('hours',0)) if comparable else dict(current=row['hours'],previous=None,delta=None,pct=None,change_type='Comparison unavailable')
            categories.append({**row,**delta,'label':label(cat),'tag_type':tag_type(cat),'share_pct':row['hours']/total*100 if total else 0})
        categories.sort(key=lambda r:(-r['hours'],r['category_key']))
        w,p=scope(start,end)
        observed=[dict(r) for r in con.execute('SELECT '+expr+' AS category_key,day,sum(hours) AS hours FROM events'+w+' GROUP BY 1,2',p)]
        day_points={(r['category_key'],r['day']):r['hours'] for r in observed}
        series=[dict(key=r['category_key'],label=r['label'],points=[dict(day=d,value=day_points.get((r['category_key'],d),0) if d in loaded else None) for d in current_dates]) for r in categories]
        # CTE asset totals are unique by host+key: joining them never multiplies hours.
        cte='WITH scoped AS (SELECT *, '+expr+' AS cat FROM events'+w+'''), asset_totals AS (
          SELECT req_host,video_key,sum(hours) AS asset_hours,count(DISTINCT cat) AS category_count,
          max(CASE WHEN title_status='Verified override' THEN title END) AS verified_title,
          max(CASE WHEN raw_title IS NOT NULL AND raw_title NOT IN ('','Unknown') THEN request_ist || '|' || raw_title END) AS latest_label,
          min(title) AS fallback_title FROM scoped GROUP BY req_host,video_key), memberships AS (
          SELECT s.req_host AS host,s.video_key,s.cat AS category_key,sum(s.hours) AS hours,
          a.asset_hours,a.category_count,coalesce(a.verified_title,a.latest_label,a.fallback_title) AS title_evidence,
          max(CASE WHEN a.verified_title IS NOT NULL THEN 1 ELSE 0 END) AS verified
          FROM scoped s JOIN asset_totals a ON s.req_host=a.req_host AND s.video_key=a.video_key
          GROUP BY s.req_host,s.video_key,s.cat,a.asset_hours,a.category_count,a.verified_title,a.latest_label,a.fallback_title)
        '''
        conditions=[];params=list(p)
        if focus:conditions.append('category_key=?');params.append(focus)
        if search:
            conditions.append("(lower(title_evidence) LIKE ? ESCAPE '\\' OR lower(video_key) LIKE ? ESCAPE '\\' OR lower(host) LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM scoped history WHERE history.req_host=memberships.host AND history.video_key=memberships.video_key AND lower(history.raw_title) LIKE ? ESCAPE '\\'))")
            needle='%'+search.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';params.extend([needle]*4)
        condition=' WHERE '+' AND '.join(conditions) if conditions else ''
        count=con.execute(cte+' SELECT count(*) FROM memberships'+condition,params).fetchone()[0]
        page_size=100;actual_page=min(page,max(0,(count-1)//page_size))
        suffix='' if export else ' LIMIT ? OFFSET ?'
        selected=[dict(r) for r in con.execute(cte+' SELECT * FROM memberships'+condition+' ORDER BY hours DESC,host,video_key,category_key'+suffix,params+([] if export else [page_size,actual_page*page_size]))]
        def membership(row):
            evidence=row.pop('title_evidence') or 'Unknown';verified=row.pop('verified')
            row.update(title=evidence.split('|',1)[1] if not verified and re.match(r'^\d{4}-\d{2}-\d{2}[ T]',evidence) and '|' in evidence else evidence,category_label=label(row['category_key']),asset_category_share_pct=row['hours']/row['asset_hours']*100 if row['asset_hours'] else 0,known_asset=row['video_key']!='Unknown')
            return row
        members=[membership(r) for r in selected]
        focus_rows=[membership(dict(r)) for r in con.execute(cte+' SELECT * FROM memberships WHERE host=? AND video_key=? ORDER BY hours DESC,category_key',p+[host,key])] if host else []
        duplicates=con.execute(cte+" SELECT count(*) FROM asset_totals WHERE video_key!='Unknown' AND category_count>1",p).fetchone()[0]
        aliases=[dict(r) for r in con.execute('SELECT '+expr+' AS category_key,category AS raw_label,sum(hours) AS hours FROM events'+w+' GROUP BY 1,2 ORDER BY hours DESC',p)]
        result=dict(kind='categories',backend='columnar' if columnar else 'sqlite',metric='hours',metric_label='Estimated watch hours',comparison_available=comparable,
          period=dict(start=start.isoformat(),end=end.isoformat(),days=length,loaded_days=sum(d in loaded for d in current_dates),complete=complete),
          previous_period=dict(start=old_start.isoformat(),end=old_end.isoformat(),days=length,loaded_days=sum(d in loaded for d in previous_dates),complete=prior_complete),
          summary=change(total,prior_total) if comparable else dict(current=total,previous=None,delta=None,pct=None,change_type='Comparison unavailable'),categories=categories,series=series,
          memberships=members,membership_count=count,page=actual_page,page_size=page_size,category_focus=focus,search=search,asset_focus=focus_rows,multi_category_assets=duplicates,raw_labels=aliases,
          attribution='Each row contributes its estimated hours only to its recorded category. Case/spacing aliases are merged. Asset identity is host + video key; names and SEO aliases do not split an asset. A title shared by different keys is not merged. Unknown keys are unidentified buckets, not confirmed individual assets.',
          limitations=['Source categories include genres, placements, collections and campaigns; no genre is inferred from a title or banner.','Category hours add to the selected total. Asset counts can overlap across categories and must not be added.','Category movement can reflect placement/tagging changes for the same asset; inspect its combined asset hours before interpreting demand.','Asset total hours include every category within the applied master filters; local category selection only narrows the title list.','Changes compare equal complete calendar periods with identical master/time filters; missing dates are chart gaps, not zeros.','Watch hours are request-derived estimates, not verified human watch time.'])
        assert abs(sum(r['hours'] for r in categories)-total)<1e-6
    with LOCK:
        CACHE[cache_key]=deepcopy(result)
        while len(CACHE)>6:CACHE.popitem(last=False)
    return result
