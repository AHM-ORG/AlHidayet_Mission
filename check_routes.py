import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find any routes related to billing or syncing
import re
routes = re.findall(r"@app\.route\('([^']+)'", content)
sync_routes = [r for r in routes if 'sync' in r or 'bill' in r or 'due' in r]
print("Billing/Sync routes found:", sync_routes)