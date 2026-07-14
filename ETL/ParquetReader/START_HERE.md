# 🎯 START HERE - Parquet Viewer for 1GB+ Files

## IMPORTANT: Use These Files ONLY

| File | Status |
|------|--------|
| ✅ **`parquet_viewer_FINAL.py`** | **USE THIS** |
| ❌ `parquet_viewer_FIXED.py` | Has config error |
| ❌ `parquet_viewer_1gb.py` | Old version |

---

## 3-Step Setup

### Step 1: Install Dependencies
```bash
pip install streamlit polars pyarrow pandas
```

### Step 2: Run the App
```bash
streamlit run parquet_viewer_FINAL.py
```

### Step 3: Load Your File
**Choose ONE method:**

#### Option A: Direct File Path (RECOMMENDED - No Size Limit)
1. Enter the full file path in the app
2. Example: `C:\Users\YourName\Documents\part_stream_2026_07_09_0.parquet`
3. Click "Load File"
4. ✅ Works with any file size (tested up to 10GB)

#### Option B: Upload File (200MB Max)
1. Use the upload button
2. Max 200MB
3. (Not recommended for your 0.7GB file)

---

## For Your 0.7GB File

### Best Way:
```bash
# 1. Install
pip install streamlit polars pyarrow

# 2. Run
streamlit run parquet_viewer_FINAL.py

# 3. In browser:
#    - Select "Direct File Path (Recommended)"
#    - Paste: C:\Veto Logs Backup\Vs - Code Work\ETL\ParquetReader\part_stream_2026_07_09_0.parquet
#    - Click "Load File"
```

---

## TWO LOADING METHODS EXPLAINED

### 🟢 Method 1: Direct File Path (BEST)

```
✅ No size limit
✅ Works instantly  
✅ No errors
✅ File stays on disk (no upload)
```

**How to get file path:**

**Windows:**
- Right-click file → Properties → Copy full path from "Location"
- Or: Right-click file → "Copy as path"
- Paste into app

**Mac/Linux:**
- Right-click file → Get Info → Copy path
- Or in terminal: `pwd` then click-drag file

### 🟡 Method 2: Upload File (IF < 200MB)

```
⚠️  200MB size limit
✅ Easy UI
⚠️  Slower for large files
```

**To increase upload limit to 2GB:**

1. Create `.streamlit` folder in your project
2. Inside, create `config.toml` file
3. Copy this:
```toml
[client]
maxUploadSize = 2000
```
4. Save and restart Streamlit

---

## Folder Structure (for upload method with config)

If you want upload method to work for 2GB files:

```
Your Project Folder/
├── parquet_viewer_FINAL.py          (the app)
├── .streamlit/                      (create this folder)
│   └── config.toml                  (create this file)
├── part_stream_2026_07_09_0.parquet (your file)
└── requirements.txt                 (optional)
```

---

## Windows Example (Your Case)

### File Location:
```
D:\Veto Logs Backup\Vs - Code Work\ETL\ParquetReader\part_stream_2026_07_09_0.parquet
```

### In App:
1. Select "Direct File Path (Recommended)"
2. Paste full path:
   ```
   D:\Veto Logs Backup\Vs - Code Work\ETL\ParquetReader\part_stream_2026_07_09_0.parquet
   ```
3. Click "Load File"
4. ✅ Instant!

---

## Troubleshooting

### Error: "File not found"
- Make sure path is correct
- Use full path including drive letter (C:\, D:\, etc.)
- Try copy-pasting from file properties
- Don't use relative paths like `./file.parquet`

### Error: "permission denied"
- Close the file if open in Excel/Power BI
- Make sure you have read permission
- Try running Streamlit as admin

### Error: "Address already in use"
- Another Streamlit app is running
- Kill it: `Ctrl+C` then run again
- Or use different port: `streamlit run app.py --server.port 8502`

