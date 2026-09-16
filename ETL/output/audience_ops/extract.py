import re

html_path = 'D:/Veto Logs Backup/Vs - Code Work/ETL/output/audience_ops/veto_audience_operations.html'

with open(html_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'fast' in line.lower() or 'state' in line.lower() or 'citi' in line.lower() or 'city' in line.lower():
            print(f"Match found at line {i+1}: {line[:200]}")
            break
