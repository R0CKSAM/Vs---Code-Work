"""Report confirmed Fire TV Stick STREAM usage across all channels."""
import argparse
import csv
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from build_concurrency import DEFAULT_LAKE_FOLDER, configure_lake_selection, parquet_source_sql
from build_fast_platform_channel_ua_device import DEFAULT_LOOKUP, ensure_lookup_table, ua_norm_sql
from build_identity_minute import normalized_identity_sql


def write_daily_model_minutes(source: Path) -> Path:
    """Publish only the requested dimensions and metrics, without rounding hours."""
    destination = source.with_name(source.stem + '_minutes.csv')
    with source.open(newline='', encoding='utf-8-sig') as incoming:
        with destination.open('w', newline='', encoding='utf-8-sig') as outgoing:
            writer = csv.writer(outgoing)
            writer.writerow(['date_ist', 'firestick_model', 'raw_watch_minutes_estimated',
                             'distinct_cliip', 'distinct_device_id'])
            for row in csv.DictReader(incoming):
                writer.writerow([row['date_ist'], row['model'],
                                 str(Decimal(row['raw_watch_seconds']) / 60),
                                 row['distinct_cliip'], row['distinct_device_id']])
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.lake, args.source, args.archive_lake = DEFAULT_LAKE_FOLDER, 'stream', []
    configure_lake_selection(args)
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    dates = {(start + dt.timedelta(days=i)).isoformat() for i in range((end-start).days+1)}
    if dates != {p.date_text for p in args.selected_partitions}:
        raise SystemExit('Missing partitions; refusing to publish an incomplete report.')
    args.out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=2")
    con.execute("SET memory_limit='2GB'")
    con.execute("SET temp_directory=?", [str(args.out_dir / 'scratch')])
    ensure_lookup_table(con, DEFAULT_LOOKUP)
    con.execute("""CREATE TEMP TABLE sticks AS SELECT ua_norm, model FROM ua_lookup
        WHERE lower(coalesce(model,'')) LIKE '%fire tv stick%'""")
    con.execute('CREATE TEMP TABLE matched(day VARCHAR, model VARCHAR, ip VARCHAR, device VARCHAR, requests BIGINT, ok BIGINT)')
    audit = []
    for part in args.selected_partitions:
        source = parquet_source_sql(list(part.files))
        # Normalize once per distinct UA, not once per CDN request.
        con.execute(f"""CREATE OR REPLACE TEMP TABLE raw_ua AS
            SELECT DISTINCT UA FROM read_parquet({source}, hive_partitioning=true, union_by_name=true)
            WHERE lower(coalesce(reqPath,'')) LIKE '%.ts'""")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE matched_ua AS
            SELECT raw_ua.UA, sticks.model FROM raw_ua
            JOIN sticks ON {ua_norm_sql('raw_ua.UA')} = sticks.ua_norm""")
        device = normalized_identity_sql('device_id')
        con.execute(f"""INSERT INTO matched
            SELECT ?, m.model, NULLIF(trim(r.cliIP),''),
                CASE WHEN lower(coalesce({device},'')) IN ('','null','none','undefined','unknown','nan','0')
                     THEN NULL ELSE {device} END,
                count(*), count(*) FILTER(WHERE try_cast(statusCode AS INTEGER)=200)
            FROM read_parquet({source}, hive_partitioning=true, union_by_name=true) r
            JOIN matched_ua m ON r.UA=m.UA
            WHERE lower(coalesce(reqPath,'')) LIKE '%.ts'
            GROUP BY 1,2,3,4""", [part.date_text])
        row = con.execute('SELECT coalesce(sum(requests),0),count(distinct ip),count(distinct device) FROM matched WHERE day=?', [part.date_text]).fetchone()
        audit.append({'date':part.date_text,'files':[str(p) for p in part.files], 'segment_requests':row[0], 'distinct_cliip':row[1], 'distinct_device_id':row[2]})
        print(part.date_text, row, flush=True)
    measures = """coalesce(sum(requests),0) AS ts_requests,
        coalesce(sum(requests),0)*6 AS raw_watch_seconds,
        round(coalesce(sum(requests),0)/600.0,6) AS raw_watch_hours_estimated,
        round(coalesce(sum(ok),0)/600.0,6) AS status_200_watch_hours_estimated,
        count(distinct ip) AS distinct_cliip, count(distinct device) AS distinct_device_id,
        coalesce(sum(requests) FILTER(WHERE device IS NOT NULL),0) AS requests_with_device_id"""
    stem = f'stream_firestick_all_channels_{args.start}_to_{args.end}'
    queries = {
        'daily':f"SELECT d.day AS date_ist,{measures} FROM (SELECT unnest(?) AS day) d LEFT JOIN matched USING(day) GROUP BY d.day ORDER BY d.day",
        'total':f'SELECT {measures} FROM matched',
        'models':f'SELECT model,{measures} FROM matched GROUP BY model ORDER BY ts_requests DESC',
        'daily_models':f"""SELECT d.day AS date_ist, d.model, {measures}
            FROM (SELECT dates.day, models.model
                  FROM (SELECT unnest(?) AS day) dates
                  CROSS JOIN (SELECT DISTINCT model FROM matched) models) d
            LEFT JOIN matched USING(day,model)
            GROUP BY d.day,d.model ORDER BY d.day,ts_requests DESC,d.model""",
    }
    for kind, query in queries.items():
        result = con.execute(query, [sorted(dates)] if kind in {'daily','daily_models'} else [])
        with (args.out_dir / (stem+'_'+kind+'.csv')).open('w',newline='',encoding='utf-8-sig') as out:
            writer = csv.writer(out)
            writer.writerow([col[0] for col in result.description])
            writer.writerows(result.fetchall())
    write_daily_model_minutes(args.out_dir / (stem+'_daily_models.csv'))
    manifest = {'source':'stream','channels':'all combined','start_ist':args.start,'end_ist':args.end,
        'classification':'Decoded model explicitly contains Fire TV Stick; conflicting family-only labels, generic Fire TV and unresolved models excluded.',
        'watch_hours':'Estimated: all .ts requests * 6 / 3600; includes retries and errors. Not measured player watch time.',
        'identities':'Distinct cliIP and non-empty/non-placeholder queryStr device_id on matching .ts requests; totals deduplicated across all days/channels.',
        'lookup':str(DEFAULT_LOOKUP),'coverage':audit}
    (args.out_dir / (stem+'_manifest.json')).write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('TOTAL', con.execute(f'SELECT {measures} FROM matched').fetchone(), flush=True)


if __name__ == '__main__':
    main()
