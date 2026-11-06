"""Exercise pack folder controls in Chrome against a synthetic conversation."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64, html, json, re, subprocess, sys, tempfile, threading

ROOT=Path(__file__).resolve().parent.parent
PACK=Path(sys.argv[1])
PIXEL=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6WQAAAABJRU5ErkJggg==')
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path=='/popup.html?pack-test':
            body=(ROOT/'popup.html').read_text(encoding='utf-8').replace('<script src="importer.js">','<script src="tests/repeat-popup-mock.js"></script><script src="importer.js">',1).replace('</body>','<script src="tests/mapped-popup-checks.js"></script></body>',1).encode()
            mime='text/html; charset=utf-8'
        elif self.path=='/pack-fixture.json':
            body=json.dumps(dict(csv=(PACK/'S01_First_5_Test.csv').read_text(encoding='utf-8-sig'),manifest=(PACK/'Attachment_Manifest.csv').read_text(encoding='utf-8-sig'),names=[p.name for p in (PACK/'references').glob('*.png')])).encode()
            mime='application/json'
        elif self.path.startswith('/pixel.png'):
            body=PIXEL;mime='image/png'
        else: return super().do_GET()
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with tempfile.TemporaryDirectory(prefix='smart-flow-pack-') as profile:
        result=subprocess.run([r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless=new','--no-sandbox','--disable-gpu','--disable-extensions','--no-first-run','--user-data-dir='+profile,'--virtual-time-budget=360000','--dump-dom',f'http://127.0.0.1:{server.server_port}/popup.html?pack-test'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
        match=re.search(r'<pre id="test-result">(.*?)</pre>',result.stdout,re.S)
        if not match: raise RuntimeError(result.stdout[-2500:]+result.stderr[-1000:])
        report=json.loads(html.unescape(match.group(1)));print(json.dumps(report));assert report['status']=='PASS',report
finally:
    server.shutdown();thread.join();server.server_close()
