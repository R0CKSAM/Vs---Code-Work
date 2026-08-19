import duckdb
import pandas as pd
from pathlib import Path

# Paths
base_dir = Path(r"d:\Veto Logs Backup\Vs - Code Work\ETL")
parquet_file = base_dir / "output" / "watch_hours" / "concurrency" / "concurrency_minute.parquet"
out_dir = base_dir / "output"

# Ensure output directory exists
out_dir.mkdir(parents=True, exist_ok=True)

# Output files
out_csv_1 = out_dir / "stream_concurrency_combined_Jun17_Jul16.csv"
out_csv_2 = out_dir / "stream_concurrency_combined_Jul17_Aug16.csv"

def export_concurrency(start_date, end_date, out_file):
    print(f"Exporting stream concurrency for {start_date} to {end_date}...")
    query = f"""
        SELECT 
            minute_ist,
            SUM(unique_viewers) as total_unique_viewers,
            SUM(unique_ua_viewers) as total_unique_ua_viewers,
            SUM(segment_viewers_estimate) as total_segment_viewers_estimate,
            SUM(status_200_segment_viewers_estimate) as total_status_200_segment_viewers_estimate,
            SUM(raw_ts_rows) as total_raw_ts_rows,
            SUM(status_200_ts_rows) as total_status_200_ts_rows
        FROM read_parquet('{parquet_file}')
        WHERE source = 'stream'
          AND log_date >= '{start_date}'
          AND log_date <= '{end_date}'
        GROUP BY minute_ist
        ORDER BY minute_ist
    """
    
    con = duckdb.connect()
    df = con.execute(query).fetchdf()
    df.to_csv(out_file, index=False)
    print(f"Successfully exported {len(df)} rows to {out_file}")

if __name__ == "__main__":
    if not parquet_file.exists():
        print(f"Error: {parquet_file} does not exist.")
    else:
        # Date range 1: 17 Jun - 16 Jul
        export_concurrency('2026-06-17', '2026-07-16', out_csv_1)
        
        # Date range 2: 17 Jul - 16 Aug
        export_concurrency('2026-07-17', '2026-08-16', out_csv_2)
        
        print("Done!")
