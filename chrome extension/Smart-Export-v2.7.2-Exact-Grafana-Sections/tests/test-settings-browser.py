"""Run real workspace modules in isolated Chrome with mocked extension APIs."""
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

ROOT = Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/workspace.html':
            body = (ROOT / 'workspace.html').read_text(encoding='utf-8')
            body = body.replace('<head>', '<head><script src="tests/settings-mock.js"></script>', 1)
            body = body.replace('</body>', '<script src="tests/settings-checks.mjs" type="module"></script></body>', 1)
            self.send_body(body, 'text/html')
        elif path == '/storage-audit.html':
            self.send_body('<!doctype html><pre id="ui-test-result">PENDING</pre><script type="module" src="tests/storage-checks.mjs"></script>', 'text/html')
        elif path == '/report-db.mjs' and 'real-storage' not in self.path:
            self.send_body('export const allReportRows=async()=>({...window.UI_TEST.rows});', 'text/javascript')
        else:
            super().do_GET()

    def send_body(self, body, content_type):
        encoded = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default=shutil.which('chromium') or shutil.which('google-chrome') or r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    parser.add_argument('--node', default=shutil.which('node') or str(ROOT.parents[1] / '.tmp' / 'node-runtime' / 'node.exe'))
    parser.add_argument('--screenshot', default=None)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for width, page in ((1280, 'workspace.html'), (480, 'workspace.html')):
            with tempfile.TemporaryDirectory(prefix='smart-export-settings-test-') as profile:
                result = subprocess.run([
                    args.chrome, '--headless', '--disable-gpu', '--disable-extensions', '--no-first-run', '--no-default-browser-check',
                    '--user-data-dir=' + profile, f'--window-size={width},900', '--force-device-scale-factor=1', '--force-prefers-reduced-motion',
                    '--virtual-time-budget=20000', '--dump-dom', f'http://127.0.0.1:{server.server_port}/{page}'
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
                match = re.search(r'<pre id="ui-test-result">(.*?)</pre>', result.stdout, re.S)
                if not match:
                    raise RuntimeError(f'Browser did not finish checks: {result.stderr[-1500:]}\n{result.stdout[-1000:]}')
                raw = html.unescape(match.group(1))
                if raw == 'PENDING':
                    raise RuntimeError(f'{page}: browser checks did not complete')
                payload = json.loads(raw)
                print(json.dumps(payload))
                assert payload['status'] == 'PASS', payload
        storage = subprocess.run([args.node, str(ROOT / 'tests' / 'cdp-storage-check.mjs'), f'http://127.0.0.1:{server.server_port}/storage-audit.html', args.chrome], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
        print(storage.stdout.strip())
        assert storage.returncode == 0, storage.stderr
        if args.screenshot:
            visual = subprocess.run([args.node, str(ROOT / 'tests' / 'cdp-storage-check.mjs'), f'http://127.0.0.1:{server.server_port}/workspace.html', args.chrome, args.screenshot], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
            print(visual.stdout.strip())
            assert visual.returncode == 0, visual.stderr
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__ == '__main__':
    main()
