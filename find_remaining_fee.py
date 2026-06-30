import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
for i, line in enumerate(lines):
    if 'remaining_fee' in line and 'request' in line:
        out.append(f"{i+1}: {line.strip()}")

with open('find_remaining_fee.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
