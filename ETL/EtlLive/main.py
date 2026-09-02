import os
import time
import duckdb
from dotenv import load_dotenv

# 1. Load credentials from .env
load_dotenv()

LINODE_ENDPOINT = os.getenv('LINODE_ENDPOINT', '').replace('https://', '').replace('http://', '').strip('/')
ACCESS_KEY = os.getenv('LINODE_ACCESS_KEY')
SECRET_KEY = os.getenv('LINODE_SECRET_KEY')
BUCKET_NAME = os.getenv('LINODE_BUCKET_NAME')

if not all([LINODE_ENDPOINT, ACCESS_KEY, SECRET_KEY, BUCKET_NAME]):
    raise ValueError("Missing required environment variables in .env file.")

TARGET_DATE = "2026-09-01"

# Target recursive files inside month 09 / day 01 subfolders
S3_FILE_PATTERN = f"s3://{BUCKET_NAME}/veto-fast-logs/09/01/**/*.gz"

def run_fast_distinct_count():
    start_time = time.time()
    
    con = duckdb.connect(database=':memory:')
    
    print("Initializing DuckDB parallel S3 reader...")
    
    # Configure S3 client settings for Linode Object Storage
    con.execute(f"""
        INSTALL httpfs;
        LOAD httpfs;
        SET s3_endpoint='{LINODE_ENDPOINT}';
        SET s3_access_key_id='{ACCESS_KEY}';
        SET s3_secret_access_key='{SECRET_KEY}';
        SET s3_url_style='path';
        SET s3_use_ssl=true;
        SET threads=16;
    """)
    
    print(f"Executing parallel query against: {S3_FILE_PATTERN} ...")
    
    query = f"""
        WITH parsed_logs AS (
            SELECT 
                cliIP,
                strftime(to_timestamp(CAST(reqTimeSec AS DOUBLE)), '%Y-%m-%d') as log_date
            FROM read_ndjson_auto(
                '{S3_FILE_PATTERN}',
                ignore_errors=true
            )
        )
        SELECT 
            COUNT(DISTINCT cliIP) AS distinct_client_ips,
            COUNT(*) AS total_log_lines
        FROM parsed_logs
        WHERE log_date = '{TARGET_DATE}';
    """
    
    try:
        res = con.execute(query).fetchone()
        elapsed = time.time() - start_time
        
        print("\n==================================================")
        print(f" Target Date         : {TARGET_DATE}")
        print(f" Distinct Client IPs : {res[0]:,}")
        print(f" Total Log Lines     : {res[1]:,}")
        print(f" Execution Time      : {elapsed:.2f} seconds")
        print("==================================================")
        
    except Exception as e:
        print(f"\nError reading from S3 pattern: {e}")

if __name__ == "__main__":
    run_fast_distinct_count()