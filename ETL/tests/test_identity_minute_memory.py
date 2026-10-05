from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import duckdb


TOOLS = Path(__file__).resolve().parents[1] / 'src' / 'tools'


def test_identity_host_optimization_preserves_all_metrics(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    from build_identity_minute import build_identity_minute_table
    from build_concurrency import register_maps, q

    con = duckdb.connect()
    try:
        register_maps(con)
        con.execute('''CREATE TABLE raw(source VARCHAR,year INTEGER,month INTEGER,day INTEGER,
            reqTimeSec DOUBLE,reqHost VARCHAR,reqPath VARCHAR,cliIP VARCHAR,UA VARCHAR,
            statusCode VARCHAR,queryStr VARCHAR)''')
        epoch = datetime(2026,10,4,12,tzinfo=timezone.utc).timestamp()
        rows = [
            (epoch, 'indiatv-samsung-z', '/example/seg.ts', 'ip1', 'UA  one', '200', 'session_id=s1&device_id=d1'),
            (epoch+1, 'indiatv-samsung-a', '/example/seg.ts', 'ip1', 'UA one', '200.0', 'session_id=s1&device_id=d1'),
            (epoch+2, 'indiatv-samsung-a', '/example/seg.ts', 'ip2', None, '404', 'session_id=s%202&device_id=d2'),
            (epoch+3, 'indiatv-samsung-a', '/example/index.m3u8', 'ip3', 'UA three', '200', 'session_id=s3'),
            (epoch+4, None, '/example/seg.ts', None, None, None, None),
            (epoch+5, '', '/example/seg.ts', '', 'UA only', '200', ''),
            (epoch+60, 'indiatv-samsung-a', '/example/seg.ts', 'ip1', 'UA one', '200', 'session_id=s1'),
        ]
        con.executemany('INSERT INTO raw VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        [('fast',2026,10,4,*row) for row in rows])
        source = tmp_path / 'raw.parquet'
        con.execute(f"COPY raw TO '{q(source)}' (FORMAT PARQUET)")
        args = Namespace(start='2026-10-04',end='2026-10-04',source='fast',selected_lake_files=[source])
        build_identity_minute_table(con,args)
        actual = con.execute('SELECT * FROM identity_minute_new ORDER BY ALL').fetchall()
        class OrderedReference:
            def execute(self, sql):
                return con.execute(sql.replace('MIN(reqHost) AS reqHost',
                                               'any_value(reqHost ORDER BY reqHost) AS reqHost'))
        build_identity_minute_table(OrderedReference(),args)
        expected = con.execute('SELECT * FROM identity_minute_new ORDER BY ALL').fetchall()
        assert actual == expected
        assert sum(row[10] for row in actual) == 6
        assert any(row[8] == 'indiatv-samsung-a' for row in actual)
    finally:
        con.close()


def test_identity_aggregation_under_small_memory_limit(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    from build_identity_minute import build_identity_minute_table
    from build_concurrency import register_maps, q

    con = duckdb.connect(config={'memory_limit':'128MB','threads':2})
    try:
        register_maps(con)
        source = tmp_path / 'volume.parquet'
        epoch = datetime(2026,10,4,12,tzinfo=timezone.utc).timestamp()
        con.execute(f"""COPY (SELECT 'fast' AS source,2026 AS year,10 AS month,4 AS day,
            {epoch} + i%60 AS reqTimeSec,'indiatv-samsung-test' AS reqHost,
            '/example/segment.ts' AS reqPath,'ip-' || CAST(i%1000 AS VARCHAR) AS cliIP,
            repeat('test agent ',20) AS UA,'200' AS statusCode,
            'session_id=s1&device_id=d1' AS queryStr FROM range(1000000) t(i))
            TO '{q(source)}' (FORMAT PARQUET)""")
        args = Namespace(start='2026-10-04',end='2026-10-04',source='fast',selected_lake_files=[source])
        build_identity_minute_table(con,args)
        assert con.execute('''SELECT raw_ts_rows,status_200_ts_rows,distinct_cliips,
            distinct_ipua_pairs,distinct_devices,distinct_sessions FROM identity_minute_new''').fetchall() == [
                (1000000,1000000,1000,1000,1,1)]
    finally:
        con.close()


def test_fast_identity_pipeline_caps_parallel_aggregation():
    source = (TOOLS.parent / 'orchestrator' / 'run_pipeline.py').read_text(encoding='utf-8')
    command = source.split('identity_minute_fast_cmd = [',1)[1].split(']',1)[0]
    assert 'str(max(1, min(2, int(args.concurrency_threads))))' in command
    assert 'identity_minute_memory,' in command
    assert 'if (_parse_memory_limit_gb(identity_minute_memory) or 0) > 8:' in source
