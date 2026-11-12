"""Reformat a country export with all-status TS request estimates, without rescanning lake."""
import csv,json,sys
from pathlib import Path
from collections import defaultdict
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter

def run(folder):
    folder=Path(folder)
    summary=json.loads((folder/'summary.json').read_text())
    with (folder/'all_request_activity.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    records=[];channels=defaultdict(lambda:defaultdict(int));ips=defaultdict(set)
    for r in rows:
        n=int(r['ts_requests'])
        record={'date_ist':summary['date_ist'],'cliIP':r['cliIP'],'channel':r['channel_name'],
          'all_http_ts_request_hours':n/600,'all_http_ts_requests':n,
          'all_requests':int(r['all_requests']),
          'http200_ts_requests':int(r['http200_ts_requests']),
          'http206_ts_requests':int(r['http206_ts_requests']),
          'other_http_ts_requests':n-int(r['http200_ts_requests'])-int(r['http206_ts_requests']),
          'http_error_requests_all_types':int(r['http_error_requests']),
          'http200_deduplicated_estimated_hours':float(r['estimated_watch_hours']),
          'regions':r['regions'],'cities':r['cities'],
          'first_request_ist':r['first_request_ist'],'last_request_ist':r['last_request_ist']}
        records.append(record)
        c=channels[r['channel_name']]
        for key in ['all_http_ts_requests','all_requests','http200_ts_requests','http206_ts_requests','other_http_ts_requests']:
            c[key]+=record[key]
        if n:ips[r['channel_name']].add(r['cliIP'])
    records.sort(key=lambda r:(-r['all_http_ts_request_hours'],-r['all_requests'],r['cliIP']))
    active=[r for r in records if r['all_http_ts_requests']]
    channel_rows=[{'channel':name,'client_ips_with_ts':len(ips[name]),'all_http_ts_request_hours':c['all_http_ts_requests']/600,**c} for name,c in channels.items()]
    channel_rows.sort(key=lambda r:-r['all_http_ts_request_hours'])
    wb=Workbook();wb.remove(wb.active)
    for title,data in [('IP channel watch hours',active),('Channel summary',channel_rows),('All request activity',records)]:
        headers=list(data[0]) if data else ['No matching records']
        ws=wb.create_sheet(title);ws.append(headers)
        with (folder/(title.lower().replace(' ','_')+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(headers)
            for r in data:
                values=[r[h] for h in headers];ws.append(values)
                w.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in values])
    with (folder/'unmapped_feeds.csv').open(encoding='utf-8-sig',newline='') as f:
        ws=wb.create_sheet('Unmapped feeds')
        for row in csv.reader(f):ws.append(row)
    summary.update({'http_scope':'ALL HTTP statuses','all_http_ts_requests':sum(r['all_http_ts_requests'] for r in records),
      'all_http_ts_request_hours':sum(r['all_http_ts_requests'] for r in records)/600,
      'client_ips_with_ts':len({r['cliIP'] for r in active}),
      'mapped_channels_with_ts':len({r['channel'] for r in active if r['channel']!='Other'}),
      'ip_channel_rows':len(active)})
    assert sum(r['all_requests'] for r in records)==summary['requests']
    assert sum(r['all_http_ts_requests'] for r in channel_rows)==summary['all_http_ts_requests']
    notes=wb.create_sheet('Read me');notes.append(['Item','Definition'])
    for k,v in summary.items():notes.append([k,str(v)])
    for row in [
      ['Primary hours','All-status .ts request count x assumed 6 seconds / 3600. Includes failed requests and repeated requests; not deduplicated. This is requested media duration, NOT confirmed playback/watch time.'],
      ['Comparison hours','http200_deduplicated_estimated_hours preserves existing STREAM profile rule: distinct successful cliIP/channel/reqPath x 6 seconds.'],
      ['All HTTP','No HTTP status excluded. Playlists and other files included in all_requests but add no watch hours.'],
      ['Country and date','Logged client country BD/Bangladesh; full selected IST date. Bangladesh local time is 30 minutes ahead.'],
      ['Client IP','An IP is not necessarily a single viewer. Shared networks and automated requests remain included.'],
      ['Channel mapping','Existing production host/candidate mapping. Other remains unresolved; see Unmapped feeds.'],
      ['First and last request','All-request activity boundaries, not session duration.'],
      ['Validation','All-request totals reconcile to extract; TS totals reconcile across IP and channel sheets.']]:notes.append(row)
    for ws in wb:
        ws.freeze_panes='A2'
        if ws.title!='Read me':ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='176B4B')
        for i,cell in enumerate(ws[1],1):ws.column_dimensions[get_column_letter(i)].width=44 if cell.value=='cliIP' else 30
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value,str):cell.data_type='s'
                if isinstance(cell.value,float):cell.number_format='0.0000'
                cell.alignment=Alignment(vertical='top',wrap_text=True)
    notes.column_dimensions['B'].width=110
    path=folder/f"STREAM_{summary['country']}_{summary['date_ist']}_IP_channel_watch_hours.xlsx"
    wb.save(path)
    check=load_workbook(path,read_only=True);assert check['IP channel watch hours'].max_row==len(active)+1;check.close()
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'file':str(path),**summary},indent=2))

if __name__=='__main__':run(sys.argv[1])
