import sqlite3
conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row
tables = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(f"Table: {t['name']}")
    print(t['sql'])
    print("-" * 50)
conn.close()
