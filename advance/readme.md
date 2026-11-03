**I’ve rewritten your attached gzip-to-Parquet converter as a complete script with automatic CPU, RAM, drive, and free-space handling.** It uses **ZSTD level 1**, preserves columns that appear later, and resumes using saved batch records.

I also updated the cleaner so it can read the new output correctly and find files saved on another drive.

## Download the complete scripts

| File | Purpose |
|---|---|
| **[veto_fast_gz.py](https://chatgpt.com/library?file_id=libfile_552d8dc400ec8191b45e1ae0f48a6eb7&account_id=personal)** | Converts your `.gz` JSONL files into Parquet. This replaces the converter you attached. |
| **[veto_fast_clean.py](https://chatgpt.com/library?file_id=libfile_24d25b60dc008191a5fbfc2e6972919c&account_id=personal)** | Updated deduplication step. Reads the converter’s output, including columns introduced in later files. |

Both downloads contain the **whole script**, ready to run.

## 1. Install the dependencies

Open PowerShell or Command Prompt in the folder where you downloaded the scripts:

```powershell
python -m pip install --upgrade pyarrow orjson psutil tqdm duckdb
```

## 2. Run the converter

For a master folder containing day folders such as `01`, `02`, and `03`:

```powershell
python veto_fast_gz.py "D:\Veto Logs Backup\Veto Stream Logs\08" --mode master
```

For just one source folder:

```powershell
python veto_fast_gz.py "D:\Veto Logs Backup\Veto Stream Logs\08\01" --mode single
```

You can also start its interactive menu:

```powershell
python veto_fast_gz.py
```

**You do not need to enter thread counts, RAM limits, temporary-drive paths, or compression settings.** The script chooses its resource settings and prints the actual output location.

### If you want to choose columns to drop

Add `--select-columns`:

```powershell
python veto_fast_gz.py "D:\Veto Logs Backup\Veto Stream Logs\08" --mode master --select-columns
```

The menu displays a small sample of columns. **Only explicitly dropped columns are removed. Fields discovered later are kept automatically.**

## 3. Run the updated cleaner afterward

Once the converter reports that all selected folders completed:

```powershell
python veto_fast_clean.py "D:\Veto Logs Backup\Veto Stream Logs\08"
```

Give the cleaner the **original source master folder**. It reads the converter’s saved output locations, including locations on other drives.

The cleaner still performs full-row deduplication:

```sql
SELECT DISTINCT *
FROM read_parquet(..., union_by_name=true)
```

`union_by_name=true` combines columns by name and fills missing fields with `NULL`. This is necessary because the converter preserves newly encountered columns without performing another complete gzip scan first. [DuckDB](https://duckdb.org/docs/2.0/data/multiple_files/combining_schemas?utm_source=chatgpt.com)

## What I changed

### Faster processing with controlled resource use

Your attached worker hardcoded:

```python
compression_level=22
```

The replacement defaults to:

```python
compression_level=1
```

Zstandard’s higher compression settings trade compression speed for smaller files. Level 1 is a practical starting point for your combination of speed and limited disk space; the fastest total runtime still depends on the logs and storage hardware. [Fast real-time compression algorithm · GitHub](https://github.com/facebook/zstd?utm_source=chatgpt.com)

The replacement also:

- Chooses worker counts from available RAM, CPU cores, and detected source-drive type.
- Uses smaller, memory-bounded buffers instead of allocating 100,000 Python records per worker regardless of row size.
- Keeps only a bounded number of batches running.
- Stores the source inventory in SQLite instead of holding millions of paths and futures in Python memory.
- Streams decompression directly into conversion buffers, without extracting a second set of uncompressed JSON files.
- Caches Windows drive-type discovery for the current run.

### Automatic drive selection and space checks

The script detects writable local drives, available space, and SSD/HDD/NVMe information when Windows exposes it. It uses those details to choose an output location and saves that location for subsequent runs.

It reserves **2% of the output drive’s capacity, with a minimum of 1 GiB and a maximum of 8 GiB**, and checks free space during inventory creation and conversion.

Temporary output is written on the same volume as the final Parquet files, then renamed into place. Publishing a completed batch therefore does not require another full-size copy.

**The final dataset still needs enough disk space to exist.** These checks cannot predict its exact compressed size or impose a hard disk quota. If space becomes insufficient, the script stops and retains completed batches. It never deletes your raw gzip files to make room.

### Resume that survives added files and interruptions

The old converter rebuilt numbered batches from the latest sorted file list. Adding a file that sorted earlier could change which inputs belonged to an existing batch number.

The replacement saves each batch’s exact membership:

- An unchanged rerun skips completed conversion work.
- Newly added inputs receive new batches.
- Completed source files are checked for changes using size and modification time.
- Empty gzip files receive completion records too.
- Interrupted publication is recovered before new conversion begins.
- The updated cleaner rebuilds a cleaned day when the converter’s completed dataset changes.

Keep the generated state files and inventory database; they make reliable resume possible.

### No successful checkpoint for a partial or corrupted input

The old converter could skip malformed JSON or retain the readable beginning of a damaged gzip file, then publish the batch as successful.

The replacement fails the affected batch if it encounters malformed JSON, a non-object record, a gzip checksum error, or a write failure. It records the error in:

```text
conversion_errors.jsonl
```

After repairing an input in an unfinished batch, rerun the same command. Completed batches remain available.

It also preserves your existing value conversion: data columns remain strings, nested objects and lists become compact JSON strings, and `None`, `"-"`, and `"^"` retain the intended null handling.

## Existing output from the old converter

**Old Parquet files without the new batch inventory are not automatically accepted as verified checkpoints.** The old script’s existence-only check cannot establish whether those files contain all expected rows and columns.

The replacement may choose a separate folder such as `01_parquet_fast`, or a location on another drive. It prints the exact path and leaves previous files in place. The updated cleaner follows the new saved location.

## Verification

I tested the conversion and recovery logic with real PyArrow and DuckDB processing, including:

- Columns appearing after the first buffer was written.
- Multiple spawned worker processes.
- Unchanged reruns that preserve existing output files.
- Adding an earlier-named source without changing previous batches.
- Malformed JSON and corrupted gzip input.
- Repairing a failed input and resuming.
- Interruptions during output publication.
- Cleaner discovery on alternate output paths and rebuilding after new input.

The concurrent failure-and-resume test produced **all 8,000 expected rows exactly once**.

These tests ran on Linux using the same `spawn` multiprocessing method used on Windows. I have not benchmarked your machine or executed its native Windows drive-discovery calls, so the automatic resource choices are informed defaults rather than a guarantee of the fastest possible setting.

**Start with the master-folder command above and the supplied ZSTD level 1 default.**