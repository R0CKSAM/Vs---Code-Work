"""Readable, uncertainty-aware comparison of two IP request profiles."""
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote
import argparse,csv,html,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'output/exports/ip_trend_20261107_20261109'
parser=argparse.ArgumentParser();parser.add_argument('--output-name',default='random_comparison');args=parser.parse_args()
if not args.output_name.replace('_','').isalnum():raise ValueError('Output name must be a simple folder name')
OUT=BASE/args.output_name
sample=json.loads((OUT/'analysis.json').read_text())
known=json.loads((ROOT/'output/exports/ip_detail_20261109/report.json').read_text())
trend=json.loads((BASE/'analysis.json').read_text())
left=known['overview'][0];right=sample['overview'][0]
day=sample['selection']['date_ist']
ranked='selection_kind' in sample['selection']
sample_label='Highest-hours other IP' if ranked else 'Random sample IP'
known_minutes=[r for r in trend['overlap_minutes'] if r['day']==day]
sample_minutes=sample['minute_activity']
def safe(s):return html.escape(str(s))
def fmt(v):return f'{v:,}' if isinstance(v,int) else str(v)
def provider(d):
    vals=[]
    for number,value in d['asn_decode'].items():
        vals.append('AS'+number+' / '+(value.get('as_name','Unknown')+' / '+value.get('asn_type','Unknown type') if value else 'Not decoded in local cache'))
    return '; '.join(vals)
def location(d):return '; '.join(dict.fromkeys(' / '.join(unquote(str(r.get(k) or 'Unknown')) for k in ['country','state','city']) for r in d['geography_asn']))
def decode_summary(d):
    return '; '.join(dict.fromkeys(' / '.join(str(r.get(k) or 'Unknown') for k in ['device_type','brand','model','os_name','os_version']) for r in d.get('ua_decode',[]))) or 'No exact UA match in current lookup'
maxfeeds=max((r['feeds'] for r in sample_minutes),default=0)
maxts=max((r['successful_ts_feeds'] for r in sample_minutes),default=0)
ident=sample['identifier_coverage'][0]
descriptions=sample.get('descriptive_query_metadata',[])
platforms='; '.join(dict.fromkeys(r['platform'] for r in descriptions if r['platform'])) or 'Not supplied'
devices='; '.join(dict.fromkeys(r['device_label'] for r in descriptions if r['device_label'])) or 'Not supplied'
titles='; '.join(dict.fromkeys(r['title'] for r in descriptions if r['title'])) or 'Not supplied'
known_ts=sum(r['requests'] for r in known['request_types'] if r['extension']=='ts')
sample_ts=sum(r['requests'] for r in sample['request_types'] if r['extension']=='ts' and r.get('source','stream')=='stream')
if ranked and abs(sample_ts/600-sample['selection']['estimated_request_hours'])>1e-8:raise ValueError('Selected raw TS estimate does not reconcile with ranking')
metrics=[
 ('IP',known['ip'],sample['selection']['ip']),
 ('Logged location',location(known),location(sample)),
 ('Cached ASN / provider / type',provider(known),provider(sample)),
 ('Requests',left['requests'],right['requests']),
 ('STREAM estimated requested-media hours (TS requests x 6 seconds)',round(known_ts/600,4),round(sample_ts/600,4)),
 ('First request IST',left['first_ist'],right['first_ist']),
 ('Last request IST',left['last_ist'],right['last_ist']),
 ('Active minutes of 1,440',left['active_minutes'],right['active_minutes']),
 ('Distinct host/feed pairs',left['host_candidate_pairs'],right['feeds']),
 ('Peak feed pairs in one minute',max(r['active_feeds'] for r in known_minutes),maxfeeds),
 ('Peak successful TS feed pairs in one minute',max(r['successful_ts_feeds'] for r in known_minutes),maxts),
 ('Distinct UA strings',left['uas'],right['uas']),
 ('Logged bytes (decimal GB)',round(left['bytes_sum']/1e9,4),round(right['bytes']/1e9,4)),
 ('HTTP 4xx/5xx requests',left['http_error_requests'],right['http_errors']),
 ('HTTP 4xx/5xx percentage',round(left['http_error_requests']/left['requests']*100,3),round(right['http_errors']/right['requests']*100,3)),
 ('Requests containing device_id',0,ident['device_id_requests']),
 ('Requests containing session_id',0,ident['session_id_requests']),
 ('Distinct non-placeholder app-reported Device IDs',0,sample.get('reported_identifier_counts',{}).get('device_id','Not counted')),
 ('Distinct non-placeholder app-reported session IDs',0,sample.get('reported_identifier_counts',{}).get('session_id','Not counted')),
 ('Client-reported platform','Not supplied',platforms),
 ('Client-reported device/model code','Not supplied',devices),
 ('Client-reported content title','Not supplied',titles),
 ('Exact raw UA strings','; '.join(r['UA'] for r in known['user_agents']),'; '.join(r['UA'] for r in sample['user_agents'])),
 ('Sample UA decode (device / brand / model / OS / version)','Software-client UAs; physical hardware unknown',decode_summary(sample))]
