"""Combine completed local batches without rereading raw GZIP files."""
import csv,json,sys,html
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'SPORTS-PDF'))
from validate_raw_grafana import aggregate,atomic,stamp

def main():
 folders=[ROOT/'utc15',ROOT/'utc16']
 for folder in folders:
  p=json.loads((folder/'progress.json').read_text())
  if p['phase']!='complete_local' or p['errors'] or p['bad_rows']:raise RuntimeError(f'Local inputs not complete and clean: {folder}')
 output=ROOT/'full_ist_day';output.mkdir(exist_ok=True)
 summary=aggregate([folder/'parts' for folder in folders],output,'2026-11-16')
 captures=json.loads((ROOT/'grafana_live_captures.json').read_text(encoding='utf-8-sig'))
 exactpath=ROOT/'grafana_full_exact.json'
 results=[]
 def add(metric,local,remote,reason='Same window and request conditions; source ingestion coverage may differ.'):
  results.append({'metric':metric,'raw_local':local,'grafana':remote,'difference_grafana_minus_local':remote-local,'percent_vs_local':None if local==0 else (remote-local)/local*100,'interpretation':reason})
 local=summary['windows']['target_full_ist_day']['metrics']
 view=captures['full']['data']['datasets']['viewership_stats'][0]
 add('Eligible TS requests',local['ts_eligible'],view['total_segments'])
 add('Estimated hours at 0.6 seconds',local['hours_0_6'],view['total_segments']*.6/3600)
 add('Estimated hours at 6 seconds',local['hours_6'],view['viewership_hours'],'Grafana hours rounded to two decimals; both use six-second eligible TS estimate.')
 add('Successful TS video bytes',local['video_bytes'],view['bandwidth_bytes'])
 if exactpath.exists():
  exact=json.loads(exactpath.read_text(encoding='utf-8-sig'));data=exact['response']['data']['results']['A']['frames'][0];remote={field['name']:data['data']['values'][i][0] for i,field in enumerate(data['schema']['fields'])}
  for k in ['raw_rows','users_including_blank','ts_all_status']:
   add(k,local[k],remote[k],'Local raw values vs Grafana ingested values; transformations and delivery coverage need review.')
  for lk,rk in [('device_ids_including_blank','unique_devices_approx'),('session_ids_including_blank','session_ids_approx'),('ip_ua_pairs','ip_ua_approx')]:
   add(rk,local[lk],remote[rk],'Diagnostic only: local exact/raw parsing vs Grafana approximate and transformed identifiers; not an exact-equivalence test.')
 report={'createdAt':stamp(),'window':summary['windows']['target_full_ist_day'],'input_batches':[json.loads((f/'progress.json').read_text()) for f in folders],'results':results,'coverage_note':'Both supplied UTC-date folders used. A complete local file inventory does not certify the upstream download inventory. Exact repeated lines detected and retained.','duplicates_extra_rows':local['raw_rows']-local['distinct_raw_lines']}
 atomic(output/'comparison.json',report)
 with (output/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 rows=''.join('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in [r['metric'],f"{r['raw_local']:,.3f}",f"{r['grafana']:,.3f}",f"{r['percent_vs_local']:+.3f}%" if r['percent_vs_local'] is not None else 'N/A',r['interpretation']])+'</tr>' for r in results)
 page='<!doctype html><html><meta charset="utf-8"><title>16 November Raw / Grafana Comparison</title><style>body{font:16px Arial;background:#f4f7fb;color:#173452;max-width:1300px;margin:40px auto;padding:24px}h1{color:#112d50}table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;border-bottom:1px solid #dbe3ec;text-align:left}th{background:#112d50;color:white}p{line-height:1.6}.callout{padding:18px;background:#fff0e5;border-left:4px solid #f36c2c}</style><h1>Raw logs vs Grafana</h1><h2>16 November 2026 · Full IST day</h2><p>00:00–24:00 IST = 15 November 18:30 UTC through 16 November 18:30 UTC (end exclusive).</p><p class="callout">Both local UTC-date folders were parsed. Counts are compared with live, unfiltered Grafana aggregates. Differences are shown as (Grafana − local) ÷ local. Approximate/transformed identifier comparisons are diagnostic, not exact-equivalence tests.</p><table><tr><th>Metric</th><th>Raw local</th><th>Grafana</th><th>Difference %</th><th>Interpretation</th></tr>'+rows+'</table><p>Exact repeated lines retained: '+str(report['duplicates_extra_rows'])+'. Raw files and shared lake were not changed. This audit cannot certify upstream file-delivery completeness.</p></html>'
 (output/'comparison.html').write_text(page,encoding='utf-8')
 print(json.dumps(report,indent=2));print('COMPARISON READY:',output/'comparison.csv')
if __name__=='__main__':main()
