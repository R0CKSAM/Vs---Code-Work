import json
import duckdb
from pathlib import Path

base_folder = Path(r"d:\Veto Logs Backup\Vs - Code Work\ETL\data")
state_file = base_folder / ".etl_02_state.json"

print("--- 1. FAILURE HISTORY ---")
try:
    with open(state_file, "r") as f:
        state = json.load(f)
    errors = []
    elapsed_times = []
    for key, val in state.items():
        if isinstance(val, dict):
            if val.get("status") == "error":
                errors.append(val)
            if "elapsed_sec" in val and val.get("status") == "ok":
                elapsed_times.append(val["elapsed_sec"])
    
    if not errors:
        print("No errors recorded in the state file.")
    else:
        for err in errors:
            err_str = err.get("error", "")
            is_mem = "memory" in err_str.lower() or "allocation" in err_str.lower()
            print(f"Source ID: {err.get('source_id')}")
            print(f"Input Rows: {err.get('input_rows')}")
            print(f"Elapsed Sec: {err.get('elapsed_sec')}")
            print(f"Updated At: {err.get('updated_at_utc')}")
            print(f"Memory/Allocation Flag: {is_mem}")
            print(f"Error: {err_str}")
            print("-" * 20)

    print("\n--- 5. TYPICAL RUNTIME ---")
    if elapsed_times:
        print(f"Typical (Median) elapsed_sec: {sorted(elapsed_times)[len(elapsed_times)//2]}")
        print(f"Max elapsed_sec: {max(elapsed_times)}")
    else:
        print("No successful runs to calculate typical runtime.")

except Exception as e:
    print(f"Failed to read state file: {e}")

print("\n--- 2. DATA SHAPE PER SOURCE ---")
try:
    con = duckdb.connect()
    parquet_folders = [p for p in base_folder.iterdir() if p.is_dir() and p.name.endswith("_parquet")]
    for pf in parquet_folders:
        print(f"\nFolder: {pf.name}")
        size = sum(f.stat().st_size for f in pf.glob('**/*') if f.is_file())
        print(f"Total Size: {size / (1024*1024):.2f} MB")
        
        try:
            # Row count
            row_count_res = con.execute(f"SELECT COUNT(*) FROM read_parquet('{pf.as_posix()}/*.parquet')").fetchone()
            print(f"Row count: {row_count_res[0]}")
            
            # Columns
            cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{pf.as_posix()}/*.parquet')").fetchall()
            for c in cols:
                c_name = c[0]
                c_type = c[1]
                flag = ""
                if any(t in c_type.upper() for t in ['VARCHAR', 'TEXT', 'JSON', 'BLOB']):
                    # Estimate max length
                    try:
                        max_len = con.execute(f"SELECT MAX(LENGTH({c_name}::VARCHAR)) FROM read_parquet('{pf.as_posix()}/*.parquet')").fetchone()[0]
                        flag = f" [FLAG: VARCHAR/TEXT, max len: {max_len}]"
                    except:
                        flag = " [FLAG: VARCHAR/TEXT, max len unknown]"
                print(f"  - {c_name}: {c_type}{flag}")
        except Exception as e:
            print(f"Could not read parquet info: {e}")
            
except Exception as e:
    print(f"Failed to process parquet folders: {e}")

