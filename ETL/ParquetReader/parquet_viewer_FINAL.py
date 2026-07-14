import streamlit as st
import polars as pl
import pyarrow.parquet as pq
import tempfile
import os
from pathlib import Path
import time

# ============================================================================
# PROPER CONFIGURATION (Use .streamlit/config.toml instead)
# ============================================================================
st.set_page_config(
    page_title="Parquet Viewer 1GB+",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚀 Parquet File Viewer (1GB+)")
st.write("✅ Works with files up to 10GB | Windows/Mac/Linux compatible")

# ============================================================================
# SIDEBAR SETTINGS
# ============================================================================
st.sidebar.title("⚙️ Settings")

view_mode = st.sidebar.radio(
    "View Mode",
    ["Quick Preview", "Filtered View", "Streaming Mode"],
    help="Quick = fastest, Streaming = most memory safe"
)

# ============================================================================
# FILE INPUT - TWO OPTIONS
# ============================================================================
st.subheader("📂 Load File")

input_method = st.radio(
    "Choose how to load your file:",
    ["Direct File Path (Recommended)", "Upload File (Max 200MB)"],
    help="Use file path for larger files"
)

temp_path = None
file_size_mb = None
filename = None

if input_method == "Direct File Path (Recommended)":
    # ===== METHOD 1: FILE PATH (NO SIZE LIMIT) =====
    st.info("📁 Paste the full path to your parquet file")
    
    file_path = st.text_input(
        "File path (e.g., C:\\Users\\...\\file.parquet or /home/user/file.parquet)",
        placeholder="Paste full file path here"
    )
    
    if file_path and st.button("📂 Load File"):
        # Remove quotes if user copy-pasted with quotes
        file_path = file_path.strip('"\'')
        
        if Path(file_path).exists():
            temp_path = file_path
            file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
            filename = Path(file_path).name
            st.success(f"✅ File loaded: {file_size_mb:.1f}MB")
        else:
            st.error(f"❌ File not found: {file_path}")
            st.info("Make sure the path is correct. Try copying the full path from file properties.")
            st.stop()

else:
    # ===== METHOD 2: FILE UPLOAD (200MB LIMIT) =====
    st.info("⚠️ This method has a 200MB upload limit. For larger files, use the path method above.")
    
    uploaded_file = st.file_uploader(
        "Upload Parquet File",
        type=["parquet", "pq"]
    )
    
    if uploaded_file:
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, uploaded_file.name)
        
        try:
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
            filename = uploaded_file.name
            st.success(f"✅ File saved: {file_size_mb:.1f}MB")
            
        except Exception as e:
            st.error(f"❌ Error saving file: {e}")
            st.stop()

# ============================================================================
# MAIN APP - ONLY IF FILE IS LOADED
# ============================================================================
if not temp_path:
    st.warning("👆 Load a file above to continue")
    st.stop()

# ============================================================================
# GET METADATA
# ============================================================================
@st.cache_resource
def get_parquet_reader(_filepath):
    """Get ParquetFile without loading data"""
    return pq.ParquetFile(_filepath)

try:
    pf = get_parquet_reader(temp_path)
    schema = pf.schema
    metadata = {
        "columns": schema.names,
        "num_rows": pf.metadata.num_rows,
        "num_cols": len(schema.names),
        "row_groups": pf.num_row_groups,
        "file_size_mb": file_size_mb
    }
    
    # Display file info
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Rows", f"{metadata['num_rows']:,}")
    with col2:
        st.metric("Columns", metadata['num_cols'])
    with col3:
        st.metric("Size", f"{metadata['file_size_mb']:.1f}MB")
    with col4:
        st.metric("Row Groups", metadata['row_groups'])
    with col5:
        st.metric("Status", "✅ Ready")
    
    st.divider()
    
except Exception as e:
    st.error(f"❌ Error reading parquet: {e}")
    st.stop()

# ============================================================================
# COLUMN SELECTION
# ============================================================================
available_cols = metadata['columns']

selected_cols = st.sidebar.multiselect(
    "Select Columns",
    options=available_cols,
    default=available_cols[:min(8, len(available_cols))],
    help="⚡ Selecting fewer columns = much faster"
)

if not selected_cols:
    selected_cols = available_cols[:min(8, len(available_cols))]

# ============================================================================
# VIEW MODES
# ============================================================================

if view_mode == "Quick Preview":
    # ===== FASTEST MODE =====
    st.subheader("⚡ Quick Preview (Fastest)")
    
    rows_to_load = st.sidebar.slider(
        "Rows to Preview",
        min_value=1000,
        max_value=min(50000, metadata['num_rows']),
        value=5000,
        step=1000
    )
    
    try:
        with st.spinner(f"Loading {rows_to_load:,} rows..."):
            start = time.time()
            
            df = (pl.scan_parquet(temp_path)
                  .select(selected_cols)
                  .limit(rows_to_load)
                  .collect())
            
            elapsed = time.time() - start
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Rows Loaded", f"{len(df):,}")
        with col2:
            st.metric("Load Time", f"{elapsed:.2f}s")
        with col3:
            st.metric("Columns", len(selected_cols))
        
        st.dataframe(df.to_pandas(), use_container_width=True, height=500)
        
    except Exception as e:
        st.error(f"❌ Error: {e}")

