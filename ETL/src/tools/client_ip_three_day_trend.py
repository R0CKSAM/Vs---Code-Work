"""Auditable request trends, not human watch-time, for a single client IP."""
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import argparse, csv, json, sys, ipaddress
import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src/profile'))
from src.common.lake_partitions import partition_for_date, resolve_lake_roots
from vglive_core import channel_candidate_sql, resolve_channel


def run(ip, end):
    ip = str(ipaddress.ip_address(ip))
    last = date.fromisoformat(end)
    days = [(last - timedelta(days=i)).isoformat() for i in [2, 1, 0]]
    out = ROOT / 'output/exports' / ('ip_trend_' + days[0].replace('-', '') + '_' + end.replace('-', ''))
    out.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(out / 'activity.duckdb'))
    db.execute('SET threads=2')
    db.execute("SET memory_limit='2GB'")
    db.execute('CREATE TABLE IF NOT EXISTS activity(day VARCHAR,source VARCHAR,ts TIMESTAMP,reqHost VARCHAR,candidate VARCHAR,UA VARCHAR,status INTEGER,bytes DOUBLE,extension VARCHAR)')
    db.execute('CREATE TABLE IF NOT EXISTS scanned(day VARCHAR,source VARCHAR,files VARCHAR,PRIMARY KEY(day,source))')
    roots = resolve_lake_roots(ROOT / 'data/lake', [Path('Z:/Veto Logs Backup/DO NOT DELETE')])
    # Bind a resumable cache to its identity, preventing accidental cross-IP reuse.
    meta = out / 'identity.json'
    identity = {'ip': ip, 'days': days}
    if meta.exists() and json.loads(meta.read_text()) != identity:
        raise ValueError('Output cache belongs to a different IP/date range')
    meta.write_text(json.dumps(identity), encoding='utf-8')
    for day in days:
        checkpoint = ROOT / 'output/state/daily_runs' / (day + '.json')
        if not checkpoint.exists() or json.loads(checkpoint.read_text(encoding='utf-8-sig')).get('status') != 'complete':
            raise RuntimeError('Day is not marked complete: ' + day)
        start = datetime.combine(date.fromisoformat(day), datetime.min.time(), timezone(timedelta(hours=5, minutes=30))).timestamp()
        for source in ['stream', 'fast']:
            if db.execute('SELECT count(*) FROM scanned WHERE day=? AND source=?', [day, source]).fetchone()[0]:
                print('Cached', day, source, flush=True)
                continue
            part = partition_for_date(roots, source, day)
            if not part:
                raise FileNotFoundError((day, source))
            files = [str(p) for p in part.files]
            print('Scanning', day, source, len(files), 'files', flush=True)
            db.execute('BEGIN')
            db.execute(f"""INSERT INTO activity SELECT ?,?,to_timestamp(try_cast(reqTimeSec AS DOUBLE)) AT TIME ZONE 'Asia/Kolkata',reqHost,
                {channel_candidate_sql()},UA,try_cast(statusCode AS INTEGER),try_cast(bytes AS DOUBLE),
                regexp_extract(lower(reqPath),'\\.([a-z0-9]+)(?:\\?|$)',1)
                FROM read_parquet(?,hive_partitioning=false,union_by_name=true)
                WHERE lower(trim(cliIP))=? AND try_cast(reqTimeSec AS DOUBLE)>=? AND try_cast(reqTimeSec AS DOUBLE)<?""",
                [day, source, files, ip, start, start + 86400])
            db.execute('INSERT INTO scanned VALUES (?,?,?)', [day, source, json.dumps(files)])
            db.execute('COMMIT')
            print('Completed', day, source, db.execute('SELECT count(*) FROM activity WHERE day=? AND source=?', [day, source]).fetchone()[0], flush=True)
    data = dict(identity)
    def extract(name, sql):
        cur = db.execute(sql)
        keys = [c[0] for c in cur.description]
        rows = [dict(zip(keys, row)) for row in cur.fetchall()]
        if rows and 'reqHost' in keys:
            for row in rows:
                mapped = resolve_channel(row['reqHost'], row['candidate'])
                row['feed'] = (mapped if mapped != 'Other' else row['reqHost']) + ' / ' + (row['candidate'] or '(none)')
        data[name] = rows
        with (out / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else keys)
            w.writeheader()
            for row in rows:
                w.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
        return rows
    extract('daily', "SELECT day,count(*) requests,count(*) FILTER(WHERE source='stream') stream_requests,count(*) FILTER(WHERE source='fast') fast_requests,count(distinct date_trunc('minute',ts)) active_minutes,count(distinct (reqHost,candidate)) feeds,count(distinct UA) uas,sum(bytes) bytes,count(*) FILTER(WHERE status BETWEEN 400 AND 599) errors FROM activity GROUP BY day ORDER BY day")
    extract('hourly', "SELECT day,extract('hour' FROM ts)::INT AS \"hour\",count(*) requests,count(*) FILTER(WHERE status BETWEEN 400 AND 599) errors FROM activity GROUP BY ALL ORDER BY day,\"hour\"")
    extract('feed_daily', 'SELECT day,source,reqHost,candidate,count(*) requests FROM activity GROUP BY ALL ORDER BY day,requests DESC')
    extract('feed_hourly', "SELECT day,source,reqHost,candidate,extract('hour' FROM ts)::INT AS \"hour\",count(*) requests FROM activity GROUP BY ALL ORDER BY day,\"hour\",requests DESC")
    extract('ua_daily', 'SELECT day,UA,count(*) requests FROM activity GROUP BY ALL ORDER BY day,requests DESC')
    extract('status_daily', 'SELECT day,status,count(*) requests FROM activity GROUP BY ALL ORDER BY day,requests DESC')
    extract('overlap_minutes', "SELECT day,date_trunc('minute',ts) minute_ist,count(distinct (reqHost,candidate)) active_feeds,count(distinct (reqHost,candidate)) FILTER(WHERE extension='ts' AND status BETWEEN 200 AND 299 AND bytes>0) successful_ts_feeds,count(*) requests FROM activity GROUP BY ALL ORDER BY day,minute_ist")
    extract('overlap_summary', 'SELECT day,min(active_feeds) min_feeds_per_minute,max(active_feeds) max_feeds_per_minute,avg(active_feeds) avg_feeds_per_active_minute,max(successful_ts_feeds) max_successful_ts_feeds_per_minute,count(*) FILTER(WHERE active_feeds>1) multi_feed_minutes FROM (SELECT day,date_trunc(\'minute\',ts) minute_ist,count(distinct (reqHost,candidate)) active_feeds,count(distinct (reqHost,candidate)) FILTER(WHERE extension=\'ts\' AND status BETWEEN 200 AND 299 AND bytes>0) successful_ts_feeds FROM activity GROUP BY ALL) GROUP BY day ORDER BY day')
    data['validation'] = {}
    for d in data['daily']:
        for key in ['hourly', 'feed_daily', 'feed_hourly', 'ua_daily', 'status_daily', 'overlap_minutes']:
            assert sum(r['requests'] for r in data[key] if r['day'] == d['day']) == d['requests'], (key, d['day'])
        old = ROOT / 'output/exports' / ('ip_detail_' + d['day'].replace('-', '')) / 'report.json'
        if old.exists():
            assert json.loads(old.read_text())['overview'][0]['requests'] == d['requests']
    assert db.execute('SELECT count(*) FROM scanned').fetchone()[0] == 6
    data['validation'] = {'breakdowns_reconcile': True, 'previous_reports_match': True, 'six_source_days_scanned': True}
    data['source_files'] = [dict(zip(['day', 'source', 'files'], row)) for row in db.execute('SELECT * FROM scanned ORDER BY day,source').fetchall()]
    (out / 'analysis.json').write_text(json.dumps(data, default=str, indent=2), encoding='utf-8')
    db.close()
    print('READY', str(out), json.dumps(data['daily']), json.dumps(data['overlap_summary']), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ip', required=True)
    p.add_argument('--end', required=True)
    a = p.parse_args()
    run(a.ip, a.end)
