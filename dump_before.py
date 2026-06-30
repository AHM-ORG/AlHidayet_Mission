import re

with open('app.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'before_request' in line or 'context_processor' in line:
            print(f"{i+1}: {line.strip()}")
