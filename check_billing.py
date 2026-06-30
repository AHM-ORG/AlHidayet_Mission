import ast

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find any references to month_end_billing_count
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'month_end_billing_count' in line:
        print(f"Line {i+1}: {line.strip()}")
