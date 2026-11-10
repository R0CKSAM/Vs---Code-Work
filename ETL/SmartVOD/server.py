"""SmartVOD: local, read-only analytics server. Run prepare.py first."""
import argparse
import csv
import io
import json
import sqlite3
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from contextlib import contextmanager
from datetime import date, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from journey import build_sessions, CONTENT_FIELDS
from insights import analyze

ROOT = Path(__file__).resolve().parent
QUERY_CACHE = OrderedDict()
QUERY_CACHE_LOCK = Lock()
QUERY_CACHE_LIMIT = 8
FIELDS = {'title': 'Titles', 'category': 'Categories', 'video_key': 'Video keys',
          'device_id': 'Device ID', 'cli_ip': 'Client IP', 'os': 'Operating system',
          'region': 'Region', 'isp': 'ISP / ASN', 'device_type': 'Device type',
          'identity_confidence':'Identity confidence','title_status':'Title quality'}


@contextmanager
def connection():
    meta=json.loads((ROOT/'data/manifest.json').read_text())
    database=ROOT/'data'/meta.get('database','smartvod.sqlite')
    con = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def where(body, omit=None):
    identity_basis(body)
    clauses, params = [], []
    filters = body.get('filters', {})
    if not isinstance(filters, dict):
        raise ValueError('Invalid filters')
    for field, values in filters.items():
        if field not in FIELDS or not isinstance(values, list) or len(values) > 1000:
            raise ValueError('Invalid filter selection')
        if any(not isinstance(v, str) for v in values):
            raise ValueError('Filter values must be text')
        if field == omit or not values:
            continue
        clauses.append(f'{field} IN ({",".join("?" for _ in values)})')
        params.extend(values)
    start, end = body.get('start'), body.get('end')
    if not isinstance(start,str) or not isinstance(end,str) or len(start)!=10 or len(end)!=10 or date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('Choose a valid date range')
    clauses.append('day BETWEEN ? AND ?')
    params.extend([start, end])
    lo, hi = body.get('timeStart', '00:00'), body.get('timeEnd', '23:59')
    time.fromisoformat(lo); time.fromisoformat(hi)
    if len(lo) != 5 or len(hi) != 5:
        raise ValueError('Use HH:MM time')
    clauses.append('(clock BETWEEN ? AND ?)' if lo <= hi else '(clock >= ? OR clock <= ?)')
    params.extend([lo, hi])
    # Broad, skewed values (Unknown/title quality/OS) otherwise scan all history.
    # Known device/IP lookups stay selective; other filters start from the date slice.
    index='idx_day'
    if omit!='device_id' and filters.get('device_id') and 'Unknown' not in filters['device_id']:
        index='idx_device_day'
    elif omit!='cli_ip' and filters.get('cli_ip') and 'Unknown' not in filters['cli_ip']:
        index='idx_cli_ip'
    return ' INDEXED BY '+index+' WHERE ' + ' AND '.join(clauses), params


