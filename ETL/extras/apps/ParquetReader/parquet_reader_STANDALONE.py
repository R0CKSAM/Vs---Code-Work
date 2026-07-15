"""
STANDALONE PARQUET READER - 1GB+ Files
No Streamlit dependency - Works on Windows/Mac/Linux
"""

import polars as pl
import pyarrow.parquet as pq
from pathlib import Path
import time

def read_parquet_preview(filepath: str, rows: int = 10000, columns: list = None):
    """⚡ Fastest - preview first N rows"""
    print(f"\n📊 Loading {rows:,} rows from {Path(filepath).name}...")
    start = time.time()
    
    df = pl.scan_parquet(filepath)
    
    if columns:
        df = df.select(columns)
    
    df = df.limit(rows).collect()
    elapsed = time.time() - start
    
    print(f"✅ Loaded in {elapsed:.2f}s")
    print(f"📊 Rows: {len(df):,} | Columns: {len(df.columns)}")
    print(f"\n{df.to_pandas()}")
    
    return df

def read_parquet_filtered(filepath: str, column: str, value, columns: list = None):
    """🔍 Filter before loading (smart)"""
    print(f"\n📊 Loading filtered data from {Path(filepath).name}...")
    print(f"   Filter: {column} == {value}")
    
    start = time.time()
    
    df = pl.scan_parquet(filepath)
    
    if columns:
        df = df.select(columns)
    
    df = df.filter(pl.col(column) == value).collect()
    elapsed = time.time() - start
    
    print(f"✅ Loaded in {elapsed:.2f}s")
    print(f"📊 Rows: {len(df):,} (matching filter)")
    print(f"\n{df.to_pandas()}")
    
    return df

def read_parquet_stream(filepath: str, callback=None):
    """🌊 Stream processing - 100% memory safe"""
    print(f"\n📊 Streaming {Path(filepath).name}...")
    
    pf = pq.ParquetFile(filepath)
    total_rows = 0
    
    for i in range(pf.num_row_groups):
        table = pf.read_row_group(i)
        df = pl.from_arrow(table)
        total_rows += len(df)
        
        if callback:
            callback(df)
        
        print(f"  ✅ Chunk {i+1}/{pf.num_row_groups}: {len(df):,} rows")
    
    print(f"\n📊 Total rows processed: {total_rows:,}")

def get_file_info(filepath: str):
    """Show file metadata without loading data"""
    pf = pq.ParquetFile(filepath)
    schema = pf.schema
    file_size_mb = Path(filepath).stat().st_size / (1024 * 1024)
    
    print(f"\n{'='*60}")
    print(f"📁 FILE: {Path(filepath).name}")
    print(f"{'='*60}")
    print(f"Size:        {file_size_mb:.1f} MB")
    print(f"Rows:        {pf.metadata.num_rows:,}")
    print(f"Columns:     {len(schema.names)}")
    print(f"Row Groups:  {pf.num_row_groups}")
    print(f"\n📋 COLUMNS:")
    for col in schema.names:
        col_type = str(schema.field(col).type)
        print(f"   • {col:30s} : {col_type}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    import sys
    
    # Change this to your file path
    PARQUET_FILE = "part_stream_2026_07_09_0.parquet"  # Your 0.7GB file
    
    if len(sys.argv) > 1:
        PARQUET_FILE = sys.argv[1]
    
    if not Path(PARQUET_FILE).exists():
        print(f"❌ File not found: {PARQUET_FILE}")
        print("\nUsage: python parquet_reader.py <path_to_file.parquet>")
        sys.exit(1)
    
    # Show file info
    get_file_info(PARQUET_FILE)
    
    # EXAMPLE 1: Preview
    print("\n" + "="*60)
    print("EXAMPLE 1: Quick Preview (Fastest)")
    print("="*60)
    df = read_parquet_preview(PARQUET_FILE, rows=5000)
    
    # EXAMPLE 2: Filtered load
    print("\n" + "="*60)
    print("EXAMPLE 2: Filtered Load")
    print("="*60)
    # Change column name and value to match your data
    # df = read_parquet_filtered(PARQUET_FILE, column="status", value="active")
    print("(Uncomment line above and modify column/value to use)")
    
    # EXAMPLE 3: Stream processing
    print("\n" + "="*60)
    print("EXAMPLE 3: Stream Processing (No Memory Limit)")
    print("="*60)
    
    def process_batch(batch_df):
        """Example: count rows per batch"""
        print(f"    Processing batch of {len(batch_df)} rows...")
        # Add your processing logic here
        # Example: aggregate, filter, etc.
    
    read_parquet_stream(PARQUET_FILE, callback=process_batch)
    
    # EXAMPLE 4: Export filtered data
    print("\n" + "="*60)
    print("EXAMPLE 4: Export to CSV")
    print("="*60)
    
    df_export = read_parquet_preview(PARQUET_FILE, rows=10000)
    output_path = PARQUET_FILE.replace(".parquet", ".csv")
    df_export.to_pandas().to_csv(output_path, index=False)
    print(f"✅ Exported to {output_path}")
    
    print("\n" + "="*60)
    print("🎉 Done!")
    print("="*60)