with (OUT/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['metric','suspected_automated_ip','selected_comparison_ip']);w.writerows(metrics)
fig,axes=plt.subplots(3,1,figsize=(14,11),constrained_layout=True)
fig.suptitle(sample_label+' vs investigated cloud IP | '+day+' IST',fontsize=17,fontweight='bold')
for ax,rows,title,color in [(axes[0],known['hourly'],known['ip']+' | request counts, own scale','#bd591c'),(axes[1],sample['hourly'],sample['selection']['ip']+' | request counts, own scale','#008b66')]:
    counts={int(r.get('hour',str(r.get('hour_ist',''))[11:13] or 0)):r['requests'] for r in rows}
    ax.plot(range(24),[counts.get(h,0) for h in range(24)],marker='o',color=color,linewidth=2)
    ax.fill_between(range(24),[counts.get(h,0) for h in range(24)],alpha=.1,color=color)
    ax.set(title=title,ylabel='Requests / hour',xticks=range(0,24,2),xlim=(0,23),ylim=(0,None))
def minuteindex(value):
    t=datetime.fromisoformat(value);return t.hour*60+t.minute
km={minuteindex(r['minute_ist']):r['active_feeds'] for r in known_minutes}
sm={minuteindex(r['minute_ist']):r['feeds'] for r in sample_minutes}
axes[2].plot(range(1440),[km.get(i,0) for i in range(1440)],label='Investigated cloud IP',color='#bd591c',linewidth=1.3)
axes[2].plot(range(1440),[sm.get(i,0) for i in range(1440)],label=sample_label,color='#008b66',linewidth=1.8)
axes[2].set(title='Distinct feed pairs requested within each minute | same scale',ylabel='Host + feed candidate pairs',xlabel='Time (IST)',xticks=range(0,1440,120),xticklabels=[f'{h:02}:00' for h in range(0,24,2)],ylim=(0,None),xlim=(0,1439));axes[2].legend()
for ax in axes:ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
fig.savefig(OUT/'comparison.png',dpi=150,facecolor='white');fig.savefig(OUT/'comparison.svg',facecolor='white');plt.close(fig)
# Activity windows are gaps between requests, not measured playback sessions.
windows=[]
for row in sample_minutes:
    now=datetime.fromisoformat(row['minute_ist'])
    if not windows or (now-datetime.fromisoformat(windows[-1]['last_ist'])).total_seconds()>1800:
        windows.append({'first_ist':str(now),'last_ist':str(now),'requests':row['requests'],'active_minutes':1})
    else:windows[-1]['last_ist']=str(now);windows[-1]['requests']+=row['requests'];windows[-1]['active_minutes']+=1
