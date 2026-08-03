import pandas as pd
import json
import re

HTML_FILE = "CTV_FCT_Dashboard.html"
EXCEL_FILE = "dashboard_data.xlsx"
OUTPUT_HTML = "CTV_FCT_Dashboard_updated.html"

# Read Excel
df = pd.read_excel(EXCEL_FILE)

# Convert to JSON
dataset = df.fillna("").to_dict(orient="records")
json_text = json.dumps(dataset, ensure_ascii=False)

# Read HTML
with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

# Replace PRELOADED_DATASET
pattern = r'window\.PRELOADED_DATASET\s*=\s*\[.*?\]\s*;'

replacement = f'window.PRELOADED_DATASET = {json_text};'

new_html = re.sub(pattern, replacement, html, flags=re.DOTALL)

# Save new HTML
with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(new_html)

print("Dashboard updated successfully!")