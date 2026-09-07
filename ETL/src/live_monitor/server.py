from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .operations_page import PAGE as OPERATIONS_PAGE


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veto Live Audience Operations</title><style>
:root{color-scheme:dark;--bg:#0b1117;--panel:#121b24;--line:#263442;--text:#e7edf3;--muted:#8fa2b5;--green:#4ade80;--blue:#38bdf8;--red:#fb7185}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Segoe UI,Arial,sans-serif}header{height:58px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px}h1,h2{margin:0;letter-spacing:0}h1{font-size:18px}h2{font-size:14px}.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.controls{display:flex;gap:10px;align-items:center;margin-bottom:14px}select{background:var(--panel);color:var(--text);border:1px solid var(--line);padding:7px}.cards{display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:10px}.card,.chart,.events,.minute-table{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px}.label{color:var(--muted);font-size:11px;text-transform:uppercase}.value{font-size:24px;font-weight:650;margin-top:5px}.ok,.inc{color:var(--green)}.bad,.dec{color:var(--red)}.chart{margin-top:10px}.chart-shell{position:relative;display:grid;grid-template-columns:64px minmax(0,1fr);height:330px}.y-axis{width:64px;height:300px;border-right:1px solid var(--line);background:var(--panel);position:relative;z-index:2}.chart-scroll{overflow-x:auto;overflow-y:hidden;height:330px;scrollbar-color:#52677a #0b1117}.plot{display:block;height:300px}.tooltip{display:none;position:absolute;z-index:5;pointer-events:none;background:#071019;border:1px solid #52677a;border-radius:4px;padding:7px 9px;white-space:nowrap;box-shadow:0 6px 18px #0008}.minute-table,.events{margin-top:10px}.table-scroll{max-height:340px;overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px}th{color:var(--muted);font-size:11px;position:sticky;top:0;background:var(--panel);z-index:1}.num{text-align:right}.current-row td{background:#142534}small{color:var(--muted)}@media(max-width:1100px){.cards{grid-template-columns:repeat(4,1fr)}}@media(max-width:700px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:12px}.chart-shell{grid-template-columns:54px}.y-axis{width:54px}}
</style></head><body><header><h1>Veto Live Audience Operations</h1><small id="stamp">Loading</small></header><main>
<div class="controls"><label>Channel <select id="target"></select></label><small id="note"></small></div>
<section class="cards"><div class="card"><div class="label">Active client IPs</div><div class="value" id="current">-</div></div><div class="card"><div class="label">Peak active IPs</div><div class="value" id="peak">-</div></div><div class="card"><div class="label">Known device IDs</div><div class="value" id="devices">-</div></div><div class="card"><div class="label">Known session IDs</div><div class="value" id="sessions">-</div></div><div class="card"><div class="label">Requests / min</div><div class="value" id="requests">-</div></div><div class="card"><div class="label">Bytes / min</div><div class="value" id="bytes">-</div></div><div class="card"><div class="label">Data lag</div><div class="value" id="lag">-</div></div></section>
<section class="chart"><div class="section-head"><h2>Minute-by-minute concurrency</h2><small>IST · scroll horizontally for history · 15-minute intervals</small></div><div class="chart-shell" id="chartShell"><canvas class="y-axis" id="yAxis"></canvas><div class="chart-scroll" id="chartScroll"><canvas class="plot" id="chart"></canvas></div><div class="tooltip" id="tooltip"></div></div></section>
<section class="minute-table"><div class="section-head"><h2>Concurrency by minute</h2><small>Newest minute first</small></div><div class="table-scroll"><table><thead><tr><th>Date</th><th>Time IST</th><th class="num">Concurrency</th><th class="num">Minute change</th><th class="num">Known device IDs</th><th class="num">Known session IDs</th></tr></thead><tbody id="minuteRows"></tbody></table></div></section>
<section class="events"><div class="section-head"><h2>Runtime events</h2></div><table><thead><tr><th>Component</th><th>Level</th><th>Message</th></tr></thead><tbody id="events"></tbody></table></section>
</main><script>
const $=id=>document.getElementById(id),fmt=n=>new Intl.NumberFormat('en-IN').format(Number(n||0)),esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c])),timeIST=v=>String(v||'').slice(11,19),dateIST=v=>String(v||'').slice(0,10);let data=null,plotState={rows:[],points:[]};
function nextMinuteIST(value){const match=String(value||'').match(/^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2})/);if(!match)return null;const date=new Date(Date.UTC(+match[1],+match[2]-1,+match[3],+match[4],+match[5]+1));return date.toISOString().slice(0,16)+':00+0530'}
function channelRows(key){const selected=data.series[key]||[],reference=key==='__all__'?selected:[...(data.series.__all__||[]),...selected],selectedByMinute=new Map(selected.map(row=>[row.minute_ist,row])),sorted=[...new Set(reference.map(row=>row.minute_ist))].sort();if(!sorted.length)return [];const rows=[];for(let minute=sorted[0],guard=0;minute&&minute<=sorted.at(-1)&&guard<10080;minute=nextMinuteIST(minute),guard++)rows.push(selectedByMinute.get(minute)||{minute_ist:minute,active_cliips:0,device_ids:0,session_ids:0,requests:0,bytes:0,errors_4xx:0,errors_5xx:0,media_segments:0});return rows}
function canvas2d(canvas,width,height){const dpr=devicePixelRatio||1;canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);const context=canvas.getContext('2d');context.setTransform(dpr,0,0,dpr,0,0);return context}
function draw(rows){const scroll=$('chartScroll'),c=$('chart'),axis=$('yAxis'),h=300,pad={top:24,right:28,bottom:40,left:22},spacing=12,wasAtEnd=scroll.scrollWidth-scroll.clientWidth-scroll.scrollLeft<36,w=Math.max(scroll.clientWidth,Math.max(1,rows.length-1)*spacing+pad.left+pad.right),maxRaw=Math.max(1,...rows.map(r=>Number(r.active_cliips||0))),magnitude=Math.pow(10,Math.max(0,String(Math.ceil(maxRaw)).length-1)),max=Math.ceil(maxRaw/magnitude)*magnitude,x=canvas2d(c,w,h),yctx=canvas2d(axis,axis.clientWidth||64,h),plotH=h-pad.top-pad.bottom;x.clearRect(0,0,w,h);yctx.clearRect(0,0,axis.clientWidth||64,h);x.font=yctx.font='11px Segoe UI';x.textBaseline=yctx.textBaseline='middle';for(let i=0;i<=4;i++){const py=pad.top+plotH*i/4,value=Math.round(max*(1-i/4));x.strokeStyle='#263442';x.lineWidth=1;x.beginPath();x.moveTo(0,py);x.lineTo(w,py);x.stroke();yctx.fillStyle='#8fa2b5';yctx.textAlign='right';yctx.fillText(fmt(value),(axis.clientWidth||64)-8,py)}x.strokeStyle='#52677a';x.beginPath();x.moveTo(0,h-pad.bottom);x.lineTo(w,h-pad.bottom);x.stroke();const points=[];rows.forEach((r,i)=>{const px=pad.left+i*spacing,py=pad.top+plotH*(1-Number(r.active_cliips||0)/max);points.push({x:px,y:py,row:r});if(String(r.minute_ist||'').slice(14,16)%15===0){x.strokeStyle='#1b2a37';x.beginPath();x.moveTo(px,pad.top);x.lineTo(px,h-pad.bottom);x.stroke();x.save();x.translate(px,h-25);x.rotate(-Math.PI/4);x.fillStyle='#8fa2b5';x.textAlign='right';x.fillText(timeIST(r.minute_ist).slice(0,5),0,0);x.restore()}});if(points.length){x.beginPath();let drawing=false;points.forEach(p=>{if(Number(p.row.active_cliips||0)<=0){drawing=false;return}if(drawing)x.lineTo(p.x,p.y);else{x.moveTo(p.x,p.y);drawing=true}});x.strokeStyle='#38bdf8';x.lineWidth=2;x.stroke();const p=points.at(-1);if(Number(p.row.active_cliips||0)>0){x.fillStyle='#4ade80';x.beginPath();x.arc(p.x,p.y,5,0,Math.PI*2);x.fill()}}else{x.fillStyle='#8fa2b5';x.fillText('No minute data for this channel',pad.left,40)}plotState={rows,points};if(wasAtEnd)requestAnimationFrame(()=>{scroll.scrollLeft=scroll.scrollWidth})}
function renderMinuteTable(rows){$('minuteRows').innerHTML=rows.map((row,index)=>{const previous=index?Number(rows[index-1].active_cliips||0):null,current=Number(row.active_cliips||0),change=previous==null?null:current-previous,label=change==null?'—':(change>0?'+':'')+fmt(change),cls=change>0?'inc':change<0?'dec':'';return `<tr class="${index===rows.length-1?'current-row':''}"><td>${esc(dateIST(row.minute_ist))}</td><td>${esc(timeIST(row.minute_ist))}</td><td class="num">${fmt(current)}</td><td class="num ${cls}">${label}</td><td class="num">${fmt(row.device_ids)}</td><td class="num">${fmt(row.session_ids)}</td></tr>`}).reverse().join('')||'<tr><td colspan="6">No minute data for this channel</td></tr>'}
function render(){if(!data)return;const key=$('target').value||'__all__',rows=channelRows(key),last=rows.at(-1)||{};$('current').textContent=fmt(last.active_cliips);$('peak').textContent=fmt(Math.max(0,...rows.map(r=>r.active_cliips||0)));$('devices').textContent=fmt(last.device_ids);$('sessions').textContent=fmt(last.session_ids);$('requests').textContent=fmt(last.requests);$('bytes').textContent=fmt(last.bytes);const lag=data.lag_seconds,syncing=data.runtime?.sync_in_progress;$('lag').textContent=lag==null?(syncing?'Syncing':'No data'):Math.round(lag)+' sec';$('lag').className='value '+(lag!=null&&lag<180?'ok':syncing?'':'bad');$('stamp').textContent='Updated '+data.generated_at;$('note').textContent=data.metric_note;draw(rows);renderMinuteTable(rows);$('events').innerHTML=(data.events||[]).map(e=>`<tr><td>${esc(e.component)}</td><td>${esc(e.level)}</td><td>${esc(e.message)}</td></tr>`).join('')||'<tr><td colspan="3">No runtime errors</td></tr>'}
async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error(await r.text());const previous=$('target').value;data=await r.json();const keys=Object.keys(data.series||{}).sort((a,b)=>a==='__all__'?-1:b==='__all__'?1:a.localeCompare(b));$('target').innerHTML=keys.map(k=>`<option value="${esc(k)}">${k==='__all__'?'All channels':esc(k)}</option>`).join('');$('target').value=keys.includes(previous)?previous:'__all__';render()}catch(e){$('stamp').textContent='State unavailable: '+e.message}}
$('chart').onmousemove=event=>{if(!plotState.points.length)return;const rect=$('chart').getBoundingClientRect(),x=event.clientX-rect.left,point=plotState.points.reduce((best,item)=>Math.abs(item.x-x)<Math.abs(best.x-x)?item:best),tip=$('tooltip'),shell=$('chartShell').getBoundingClientRect();tip.innerHTML='<strong>'+esc(dateIST(point.row.minute_ist))+' '+esc(timeIST(point.row.minute_ist))+' IST</strong><br>Concurrency: '+fmt(point.row.active_cliips)+'<br>Known device IDs: '+fmt(point.row.device_ids)+'<br>Known session IDs: '+fmt(point.row.session_ids);tip.style.display='block';tip.style.left=Math.min(shell.width-tip.offsetWidth-8,event.clientX-shell.left+12)+'px';tip.style.top=Math.max(8,event.clientY-shell.top-tip.offsetHeight-12)+'px'};$('chart').onmouseleave=()=>{$('tooltip').style.display='none'};$('target').onchange=render;addEventListener('resize',render);refresh();setInterval(refresh,5000);
</script></body></html>"""

# Keep the earlier compact page above as a rollback reference while the
# production operations view is served and exercised.
PAGE = OPERATIONS_PAGE


class SnapshotServer:
    def __init__(self, host: str, port: int, snapshot_path: Path):
        self.snapshot_path = snapshot_path
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    return self._send(200, "text/html; charset=utf-8", PAGE.encode())
                if self.path in {"/api/state", "/healthz"}:
                    try:
                        raw = owner.snapshot_path.read_bytes()
                        payload = json.loads(raw)
                    except (OSError, json.JSONDecodeError):
                        return self._send(503, "application/json", b'{"error":"state unavailable"}')
                    if self.path == "/healthz":
                        health = payload.get("health") if isinstance(payload, dict) else None
                        if isinstance(health, dict):
                            body = json.dumps(health, separators=(",", ":")).encode()
                            return self._send(
                                200 if health.get("ok") else 503,
                                "application/json",
                                body,
                            )
                        return self._send(200, "application/json", b'{"ok":true}')
                    return self._send(200, "application/json", raw)
                self._send(404, "text/plain; charset=utf-8", b"Not found")

            def _send(self, status: int, content_type: str, body: bytes):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="http", daemon=True
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
