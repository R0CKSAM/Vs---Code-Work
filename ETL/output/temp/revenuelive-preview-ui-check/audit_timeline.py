"""Real browser checks with synthetic revenue and an isolated SQL database."""
import csv
import datetime as dt
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[3]/'RevenueLive'
sys.path.insert(0,str(ROOT/'tests'))
from test_database_uploads import DatabaseUploadTest, HEADERS
from werkzeug.serving import make_server, WSGIRequestHandler

class QuietHandler(WSGIRequestHandler):
    def log(self,*args,**kwargs):
        pass

env=os.environ.copy();node=shutil.which('node')
case=DatabaseUploadTest();case.setUp()
try:
    content=io.StringIO();writer=csv.writer(content);writer.writerow(HEADERS)
    for index in range(222):
        day=dt.date(2026,2,20)+dt.timedelta(days=index)
        writer.writerow([day.isoformat(),'Example',100+index,50+index,1000+index,500,1500+index])
    preview=case.client.post('/api/uploads/preview',headers=case.headers,data={'file':(io.BytesIO(content.getvalue().encode()),'synthetic.csv')})
    assert preview.status_code==200,preview.json
    case.action(preview.json['id'],'commit')
    server=make_server('127.0.0.1',0,case.app,threaded=True,request_handler=QuietHandler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        env['TIMELINE_TEST_URL']=f'http://127.0.0.1:{server.server_port}'
        subprocess.run([node,str(Path(__file__).with_name('timeline-live.cjs'))],env=env,check=True,timeout=120)
    finally:
        server.shutdown();worker.join();server.server_close()
finally:
    case.doCleanups()