def query(body):
    basis=identity_basis(body)
    avg=f"sum(CASE WHEN {basis}!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif({basis},'Unknown')),0)"
    averages=','.join(f"sum(CASE WHEN {field}!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif({field},'Unknown')),0) average_{label}_minutes" for field,label in [('device_id','device'),('cli_ip','ip')])
    w, p = where(body)
    with connection() as con:
        database=Path(con.execute('PRAGMA database_list').fetchone()[2])
        stat=database.stat()
        cache_key=(str(database),stat.st_size,stat.st_mtime_ns,json.dumps(body,sort_keys=True))
        with QUERY_CACHE_LOCK:
            if cache_key in QUERY_CACHE:
                QUERY_CACHE.move_to_end(cache_key)
                return deepcopy(QUERY_CACHE[cache_key])
        kpi = dict(con.execute('SELECT count(*) records, coalesce(sum(hours),0) hours, '
            'coalesce(sum(delivered),0) delivered, coalesce(sum(segments),0) segments, '
            "count(DISTINCT nullif(cli_ip,'Unknown')) ips, count(DISTINCT nullif(device_id,'Unknown')) devices, "
            "count(DISTINCT nullif(video_key,'Unknown')) videos FROM events" + w, p).fetchone())
        kpi.update(dict(con.execute('SELECT '+averages+' FROM events'+w,p).fetchone()))
        kpi['average_watch_minutes']=kpi['average_device_minutes' if basis=='device_id' else 'average_ip_minutes']
        has_status=any(r[1]=='status_code' for r in con.execute('PRAGMA table_info(events)'))
        delivery_statuses=[dict(r) for r in con.execute('SELECT status_code code,sum(segments) requests,sum(hours) hours FROM events'+w+' GROUP BY status_code ORDER BY requests DESC,code DESC',p)] if has_status else []
        hourly = [dict(r) for r in con.execute('SELECT substr(clock,1,2) hour,sum(hours) hours FROM events'+w+' GROUP BY 1 ORDER BY 1', p)]
        trend_dates=[r[0] for r in con.execute('SELECT DISTINCT day FROM events INDEXED BY idx_day WHERE day BETWEEN ? AND ? ORDER BY day',[body['start'],body['end']])]
        hourly_by_day=[dict(r) for r in con.execute('SELECT day,substr(clock,1,2) hour,sum(hours) hours FROM events'+w+' GROUP BY 1,2 ORDER BY 1,2',p)]
        breakdown = {}
        breakdown_trends={}
        for field in ('device_type', 'os', 'region', 'isp'):
            breakdown[field] = [dict(r) for r in con.execute(f'SELECT {field} label,sum(hours) hours FROM events'+w+' GROUP BY 1 ORDER BY 2 DESC,1 LIMIT 5', p)]
            labels=[row['label'] for row in breakdown[field]]
            breakdown_trends[field]=[dict(r) for r in con.execute(f'SELECT day,substr(clock,1,2) hour,{field} label,sum(hours) hours FROM events'+w+f' AND {field} IN ({",".join("?" for _ in labels)}) GROUP BY 1,2,3 ORDER BY 1,2,3',p+labels)] if labels else []
        table = [dict(r) for r in con.execute('SELECT '+avg+' average_watch_minutes,'+averages+',video_key,title,req_host,title_status,sum(hours) hours,sum(delivered) delivered,'
            "count(DISTINCT nullif(cli_ip,'Unknown')) ips,count(DISTINCT nullif(device_id,'Unknown')) devices "
            'FROM events'+w+' GROUP BY video_key,title,req_host,title_status ORDER BY hours DESC,video_key,title LIMIT 100', p)]
        explorers={field:[dict(r) for r in con.execute(f"SELECT {field} identity_value,sum(hours) hours,count(DISTINCT video_key) videos,group_concat(DISTINCT identity_confidence) confidence FROM events"+w+f" AND {field}!='Unknown' GROUP BY {field} ORDER BY hours DESC,{field} LIMIT 20",p)] for field in ('device_id','cli_ip')}
    result=dict(trend_dates=trend_dates,hourly_by_day=hourly_by_day,breakdown_trends=breakdown_trends,delivery_statuses=delivery_statuses,delivery_status_available=has_status,kpi=kpi, hourly=hourly, breakdown=breakdown, table=table,devices=explorers[basis],explorers=explorers,identity_basis=basis)
    with QUERY_CACHE_LOCK:
        QUERY_CACHE[cache_key]=deepcopy(result)
        QUERY_CACHE.move_to_end(cache_key)
        while len(QUERY_CACHE)>QUERY_CACHE_LIMIT:
            QUERY_CACHE.popitem(last=False)
    return result


def identity_basis(body):
    value=body.get('identity_basis','device_id')
    if value not in ('device_id','cli_ip'):raise ValueError('Choose Device ID or Client IP as identity basis')
    return value


def journey_data(body):
    where(body)
    basis=identity_basis(body)
    label='Device ID' if basis=='device_id' else 'Client IP'
    devices=body.get('filters',{}).get(basis,[])
    if len(devices)!=1 or devices[0]=='Unknown':
        return {'sessions':[], 'identity_basis':basis,'message':f'Select exactly one known {label} and apply filters to explore its journey.'}
    scope={**body,'filters':{k:v for k,v in body['filters'].items() if k not in CONTENT_FIELDS}}
    w,p=where(scope)
    with connection() as con:rows=[dict(r) for r in con.execute('SELECT * FROM events'+w,p)]
    sessions=build_sessions(rows,body['filters'])
    return {basis:devices[0],'identity_value':devices[0],'identity_basis':basis,'sessions':sessions,'matching_sessions':sum(s['matched'] for s in sessions),
            'message':('Client IP activity may combine multiple viewers behind a shared address. ' if basis=='cli_ip' else '')+'Observed request sequence in the applied filters. Content filters highlight matches; surrounding titles remain visible.'}


def csv_bytes(headers,rows):
    output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(headers)
    for row in rows:
        writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for v in row])
    return output.getvalue().encode('utf-8-sig')


