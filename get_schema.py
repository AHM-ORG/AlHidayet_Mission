import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(db_path):
    db_path = os.path.join(BASE_DIR, 'users.db')

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("PRAGMA table_info(student_info);")
print(c.fetchall())
conn.close()
