"""Export country-filtered STREAM IP/channel estimates using production profile rules."""
import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src/profile'))
from src.common.lake_partitions import resolve_lake_roots, partition_for_date
from vglive_core import channel_candidate_sql, _register_mapping_tables


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--date', required=True)
    p.add_argument('--country', default='BD')
    args = p.parse_args()
    day = args.date
    country = args.country.upper()
    start = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=5, minutes=30))).timestamp()
    part = partition_for_date(resolve_lake_roots(ROOT / 'data/lake'), 'stream', day)
    if not part:
        raise FileNotFoundError(day)
    out = ROOT / 'output/exports' / f'stream_{country}_{day}'
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET threads=2')
    con.execute("SET memory_limit='2GB'")
    print(f'Scanning {len(part.files)} STREAM partition files for {country} on {day} IST', flush=True)
    con.execute('''CREATE TABLE raw AS SELECT cliIP,lower(reqHost) AS reqHost,reqPath,
      try_cast(statusCode AS INT) AS status,try_cast(reqTimeSec AS DOUBLE) AS epoch,
      country,state,city FROM read_parquet(?,hive_partitioning=false,union_by_name=true)
      WHERE upper(trim(country)) IN (?,?) AND try_cast(reqTimeSec AS DOUBLE)>=?
      AND try_cast(reqTimeSec AS DOUBLE)<?''',
      [[str(f) for f in part.files], country, 'BANGLADESH' if country == 'BD' else country, start, start + 86400])
    print('Country extract:', con.execute('SELECT count(*) FROM raw').fetchone()[0], flush=True)
    _register_mapping_tables(con)
    con.execute(f'''CREATE VIEW base AS SELECT *,{channel_candidate_sql()} AS candidate_id FROM raw''')
    con.execute('''CREATE TABLE mapped AS SELECT b.*,
      coalesce(hc.host_candidate_channel_name,h.host_channel_name,p.path_channel_name,'Other') AS channel_name
      FROM base b LEFT JOIN host_candidate_map hc ON b.reqHost=hc.reqHost AND b.candidate_id=hc.candidate_id
      LEFT JOIN host_map h ON b.reqHost=h.reqHost LEFT JOIN path_map p ON b.candidate_id=p.candidate_id''')
    con.execute('''CREATE TABLE detail AS SELECT cliIP,channel_name,
      count(DISTINCT reqPath) FILTER(WHERE status=200 AND reqPath LIKE '%.ts') AS distinct_successful_segments,
      distinct_successful_segments/600.0 AS estimated_watch_hours,
      count(*) AS all_requests,
      count(*) FILTER(WHERE reqPath LIKE '%.ts') AS ts_requests,
      count(*) FILTER(WHERE status=200 AND reqPath LIKE '%.ts') AS http200_ts_requests,
      count(*) FILTER(WHERE status=206 AND reqPath LIKE '%.ts') AS http206_ts_requests,
      count(*) FILTER(WHERE status BETWEEN 400 AND 599) AS http_error_requests,
      string_agg(DISTINCT coalesce(state,''),'; ' ORDER BY coalesce(state,'')) AS regions,
      string_agg(DISTINCT coalesce(city,''),'; ' ORDER BY coalesce(city,'')) AS cities,
      to_timestamp(min(epoch)) AT TIME ZONE 'Asia/Kolkata' AS first_request_ist,
      to_timestamp(max(epoch)) AT TIME ZONE 'Asia/Kolkata' AS last_request_ist
      FROM mapped GROUP BY cliIP,channel_name''')
    queries = {
      'IP channel watch hours': "SELECT ? AS date_ist,? AS country,* FROM detail WHERE distinct_successful_segments>0 ORDER BY estimated_watch_hours DESC,cliIP,channel_name",
      'Channel summary': '''SELECT channel_name,count(DISTINCT cliIP) FILTER(WHERE distinct_successful_segments>0) AS active_client_ips,
        sum(distinct_successful_segments) AS distinct_successful_segments,sum(estimated_watch_hours) AS estimated_watch_hours,
        sum(all_requests) AS all_requests,sum(http206_ts_requests) AS http206_ts_requests FROM detail GROUP BY channel_name ORDER BY estimated_watch_hours DESC''',
      'All request activity': 'SELECT * FROM detail ORDER BY estimated_watch_hours DESC,all_requests DESC',
      'Unmapped feeds': '''SELECT reqHost,candidate_id,count(*) AS requests,
        count(*) FILTER(WHERE status=200 AND reqPath LIKE '%.ts') AS http200_ts_requests
        FROM mapped WHERE channel_name='Other' GROUP BY ALL ORDER BY requests DESC'''
    }
    wb = Workbook(); wb.remove(wb.active)
    exported = {}
    for title, sql in queries.items():
        cur = con.execute(sql, [day,country] if title == 'IP channel watch hours' else [])
        headers = [c[0] for c in cur.description]; rows = cur.fetchall(); exported[title] = rows
        ws = wb.create_sheet(title); ws.append(headers)
        with (out / (title.lower().replace(' ','_')+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.writer(f); writer.writerow(headers)
            for row in rows:
                writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])
                ws.append(row)
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='176B4B')
        for i,header in enumerate(headers,1):
            ws.column_dimensions[get_column_letter(i)].width=44 if header=='cliIP' else 28
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,str): cell.data_type='s'
                if isinstance(cell.value,float): cell.number_format='0.0000'
    raw_count = con.execute('SELECT count(*) FROM raw').fetchone()[0]
    totals = con.execute('''SELECT sum(all_requests),sum(distinct_successful_segments),sum(estimated_watch_hours),
      count(DISTINCT cliIP) FILTER(WHERE distinct_successful_segments>0),
      count(DISTINCT channel_name) FILTER(WHERE distinct_successful_segments>0 AND channel_name<>'Other') FROM detail''').fetchone()
    assert (totals[0] or 0) == raw_count
    assert abs((totals[2] or 0)-(totals[1] or 0)/600)<1e-8
    summary={'date_ist':day,'country':country,'requests':raw_count,'distinct_successful_segments':totals[1] or 0,
      'estimated_watch_hours':totals[2] or 0,'client_ips_with_segments':totals[3],
      'mapped_channels_with_segments':totals[4], 'ip_channel_rows':len(exported['IP channel watch hours']),
      'unmapped_feed_rows':len(exported['Unmapped feeds']), 'source_files':[str(f) for f in part.files]}
    notes=wb.create_sheet('Read me')
    notes.append(['Item','Definition'])
    for k,v in summary.items(): notes.append([k,str(v)])
    for row in [
      ['Time','Full IST day; Bangladesh local time is 30 minutes ahead.'],
      ['Country','Logged client country BD/Bangladesh; not server country or ASN registration country.'],
      ['Estimated watch hours','Existing STREAM profile rule: HTTP 200, path ends .ts, distinct cliIP + mapped channel + reqPath, assumed 6 seconds each / 3600.'],
      ['Other responses','206, errors and playlists excluded from hours; included in All request activity for transparency.'],
      ['Mapping','Existing production host/candidate rules. Other means unresolved; exact host/candidate details retained in Unmapped feeds.'],
      ['Limitations','IP is not a person. Shared addresses, automated traffic, retries and varying segment duration can distort estimates. These are not measured player watch hours.'],
      ['Activity times','First/last request times include all requests, not session duration.'],
      ['Validation','Request totals reconcile to country extract; segment total / 600 reconciles to hours.']]:notes.append(row)
    notes.column_dimensions['A'].width=32;notes.column_dimensions['B'].width=110
    path=out/f'STREAM_{country}_{day}_IP_channel_watch_hours.xlsx';wb.save(path)
    check=load_workbook(path,read_only=True);assert check['IP channel watch hours'].max_row==summary['ip_channel_rows']+1;check.close()
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'workbook':str(path),**summary},indent=2),flush=True)

if __name__=='__main__': main()
