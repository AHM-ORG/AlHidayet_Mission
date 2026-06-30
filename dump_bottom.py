import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("".join(lines[-100:]))
