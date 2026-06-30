import re

with open('templates/admin/audit_report.html', 'r', encoding='utf-8') as f:
    content = f.read()

matches = re.findall(r'fetch\([^\)]+\)|\$\.ajax|\$\.post|\$\.get|XMLHttpRequest', content)
print("Ajax calls in audit_report.html:", set(matches))
