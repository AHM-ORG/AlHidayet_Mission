import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()
c.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables in users.db:")
for name, sql in tables:
    print(f"\nTable: {name}")
    print(sql)
conn.close()
