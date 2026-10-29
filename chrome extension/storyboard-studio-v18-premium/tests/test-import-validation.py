"""Exercise file validation and persistent upload notices in both real extension popups."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import html
import json
import re
import subprocess
import tempfile
import threading
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / 'storyboard-studio-v18-premium'


def workbook(rows, extra=False):
    content = []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, value in enumerate(row):
            ref = chr(65+j)+str(i)
            if isinstance(value, dict):
                cells.append(f'<c r="{ref}"><f>{escape(value["formula"])}</f></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        content.append(f'<row r="{i}">'+''.join(cells)+'</row>')
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Frames" r:id="r1"/>'+('<sheet name="Reference" r:id="r2"/>' if extra else '')+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet><sheetData>'+''.join(content)+'</sheetData></worksheet>')
    return stream.getvalue()


HEADER = ['Frame', 'Master Prompt', 'Scene Prompt']
fixtures = {
    'valid.xlsx': workbook([HEADER, ['Frame 001', 'Shared style', 'A sunny courtyard.'], ['Frame 002', 'Shared style', 'Close-up of the drum.']], True),
    'wrong-headers.xlsx': workbook([['Number', 'Description'], ['1', 'An image']]),
    'partial.xlsx': workbook([HEADER, ['Frame 001', 'Shared style', 'Scene one'], ['Frame 002', 'Shared style', '']]),
    'masters.xlsx': workbook([HEADER, ['1', 'Style one', 'Scene one'], ['2', 'Style two', 'Scene two']]),
    'duplicate.xlsx': workbook([['Scene Prompt', 'Scene Prompt'], ['Scene one', 'Scene two']]),
    'formula.xlsx': workbook([HEADER, ['1', 'Style', {'formula': '"text"'}]]),
    'formula-empty.xlsx': workbook([HEADER, ['', '', {'formula': '"text"'}]]),
    'empty.xlsx': workbook([HEADER]),
    'extra.xlsx': workbook([HEADER+['QC Notes'], ['1', '', 'Scene one', 'Not a prompt']]),
    'optional.xlsx': workbook([['Scene Prompt'], ['Scene one']]),
    'corrupt.xlsx': b'Not a ZIP',
    'old.xls': b'Old Excel',
    'quoted.csv': b'Frame,Master Prompt,Scene Prompt\n1,Style,"not closed',
}
actual = ROOT / 'AAROHAN_S2E1_110_Frames_Cast_Instrument_AUDITED_V6.xlsx'
if actual.exists():
    fixtures['actual.xlsx'] = actual.read_bytes()
aarohan11 = Path(r'Y:\Veto Logs Backup\Aarohan\Smart Flow Uploads\1.1_Smart_Flow_UPLOAD.xlsx')
if aarohan11.exists():
    fixtures['aarohan11.xlsx'] = aarohan11.read_bytes()

CHECKS = r'''
(async()=>{
const pause=()=>new Promise(r=>setTimeout(r,10));let checks=0;
const debug=document.createElement('pre');debug.id='import-debug';document.body.append(debug);
setTimeout(()=>{debug.textContent+=' '+JSON.stringify({errors:PICKER_TEST.errors,messages:PICKER_TEST.messages,queueErrors:PICKER_TEST.queue()?.errors,listener:!!PICKER_TEST.queue()?.listener});},14000);
const check=(ok,message)=>{if(!ok)throw Error(message);checks++;};
await PICKER_TEST.ready;for(let i=0;!PICKER_TEST.interval&&i<100;i++)await pause();
await PICKER_TEST.interval();const queue=PICKER_TEST.queue();
const load=async name=>{debug.textContent=name;const bytes=await(await fetch('/fixtures/'+name)).arrayBuffer();await importFile(new File([bytes],name));};
const snapshot=()=>JSON.stringify(queue.data);
for(const [name,reason] of [['wrong-headers.xlsx','Scene Prompt column'],['partial.xlsx','row(s) 3'],['masters.xlsx','different Master Prompt'],['duplicate.xlsx','Duplicate column header'],['formula.xlsx','formula'],['formula-empty.xlsx','formula'],['empty.xlsx','No scene prompts'],['corrupt.xlsx','Invalid XLSX'],['old.xls','Upload a .txt'],['quoted.csv','CSV quote']]){
 const before=snapshot();await load(name);
 check(snapshot()===before,name+': queue, progress and pending frame must be preserved');
 check(!document.getElementById('importNotice').hidden&&document.getElementById('importNotice').textContent.includes(reason),name+': specific incompatibility must be shown');
 check(document.getElementById('importNotice').textContent.includes('example Excel'),name+': actionable format instructions must be visible');
 await PICKER_TEST.interval();check(!document.getElementById('importNotice').hidden,name+': refresh must not dismiss notice');
}
await load('valid.xlsx');
check(queue.data.prompts.length===2&&queue.data.master==='Shared style','Valid workbook must import all scenes');
check(document.getElementById('importNotice').textContent.includes('Loaded 2 frames'),'Success must be visible');
check(document.getElementById('importNotice').textContent.includes('Other 1 worksheet'),'Unused worksheets must be disclosed');
check(!document.getElementById('importNotice').classList.contains('import-error'),'Success must replace error styling');
await load('extra.xlsx');check(document.getElementById('importNotice').textContent.includes('additional column'),'Unused columns must be disclosed');
await load('optional.xlsx');check(document.getElementById('importNotice').textContent.includes('No Frame column')&&document.getElementById('importNotice').textContent.includes('No Master Prompt'),'Supported optional headers must have clear notices');
const file=document.getElementById('file'),dt=new DataTransfer();dt.items.add(new File(['not excel'],'same.xlsx'));file.files=dt.files;file.dispatchEvent(new Event('change'));
for(let i=0;importBusy&&i<100;i++)await pause();
check(file.value===''&&!file.disabled,'File input must reset so the same file can be retried');
const response=await fetch('/fixtures/actual.xlsx');if(response.ok){await importFile(new File([await response.arrayBuffer()],'actual.xlsx'));check(queue.data.prompts.length===110,'Actual AAROHAN workbook must still import 110 frames');}
if(location.pathname.startsWith('/flow/')){
 const response=await fetch('/fixtures/aarohan11.xlsx');if(response.ok){
  await importFile(new File([await response.arrayBuffer()],'1.1_Smart_Flow_UPLOAD.xlsx'));
  check(!document.getElementById('start').disabled,'Start must be immediately usable after workbook import');
  document.getElementById('start').click();await queue.flush();await pause();await queue.flush();
  check(queue.data.phase==='running'&&queue.data.pending?.state==='prepared','Actual uploaded 1.1 workbook must start and prepare Frame 001');
  check(queue.editor().value.includes('STYLE LOCK: 3D ANIME ONLY')&&queue.editor().value.includes('Frame: Frame 001')&&queue.editor().value.includes('looking INTO the hall'),'Actual 3D/hall instructions must reach the ChatGPT composer');
  check(queue.data.queueMode==='storyboard'&&queue.clicks===0,'Workbook start must use storyboard mode and not bypass Send stabilization');
 }
}
check(!PICKER_TEST.errors.length,JSON.stringify(PICKER_TEST.errors));
const result=document.createElement('pre');result.id='test-result';result.textContent=JSON.stringify({status:'PASS',checks,feature:'Excel validation and persistent popup upload notices'});document.body.append(result);
})().catch(e=>{const result=document.createElement('pre');result.id='test-result';result.textContent=JSON.stringify({status:'FAIL',error:e.stack,errors:PICKER_TEST.errors});document.body.append(result);});
'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split('?')[0]
        if path.startswith('/fixtures/'):
            body = fixtures.get(path.split('/')[-1])
            mime = 'application/octet-stream'
        else:
            _, app, *tail = path.split('/')
            relative = '/'.join(tail)
            folder = STUDIO if app == 'studio' else ROOT / 'smart-flow-v20.2'
            if relative == 'popup.html':
                body = (folder / relative).read_text(encoding='utf-8').replace('<script src="importer.js">', '<script src="tests/frame-picker-mock.js"></script><script src="importer.js">', 1).replace('</body>', '<script src="tests/import-checks.js"></script></body>', 1).encode()
            elif relative == 'tests/import-checks.js':
                body = CHECKS.encode()
            else:
                target = (STUDIO if relative.startswith('tests/') else folder) / relative
                body = target.read_bytes() if target.is_file() else None
            mime = 'text/html; charset=utf-8' if relative.endswith('.html') else 'text/javascript; charset=utf-8' if relative.endswith('.js') else 'text/css' if relative.endswith('.css') else 'image/png'
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    for app in ['studio', 'flow']:
        with tempfile.TemporaryDirectory(prefix='storyboard-import-') as profile:
            r = subprocess.run([r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-extensions', '--no-first-run', '--user-data-dir='+profile, '--virtual-time-budget=120000', '--dump-dom', f'http://127.0.0.1:{server.server_port}/{app}/popup.html'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
            match = re.search(r'<pre id="test-result">(.*?)</pre>', r.stdout, re.S)
            if not match:
                raise RuntimeError('Browser tests did not finish: '+str(re.findall(r'<pre id="import-debug">(.*?)</pre>',r.stdout))+r.stderr[-1000:]+r.stdout[-1000:])
            result = json.loads(html.unescape(match.group(1)))
            print(app+': '+json.dumps(result))
            assert result['status'] == 'PASS', result
finally:
    server.shutdown()
    thread.join()
    server.server_close()