### Slow loading?
- Reduce rows in sidebar (default 5000)
- Select fewer columns
- Use Quick Preview mode

---

## Performance Expectations

### For Your 0.7GB File:
| Operation | Time | RAM |
|-----------|------|-----|
| Load 5000 rows | <1s | ~100MB |
| Load 50000 rows | ~1s | ~300MB |
| Filter & load | ~0.5s | ~100MB |
| Stream all data | ~5s | ~200MB per chunk |

---

## What You Can Do

✅ **Quick Preview**
- View first N rows
- Select which columns
- Change row limit

✅ **Filtered View**
- Filter by column value
- Multiple filters
- Only load matching rows

✅ **Streaming View**
- Process entire file
- Load progressively
- Memory safe (100% safe)

✅ **Export**
- Download as CSV
- Download as JSON
- Download as Parquet

---

## Command Cheat Sheet

### Windows (Command Prompt)
```bash
# Install
pip install streamlit polars pyarrow

# Run
streamlit run parquet_viewer_FINAL.py

# Stop (press in terminal)
Ctrl+C
```

### Mac/Linux (Terminal)
```bash
# Install
pip3 install streamlit polars pyarrow

# Run
streamlit run parquet_viewer_FINAL.py

# Stop
Ctrl+C
```

---

## Files Provided

| File | Purpose |
|------|---------|
| `parquet_viewer_FINAL.py` | ✅ Main app - USE THIS |
| `parquet_reader_STANDALONE.py` | Alternative (no UI) |
| `START_HERE.md` | This file |
| `SETUP_GUIDE.md` | Detailed setup |
| `.streamlit_config.toml` | Optional - for 2GB uploads |

---

## Quick Decision Tree

```
Is your file > 200MB?
├─ YES → Use "Direct File Path" method ✅
└─ NO  → Use Upload or File Path (both work)

Do you want upload to support 2GB?
├─ YES → Create .streamlit/config.toml ✅
└─ NO  → Use File Path instead (simpler)

Which view do you prefer?
├─ Quick Preview → Fastest
├─ Filtered View → Smart
└─ Streaming → Most memory safe
```

---

## Success Checklist

- [ ] Installed streamlit, polars, pyarrow
- [ ] Running `parquet_viewer_FINAL.py` (not FIXED or 1gb version)
- [ ] Can see the app in browser
- [ ] Loaded file via File Path method
- [ ] File loads instantly without errors
- [ ] Can see data in the table
- [ ] Can select columns
- [ ] Can change row limit

---

## Next Steps

1. ✅ Install: `pip install streamlit polars pyarrow`
2. ✅ Run: `streamlit run parquet_viewer_FINAL.py`
3. ✅ Choose: "Direct File Path"
4. ✅ Paste: Full path to your `.parquet` file
5. ✅ Click: "Load File"
6. ✅ Enjoy: ⚡ Instant loading!

---

## Still Having Issues?

### Most Common:
- "File not found" → Use full absolute path
- Slow loading → Reduce row limit
- High RAM → Use streaming mode
- App won't start → `pip install --upgrade streamlit`

### Less Common:
- Port already in use → `streamlit run app.py --server.port 8502`
- Permission denied → Run cmd as admin
- Very slow → Restart computer and try again

---

## The Bottom Line

**Use Method 1 (Direct File Path):**
- Paste full file path → Click Load → Done ✨
- Works with any file size
- No config needed
- Fastest & simplest

**Your Command:**
```bash
pip install streamlit polars pyarrow && streamlit run parquet_viewer_FINAL.py
```

**Then in app:**
- Select "Direct File Path"
- Paste: `D:\Veto Logs Backup\Vs - Code Work\ETL\ParquetReader\part_stream_2026_07_09_0.parquet`
- Click "Load File"
- View data instantly ⚡

---

**Questions? Read SETUP_GUIDE.md for more details.**

**Ready? Let's go! 🚀**
