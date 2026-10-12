from __future__ import annotations
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from raw_sqlite import RawSQLite, PageError

st.set_page_config(page_title='VETO | Live Stream Analytics',page_icon='📡',layout='wide')
st.markdown('''<style>
.block-container{padding-top:1.5rem;max-width:1500px}
h1,h2,h3{letter-spacing:-.03em}
[data-testid="stMetric"]{border:1px solid #ced6e233;border-radius:8px;padding:15px}
</style>''', unsafe_allow_html=True)
st.title('VETO | Streaming Analytics')
st.caption('Read-only physical SQLite B-tree inspection • No SQL connection • No recovery database')

DEFAULT_DB=r'D:\live_monitor.sqlite3'
with st.sidebar:
    st.header('Database & scan')
    path=st.text_input('Database file',value=DEFAULT_DB)
    max_pages=st.number_input('Maximum B-tree pages / scan',100,10000000,20000,step=1000)
    max_rows=st.number_input('Maximum rows / scan',100,5000000,100000,step=10000)
    max_cell_mb=st.slider('Maximum record size (MiB)',1,32,8)
    st.caption('Caps protect RAM and allow bounded scans. This is a sample unless the traversal finishes.')
    st.warning('Do not scan while the database is being written. Take a consistent snapshot if needed.')

p=Path(path)
if not p.is_file():
    st.error(f'File not found: {path}'); st.stop()

try:
    with RawSQLite(path,max_cell_bytes=max_cell_mb*1024*1024) as db:
        table_info=db.tables()
        header_info={'physical_pages':db.page_count,'page_size':db.page_size,'size_gb':p.stat().st_size/1024**3}
except (OSError,PageError) as e:
    st.error(f'Cannot inspect database: {e}'); st.stop()

if not table_info:
    st.error('No readable sqlite_schema table entries found.'); st.stop()
names=[t.name for t in table_info]
with st.sidebar:
    start=names.index('daily_viewers') if 'daily_viewers' in names else 0
    table_name=st.selectbox('Table',names,index=start)
    date_prefix=st.text_input('Date prefix (YYYY-MM-DD)',value='',help='Blank for all. Applied during scan.')
    channel_filter=st.text_input('Channel / target contains',value='')
    host_filter=st.text_input('Host contains',value='')
    show_rows=st.slider('Preview row limit',10,500,100)
    trigger=st.button('Scan selected table',type='primary',use_container_width=True)

selected=next(t for t in table_info if t.name==table_name)
st.caption(f'{len(names)} discovered tables • {header_info["size_gb"]:.2f} GiB file • {header_info["physical_pages"]:,} physical pages • {header_info["page_size"]} byte pages')
st.subheader(table_name)
with st.expander('Table SQL structure'):
    st.code(selected.sql,language='sql')

COLUMNS={
'files':['path','size','mtime_ns','stable_count','status','attempts','next_attempt_at','discovered_at','updated_at','rows','rejected_rows','min_event_ts','max_event_ts','error'],
'minute_metrics':['minute_ist','req_host','target','requests','bytes','errors_4xx','errors_5xx','media_segments','ttfb_samples','ttfb_total_ms','turnaround_samples','turnaround_total_ms','transfer_samples','transfer_total_ms','throughput_samples','throughput_total','tls_overhead_samples','tls_overhead_total_ms','delivery_edge_issues'],
'minute_viewers':['minute_ist','req_host','target','viewer_key'],
'daily_viewers':['date_ist','req_host','target','viewer_key'],
'runtime_events':['occurred_at','level','component','message'],
'metadata':['key','value'],
'minute_devices':['minute_ist','req_host','target','device_key'],
'minute_sessions':['minute_ist','req_host','target','session_key'],
'minute_dimensions':['minute_ist','req_host','target','dimension','value','requests','bytes'],
'viewer_history':['target','viewer_key','first_seen_ist','last_seen_ist'],
'minute_quality_dimensions':['minute_ist','req_host','target','dimension','value','requests','errors_4xx','errors_5xx','ttfb_samples','ttfb_total_ms','turnaround_samples','turnaround_total_ms','throughput_samples','throughput_total']}

