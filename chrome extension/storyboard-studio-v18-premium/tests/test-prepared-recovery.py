"""Exercise actual content.js against a synthetic ChatGPT composer in Chrome."""
import argparse
from functools import partial
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

ROOT=Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_GET(self):
        if self.path=='/popup.html?frame-test=1':
            body=(ROOT/'popup.html').read_text(encoding='utf-8').replace('<script src="importer.js">','<script src="tests/frame-picker-mock.js"></script><script src="importer.js">',1).replace('</body>','<script src="tests/frame-picker-checks.js"></script></body>',1).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome',default=shutil.which('chromium') or shutil.which('google-chrome') or r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        for page in ('tests/recovery-fixture.html','popup.html?frame-test=1'):
          with tempfile.TemporaryDirectory(prefix='storyboard-recovery-') as profile:
            result=subprocess.run([args.chrome,'--headless','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--user-data-dir='+profile,'--virtual-time-budget=10000','--dump-dom',f'http://127.0.0.1:{server.server_port}/{page}'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
            match=re.search(r'<pre id="test-result">(.*?)</pre>',result.stdout,re.S)
            if not match:
                raise RuntimeError(result.stderr[-1000:]+result.stdout[-1000:])
            payload=html.unescape(match.group(1))
            if payload=='PENDING':
                raise RuntimeError('Browser recovery tests did not finish')
            data=json.loads(payload)
            print(json.dumps(data,indent=2))
            assert data['status']=='PASS',data
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__=='__main__':
    main()
