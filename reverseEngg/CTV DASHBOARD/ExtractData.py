import re
import json
import pandas as pd

HTML_FILE = "CTV_FCT_Dashboard.html"
OUTPUT_FILE = "dashboard_data.xlsx"

# Read HTML
with open(HTML_FILE, "r", encoding="utf-8") as f:
    html = f.read()

# Find the dataset
pattern = r'window\.PRELOADED_DATASET\s*=\s*(\[.*?\])\s*;'
match = re.search(pattern, html, re.DOTALL)

if not match:
    raise Exception("window.PRELOADED_DATASET not found!")

# Parse JSON
dataset = json.loads(match.group(1))

# Create Excel
with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

    # If it's a list of objects
    if isinstance(dataset, list):

        # Flatten nested dictionaries if present
        df = pd.json_normalize(dataset)
        df.to_excel(writer, sheet_name="Dataset", index=False)

    # If it's a dictionary
    elif isinstance(dataset, dict):
        for key, value in dataset.items():

            if isinstance(value, list):
                if len(value) > 0 and isinstance(value[0], dict):
                    df = pd.json_normalize(value)
                else:
                    df = pd.DataFrame({"value": value})

                df.to_excel(
                    writer,
                    sheet_name=key[:31],
                    index=False
                )

            elif isinstance(value, dict):
                df = pd.json_normalize(value)
                df.to_excel(
                    writer,
                    sheet_name=key[:31],
                    index=False
                )

print(f"Done! Excel saved as '{OUTPUT_FILE}'")
print(f"Rows exported: {len(dataset)}")