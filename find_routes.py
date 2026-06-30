import json
import sys

try:
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    routes = []
    for i, line in enumerate(lines):
        if 'def ' in line:
            routes.append(f"{i+1}: {line.strip()}")
            
    with open('routes.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(routes))
        
except Exception as e:
    with open('routes.txt', 'w') as f:
        f.write(str(e))
