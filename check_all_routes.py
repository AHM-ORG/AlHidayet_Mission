import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

routes = re.findall(r"@app\.route\('([^']+)'", content)
print("All routes:", routes)
