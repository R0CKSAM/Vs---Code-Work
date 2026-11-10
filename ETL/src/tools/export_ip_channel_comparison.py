"""One workbook comparing all logged requests with TS-only channel activity."""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo
import json,re,sys,shutil
import duckdb
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/profile'))
from vglive_core import HOST_MAP,PATH_MAP,HOST_CANDIDATE_MAP

IP='2400:8904::2000:b1ff:fe6b:989d';DAY='2026-11-09'
OUT=ROOT/'output/exports/ip_detail_20261109'
reference=json.loads((OUT/'report.json').read_text())
assert reference['ip']==IP and reference['date_ist']==DAY
source=ROOT/'output/exports/ip_trend_20261107_20261109/deep_dive/raw_ip_20261109.parquet'
con=duckdb.connect();con.execute('SET threads=2')
q=con.execute("""SELECT reqHost,reqPath,count(*) AS requests,
 count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 200 AND 299) AS http_2xx,
 count(*) FILTER(WHERE statusCode='200') AS http_200,
 count(*) FILTER(WHERE statusCode='206') AS http_206,
 count(*) FILTER(WHERE try_cast(statusCode AS INT) BETWEEN 400 AND 599) AS http_errors,
 count(*) FILTER(WHERE errorCode LIKE 'ERR_CLIENT_ABORT%') AS client_aborts
 FROM read_parquet(?) GROUP BY reqHost,reqPath""",[str(source)])
pairs=[dict(zip([c[0] for c in q.description],row)) for row in q.fetchall()]

def identify(host,path):
    host=host.strip().lower();clean=unquote(path).lower();tokens=clean.strip('/').split('/');candidates=[]
    for token in tokens:
        if token in PATH_MAP:candidates.append((token,'Approved path ID'))
        m=re.fullmatch(r'epic[-_](tv|bharat|bhojpuri|kids|music)(?:[-_]o)?[-_]\d+p',token)
        if m:candidates.append(('epic_'+m.group(1),'Rendition alias of approved path ID'))
    for token in re.findall(r'vglive-sk-\d+',clean):
        if token in PATH_MAP:candidates.append((token,'Approved path ID'))
    for token in tokens:
        if (host,token) in HOST_CANDIDATE_MAP:return HOST_CANDIDATE_MAP[(host,token)],'Approved host + path ID',token
    path_names={PATH_MAP[token] for token,_ in candidates}
    if host in HOST_MAP:
        if path_names and path_names!={HOST_MAP[host]}:return None,'Conflicting host and path evidence',''
        return HOST_MAP[host],'Approved host mapping',host
    if len(path_names)==1:
        token,rule=candidates[0];return next(iter(path_names)),rule,token
    return None,'No unique approved channel ID',''

# Root playlists can have no path identity. Associate only when that same host
# has exactly one named channel supported by other approved paths in this file.
observed=defaultdict(set)
for row in pairs:
    row['identity']=identify(row['reqHost'],row['reqPath'])
    if row['identity'][0]:observed[row['reqHost'].lower()].add(row['identity'][0])
channels=defaultdict(lambda:defaultdict(int));evidence=defaultdict(lambda:{'requests':0,'ts_requests':0,'sample_path':''})
for row in pairs:
    name,rule,matched=row['identity'];associated=False
    if name is None and rule!='Conflicting host and path evidence' and len(observed[row['reqHost'].lower()])==1:
        name=next(iter(observed[row['reqHost'].lower()]));rule='Host association: sole approved channel observed on this host';matched=row['reqHost'];associated=True
    if name is None:name='Unresolved / needs review'
    if name=='Ndtv India':name='NDTV India'
    path=row['reqPath'].lower();is_ts=bool(re.search(r'\.ts(?:\?|$)',path));is_playlist=bool(re.search(r'\.m3u8(?:\?|$)',path))
    c=channels[name];n=row['requests'];c['all_requests']+=n;c['ts_requests']+=n if is_ts else 0;c['playlist_requests']+=n if is_playlist else 0;c['other_requests']+=n if not is_ts and not is_playlist else 0
    if is_ts:
        for src,dst in [('http_2xx','ts_http_2xx'),('http_200','ts_http_200'),('http_206','ts_http_206'),('http_errors','ts_http_errors'),('client_aborts','ts_client_aborts')]:c[dst]+=row[src]
    c['host_associated_requests']+=n if associated else 0
    e=evidence[(name,row['reqHost'],rule,matched)];e['requests']+=n;e['ts_requests']+=n if is_ts else 0
    if not e['sample_path']:e['sample_path']=row['reqPath']
