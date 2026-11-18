"""Append date-level match/event context without changing combined device counts."""
from pathlib import Path
import csv,json,html,re,copy
import duckdb
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'analysis.json').read_text());source=Path(data['source']);before=source.stat()
assert before.st_size==data['source_bytes'] and before.st_mtime_ns==data['source_mtime_ns'],'Source updated: rerun the device-return analysis first.'
c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='1GB'");c.read_parquet(str(source)).create_view('r')
labels=c.execute('SELECT ist_date,list(DISTINCT "Match Name"),list(DISTINCT "Event Name") FROM r GROUP BY 1').fetchall();c.close()
context={dt:{'Match Name':' | '.join(sorted({str(x).strip() for x in matches if x is not None and str(x).strip()})),'Event Name':' | '.join(sorted({str(x).strip() for x in events if x is not None and str(x).strip()}))} for dt,matches,events in labels}
after=source.stat();assert before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns
old_counts=[(x['date_ist'],x['total_device_ids'],x['returning_device_ids']) for x in data['daily']]
for row in data['daily']:row.update(context[row['date_ist']])
data['definitions']['date_context']='Match Name and Event Name list the distinct labels represented on that date. Device counts remain deduplicated across all events; these are not event-level counts.'
with (ROOT/'daily_device_returns.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data['daily'][0]));w.writeheader();w.writerows(data['daily'])
(ROOT/'analysis.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
p=ROOT/'device_returns.html';page=p.read_text(encoding='utf-8')
page=page.replace('<th>Returning %</th>','<th>Returning %</th><th>Match Name</th><th>Event Name</th>')
def update_row(m):
    dt=m.group(1);row=context[dt]
    return m.group(0)[:-5]+''.join('<td>'+html.escape(row[k])+'</td>' for k in ['Match Name','Event Name'])+'</tr>'
page,n=re.subn(r'<tr><td>(\d{4}-\d{2}-\d{2})</td>.*?</tr>',update_row,page)
assert n==len(data['daily'])
page=page.replace('</style>','td:nth-last-child(-n+2){white-space:normal;min-width:200px;max-width:330px;text-align:left}</style>')
page=page.replace('</h1>','</h1><p>Match and event names list all labels represented on each date. Counts remain combined across all events.</p>',1)
p.write_text(page,encoding='utf-8')
from openpyxl import load_workbook
from openpyxl.styles import Alignment
wb=load_workbook(ROOT/'Sports_Daily_Device_Returns.xlsx');ws=wb['Daily device returns']
for j,k in enumerate(['Match Name','Event Name'],6):
    h=ws.cell(1,j,k);h.font=copy.copy(ws.cell(1,5).font);h.fill=copy.copy(ws.cell(1,5).fill)
    for i,row in enumerate(data['daily'],2):ws.cell(i,j,row[k]).alignment=Alignment(wrap_text=True,vertical='top')
    ws.column_dimensions[h.column_letter].width=48
ws.auto_filter.ref=ws.dimensions;wb.save(ROOT/'Sports_Daily_Device_Returns.xlsx')
assert old_counts==[(x['date_ist'],x['total_device_ids'],x['returning_device_ids']) for x in data['daily']]
assert page.count('<th>Match Name</th>')==1 and page.count('<th>Event Name</th>')==1
print(f'Updated HTML, CSV, Excel and JSON: {n} dates. Original counts unchanged.')
print([x for x in data['daily'] if ' | ' in x['Event Name']][:2])
