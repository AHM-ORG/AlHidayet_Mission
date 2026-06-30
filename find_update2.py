import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

funcs = re.findall(r"@app\.route\('([^']+)'", content)
print("Routes:", [f for f in funcs if 'update' in f or 'student' in f])

defs = re.findall(r"def (.*?)\(", content)
print("Defs:", [d for d in defs if 'update' in d or 'student' in d])
