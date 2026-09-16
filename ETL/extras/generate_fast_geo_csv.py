import pandas as pd
from datetime import timedelta

# Path to the geo daily parquet file
parquet_path = "D:/Veto Logs Backup/Vs - Code Work/ETL/output/watch_hours/daily_tables/geo_daily.parquet"
output_csv_path = "D:/Veto Logs Backup/Vs - Code Work/ETL/output/audience_ops/fast_geo_watch_hours_last_30_days.csv"

def generate_csv():
    print(f"Loading data from {parquet_path}...")
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"Error reading parquet file: {e}")
        return

    # Filter for 'fast' source
    if 'source' in df.columns:
        df_fast = df[df['source'] == 'fast'].copy()
    else:
        df_fast = df.copy()

    # The date column is 'log_date'
    if 'log_date' in df_fast.columns:
        df_fast['log_date'] = pd.to_datetime(df_fast['log_date'])
        
        # Find the max date and calculate the threshold for the last 30 days
        max_date = df_fast['log_date'].max()
        start_date = max_date - timedelta(days=30)
        print(f"Dataset max date is {max_date.date()}. Filtering for data >= {start_date.date()}")
        
        df_fast = df_fast[df_fast['log_date'] >= start_date]
    else:
        print("Error: 'log_date' column not found.")
        return

    # Group by state and city and sum raw watch hours
    agg_df = df_fast.groupby(['state', 'city'])['raw_watch_hours'].sum().reset_index()
    
    # Sort by raw_watch_hours descending
    agg_df = agg_df.sort_values(by='raw_watch_hours', ascending=False)
    
    # Save to CSV
    agg_df.to_csv(output_csv_path, index=False)
    print(f"Successfully wrote aggregated data to {output_csv_path}")
    print(agg_df.head(10))

if __name__ == "__main__":
    generate_csv()
