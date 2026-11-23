"""Append audited 12-column sports partitions; never replace completed partitions."""
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
ETL = ROOT.parent
sys.path.insert(0, str(ETL / 'src/tools'))
from export_vod_query_events import ua_norm_sql

STORE = ROOT / 'sports_store'
IST = ZoneInfo('Asia/Kolkata')


def sql(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    STORE.mkdir(exist_ok=True)
    lock = (STORE / 'writer.lock').open('a+b')
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    stamp = datetime.now(IST).strftime('%Y%m%d_%H%M%S')
    run = STORE / 'runs' / stamp
    run.mkdir(parents=True)
    shutil.copy2(ROOT / 'Reqhost Tagging.xlsx', run / 'mapping.xlsx')
    shutil.copy2(ETL / 'output/device_decode/ua_decode_lookup_both_all.parquet', run / 'ua.parquet')
    shutil.copy2(ETL / 'data/asn/ip2location_asn_cache.json', run / 'asn.json')
    mappings = []
    seen = {}
    for _, day, host, match, event in load_workbook(run / 'mapping.xlsx', data_only=True).active.iter_rows(min_row=2, values_only=True):
        if not day:
            continue
        entry = dict(date=day.date().isoformat(), host=host.strip().lower(), match=match, event=event)
        key = (entry['date'], entry['host'])
        if key in seen and seen[key] != entry:
            raise ValueError(f'Ambiguous mapping: {key}')
        if key not in seen:
            mappings.append(entry)
            seen[key] = entry
    state = dict(run=str(run), status='running', mapping_count=len(mappings), completed=[], skipped=[], issues=[])
    def status():
        state['updated_at_ist'] = datetime.now(IST).isoformat()
        # Status is operational metadata; data partitions and previous run receipts are immutable.
        (run / 'progress.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
        (STORE / 'latest_run.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    status()
    c = duckdb.connect(config={'threads': 2, 'memory_limit': '4GB', 'temp_directory': str(run / 'scratch')})
    c.read_parquet(str(run / 'ua.parquet')).create_view('ua_source')
    c.execute('''CREATE TEMP TABLE ua AS SELECT * EXCLUDE(rn) FROM
       (SELECT *,row_number() OVER(PARTITION BY ua_norm ORDER BY decoded_at_utc DESC NULLS LAST) rn FROM ua_source) WHERE rn=1''')
    cache = json.loads((run / 'asn.json').read_text(encoding='utf-8-sig'))
    c.register('asn_lookup', pd.DataFrame([{'asn_key': str(k), 'ISP': v.get('as_name'), 'asn_status': v.get('status')} for k,v in cache.items()]))
    for entry in sorted(mappings, key=lambda x: (x['date'], x['host'])):
        day, host = entry['date'], entry['host']
        key = hashlib.sha256((day+'|'+host).encode()).hexdigest()[:16]
        folder = STORE / 'data' / day
        target = folder / (key + '.parquet')
        receipt = STORE / 'receipts' / (key + '.json')
        state['current'] = entry
        status()
        if target.exists():
            if receipt.exists() and json.loads(receipt.read_text())['mapping'] == entry:
                state['skipped'].append(entry)
            else:
                state['issues'].append(dict(mapping=entry, reason='Existing partition requires review; not replaced'))
            status()
            continue
        partition = Path(r'Z:\Veto Logs Backup\DO NOT DELETE\source=stream') / ('year='+day[:4]) / ('month='+day[5:7]) / ('day='+day[8:])
        files = [str(p) for p in sorted(partition.glob('*.parquet'))]
        if not files:
            local = ETL / 'data/lake/source=stream' / ('year='+day[:4]) / ('month='+day[5:7]) / ('day='+day[8:])
            validation = ETL / 'output/validation/daily_delivery/daily_delivery_validation_latest.json'
            report = json.loads(validation.read_text(encoding='utf-8-sig')) if validation.exists() else {}
            validated = report.get('date') == day and any(
                r.get('source') == 'stream' and r.get('status') == 'PASS'
                and r.get('selected', {}).get('full_day') is True
                and Path(r['selected']['day_dir']).resolve() == local.resolve()
                for r in report.get('source_results', []))
            if validated:
                files = [str(p) for p in sorted(local.glob('*.parquet'))]
        if not files:
            state['issues'].append(dict(mapping=entry,reason='Lake partition missing'))
            status()
            continue
        print(f'{day} {host}: extracting all HTTP request groups', flush=True)
        try:
            raw_device = "NULLIF(regexp_extract(queryStr,'(?i)(?:^|[?&])device_id=([^&]*)',1),'')"
            device = f'coalesce(try(url_decode({raw_device})),{raw_device})'
            c.execute(f'''CREATE OR REPLACE TEMP TABLE grouped AS SELECT
                reqHost, nullif(trim(cliIP),'') cli_ip, {device} device_id,
                country,state,UA,asn,
                count(*) all_requests,
                count(*) FILTER(WHERE regexp_matches(lower(split_part(coalesce(reqPath,''),'?',1)), '\\.ts$')) raw_ts_requests,
                min(reqTimeSec::DOUBLE) first_epoch,max(reqTimeSec::DOUBLE) last_epoch
                FROM read_parquet(?,hive_partitioning=false)
                WHERE lower(trim(reqHost)) IN (SELECT unnest(?))
                  AND CAST(to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata' AS DATE)=CAST(? AS DATE)
                GROUP BY ALL''', [files, ([host, 'dreamboat-ch01vetointv.akamaized.net'] if host == 'vetointv.akamaized.net' else [host]), day])
            counts = c.execute('SELECT coalesce(sum(all_requests),0),coalesce(sum(raw_ts_requests),0),min(first_epoch),max(last_epoch) FROM grouped').fetchone()
            if not counts[0]:
                state['issues'].append(dict(mapping=entry,reason='No exact-host requests; host/feed mapping needs review'))
                status()
                continue
            c.execute(f'CREATE OR REPLACE TEMP TABLE ua_keys AS SELECT UA,{ua_norm_sql("UA")} ua_norm FROM (SELECT DISTINCT UA FROM grouped)')
            c.execute('''CREATE OR REPLACE TEMP TABLE enriched AS SELECT g.*,u.device_type,
                 nullif(trim(concat_ws(' ',nullif(u.os_name,''),nullif(u.os_version,''))),'') os_type,
                 a.ISP,coalesce(u.decode_status,'not_in_lookup') ua_status,
                 coalesce(a.asn_status,'not_in_lookup') asn_status
                 FROM grouped g LEFT JOIN ua_keys k ON g.UA IS NOT DISTINCT FROM k.UA
                 LEFT JOIN ua u ON k.ua_norm=u.ua_norm
                 LEFT JOIN asn_lookup a ON regexp_replace(upper(trim(g.asn)),'^AS','')=a.asn_key''')
            staged = run / (key + '.parquet')
            c.execute(f'''COPY (SELECT {sql(day)} ist_date, reqHost AS "ReqHost",
                {sql(entry['match'])} AS "Match Name", {sql(entry['event'])} AS "Event Name",
                cli_ip,device_id,country,state,device_type AS "Device Type",os_type AS "OS Type",ISP,
                sum(raw_ts_requests)::BIGINT raw_ts_requests FROM enriched GROUP BY ALL
                ) TO {sql(staged)} (FORMAT PARQUET,COMPRESSION ZSTD)''')
            result = c.execute('SELECT count(*),sum(raw_ts_requests) FROM read_parquet(?)',[str(staged)]).fetchone()
            joined = c.execute('SELECT sum(all_requests),sum(raw_ts_requests) FROM enriched').fetchone()
            assert tuple(joined) == tuple(counts[:2]) and result[1] == counts[1], 'Counts changed during decoding/aggregation'
            audit = dict(mapping=entry, accepted_hosts=([host, 'dreamboat-ch01vetointv.akamaized.net'] if host == 'vetointv.akamaized.net' else [host]), input_files=files, all_requests=counts[0],raw_ts_requests=counts[1],
                         first_epoch=counts[2],last_epoch=counts[3],rows=result[0],lookup_run=str(run),
                         ua_status_counts=c.execute('SELECT ua_status,sum(all_requests) FROM enriched GROUP BY 1').fetchall(),
                         asn_status_counts=c.execute('SELECT asn_status,sum(all_requests) FROM enriched GROUP BY 1').fetchall(),
                         source_coverage_note=('Known partial CDN source day; retained requests only' if day in ('2026-10-20','2026-10-21') else 'Export covers retained exact-host requests; not a guarantee of source completeness'),
                         validation='PASS')
            folder.mkdir(parents=True,exist_ok=True)
            receipt.parent.mkdir(exist_ok=True)
            # Exclusive creation protects old data. Keep staged copy as run evidence.
            with target.open('xb') as dest, staged.open('rb') as src:
                shutil.copyfileobj(src,dest)
            receipt.write_text(json.dumps(audit,indent=2),encoding='utf-8')
            state['completed'].append(dict(mapping=entry,rows=result[0],requests=counts[0],file=str(target)))
            print(f'{day} {host}: PASS {result[0]:,} summary rows; {counts[0]:,} requests',flush=True)
        except Exception as exc:
            state['issues'].append(dict(mapping=entry,reason=str(exc)))
            print(f'{day} {host}: ERROR {exc}',flush=True)
        status()
    paths = [str(p) for p in (STORE/'data').glob('*/*.parquet') if (STORE/'receipts'/(p.stem+'.json')).exists()]
    if paths:
        combined = run / 'sports_all_dates_12_columns.parquet'
        c.execute(f'COPY (SELECT * FROM read_parquet(?,hive_partitioning=false)) TO {sql(combined)} (FORMAT PARQUET,COMPRESSION ZSTD)',[paths])
        state['combined_file'] = str(combined)
    state['status'] = 'complete_with_issues' if state['issues'] else 'complete'
    state['current'] = None
    status()
    print(json.dumps(state),flush=True)
    c.close()
    lock.close()


if __name__ == '__main__':
    main()
