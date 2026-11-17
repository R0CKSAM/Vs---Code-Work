"""Exercise the real validator UI in isolated Chrome with fixture-only APIs."""
import html,json,re,subprocess,tempfile,threading
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DAY={'date':'2026-10-20','users_all':110,'users_positive_ts':100,'device_ids':50,'ts_requests':6000,'hours_0_6':1,'hours_6':10}
REF={'schema':'smart-export-parquet-reference/v1','timezone':'Asia/Kolkata','source':{'name':'fixture.parquet'},'scopes':[{'id':'portfolio','name':'Sports','summary':DAY,'daily':[DAY],'geo':[]}]}
ROWS={'kpis':[{'date':'2026-10-20','unique_ips':110,'unique_devices':50,'session_hours':10}],'geo':[],'viewership_stats':[]}
URL='https://grafana-apj.trafficpeak.live/d/db7ce6f6-d689-4976-89e5-ddf0b5401f97/sessions?orgId=743&var-filter='
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/validation-reference.json':return self.body(json.dumps(REF),'application/json')
  if path=='/report-db.mjs':return self.body('export const allReportRows=async()=>('+json.dumps(ROWS)+');','text/javascript')
  if path=='/tests/validator-mock.js':
   code='const fixture='+json.dumps(ROWS)+';const url='+json.dumps(URL)+';window.chrome={storage:{local:{get:async()=>({smartExportConfig:{dashboardUrl:url}})}},runtime:{sendMessage:async m=>({ok:true,data:m.type==="CURRENT_GRAFANA_TAB"?{url}:{schema:"smart-export-validation-snapshot/v1",mode:"live",capturedAt:"fixture",source:{url,timezone:"Asia/Kolkata",filters:[]},datasets:fixture}})}};'
   return self.body(code,'text/javascript')
  if path=='/validator.html':
   code=(ROOT/'validator.html').read_text(encoding='utf-8').replace('<head>','<head><script src="tests/validator-mock.js"></script>',1).replace('</body>','<script type="module" src="tests/validator-browser-checks.mjs"></script></body>')
   return self.body(code,'text/html')
  return super().do_GET()
 def body(self,body,kind):
  data=body.encode();self.send_response(200);self.send_header('Content-Type',kind+';charset=utf-8');self.end_headers();self.wfile.write(data)
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)));threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  for width in [1440,480]:
   with tempfile.TemporaryDirectory(prefix='veto-validator-ui-') as profile:
    p=subprocess.run([r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--user-data-dir='+profile,f'--window-size={width},1000','--virtual-time-budget=15000','--dump-dom',f'http://127.0.0.1:{server.server_port}/validator.html'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
    m=re.search(r'<pre id="ui-test-result">(.*?)</pre>',p.stdout,re.S)
    if not m:raise RuntimeError(p.stderr[-1000:])
    result=json.loads(html.unescape(m[1]));print(result);assert result['status']=='PASS'
 finally:server.shutdown();server.server_close()
