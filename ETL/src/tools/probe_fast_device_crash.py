"""Read-only aggregate probes for the October 10 device-query crash."""
from argparse import Namespace
from pathlib import Path
import faulthandler
import duckdb
from build_concurrency import configure_lake_selection, parquet_source_sql, date_filter_sql
from build_fast_platform_channel_ua_device import ua_norm_sql

faulthandler.enable()
etl = Path(__file__).resolve().parents[2]
lake = etl / 'output/temp/asrun_priority_20261012_1700/combined_lake'
args = Namespace(lake=lake, archive_lake=[str(lake)], source='fast', start='2026-10-10', end='2026-10-10')
configure_lake_selection(args)
con = duckdb.connect()
con.execute('SET threads=1')
con.execute("SET memory_limit='2GB'")
con.execute("SET max_temp_directory_size='0B'")
source = parquet_source_sql(args.selected_lake_files)
where = "lower(COALESCE(reqPath, '')) LIKE '%.ts' AND TRY_CAST(reqTimeSec AS DOUBLE) IS NOT NULL"
for name, expression in [('scan', "count(*),sum(length(UA))"), ('normalize', f'count(*),sum(length({ua_norm_sql("UA")}))')]:
    print(f'START {name}', flush=True)
    print(name, con.execute(f'SELECT {expression} FROM read_parquet({source}, hive_partitioning=1, union_by_name=1) WHERE {where}').fetchone(), flush=True)
con.close()
