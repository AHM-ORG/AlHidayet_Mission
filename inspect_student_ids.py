import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(db_path):
    db_path = os.path.join(BASE_DIR, 'users.db')

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
students = conn.execute("SELECT u.id, u.username, si.full_name, si.unique_code, si.class, si.roll_number FROM users u JOIN student_info si ON u.id = si.user_id").fetchall()
print(f"Total students found: {len(students)}")
for s in students[:10]:
    print(f"ID: {s['id']}, Username: {s['username']}, Name: {s['full_name']}, Class: {s['class']}, Roll: {s['roll_number']}, Unique Code: {s['unique_code']}")
conn.close()
