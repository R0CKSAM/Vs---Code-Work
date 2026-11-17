from pathlib import Path
import json,csv,html
r=Path(r'D:\Vs - Code Work\Reports\Raw_Grafana_Validation_20261116\diagnosis')
a=json.loads((r/'local_breakdown.json').read_text());b=json.loads((r/'grafana_breakdown.json').read_text(encoding='utf-8-sig'));f=b['response']['data']['results']['A']['frames'][0]
remote=[dict(zip([x['name'] for x in f['schema']['fields']],row)) for row in zip(*f['data']['values'])]
from collections import defaultdict

def grouped(rows):
 d=defaultdict(lambda:{'requests':0,'ts_eligible':0,'video_bytes':0})
 for x in rows:
  for k in ['requests','ts_eligible','video_bytes']:d[x['host']][k]+=x.get(k) or 0
 return d
local=grouped(a['host_hour_type']);grafana=grouped(remote);records=[]
for host in local.keys()|grafana.keys():
 l=local.get(host,{'requests':0,'ts_eligible':0,'video_bytes':0});g=grafana.get(host,{'requests':0,'ts_eligible':0,'video_bytes':0})
 row={'host':host,'date_ist':'2026-11-16','local_host_present':host in local,'grafana_host_present':host in grafana}
 for k,label in [('requests','requests'),('ts_eligible','eligible_ts'),('video_bytes','successful_ts_bytes')]:
  row['raw_'+label]=l[k];row['grafana_'+label]=g[k];row[label+'_difference']=g[k]-l[k];row[label+'_difference_pct']=None if l[k]==0 else (g[k]-l[k])/l[k]*100
 for seconds,label in [(.6,'hours_0_6'),(6,'hours_6')]:
  row['raw_'+label]=l['ts_eligible']*seconds/3600;row['grafana_'+label]=g['ts_eligible']*seconds/3600;row[label+'_difference']=row['grafana_'+label]-row['raw_'+label]
 row['finding']='Missing from downloaded raw files' if host not in local else 'Exact request and TS count match' if l['requests']==g['requests'] and l['ts_eligible']==g['ts_eligible'] else 'Raw count slightly higher; duplicates / ingestion rules need review' if l['requests']>g['requests'] else 'Grafana count higher; investigate source coverage'
 records.append(row)
records.sort(key=lambda x:abs(x['requests_difference']),reverse=True)
assert len(records)==35;assert sum(x['raw_requests'] for x in records)==19375867;assert sum(x['grafana_requests'] for x in records)==20041429;assert sum(x['eligible_ts_difference'] for x in records)==101884
out=r/'host_wise_comparison_2026-11-16.csv'
with out.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
(r/'host_wise_comparison_2026-11-16.json').write_text(json.dumps({'window':'2026-11-16 full IST day','difference':'Grafana minus raw; percentage baseline is raw. Missing local host has no percentage.','grafana_capture_utc':b['capturedAt'],'rows':records},indent=2))
def fmt(x):return 'N/A' if x is None else f'{x:,.0f}'
def pct(x):return 'N/A' if x is None else f'{x:+.4f}%'
trs=[]
for x in records:
 vals=[x['host'],fmt(x['raw_requests']),fmt(x['grafana_requests']),f"{x['requests_difference']:+,}",pct(x['requests_difference_pct']),fmt(x['raw_eligible_ts']),fmt(x['grafana_eligible_ts']),f"{x['eligible_ts_difference']:+,}",pct(x['eligible_ts_difference_pct']),f"{x['raw_hours_0_6']:,.3f}",f"{x['grafana_hours_0_6']:,.3f}",x['finding']]
 trs.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in vals)+'</tr>')
headers=['Host / ReqHost','Raw requests','Grafana requests','Request gap','Gap %','Raw eligible TS','Grafana eligible TS','TS gap','TS gap %','Raw hours (0.6s)','Grafana hours (0.6s)','Finding']
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Host-wise Raw vs Grafana · 16 November 2026</title><style>body{font:15px Arial;color:#173452;background:#f3f6fa;margin:0;padding:30px}h1{color:#112d50}p{max-width:1100px;line-height:1.6}.cards{display:flex;gap:14px;flex-wrap:wrap}.cards div{background:white;border-radius:10px;padding:18px;border-left:5px solid #f36c2c}.table{overflow:auto;background:white;max-height:72vh;border-radius:8px}table{border-collapse:collapse;font-size:13px;min-width:1700px;width:100%}th,td{padding:12px;text-align:right;border-bottom:1px solid #dce4ed;white-space:nowrap}th{position:sticky;top:0;background:#112d50;color:white}td:first-child,td:last-child{text-align:left}tr:first-child td{background:#fff1e6}input{padding:12px;margin:20px 0;border:1px solid #aabccd;border-radius:8px;width:360px;max-width:90%}a{color:#164e88}</style><h1>Host-wise comparison · 16 November 2026 IST</h1><p>Difference = Grafana minus raw. Negative means the raw files contain more records. Percentages use raw as the baseline. Hours use eligible TS counts × 0.6 ÷ 3600 on both sides.</p><div class="cards"><div><b>35 hosts</b><br>34 shared + 1 missing locally</div><div><b>676,820 requests</b><br>Missing India TV OTT host</div><div><b>0.0581%</b><br>Extra raw requests on shared hosts</div></div><p>Host-wise is not channel-wise: a host can serve several channels. No channel name is inferred from a host alone. Exact repeated raw lines were retained; the shared-host residual still needs ingestion-level review. Distinct users are not summed from hourly groups.</p><a href="host_wise_comparison_2026-11-16.csv">Download full Excel-ready CSV (includes bandwidth and 6-second hours)</a><br><input id="search" placeholder="Filter by host…" aria-label="Filter by host"><div class="table"><table><thead><tr>'''+''.join('<th>'+h+'</th>' for h in headers)+'''</tr></thead><tbody>'''+''.join(trs)+'''</tbody></table></div><script>document.getElementById('search').addEventListener('input',e=>{for(const r of document.querySelectorAll('tbody tr'))r.hidden=!r.cells[0].textContent.toLowerCase().includes(e.target.value.toLowerCase())})</script></html>'''
(r/'host_wise_comparison_2026-11-16.html').write_text(page,encoding='utf-8')
print('Saved',out);print('ALL HOST TOTALS RECONCILED')
print(json.dumps([{k:x[k] for k in ['host','raw_requests','grafana_requests','requests_difference','requests_difference_pct','eligible_ts_difference']} for x in records[:8]],indent=2))