(OUT/'activity_windows.json').write_text(json.dumps(windows,indent=2),encoding='utf-8')
def table(keys,rows):return '<table><thead><tr>'+''.join('<th>'+safe(k)+'</th>' for k in keys)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+safe(fmt(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
parts=['<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Random IP behaviour comparison</title><style>body{font:15px/1.6 system-ui;max-width:1400px;margin:auto;padding:24px;background:#f2f7f4;color:#183c30}section{padding:20px;background:white;border:1px solid #c3dcca;border-radius:12px;margin:18px 0;overflow:auto}h1{font-size:25px;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;min-width:640px}td,th{text-align:left;padding:10px;border-bottom:1px solid #dce8df;overflow-wrap:anywhere;max-width:560px;font-size:13px}img{width:100%;height:auto}a{color:#007c55}</style></head><body><h1>Client IP behaviour comparison — '+safe(day)+' IST</h1><p>First random selection retained. The sample is not labelled a confirmed person: a consumer-looking UA and a short viewing pattern are evidence of viewer-like activity, not proof of identity or intent.</p><section><h2>Selection method</h2><p>'+safe(sample['selection']['method'])+'</p><p>Selection pool: '+fmt(sample['selection']['pool_size'])+' distinct IPs. Both STREAM and FAST were subsequently checked for the selected IP.</p></section><section><h2>Side-by-side evidence</h2>'+table(['Metric','Investigated cloud IP','Random sample IP'],metrics)+'</section><section><h2>Activity comparison</h2><p>The two request-count panels use different vertical scales so both patterns remain visible. The feed-overlap panel uses one shared scale. Zero means no logged request in the fully scanned day.</p><img src="comparison.png" alt="Hourly requests and minute-level feed activity for both IPs"></section>']
for name in ['feed_activity','request_types','errors','geography_asn','user_agents','repeated_playlists']:
    rows=sample[name]
    if rows:parts+=['<section><h2>Random sample: '+safe(name.replace('_',' '))+'</h2>'+table(list(rows[0]),[list(r.values()) for r in rows])+'</section>']
if not ranked:parts+=['<section><h2>Assessment of this sample</h2><p>This first randomly selected IP has a viewer-like mobile-player pattern: a short, bounded burst on one feed, playlist plus video and audio requests, a mobile-ISP ASN, Android 16 player UA, and the client-reported platform '+safe(platforms)+' with device/model code '+safe(devices)+'. All 193 responses are HTTP 200 with no logged errorCode. This supports ordinary playback activity; it does not prove one person or exact watch duration.</p><p>The saved UA decoder generically labels this UA desktop. That label conflicts with the explicit Android mobile app metadata and is not used as physical-device evidence here. The manufacturer and commercial model name remain unverified.</p><p>The existing feed map labels this host/candidate Davis Cup (f98c8), while the client-supplied title is '+safe(titles)+'. The comparison preserves both labels; the feed mapping alone does not establish the programme playing at that time.</p></section>']
parts+=['<section><h2>Observed request activity windows</h2><p>Windows split after more than 30 minutes without requests. These are not measured playback sessions or watch durations.</p>'+table(list(windows[0]),[list(r.values()) for r in windows])+'</section>','<section><h2>What this comparison can establish</h2><p>Compare network classification, software-client identity, how long requests persist, whether feeds overlap, request types and repeated checks. None of these alone proves a human, malicious bot, owner or authorised purpose. IPs can be shared by several devices. Geolocation and ASN enrichment are approximate cached data; raw UA strings are client-supplied. Missing decode fields remain unknown.</p><p><a href="comparison.csv">Comparison CSV</a> · <a href="analysis.json">Sample evidence JSON</a> · <a href="comparison.png">PNG</a> · <a href="comparison.svg">SVG</a></p></section></body></html>']
if ranked:
    ranking=json.loads((OUT/'ranking_summary.json').read_text())
    summary='This IP was selected by highest estimated TS-request hours, excluding the investigated IP. High requested-media hours do not establish an ordinary viewer. The ranking retains automated clients, retries, partial transfers and overlapping streams.'
    for i in range(len(parts)):
        parts[i]=parts[i].replace('Random IP behaviour comparison','Highest-hours IP comparison').replace('Random sample IP',sample_label).replace('Random sample:',sample_label+':').replace('First random selection retained. The sample is not labelled a confirmed person: a consumer-looking UA and a short viewing pattern are evidence of viewer-like activity, not proof of identity or intent.',summary)
    automation=any(any(token in row['UA'].lower() for token in ['lavf/','ffmpeg','python-requests','adflag','curl/','wget/']) for row in sample['user_agents'])
    conclusion=('The selected IP includes explicit software-client UA signatures associated with automated fetching.' if automation else 'No FFmpeg/Python/AdFlag signature appears in the selected IP UAs. That alone does not prove a human viewer.')
    conclusion+=' It has '+str(right['active_minutes'])+' active minutes, '+str(right['feeds'])+' host/feed pairs, and a peak of '+str(maxts)+' successful TS feed pairs in one minute.'
    ids=sample.get('reported_identifier_counts',{}).get('device_id',0)
    if ids>1:conclusion+=' Requests supply '+str(ids)+' distinct non-placeholder Device ID values. This is consistent with a shared public IP used by multiple devices, a test environment, or reused/generated identifiers; it does not prove '+str(ids)+' physical devices or people.'
    repeated=sample.get('repeated_playlists',[])
    if repeated and repeated[0]['requests']>100000:
        conclusion+=' A separate anomaly is very high playlist polling: the most-requested host/path is fetched '+fmt(repeated[0]['requests'])+' times, by '+repeated[0]['UA']+'. This may indicate aggressive refresh/retry behaviour or testing; playlist response bodies and player telemetry are unavailable to establish the cause. This IP is not a clean single-viewer baseline.'
    extra='<section><h2>Highest-hours selection and interpretation</h2><p>'+safe(conclusion)+'</p><p>The selected IP ranks '+str(sample['selection']['rank'])+' overall among '+fmt(sample['selection']['pool_size'])+' STREAM IPs with TS requests. The comparison uses the highest-ranked IP other than the investigated IP. Request hours are not deduplicated or capped at 24 hours. HTTP 2xx does not guarantee a completed transfer.</p><p><a href="top_50_ip_hours.csv">Top 50 IP ranking CSV</a></p>'+table(['Overall rank','IP','TS requests','Estimated request hours','HTTP 2xx TS requests'],[[r['rank'],r['cli_ip'],r['ts_requests'],round(r['estimated_request_hours'],4),r['successful_http_ts_requests']] for r in ranking['top_50'][:10]])+'</section>'
    parts.insert(1,extra)
(OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
print(str(OUT/'report.html'));print(json.dumps({'sample':right,'peak_same_minute_feeds':maxfeeds,'peak_same_minute_ts_feeds':maxts,'location':location(sample),'provider':provider(sample),'decode':decode_summary(sample),'activity_windows':windows},default=str))
