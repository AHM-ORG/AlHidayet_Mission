import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

queries = ['academics_setting', 'bulk_marks', 'marksheet', 'get_month_sort_key', 'sync_and_normalize']
for q in queries:
    print(f"=== Results for '{q}' ===")
    for idx, line in enumerate(lines):
        if q in line:
            print(f"Line {idx+1}: {line.strip()}")
