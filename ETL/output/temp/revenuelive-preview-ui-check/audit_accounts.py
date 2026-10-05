"""Exercise account forms against disposable synthetic data, not live SQL."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[3]/'RevenueLive'
sys.path.insert(0,str(ROOT/'tests'))
from test_database_uploads import DatabaseUploadTest
from werkzeug.serving import make_server, WSGIRequestHandler

class QuietHandler(WSGIRequestHandler):
    def log(self,*args,**kwargs):
        pass

env=os.environ.copy()
node=shutil.which('node')
case=DatabaseUploadTest()
case.setUp()
try:
    server=make_server('127.0.0.1',0,case.app,threaded=True,request_handler=QuietHandler)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        env['ACCOUNT_TEST_URL']=f'http://127.0.0.1:{server.server_port}'
        subprocess.run([node,str(Path(__file__).with_name('account-ui.cjs'))],env=env,check=True,timeout=120)
    finally:
        server.shutdown()
        worker.join()
        server.server_close()
finally:
    case.doCleanups()