if 'result' not in st.session_state: st.session_state.result=None
if trigger:
    counts=Counter(); by_day=Counter(); by_channel=Counter(); by_host=Counter()
    by_day_channel=Counter(); samples=[]; warnings=[]
    matches=0; visited_rows=0
    cols=COLUMNS.get(table_name,[])
    is_viewers=table_name in ('daily_viewers','minute_viewers','minute_devices','minute_sessions')
    progress=st.progress(0,text='Reading database pages…')
    with RawSQLite(path,max_cell_bytes=max_cell_mb*1024*1024) as reader:
        stop=lambda: False
        for rowid,values in reader.scan_table(selected.root,max_pages=int(max_pages),max_rows=int(max_rows),stop=stop):
            visited_rows+=1
            if len(values)>len(cols):
                cols=cols+[f'extra_{i}' for i in range(len(values)-len(cols))]
            r=dict(zip(cols,values))
            r['rowid']=rowid
            date=str(r.get('date_ist') or r.get('minute_ist') or '')[:10]
            channel=str(r.get('target',''))
            host=str(r.get('req_host',''))
            if date_prefix and not date.startswith(date_prefix.strip()): continue
            if channel_filter and channel_filter.casefold() not in channel.casefold(): continue
            if host_filter and host_filter.casefold() not in host.casefold(): continue
            matches+=1
            counts['matching_rows']+=1
            if date: by_day[date]+=1
            if channel: by_channel[channel]+=1
            if host: by_host[host]+=1
            if date and channel: by_day_channel[(date,channel)]+=1
            if len(samples)<show_rows: samples.append(r)
            if visited_rows%5000==0:
                progress.progress(min(0.99,visited_rows/max_rows),text=f'Read {visited_rows:,} rows; matched {matches:,}')
        stats=dict(reader.stats)
    progress.empty()
    st.session_state.result=dict(table=table_name,filters=(date_prefix,channel_filter,host_filter),matches=matches,visited_rows=visited_rows,
        by_day=dict(by_day),by_channel=dict(by_channel),by_host=dict(by_host),by_day_channel=[{'day':d,'channel':c,'rows':n} for (d,c),n in by_day_channel.items()],
        samples=samples,stats=stats,max_pages=max_pages,max_rows=max_rows,cols=cols)

r=st.session_state.result
if not r or r['table']!=table_name:
    st.info('Select a table and click **Scan selected table**. `daily_viewers` is selected by default.'); st.stop()
if r['filters']!=(date_prefix,channel_filter,host_filter):
    st.info('Filters changed. Click **Scan selected table** to update results.'); st.stop()

c1,c2,c3,c4=st.columns(4)
c1.metric('Rows scanned',f'{r["visited_rows"]:,}')
c2.metric('Matching rows',f'{r["matches"]:,}')
c3.metric('B-tree pages read',f'{r["stats"].get("btree_pages",0):,}')
c4.metric('Bad pages / cells',f'{r["stats"].get("bad_pages",0):,} / {r["stats"].get("bad_cells",0):,}')

if r['stats'].get('page_limit_hit') or r['stats'].get('row_limit_hit'):
    st.warning('The scan reached a configured limit. These counts cover only scanned records, NOT complete table totals.')
else:
    st.caption('Traversal finished within configured limits. Counts describe successfully decoded, reachable records, not guaranteed complete data in the damaged database.')
if r['stats'].get('bad_pages') or r['stats'].get('bad_cells'):
    st.warning('Damaged pages or records were skipped. Figures may underestimate actual activity.')
if table_name in ('daily_viewers','minute_viewers'):
    st.info('Each decoded row represents a viewer key for a date/minute + host + target. Counts below are matching viewer-key rows, not verified unique people. `__all__` may duplicate channel-level rows: filter or exclude it before interpreting audience totals.')

left,right=st.columns(2)
with left:
    st.markdown('#### Activity by date')
    if r['by_day']:
        d=pd.DataFrame(sorted(r['by_day'].items()),columns=['Date','Rows']).set_index('Date')
        st.bar_chart(d)
    else: st.caption('No dated records in this scan.')
with right:
    st.markdown('#### Top channels / targets')
    if r['by_channel']:
        d=pd.DataFrame(Counter(r['by_channel']).most_common(15),columns=['Channel','Rows']).set_index('Channel')
        st.bar_chart(d,horizontal=True)
    else: st.caption('No target field for this table.')

st.markdown('#### Records preview')
if r['samples']:
    df=pd.DataFrame(r['samples'])
    st.dataframe(df,use_container_width=True,height=360)
    st.download_button('Download preview CSV',data=df.to_csv(index=False).encode('utf-8-sig'),file_name=f'{table_name}_preview.csv',mime='text/csv')
else: st.write('No matching rows decoded in this scan.')
with st.expander('Technical scan details'):
    st.json(r['stats'])
    st.caption('This dashboard is an inspection tool: there is no SQL optimizer, index search, or random-access date lookup. The scan visits table B-tree pages and handles standard overflow chains. Some corrupt or orphaned records may be inaccessible.')
