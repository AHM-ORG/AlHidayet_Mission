import sqlite3
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(db_path):
    db_path = os.path.join(BASE_DIR, 'users.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

schema = {}
for name, sql in tables:
    schema[name] = sql

print(json.dumps(schema, indent=2))
conn.close()