class Handler(BaseHTTPRequestHandler):
    def send(self, data, mime='application/json', code=200, filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/meta':
            return self.send(json.loads((ROOT/'data/manifest.json').read_text()))
        if path == '/api/title-review':
            meta=json.loads((ROOT/'data/manifest.json').read_text())
            return self.send((ROOT/'data'/meta['title_review']).read_bytes(),filename='smartvod_title_review.json')
        files = {'/date-range.js': ('date-range.js','text/javascript'), '/flatpickr.min.js': ('flatpickr.min.js','text/javascript'), '/flatpickr.min.css': ('flatpickr.min.css','text/css'), '/workspace.js': ('workspace.js','text/javascript'), '/journey.js': ('journey.js', 'text/javascript'), '/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        files['/layout.js']=('layout.js','text/javascript')
        files['/trends.js']=('trends.js','text/javascript')
        files['/insights.js']=('insights.js','text/javascript')
        if path not in files:
            return self.send({'error': 'Not found'}, code=404)
        name, mime = files[path]
        self.send((ROOT/'web'/name).read_bytes(), mime)

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 1000000:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body,dict):
                raise ValueError('Request must be a JSON object')
            path = urlsplit(self.path).path
            if path == '/api/insights':
                return self.send(analyze(body,connection,where))
            if path == '/api/insights-export':
                data=analyze(body,connection,where)
                headers=['section','label','metric','current','previous','change','change_pct','current_start','current_end','previous_start','previous_end','comparison_available','baseline_kind','baseline_loaded_days']
                summary=data['summary']
                rows=[['summary','All applied filters',data['metric'],summary['current'],summary['previous'],summary['delta'],summary['pct'],data['period']['start'],data['period']['end'],data['previous_period']['start'],data['previous_period']['end'],data['comparison_available'],'previous_equal_calendar_period',data['previous_period']['loaded_days']]]
                for section in ['regions','movers','alerts','drivers']:
                    for r in data[section]:
                        alert=section=='alerts';target=date.fromisoformat(data['period']['end'])
                        rows.append([section,r['label'],data['metric'],r['current'],r['previous'],r['delta'],r['pct'],r['day'] if alert else data['period']['start'],data['period']['end'],(target-timedelta(days=7)).isoformat() if alert else data['previous_period']['start'],(target-timedelta(days=1)).isoformat() if alert else data['previous_period']['end'],True if alert else data['comparison_available'],'prior_7_loaded_dates_median' if alert else 'previous_equal_calendar_period',r['baseline_days'] if alert else data['previous_period']['loaded_days']])
                for r in data['leaders']:rows.append(['top_'+data['viewer_basis'],r['identifier'],'hours',r['hours'],None,None,None,data['period']['start'],data['period']['end'],None,None,False,'not_applicable',None])
                return self.send(csv_bytes(headers,rows),'text/csv; charset=utf-8',filename='smartvod_insights.csv')
            if path == '/api/query':
                return self.send(query(body))
            if path == '/api/journey-export':
                data=journey_data(body)
                if not data.get('identity_value'):raise ValueError(data['message'])
                headers=['identity_basis','identity_value','session','video_key','title','host','first_request_ist','last_request_ist','watch_minutes_estimated','segments','identity_confidence','title_quality','content_match','overlapping_activity']
                rows=[[data['identity_basis'],data['identity_value'],s['index']+1,s['video_key'],s['title'],s['host'],s['start'],s['end'],round(s['hours']*60,6),s['segments'],'; '.join(s['identity_confidences']),'; '.join(s['title_statuses']),s['matched'],s['overlap']] for s in data['sessions']]
                return self.send(csv_bytes(headers,rows),'text/csv; charset=utf-8',filename='smartvod_viewer_journey.csv')
            if path == '/api/journey':
                return self.send(journey_data(body))
            if path == '/api/facet':
                field = body.get('field')
                if field not in FIELDS:
                    raise ValueError('Unknown filter')
                w, p = where(body, omit=field)
                search = str(body.get('search', ''))
                w += f' AND instr(lower({field}),lower(?)) > 0'
                p.append(search)
                offset = max(0, int(body.get('offset', 0)))
                sorts={'segments':'segments DESC,value DESC','hours':'hours DESC,value DESC','alpha_asc':'value COLLATE NOCASE ASC,value ASC','alpha_desc':'value COLLATE NOCASE DESC,value DESC'}
                order=sorts.get(body.get('sort','segments'))
                if not order:raise ValueError('Unknown sort mode')
                with connection() as con:
                    rows = [dict(r) for r in con.execute(f'SELECT {field} value,count(*) records,sum(segments) segments,sum(hours) hours FROM events'+w+f' GROUP BY 1 ORDER BY {order} LIMIT 101 OFFSET ?', [*p, offset])]
                return self.send({'options': rows[:100], 'more': len(rows)>100})
            if path == '/api/export':
                basis=identity_basis(body)
                w, p = where(body)
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                with connection() as con:
                    cur = con.execute(f"SELECT '{basis}' identity_basis,sum(CASE WHEN {basis}!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif({basis},'Unknown')),0) average_watch_minutes,"
                        "sum(CASE WHEN device_id!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif(device_id,'Unknown')),0) average_device_minutes,"
                        "sum(CASE WHEN cli_ip!='Unknown' THEN hours*60 ELSE 0 END)/nullif(count(DISTINCT nullif(cli_ip,'Unknown')),0) average_ip_minutes,"
                        "day date_ist,video_key,title,req_host,title_status,identity_confidence,category,device_type,os,region,isp,"
                        "sum(hours) watch_hours_estimated,sum(delivered) delivered_hours_estimated,count(DISTINCT nullif(cli_ip,'Unknown')) distinct_cliip,"
                        "count(DISTINCT nullif(device_id,'Unknown')) distinct_device_id FROM events"+w+
                        ' GROUP BY day,video_key,title,req_host,title_status,identity_confidence,category,device_type,os,region,isp ORDER BY day,video_key',p)
                    writer.writerow([c[0] for c in cur.description])
                    for row in cur:
                        writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for v in row])
                return self.send(output.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8', filename='smartvod_filtered.csv')
            self.send({'error':'Not found'}, code=404)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.send({'error':str(exc)}, code=400)
        except Exception:
            self.send({'error':'Query failed. Check the server log.'},code=500)
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    print(f'SmartVOD: http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
