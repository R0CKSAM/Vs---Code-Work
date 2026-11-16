"""Export mapped sports requests without modifying source files or prior exports."""
import argparse
from datetime import datetime, date
import json
from pathlib import Path
import shutil
import sys

import duckdb
from openpyxl import load_workbook
import pandas as pd

ROOT = Path(__file__).resolve().parent
ETL = ROOT.parent
sys.path.insert(0, str(ETL / 'src/tools'))
from export_vod_query_events import ua_norm_sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    day = args.date.isoformat()
    out = ROOT / 'exports' / (day + '_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=False)
    mapping_path = ROOT / 'Reqhost Tagging.xlsx'
    rows = []
    for values in load_workbook(mapping_path, data_only=True).active.iter_rows(min_row=2, values_only=True):
        _, d, host, match, event = values
        if d and d.date() == args.date:
            rows.append(dict(ist_date=day, host_key=host.strip().lower(), match_name=match, event_name=event))
    if not rows or len({r['host_key'] for r in rows}) != len(rows):
        raise ValueError('Missing or ambiguous date/host mappings')
    shutil.copy2(mapping_path, out / mapping_path.name)
    ua_path = out / 'ua_lookup_snapshot.parquet'
    shutil.copy2(ETL / 'output/device_decode/ua_decode_lookup_both_all.parquet', ua_path)
    asn_path = out / 'asn_lookup_snapshot.json'
    shutil.copy2(ETL / 'data/asn/ip2location_asn_cache.json', asn_path)
    cache = json.loads(asn_path.read_text(encoding='utf-8-sig'))
    asn_rows = [{'asn_key': str(k), **{'asn_decoded_' + key: str(value) if value is not None else None
                                      for key, value in entry.items()}} for k, entry in cache.items()]
    lake = Path(r'Z:\Veto Logs Backup\DO NOT DELETE') / 'source=stream' / f'year={args.date:%Y}' / f'month={args.date:%m}' / f'day={args.date:%d}'
    files = [str(p) for p in sorted(lake.glob('*.parquet'))]
    if not files:
        raise FileNotFoundError(lake)
    c = duckdb.connect(config={'threads': 2, 'memory_limit': '4GB', 'temp_directory': str(out / 'scratch')})
    c.register('mapping', pd.DataFrame(rows))
    c.register('asn_lookup', pd.DataFrame(asn_rows))
    raw_path = out / 'source_requests.parquet'
    print('Extracting all requests for mapped date/hosts...', flush=True)
    def sqlpath(path): return "'" + str(path).replace("'", "''") + "'"
    c.execute(f'''COPY (SELECT r.*, filename AS source_lake_file,
        to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS request_ist,
        m.ist_date, m.match_name, m.event_name
        FROM read_parquet(?, hive_partitioning=false, filename=true) r
        JOIN mapping m ON lower(trim(r.reqHost))=m.host_key
        WHERE CAST(to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS DATE)=CAST(? AS DATE)
        ) TO {sqlpath(raw_path)} (FORMAT PARQUET, COMPRESSION ZSTD)''', [files, day])
    c.read_parquet(str(raw_path)).create_view('requests')
    c.read_parquet(str(ua_path)).create_view('ua_snapshot')
    c.execute(f'CREATE TEMP TABLE ua_keys AS SELECT UA, {ua_norm_sql("UA")} AS normalized_ua FROM (SELECT DISTINCT UA FROM requests)')
    c.execute('''CREATE TEMP TABLE ua_latest AS SELECT * EXCLUDE(rn) FROM
        (SELECT *, row_number() OVER(PARTITION BY ua_norm ORDER BY decoded_at_utc DESC NULLS LAST) rn FROM ua_snapshot) WHERE rn=1''')
    ua_fields = [r[0] for r in c.execute('DESCRIBE ua_latest').fetchall()]
    asn_fields = list(pd.DataFrame(asn_rows).columns)
    def q(name): return '"' + name.replace('"', '""') + '"'
    ua_select = ', '.join('u.' + q(f) + ' AS ' + q('ua_decoded_' + f) for f in ua_fields)
    asn_select = ', '.join('a.' + q(f) for f in asn_fields if f != 'asn_key')
    def query(name):
        raw = f"NULLIF(regexp_extract(queryStr, '(?i)(?:^|[?&]){name}=([^&]*)', 1),'')"
        return f'coalesce(try(url_decode({raw})),{raw})'
    detailed = out / 'sports_requests_enriched.parquet'
    print('Adding UA, ASN and query-string details; preserving every original column...', flush=True)
    c.execute(f'''COPY (SELECT r.*, 'stream' AS source,
        {query('device_id')} AS device_id, {query('session_id')} AS session_id,
        {query('content_title')} AS query_content_title, {query('category_name')} AS query_category_name,
        {query('platform')} AS query_platform, {query('device')} AS query_device,
        {query('channel_name')} AS query_channel_name,
        nullif(trim(cliIP),'') AS cli_ip,
        regexp_matches(lower(split_part(coalesce(reqPath,''),'?',1)), '\\.ts$') AS is_ts_request,
        regexp_matches(lower(split_part(coalesce(reqPath,''),'?',1)), '\\.m3u8$') AS is_playlist_request,
        try_cast(statusCode AS INTEGER) AS http_status,
        k.normalized_ua,
        {ua_select}, {asn_select},
        coalesce(u.decode_status,'not_in_lookup') AS ua_lookup_status,
        coalesce(a.asn_decoded_status,'not_in_lookup') AS asn_lookup_status
        FROM requests r LEFT JOIN ua_keys k ON r.UA IS NOT DISTINCT FROM k.UA
        LEFT JOIN ua_latest u ON k.normalized_ua=u.ua_norm
        LEFT JOIN asn_lookup a ON regexp_replace(upper(trim(r.asn)),'^AS','')=a.asn_key
        ) TO {sqlpath(detailed)} (FORMAT PARQUET, COMPRESSION ZSTD)''')
    c.read_parquet(str(detailed)).create_view('enriched')
    summary = out / 'sports_audience_summary.parquet'
    c.execute(f'''COPY (SELECT ist_date, reqHost AS "ReqHost", match_name AS "Match Name", event_name AS "Event Name",
        cli_ip, device_id, country, state,
        ua_decoded_device_type AS "Device Type",
        nullif(trim(concat_ws(' ',nullif(ua_decoded_os_name,''),nullif(ua_decoded_os_version,''))),'') AS "OS Type",
        asn_decoded_as_name AS "ISP", count(*) FILTER(WHERE is_ts_request) AS raw_ts_requests
        FROM enriched GROUP BY ALL
        ) TO {sqlpath(summary)} (FORMAT PARQUET, COMPRESSION ZSTD)''')
    stats = c.execute('''SELECT count(*) requests, count(*) FILTER(WHERE is_ts_request) ts_requests,
        count(*) FILTER(WHERE is_playlist_request) playlist_requests,
        count(distinct cli_ip) distinct_client_ips, count(distinct device_id) distinct_devices,
        min(request_ist) first_request_ist, max(request_ist) last_request_ist FROM enriched''').fetchdf().to_dict('records')[0]
    original = c.execute('SELECT count(*) FROM requests').fetchone()[0]
    summary_check = c.execute('SELECT count(*),sum(raw_ts_requests) FROM read_parquet(?)',[str(summary)]).fetchone()
    assert stats['requests'] == original, 'Decode join changed request count'
    assert summary_check[1] == stats['ts_requests'], 'Summary TS counts do not reconcile'
    original_fields = [r[0] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?,hive_partitioning=false)',[files]).fetchall()]
    output_fields = [r[0] for r in c.execute('DESCRIBE enriched').fetchall()]
    assert set(original_fields).issubset(output_fields)
    report = dict(date=day, timezone='Asia/Kolkata', mappings=rows, input_files=files,
                  statistics=stats, summary_rows=summary_check[0], original_columns_preserved=original_fields,
                  enriched_columns=output_fields,
                  ua_status_counts=c.execute('SELECT ua_lookup_status,count(*) FROM enriched GROUP BY 1').fetchall(),
                  asn_status_counts=c.execute('SELECT asn_lookup_status,count(*) FROM enriched GROUP BY 1').fetchall(),
                  status_codes=c.execute('SELECT statusCode,count(*) FROM enriched GROUP BY 1 ORDER BY 2 DESC').fetchall(),
                  validation='PASS')
    (out / 'audit.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    (out / 'README.txt').write_text('''Sports export: all HTTP requests for the workbook date and exact mapped host(s).
sports_requests_enriched.parquet: one row per lake request, all original columns retained plus enrichment.
sports_audience_summary.parquet: the requested 12-column format. Rows group by all 11 descriptive dimensions.
raw_ts_requests counts .ts paths across ALL status codes, including retries/failures; no deduplication.
Zero-TS groups remain. No device/IP, UA, country or status filter was applied.
source_requests.parquet is the retained un-enriched extract. Lookup and mapping snapshots are retained.
Missing decoded values remain null/unknown; lookup status and provenance are in the detailed file.
Country/state/city are CDN log geography. ASN country describes the network, not viewer location.
ASN organization is an ISP/network label, and does not always identify a retail ISP.
UA bot labels are decoder signals, not proof of human or automated viewing.
No watch duration is inferred: requests alone do not prove watching or exact playback time.
An IP can occur in multiple summary rows; do not sum row-level IP counts for a unique audience.
All query-string fields remain in original queryStr even if not separately extracted.
Existing source files, workbooks and prior exports were not modified or removed.
''',encoding='utf-8')
    print(json.dumps(report,default=str),flush=True)
    print('EXPORT FOLDER: '+str(out),flush=True)
    c.close()


if __name__ == '__main__':
    main()
