"""Run real channel-editor browser checks on a disposable database only."""
import os
from pathlib import Path
import subprocess
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[3] / 'RevenueLive'
sys.path.insert(0, str(ROOT / 'tests'))
from test_database_uploads import DatabaseUploadTest
from werkzeug.serving import make_server

process_env = os.environ.copy()
node = shutil.which('node')
case = DatabaseUploadTest()
case.setUp()
try:
    server = make_server('127.0.0.1', 0, case.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(process_env, CHANNEL_TEST_URL=f'http://127.0.0.1:{server.server_port}')
        result = subprocess.run([node, str(Path(__file__).with_name('channel-editor.cjs'))], env=env, check=False, timeout=120)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    if result.returncode:
        raise SystemExit(result.returncode)
finally:
    case.doCleanups()
