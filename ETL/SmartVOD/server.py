"""SmartVOD: local, read-only analytics server. Run prepare.py first."""
import argparse
import csv
import io
import json
import sqlite3
from datetime import date, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from journey import build_sessions, CONTENT_FIELDS

ROOT = Path(__file__).resolve().parent
FIELDS = {'title': 'Titles', 'category': 'Categories', 'video_key': 'Video keys',
          'device_id': 'Device ID', 'cli_ip': 'Client IP', 'os': 'Operating system',
          'region': 'Region', 'isp': 'ISP / ASN', 'device_type': 'Device type'}


def connection():
    con = sqlite3.connect(f"file:{(ROOT/'data/smartvod.sqlite').as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def where(body, omit=None):
    clauses, params = [], []
    filters = body.get('filters', {})
    if not isinstance(filters, dict):
        raise ValueError('Invalid filters')
    for field, values in filters.items():
        if field not in FIELDS or not isinstance(values, list) or len(values) > 1000:
            raise ValueError('Invalid filter selection')
        if field == omit or not values:
            continue
        if any(not isinstance(v, str) for v in values):
            raise ValueError('Filter values must be text')
        clauses.append(f'{field} IN ({",".join("?" for _ in values)})')
        params.extend(values)
    start, end = body.get('start'), body.get('end')
    if not start or not end or date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('Choose a valid date range')
    clauses.append('day BETWEEN ? AND ?')
    params.extend([start, end])
    lo, hi = body.get('timeStart', '00:00'), body.get('timeEnd', '23:59')
    time.fromisoformat(lo); time.fromisoformat(hi)
    if len(lo) != 5 or len(hi) != 5:
        raise ValueError('Use HH:MM time')
    clauses.append('(clock BETWEEN ? AND ?)' if lo <= hi else '(clock >= ? OR clock <= ?)')
    params.extend([lo, hi])
    return ' WHERE ' + ' AND '.join(clauses), params


def query(body):
    w, p = where(body)
    with connection() as con:
        kpi = dict(con.execute('SELECT count(*) records, coalesce(sum(hours),0) hours, '
            'coalesce(sum(delivered),0) delivered, coalesce(sum(segments),0) segments, '
            "count(DISTINCT nullif(cli_ip,'Unknown')) ips, count(DISTINCT nullif(device_id,'Unknown')) devices, "
            "count(DISTINCT nullif(video_key,'Unknown')) videos FROM events" + w, p).fetchone())
        hourly = [dict(r) for r in con.execute('SELECT substr(clock,1,2) hour,sum(hours) hours FROM events'+w+' GROUP BY 1 ORDER BY 1', p)]
        breakdown = {}
        for field in ('device_type', 'os', 'region', 'isp'):
            breakdown[field] = [dict(r) for r in con.execute(f'SELECT {field} label,sum(hours) hours FROM events'+w+' GROUP BY 1 ORDER BY 2 DESC,1 LIMIT 5', p)]
        table = [dict(r) for r in con.execute('SELECT video_key,title,sum(hours) hours,sum(delivered) delivered,'
            "count(DISTINCT nullif(cli_ip,'Unknown')) ips,count(DISTINCT nullif(device_id,'Unknown')) devices "
            'FROM events'+w+' GROUP BY video_key,title ORDER BY hours DESC,video_key,title LIMIT 100', p)]
    return dict(kpi=kpi, hourly=hourly, breakdown=breakdown, table=table)


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
        files = {'/journey.js': ('journey.js', 'text/javascript'), '/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
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
            path = urlsplit(self.path).path
            if path == '/api/query':
                return self.send(query(body))
            if path == '/api/journey':
                where(body)  # Validate the complete request before changing content scope.
                devices=body.get('filters',{}).get('device_id',[])
                if len(devices)!=1 or devices[0]=='Unknown':
                    return self.send({'sessions':[], 'message':'Select exactly one known Device ID and apply filters to explore its journey.'})
                scope={**body,'filters':{k:v for k,v in body['filters'].items() if k not in CONTENT_FIELDS}}
                w,p=where(scope)
                with connection() as con:
                    rows=[dict(r) for r in con.execute('SELECT * FROM events'+w,p)]
                sessions=build_sessions(rows,body['filters'])
                return self.send({'device_id':devices[0],'sessions':sessions,'matching_sessions':sum(s['matched'] for s in sessions),
                                  'message':'Observed request sequence in the applied date/time and audience filters. Content filters highlight matching sessions; surrounding titles remain visible.'})
            if path == '/api/facet':
                field = body.get('field')
                if field not in FIELDS:
                    raise ValueError('Unknown filter')
                w, p = where(body, omit=field)
                search = str(body.get('search', ''))
                w += f' AND instr(lower({field}),lower(?)) > 0'
                p.append(search)
                offset = max(0, int(body.get('offset', 0)))
                with connection() as con:
                    rows = [dict(r) for r in con.execute(f'SELECT {field} value,count(*) records,sum(segments) segments FROM events'+w+' GROUP BY 1 ORDER BY segments DESC,value DESC LIMIT 101 OFFSET ?', [*p, offset])]
                return self.send({'options': rows[:100], 'more': len(rows)>100})
            if path == '/api/export':
                w, p = where(body)
                output = io.StringIO(newline='')
                writer = csv.writer(output)
                with connection() as con:
                    cur = con.execute('SELECT day date_ist,video_key,title,category,device_type,os,region,isp,'
                        "sum(hours) watch_hours_estimated,sum(delivered) delivered_hours_estimated,count(DISTINCT nullif(cli_ip,'Unknown')) distinct_cliip,"
                        "count(DISTINCT nullif(device_id,'Unknown')) distinct_device_id FROM events"+w+
                        ' GROUP BY day,video_key,title,category,device_type,os,region,isp ORDER BY day,video_key',p)
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
