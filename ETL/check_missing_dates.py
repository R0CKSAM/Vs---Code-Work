import pandas as pd
from pathlib import Path

base_dir = Path(r"d:\Veto Logs Backup\Vs - Code Work\ETL\output")
csv1 = base_dir / "stream_concurrency_combined_Jun17_Jul16.csv"
csv2 = base_dir / "stream_concurrency_combined_Jul17_Aug16.csv"

def check_missing_dates(csv_path, expected_start, expected_end):
    print(f"\n--- Checking {csv_path.name} ---")
    if not csv_path.exists():
        print("File does not exist.")
        return

    # Read the CSV
    df = pd.read_csv(csv_path)
    if df.empty:
        print("File is empty.")
        return
        
    # Ensure minute_ist is parsed as datetime
    df['minute_ist'] = pd.to_datetime(df['minute_ist'])
    
    # Extract just the date part
    df['date'] = df['minute_ist'].dt.date
    
    # Expected dates
    expected_dates = pd.date_range(start=expected_start, end=expected_end).date
    
    # Actual dates present
    actual_dates = df['date'].unique()
    
    # Find missing dates
    missing_dates = set(expected_dates) - set(actual_dates)
    
    if not missing_dates:
        print("✅ No missing dates! All days in the expected range are present.")
    else:
        print("❌ Missing Dates:")
        for md in sorted(missing_dates):
            print(f"  - {md}")
            
    print("\n--- Daily Minute Coverage ---")
    # Check for partially missing dates (a full day should have 1440 minutes)
    daily_counts = df.groupby('date').size()
    partial_days = []
    for d, count in daily_counts.items():
        if count < 1440:
            partial_days.append((d, count))
            
    if not partial_days:
        print("✅ All present dates have a full 1440 minutes of data.")
    else:
        print("⚠️  The following dates have fewer than 1440 minutes (partial data):")
        for d, count in partial_days:
            print(f"  - {d}: {count}/1440 minutes")

if __name__ == "__main__":
    check_missing_dates(csv1, "2026-06-17", "2026-07-16")
    check_missing_dates(csv2, "2026-07-17", "2026-08-16")
