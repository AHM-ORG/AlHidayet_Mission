import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

funcs = re.findall(r"def (.*?)\(", content)
print("Functions around 14500:", [f for f in funcs if 'bill' in f.lower() or 'month' in f.lower()])
