import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove <int:> constraint to allow string UUIDs from Turso/SQLite
content = re.sub(r"@app\.route\('/admin/reset-student-fee/<int:student_id>'", 
                 r"@app.route('/admin/reset-student-fee/<student_id>'", content)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied fix for reset-student-fee route")
