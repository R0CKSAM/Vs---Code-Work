# CTV FCT Dashboard Project

This project builds and updates a CTV FCT dashboard from Excel data.

## What this project does
- Reads Excel files from the Data/Incoming folder
- Combines new data into a master workbook
- Archives processed files
- Generates or updates the dashboard output

## Project structure
- Data/Incoming: place new Excel files here
- Data/Archive: processed files are moved here after update
- Data/Master_Data.xlsx: the combined master file used by the dashboard
- update_master.py: Python script to merge new Excel files into the master workbook
- build_dashboard_html.py: script that generates the dashboard HTML from data sources
- build_excel_dashboard.ps1: PowerShell script for Excel-based dashboard generation
- CTV FCT Dashboard.html: generated dashboard output

## How to update with a new Excel file
1. Copy your new Excel file into Data/Incoming.
2. Open PowerShell in this project folder.
3. Run:

```powershell
Set-Location "D:\Vs - Code Work\Raj\P1 - CTV FCT ana"
.\.venv\Scripts\python.exe .\update_master.py
```

4. The script will:
   - read the new file
   - check the columns
   - append new rows to the master workbook
   - save the updated Master_Data.xlsx
   - move the processed file to Data/Archive

## Requirements
Install the required Python packages:

```powershell
.\.venv\Scripts\python.exe -m pip install pandas openpyxl
```

## How to open the dashboard
Open the generated HTML file:
- CTV FCT Dashboard.html

## Notes for new users
- Do not manually edit the master workbook unless you know what you are doing.
- Always place new source Excel files in Data/Incoming.
- If the dashboard does not refresh after updating data, regenerate the HTML output using the dashboard scripts.

## Common folder names
- Incoming: new data files go here
- Archive: old/processed files go here
- Master_Data.xlsx: main combined data source
