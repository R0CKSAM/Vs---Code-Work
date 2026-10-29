"""Run repeat-message queue and actual popup against synthetic Chrome DOM/downloads."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import html
import json
import re
import subprocess
import tempfile
import threading

ROOT=Path(__file__).resolve().parent.parent
PIXEL=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6WQAAAABJRU5ErkJggg==')


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_GET(self):
        if self.path.startswith('/pixel.png'):
            body=PIXEL
            mime='image/png'
        elif self.path=='/popup.html?repeat-test':
            body=(ROOT/'popup.html').read_text(encoding='utf-8').replace('<script src="importer.js">','<script src="tests/repeat-popup-mock.js"></script><script src="importer.js">',1).replace('</body>','<script src="tests/repeat-popup-checks.js"></script></body>',1).encode()
            mime='text/html; charset=utf-8'
        else:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
try:
    for page in ['tests/repeat-fixture.html','popup.html?repeat-test']:
        with tempfile.TemporaryDirectory(prefix='smart-flow-repeat-') as profile:
            r=subprocess.run([r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless=new','--no-sandbox','--disable-gpu','--disable-extensions','--no-first-run','--user-data-dir='+profile,'--virtual-time-budget=360000','--dump-dom',f'http://127.0.0.1:{server.server_port}/{page}'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
            match=re.search(r'<pre id="test-result">(.*?)</pre>',r.stdout,re.S)
            if not match or match.group(1)=='PENDING':
                raise RuntimeError('Browser tests did not finish: '+r.stderr[-1000:]+r.stdout[-1000:])
            result=json.loads(html.unescape(match.group(1)))
            print(json.dumps(result,ensure_ascii=False))
            assert result['status']=='PASS',result
finally:
    server.shutdown()
    thread.join()
    server.server_close()