ordered=sorted(channels.items(),key=lambda x:(-x[1]['all_requests'],x[0]));totals={key:sum(c[key] for c in channels.values()) for key in ['all_requests','ts_requests','playlist_requests','other_requests','ts_http_2xx','ts_http_200','ts_http_206','ts_http_errors','ts_client_aborts','host_associated_requests']}
assert totals['all_requests']==865770 and totals['ts_requests']==387281 and totals['playlist_requests']==478489 and totals['other_requests']==0
assert totals['ts_http_2xx']==387194 and totals['ts_http_errors']==87 and totals['ts_http_200']==0
assert totals['ts_requests']+totals['playlist_requests']+totals['other_requests']==totals['all_requests']
assert len(channels)==38 and 'Unresolved / needs review' not in channels
assert sum(c['ts_requests']>0 for c in channels.values())==9
assert totals['host_associated_requests']==6770

wb=Workbook();overview=wb.active;overview.title='Summary';breakdown=wb.create_sheet('Channel breakdown');audit=wb.create_sheet('Mapping evidence');rules=wb.create_sheet('Counting rules')
overview.append(['Client IP',IP]);overview.append(['Date / timezone',DAY+' / IST (Asia/Kolkata)']);overview.append(['Source','STREAM; FAST checked separately: 0 matching requests'])
overview.append(['Generated at',datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')]);overview.append([]);overview.append(['Measure','Distinct channel names','Logged request rows'])
overview.append(['TS requests only',9,totals['ts_requests']]);overview.append(['All requests (TS + playlists)',38,totals['all_requests']]);overview.append(['Playlist requests',38,totals['playlist_requests']]);overview.append(['Playlist-only channels (no TS)',29,sum(c['all_requests'] for c in channels.values() if c['ts_requests']==0)])
overview.append([]);overview.append(['TS subset','Channels','TS request rows']);overview.append(['HTTP 2xx TS responses',9,totals['ts_http_2xx']]);overview.append(['HTTP 200 TS responses',0,0]);overview.append(['HTTP 206 TS responses',9,totals['ts_http_206']]);overview.append(['HTTP 4xx/5xx TS responses',sum(c['ts_http_errors']>0 for c in channels.values()),totals['ts_http_errors']]);overview.append(['TS responses with client-abort flag','Subset, not extra requests',totals['ts_client_aborts']]);overview.append([])
overview.append(['Read the result','9 names have TS fetching; 29 more appear only in playlist requests. All 38 are request-associated names, not proof of human watching.'])
overview.append(['Mapping caveat','6,770 root-playlist requests are associated with Epic Bharat by its host; their path has no feed identifier. This is labelled separately.'])
overview.append(['Why the earlier list had 36','It grouped host/candidate buckets. Splitting the YRF bucket into four names adds 3; merging the Epic Bharat root entry removes 1: 36 + 3 - 1 = 38.'])

headers=['Rank','Channel','Has TS requests','All requests','TS requests','Playlist requests','Other requests','TS HTTP 2xx','TS HTTP 200','TS HTTP 206','TS HTTP 4xx/5xx','TS client-abort subset','Host-associated requests']
breakdown.append(headers)
for i,(name,c) in enumerate(ordered,1):breakdown.append([i,name,'Yes' if c['ts_requests'] else 'No',*[c[k] for k in ['all_requests','ts_requests','playlist_requests','other_requests','ts_http_2xx','ts_http_200','ts_http_206','ts_http_errors','ts_client_aborts','host_associated_requests']]])
breakdown.append(['','TOTAL','9 with TS / 38 all',*[totals[k] for k in ['all_requests','ts_requests','playlist_requests','other_requests','ts_http_2xx','ts_http_200','ts_http_206','ts_http_errors','ts_client_aborts','host_associated_requests']]])
audit.append(['Channel','Observed reqHost','Mapping basis','Matched ID / host','All requests','TS requests','Example reqPath'])
for (name,host,rule,matched),e in sorted(evidence.items(),key=lambda x:(-x[1]['requests'],x[0])):audit.append([name,host,rule,matched,e['requests'],e['ts_requests'],e['sample_path']])
rules.append(['Parameter','Rule'])
for row in [
 ['IP',IP],['Date','9 November 2026, 00:00:00 inclusive to 10 November 00:00:00 exclusive, IST. Adjacent raw-date spillover included.'],
 ['Source data','Saved IP-only extract from the completed processed STREAM lake; original extraction was filtered to this IP and IST date.'],
 ['TS-only','reqPath extension .ts, including all HTTP statuses. A name is counted once if it has at least one TS request.'],
 ['All requests','All HTTP statuses and UAs; TS, playlist and any other requests. A channel name is counted once across hosts/renditions.'],
 ['Playlists','.m3u8 requests. The path mono.ts.m3u8 is a playlist, not a TS request.'],
 ['Deduplication','No request-ID or URL deduplication. Every logged row contributes once.'],
 ['Channel identity','Existing approved host/path mappings; search full path segments rather than stopping at generic hls/live. Exact Epic rendition variants are linked to their approved canonical IDs.'],
 ['Root playlist','master_360.m3u8 on epic-bharat-veto.akamaized-staging.net is host-associated with Epic Bharat, the sole approved channel observed on that host in this extract. It is not a separate channel.'],
 ['Availability','Playlist requests and mapped names do not establish that a feed was available; failed/probed URLs remain in the all-request count.'],
 ['Playback','HTTP 2xx is not proof of complete playback. The client-abort column is a subset and must not be added to status totals.'],
 ['Watch hours','Not calculated here. This workbook compares request counts and distinct channel names.'],
 ['Production changes','No ETL, channel configuration or dashboard metric was modified by this export.']]:rules.append(row)

for sheet in wb:
    sheet.freeze_panes='A2';sheet.sheet_view.zoomScale=90
    for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF',size=12);cell.fill=PatternFill('solid',fgColor='176B4B')
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value,str):cell.data_type='s'
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if isinstance(cell.value,int):cell.number_format='#,##0'
    if sheet in (breakdown,audit):sheet.auto_filter.ref=f'A1:{get_column_letter(sheet.max_column)}{sheet.max_row-(1 if sheet==breakdown else 0)}'
    sheet.print_options.horizontalCentered=True;sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
for i,width in enumerate([48,105,24],1):overview.column_dimensions[get_column_letter(i)].width=width
for i,width in enumerate([8,28,18,19,19,20,18,19,19,19,22,24,24],1):breakdown.column_dimensions[get_column_letter(i)].width=width
for i,width in enumerate([28,48,66,40,18,18,100],1):audit.column_dimensions[get_column_letter(i)].width=width
rules.column_dimensions['A'].width=26;rules.column_dimensions['B'].width=125
for r in [6,12]:
    for cell in overview[r]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='176B4B')
for row in breakdown.iter_rows(min_row=2,max_row=39):
    if row[2].value=='Yes':
        for cell in row:cell.fill=PatternFill('solid',fgColor='E5F3EA')
for cell in breakdown[40]:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='D1E9DB')
path=OUT/'cliIP_2400_8904_2026-11-09_channel_breakdown.xlsx';wb.save(path)
check=load_workbook(path,read_only=True,data_only=True);assert check['Channel breakdown'].max_row==40
rows=list(check['Channel breakdown'].iter_rows(min_row=2,max_row=39,values_only=True));assert len({r[1] for r in rows})==38 and sum(r[2]=='Yes' for r in rows)==9
assert sum(r[3] for r in rows)==865770 and sum(r[4] for r in rows)==387281 and sum(r[5] for r in rows)==478489
check.close()
download=Path(r'C:\Users\Intern\Downloads')/path.name;shutil.copy2(path,download)
print(json.dumps({'file':str(download),'workspace_copy':str(path),'ts_channels':9,'all_request_channels':38,'playlist_only_channels':29,'totals':totals,'checks':'Distinct counts, request reconciliation and saved workbook read-back passed.'}))
