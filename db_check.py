import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(db_path):
    db_path = os.path.join(BASE_DIR, 'users.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
tables = cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    if t[0] in ['subjects', 'teacher_subjects']:
        print(t[0], ':', t[1])
