import re
f = open('ETL/output/overview/overview_dashboard.html', encoding='utf-8').read()
for line in f.splitlines():
    if 'true_data_range' in line or 'generated' in line or 'data_range' in line:
        print(line[:200])
