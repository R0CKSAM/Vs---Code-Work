import duckdb
from pathlib import Path

parquet_file = Path(r"d:\Veto Logs Backup\Vs - Code Work\ETL\output\watch_hours\concurrency\concurrency_minute.parquet")

def get_watch_hours():
    query = """
        SELECT 
            SUM(segment_viewers_estimate) / 60 AS raw_watch_hours,
            SUM(status_200_segment_viewers_estimate) / 60 AS status_200_watch_hours
        FROM read_parquet('{}')
        WHERE source = 'stream'
          AND log_date >= '2026-07-17'
          AND log_date <= '2026-08-16'
    """.format(parquet_file)
    
    con = duckdb.connect()
    result = con.execute(query).fetchone()
    
    raw_wh = result[0] or 0
    status_200_wh = result[1] or 0
    
    print("--- Watch Hours for STREAM (17 Jun 2026 to 16 Jul 2026) ---")
    print(f"Total Raw Watch Hours: {raw_wh:,.2f}")
    print(f"Total Status-200 Watch Hours: {status_200_wh:,.2f}")

if __name__ == "__main__":
    if parquet_file.exists():
        get_watch_hours()
    else:
        print(f"Error: {parquet_file} does not exist.")