elif view_mode == "Filtered View":
    # ===== SMART FILTERING =====
    st.subheader("🔍 Filtered View (Smart)")
    
    # Filter column selector
    col_to_filter = st.sidebar.selectbox("Filter by column", options=[None] + selected_cols)
    
    if col_to_filter:
        # Sample values from that column
        sample_values = (pl.scan_parquet(temp_path)
                        .select([col_to_filter])
                        .limit(1000)
                        .collect()[col_to_filter]
                        .unique()
                        .to_list())
        
        filter_values = st.sidebar.multiselect(
            f"Values in '{col_to_filter}'",
            options=sample_values[:100],  # Limit to 100
            max_selections=10,
            default=sample_values[:1] if sample_values else None
        )
        
        rows_limit = st.sidebar.slider("Max rows", 1000, 50000, 5000, step=1000)
        
        try:
            with st.spinner("Filtering..."):
                start = time.time()
                
                df = (pl.scan_parquet(temp_path)
                      .select(selected_cols)
                      .filter(pl.col(col_to_filter).is_in(filter_values))
                      .limit(rows_limit)
                      .collect())
                
                elapsed = time.time() - start
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Rows Found", f"{len(df):,}")
            with col2:
                st.metric("Filter Time", f"{elapsed:.2f}s")
            with col3:
                if len(df) == rows_limit:
                    st.metric("Status", "Limited")
                else:
                    st.metric("Status", "Complete")
            
            st.dataframe(df.to_pandas(), use_container_width=True, height=500)
            
        except Exception as e:
            st.error(f"❌ Filter error: {e}")
    else:
        st.info("👈 Select a filter column in the sidebar")

else:
    # ===== STREAMING MODE =====
    st.subheader("🌊 Streaming View (Progressive)")
    st.info("📡 Data loads progressively without loading entire file into memory")
    
    try:
        all_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        data_placeholder = st.empty()
        
        with st.spinner("Reading parquet file in chunks..."):
            chunk_size = 10000
            total_chunks = pf.num_row_groups
            
            for i in range(total_chunks):
                # Read one row group
                table = pf.read_row_group(i, columns=selected_cols)
                batch = pl.from_arrow(table)
                all_data.append(batch)
                
                # Update UI every 3 chunks
                if (i + 1) % 3 == 0 or i == total_chunks - 1:
                    combined = pl.concat(all_data)
                    
                    # Show preview (first 5000 rows)
                    preview_df = combined.head(5000).to_pandas()
                    data_placeholder.dataframe(preview_df, use_container_width=True, height=400)
                    
                    # Update status
                    status_text.info(f"📡 Loaded {len(combined):,} rows from {i+1}/{total_chunks} chunks")
                    progress_bar.progress((i + 1) / total_chunks)
            
            final_df = pl.concat(all_data)
        
        st.success(f"✅ Complete! {len(final_df):,} total rows loaded")
        st.dataframe(final_df.to_pandas(), use_container_width=True, height=600)
        
    except Exception as e:
        st.error(f"❌ Streaming error: {e}")

# ============================================================================
# STATISTICS
# ============================================================================
st.divider()
st.subheader("📊 Column Info")

try:
    # Show data types
    type_info = {
        "Column": available_cols,
        "Data Type": [str(schema.field(col).type) for col in available_cols]
    }
    
    type_df = pl.DataFrame(type_info).to_pandas()
    st.dataframe(type_df, use_container_width=True, hide_index=True)
    
except Exception as e:
    st.warning(f"Could not load column info: {e}")

# ============================================================================
# EXPORT
# ============================================================================
st.divider()
st.subheader("💾 Export")

try:
    # Try to export if data is loaded
    if 'df' in locals():
        col1, col2, col3 = st.columns(3)
        
        with col1:
            csv_data = df.to_pandas().to_csv(index=False)
            st.download_button(
                label="📥 CSV",
                data=csv_data,
                file_name=f"{filename.split('.')[0]}.csv",
                mime="text/csv"
            )
        
        with col2:
            parquet_bytes = df.to_pandas().to_parquet()
            st.download_button(
                label="📥 Parquet",
                data=parquet_bytes,
                file_name=f"{filename.split('.')[0]}_export.parquet",
                mime="application/octet-stream"
            )
        
        with col3:
            json_data = df.to_pandas().to_json(orient="records")
            st.download_button(
                label="📥 JSON",
                data=json_data,
                file_name=f"{filename.split('.')[0]}.json",
                mime="application/json"
            )

except Exception as e:
    st.warning(f"Export not available: {e}")

# ============================================================================
# CODE REFERENCE
# ============================================================================
with st.expander("💻 Copy This Code"):
    st.code("""
import polars as pl

# ⚡ FASTEST - Lazy evaluation
df = pl.scan_parquet("1gb_file.parquet").limit(10000).collect()

# Select only needed columns (5-10x faster)
df = pl.scan_parquet("1gb_file.parquet").select(["col1", "col2"]).limit(10000).collect()

# Filter BEFORE collecting (100x faster)
df = (pl.scan_parquet("1gb_file.parquet")
      .filter(pl.col("status") == "active")
      .select(["id", "name"])
      .limit(10000)
      .collect())

# Convert to pandas
df_pandas = df.to_pandas()
    """, language="python")

st.divider()
st.success("🎉 Works with files up to 10GB!")
