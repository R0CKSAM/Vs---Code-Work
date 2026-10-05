"""Opt-in real workbook audit against disposable SQLite only; no deployment config."""
import csv
from contextlib import closing
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[3]/'RevenueLive'
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from app import parse_upload,channel_key,verify_audit_chain
from test_database_uploads import DatabaseUploadTest
from werkzeug.serving import make_server,WSGIRequestHandler

WORKBOOK=ROOT/'notneeded'/'Book2.xlsx'
content=WORKBOOK.read_bytes()
source=parse_upload(content,'.xlsx',allow_total_warnings=True)
names={channel_key(row['channel']):row['channel'] for row in source}
FIELDS=('views','impressions','ad','other','total')
NODE=shutil.which('node')
process_env=os.environ.copy()

class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):
        pass

def scenario(map_campaigns):
    case=DatabaseUploadTest('runTest')
    case.setUp()
    server=None
    try:
        case.uploader_login()
        parent=names[channel_key('MP Govt Activity')]
        targets={key:parent if map_campaigns and (key.startswith('mp govt') or key.startswith('mpgovt')) else name for key,name in names.items()}
        actions=[{'source':name,'action':'create'} if targets[key]==name else
                 {'source':name,'action':'map_new','target_source':targets[key]} for key,name in names.items()]
        def upload(decisions=None):
            return case.client.post('/api/uploads/preview',headers=case.headers,data={
                'file':(io.BytesIO(content),WORKBOOK.name),'channel_actions':json.dumps(decisions or [])})
        first=upload()
        case.assertEqual(first.status_code,400,first.json)
        case.assertEqual(len(first.json['channel_issues']),42)
        response=upload(actions)
        case.assertEqual(response.status_code,200,response.json.get('error'))
        initial=response.json
        uid=initial['id']
        case.assertEqual(sum(len(row.get('source_entries',[row])) for row in initial['rows']),4045)
        case.assertFalse(any(row.get('blocking_error') or row.get('entry_group') for row in initial['rows']))
        case.assertEqual([row['source_row'] for row in initial['rows'] if row.get('warning')],[318,1378])
        case.assertEqual(upload().status_code,400,'An identical pending file must not be accepted twice')
        grouped={};seen=set();skipped=[]
        for row in source:
            key=(row['day'],targets[channel_key(row['channel'])])
            identity=(key,channel_key(row['channel']),tuple(row[field] for field in FIELDS),tuple(row.get('source_revenue',[])),str(row.get('warning',{}).get('supplied_total','')))
            if identity in seen:
                skipped.append(row['source_row']);continue
            seen.add(identity)
            values=grouped.setdefault(key,dict.fromkeys(FIELDS,0))
            for field in FIELDS:
                values[field]+=row[field]
        expected={field:sum(row[field] for row in grouped.values()) for field in FIELDS}
        case.assertEqual(case.client.post(f'/api/uploads/{uid}/commit',headers=case.headers,json={}).status_code,400)
        reviewed=initial['rows']
        case.assertEqual(len(reviewed),len(grouped))
        case.assertEqual(sum(len(row.get('source_entries',[row])) for row in reviewed),len(source))
        for row in reviewed:
            case.assertEqual({field:row[field] for field in FIELDS},grouped[(row['day'],row['channel'])])
        case.assertEqual(case.client.get('/api/report').json['rows'],[])
        case.assertEqual(case.client.post(f'/api/uploads/{uid}/commit',headers=case.headers,json={}).status_code,400)
        case.action(uid,'commit',{'accept_total_mismatches':True})
        case.assertEqual(case.client.get('/api/report').json['totals'],expected)
        exported=list(csv.DictReader(io.StringIO(case.client.get(f'/api/uploads/{uid}/file').data.decode('utf-8-sig'))))
        case.assertEqual(len(exported),len(grouped))
        case.assertEqual(sum(int(row['Ad Impressions']) for row in exported),expected['impressions'])
        case.assertEqual(sum(int(Decimal(row['Total Revenue'])*100) for row in exported),expected['total'])
        case.client.post('/api/login',json={'username':'admin','password':'synthetic-password'})
        case.headers={'X-CSRF-Token':case.client.get('/api/me').json['csrf']}
        case.action(uid,'archive',{'archived':True})
        case.assertEqual(case.client.get('/api/report').json['rows'],[])
        case.action(uid,'unarchive')
        case.assertEqual(case.client.get('/api/report').json['totals'],expected)
        case.action(uid,'reject')
        case.action(uid,'unarchive')
        case.assertEqual(case.client.get('/api/report').json['totals'],expected)
        case.action(uid,'delete')
        case.assertEqual(case.client.get('/api/report').json['rows'],[])
        with closing(case.app.extensions['database'].connect()) as db:
            case.assertTrue(verify_audit_chain(db)[0])
        print(json.dumps({'scenario':'MP campaign mapping' if map_campaigns else 'Original channel names',
            'source_rows':len(source),'output_rows':len(reviewed),'skipped_exact_rows':skipped,
            'repeated_groups':sum(bool(row.get('source_entries')) for row in initial['rows']),
            'warnings':[row['source_row'] for row in source if row.get('warning')],
            'mapped_parent_sample':{day:grouped.get((day,parent),{}).get('impressions') for day in ['2026-07-19','2026-07-23']},
            'checks':'create/map, preview, sum, publish, CSV totals, archive, restore, delete and audit PASS'}),flush=True)
        if not map_campaigns:
            server=make_server('127.0.0.1',0,case.app,threaded=True,request_handler=QuietHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            subprocess.run([NODE,str(Path(__file__).with_name('book2-browser.cjs')),f'http://127.0.0.1:{server.server_port}',str(WORKBOOK)],
                           check=True,env=process_env,timeout=180)
            server.shutdown();thread.join();server.server_close();server=None
    finally:
        if server:
            server.shutdown();server.server_close()
        case.doCleanups()

scenario(False)
scenario(True)
