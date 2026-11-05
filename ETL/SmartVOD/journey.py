"""Observed device request sequences, not player-measured viewing sessions."""
from datetime import datetime

CONTENT_FIELDS=('title','category','video_key')

def build_sessions(rows, filters, gap_minutes=30):
    sessions=[]
    for row in sorted(rows,key=lambda r:(r['request_ist'],r['last_request_ist'],r['req_host'],r['video_key'])):
        start=datetime.fromisoformat(row['request_ist'])
        end=datetime.fromisoformat(row['last_request_ist'])
        matched=all(not filters.get(k) or row[k] in filters[k] for k in CONTENT_FIELDS)
        previous=sessions[-1] if sessions else None
        new=(previous is None or previous['video_key']!=row['video_key'] or previous['host']!=row['req_host']
             or (start-datetime.fromisoformat(previous['end'])).total_seconds()>gap_minutes*60
             or (previous['session_id'] and row['session_id'] and previous['session_id']!=row['session_id']))
        if new:
            sessions.append(dict(index=len(sessions),video_key=row['video_key'],title=row['title'],host=row['req_host'],
                                 start=row['request_ist'],end=row['last_request_ist'],session_id=row['session_id'],
                                 hours=0,segments=0,matched=False,identity_sources=[],overlap=False))
        s=sessions[-1]
        if not s['session_id'] and row['session_id']:
            s['session_id']=row['session_id']
        s['hours']+=row['hours'];s['segments']+=row['segments'];s['matched']|=matched
        if row['last_request_ist']>s['end']:s['end']=row['last_request_ist']
        if row['identity_source'] not in s['identity_sources']:s['identity_sources'].append(row['identity_source'])
        if s['title']=='Unknown' and row['title']!='Unknown':s['title']=row['title']
        if len(sessions)>1 and start<datetime.fromisoformat(sessions[-2]['end']):
            s['overlap']=True;sessions[-2]['overlap']=True
    return sessions
