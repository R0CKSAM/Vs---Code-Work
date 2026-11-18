"""Local-only device/IP explorer. Run with the workspace Python environment."""
from __future__ import annotations
import argparse,csv,io,json,os,time
from datetime import date,datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import duckdb

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[1]
INVALID="('','unknown','null','none','nan','-','0','na','n/a')"
VERSION=1

def build(source,cache):
    source=Path(source).resolve();cache=Path(cache).resolve();cache.parent.mkdir(parents=True,exist_ok=True)
    stat=source.stat();fingerprint={'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'version':VERSION}
    if cache.exists():
        try:
            c=duckdb.connect(str(cache),read_only=True);old=json.loads(c.execute('SELECT data FROM metadata').fetchone()[0]);c.close()
            if old['fingerprint']==fingerprint:return old
        except duckdb.Error:pass
    temp=cache.with_name(cache.stem+'.building.duckdb')
    # A prior interrupted build is not a valid database. Keep it for inspection.
    if temp.exists():temp=temp.with_name(cache.stem+f'.building-{int(time.time())}.duckdb')
    started=time.monotonic();c=duckdb.connect(str(temp));c.execute("SET threads=4");c.execute("SET memory_limit='2GB'")
    c.read_parquet(str(source)).create_view('r')
    fields=[x[0] for x in c.execute('DESCRIBE r').fetchall()]
    print('Building observations from source snapshot…',flush=True)
    c.execute(f'''CREATE TABLE observations AS SELECT cast(ist_date AS DATE) dt,
      CASE WHEN lower(trim(coalesce(device_id,''))) IN {INVALID} THEN NULL ELSE trim(device_id) END dev,
      CASE WHEN lower(trim(coalesce(cli_ip,''))) IN {INVALID} THEN NULL ELSE trim(cli_ip) END ip,
      coalesce("Event Name",'') event_name,coalesce("Match Name",'') match_name,coalesce(ReqHost,'') host,
      coalesce(country,'') country,coalesce(state,'') region,coalesce("Device Type",'') device_type,
      coalesce("OS Type",'') os_type,coalesce(ISP,'') isp,raw_ts_requests ts_requests FROM r''')
    print('Building date and relationship tables…',flush=True)
    c.execute('CREATE TABLE device_day AS SELECT DISTINCT dt,dev FROM observations WHERE dev IS NOT NULL')
    c.execute('CREATE TABLE first_seen AS SELECT dev,min(dt) first_dt,max(dt) last_dt,count(*) active_dates FROM device_day GROUP BY 1')
    c.execute('CREATE TABLE links AS SELECT dev,ip,min(dt) first_dt,max(dt) last_dt,count(distinct dt) active_dates FROM observations WHERE dev IS NOT NULL AND ip IS NOT NULL GROUP BY 1,2')
    c.execute('CREATE TABLE device_profile AS SELECT f.*,coalesce(p.ip_count,0) ip_count FROM first_seen f LEFT JOIN (SELECT dev,count(*) ip_count FROM links GROUP BY 1) p USING(dev)')
    c.execute('CREATE INDEX link_dev ON links(dev)');c.execute('CREATE INDEX link_ip ON links(ip)');c.execute('CREATE INDEX profile_dev ON device_profile(dev)')
    # Fast exact searches; no full database is sent to the browser.
    c.execute('CREATE INDEX observation_dev ON observations(dev)');c.execute('CREATE INDEX observation_ip ON observations(ip)')
    first,last=c.execute('SELECT min(dt),max(dt) FROM observations').fetchone()
    metadata={'fingerprint':fingerprint,'source_name':source.name,'createdAt':datetime.now(timezone.utc).isoformat(),'first':str(first),'last':str(last),'events':[x[0] for x in c.execute('SELECT DISTINCT event_name FROM observations ORDER BY 1').fetchall()],'ua_available':'UA' in fields,'user_id_available':False,'session_id_available':False,'build_seconds':round(time.monotonic()-started,1),'notes':'Daily observations only. Network links do not identify a person. No watch time is attributed to device IDs.'}
    c.execute('CREATE TABLE metadata(data VARCHAR)');c.execute('INSERT INTO metadata VALUES (?)',[json.dumps(metadata)]);c.execute('CHECKPOINT');c.close()
    after=source.stat()
    if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise RuntimeError('Source changed during snapshot build. Retry after it finishes updating.')
    temp.replace(cache);print(f'Snapshot ready in {metadata["build_seconds"]} seconds: {cache}',flush=True);return metadata

class Explorer:
    def __init__(self,cache):
        self.cache=Path(cache)
        with self.connection() as c:self.meta=json.loads(c.execute('SELECT data FROM metadata').fetchone()[0])
    def connection(self):
        c=duckdb.connect(str(self.cache),read_only=True);c.execute("SET threads=2");c.execute("SET memory_limit='2GB'");return c
    def scope(self,p,alias='o'):
        lo=p.get('from') or self.meta['first'];hi=p.get('to') or self.meta['last']
        date.fromisoformat(lo);date.fromisoformat(hi)
        if lo>hi:raise ValueError('From date must be before Through date.')
        where=f'{alias}.dt>=? AND {alias}.dt<=?';args=[lo,hi]
        event=p.get('event','')
        if event:
            if event not in self.meta['events']:raise ValueError('Unknown event')
            where+=f' AND {alias}.event_name=?';args.append(event)
        return where,args
    @staticmethod
    def query(c,sql,args=None):
        r=c.execute(sql,args or []);cols=[x[0] for x in r.description];return [dict(zip(cols,row)) for row in r.fetchall()]
    def overview(self,p):
        where,args=self.scope(p);q=self.query
        with self.connection() as c:
            summary=q(c,f'''SELECT count(*) source_rows,count(distinct dev) devices,count(distinct ip) ips,
              count(*) FILTER(WHERE dev IS NULL) missing_device_rows,count(distinct ip) FILTER(WHERE dev IS NOT NULL) linked_ips,
              count(*) FILTER(WHERE dev IS NOT NULL AND ts_requests>0) device_rows_with_ts,
              count(distinct dt) represented_dates FROM observations o WHERE {where}''',args)[0]
            daily=q(c,f'''WITH dd AS (SELECT DISTINCT dt,dev FROM observations o WHERE {where} AND dev IS NOT NULL),
              dates AS (SELECT DISTINCT dt FROM observations o WHERE {where}),counts AS (SELECT d.dt,count(*) devices,count(*) FILTER(WHERE d.dt>f.first_dt) returning_devices,count(*) FILTER(WHERE d.dt=f.first_dt) first_observed FROM dd d JOIN first_seen f USING(dev) GROUP BY 1)
              SELECT strftime(d.dt,'%Y-%m-%d') date,coalesce(devices,0) devices,coalesce(returning_devices,0) returning_devices,coalesce(first_observed,0) first_observed FROM dates d LEFT JOIN counts USING(dt) ORDER BY 1''',args+args)
            top_ips=q(c,f'''SELECT ip,count(distinct dev) devices,count(distinct dt) active_dates FROM observations o WHERE {where} AND dev IS NOT NULL AND ip IS NOT NULL GROUP BY 1 ORDER BY devices DESC,ip LIMIT 10''',args)
            top_devices=q(c,f'''SELECT dev,count(distinct ip) ips,count(distinct dt) active_dates FROM observations o WHERE {where} AND dev IS NOT NULL GROUP BY 1 ORDER BY ips DESC,dev LIMIT 10''',args)
            distribution=q(c,f'''SELECT CASE WHEN n=1 THEN '1 IP' WHEN n=2 THEN '2 IPs' WHEN n<=5 THEN '3–5 IPs' WHEN n<=10 THEN '6–10 IPs' ELSE '11+ IPs' END category,count(*) devices FROM (SELECT dev,count(distinct ip) n FROM observations o WHERE {where} AND dev IS NOT NULL AND ip IS NOT NULL GROUP BY 1) GROUP BY 1 ORDER BY min(n)''',args)
        return {'meta':self.meta,'summary':summary,'daily':daily,'top_ips':top_ips,'top_devices':top_devices,'distribution':distribution}
    def explore(self,p):
        kind=p.get('kind');identifier=str(p.get('identifier','')).strip()
        if kind not in ('device','ip') or not identifier or len(identifier)>256:raise ValueError('Enter a complete IP or device ID (maximum 256 characters).')
        column='dev' if kind=='device' else 'ip';opposite='ip' if kind=='device' else 'dev'
        where,args=self.scope(p);where+=f' AND o.{column}=?';args.append(identifier)
        offset=p.get('offset',0)
        if not isinstance(offset,int) or offset<0 or offset>10000000:raise ValueError('Invalid page offset')
        q=self.query
        with self.connection() as c:
            summary=q(c,f'''SELECT count(*) source_rows,count(distinct dt) active_dates,count(distinct dev) devices,count(distinct ip) ips,count(distinct event_name) events,min(dt) first_date,max(dt) last_date,count(*) FILTER(WHERE dev IS NULL) unlinked_rows FROM observations o WHERE {where}''',args)[0]
            if not summary['source_rows']:return {'kind':kind,'identifier':identifier,'summary':summary,'timeline':[],'neighbors':[],'dimensions':{},'observations':[],'has_more':False}
            neighbors=q(c,f'''SELECT {opposite} identifier,count(distinct dt) active_dates,min(dt) first_date,max(dt) last_date FROM observations o WHERE {where} AND {opposite} IS NOT NULL GROUP BY 1 ORDER BY active_dates DESC,identifier LIMIT 21 OFFSET ?''',args+[offset])
            timeline=q(c,f'''SELECT strftime(dt,'%Y-%m-%d') date,count(distinct dev) devices,count(distinct ip) ips,list(distinct event_name) events,list(distinct match_name) matches,list(distinct region) regions FROM observations o WHERE {where} GROUP BY 1 ORDER BY 1''',args)
            dimensions={}
            for field in ['event_name','match_name','country','region','device_type','os_type','isp','host']:
                dimensions[field]=q(c,f'SELECT {field} AS "value",count(distinct dt) active_dates FROM observations o WHERE {where} GROUP BY 1 ORDER BY active_dates DESC,"value" LIMIT 20',args)
            observations=q(c,f'''SELECT DISTINCT strftime(dt,'%Y-%m-%d') date,dev,ip,event_name,match_name,country,region,device_type,os_type,isp FROM observations o WHERE {where} ORDER BY date DESC,event_name LIMIT 101''',args)
            first=None
            if kind=='device':first=q(c,'SELECT first_dt,last_dt,active_dates,ip_count FROM device_profile WHERE dev=?',[identifier])
        return {'kind':kind,'identifier':identifier,'summary':summary,'all_file_device_profile':first,'timeline':timeline,'neighbors':neighbors[:20],'has_more':len(neighbors)>20,'offset':offset,'observations':observations[:100],'observations_truncated':len(observations)>100,'dimensions':dimensions,'graph_rule':'Only direct device↔IP links; never merge people through a shared IP.'}
    def cohorts(self,p):
        where,args=self.scope(p);q=self.query
        with self.connection() as c:
            records=q(c,f'''WITH active AS (SELECT DISTINCT date_trunc('week',dt)::DATE active_week,dev FROM observations o WHERE {where} AND dev IS NOT NULL),cohorts AS (SELECT dev,date_trunc('week',first_dt)::DATE cohort FROM first_seen)
              SELECT strftime(cohort,'%Y-%m-%d') cohort,strftime(active_week,'%Y-%m-%d') active_week,count(*) devices FROM active a JOIN cohorts c USING(dev) GROUP BY 1,2 ORDER BY 1,2''',args)
            sizes=q(c,"SELECT strftime(date_trunc('week',first_dt),'%Y-%m-%d') cohort,count(*) devices FROM first_seen GROUP BY 1 ORDER BY 1")
            coverage=q(c,f"SELECT strftime(date_trunc('week',dt),'%Y-%m-%d') AS week_start,count(distinct dt) represented_dates FROM observations o WHERE {where} GROUP BY 1 ORDER BY 1",args)
        return {'records':records,'sizes':sizes,'coverage':coverage,'definition':'Cohort = first-observed calendar week in the complete file. Cells = devices from that cohort observed in the selected scope/week ÷ complete-file cohort size. Missing source dates prevent a complete retention/churn claim.'}

class Handler(BaseHTTPRequestHandler):
    server_version='VetoIdentityExplorer/1'
    def log_message(self,*args):pass
    def send(self,status,payload,ctype='application/json'):
        data=json.dumps(payload,default=str).encode() if ctype=='application/json' else payload
        self.send_response(status);self.send_header('Content-Type',ctype+'; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'");self.end_headers();self.wfile.write(data)
    def safe_host(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.safe_host():return self.send(403,{'error':'Open the local 127.0.0.1 URL.'})
        path=urlsplit(self.path).path
        if path=='/health':return self.send(200,{'application':'veto-identity-explorer','meta':self.server.explorer.meta})
        files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if path not in files:return self.send(404,{'error':'Not found'})
        name=files[path];kind={'html':'text/html','js':'application/javascript','css':'text/css'}[name.split('.')[-1]];self.send(200,(HERE/name).read_bytes(),kind)
    def do_POST(self):
        origin=f'http://127.0.0.1:{self.server.server_port}'
        if not self.safe_host() or self.headers.get('Origin')!=origin:return self.send(403,{'error':'Same-origin local requests only.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('Invalid request length')
            p=json.loads(self.rfile.read(length))
            if not isinstance(p,dict):raise ValueError('Expected object')
            route={'/api/overview':self.server.explorer.overview,'/api/explore':self.server.explorer.explore,'/api/cohorts':self.server.explorer.cohorts}.get(self.path)
            if route is None:return self.send(404,{'error':'Unknown endpoint'})
            self.send(200,route(p))
        except (ValueError,TypeError,KeyError,duckdb.Error) as e:self.send(400,{'error':str(e)[:300]})

def serve(cache,port=8768):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.explorer=Explorer(cache)
    print(f'Open http://127.0.0.1:{port} — source data stays on this PC.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path(r'Y:\Veto Logs Backup\Chinmoy\sports_all_dates_12_columns.parquet'));p.add_argument('--cache',type=Path,default=WORKSPACE/'Reports/Sports_Identity_Explorer_20261118/identity.duckdb');p.add_argument('--port',type=int,default=8768);p.add_argument('--build-only',action='store_true');a=p.parse_args();build(a.source,a.cache)
    if not a.build_only:serve(a.cache,a.port)
