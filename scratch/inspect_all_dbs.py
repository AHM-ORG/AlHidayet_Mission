import sqlite3
import os

dbs = ['users.db', 'school.db', 'ahm.db']

for db in dbs:
    if os.path.exists(db):
        print(f"=== {db} ===")
        conn = sqlite3.connect(db)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        print(f"Tables: {tables}")
        for t in tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {t}")
                count = c.fetchone()[0]
                print(f"  - {t}: {count} rows")
            except Exception as e:
                print(f"  - {t}: error ({e})")
        conn.close()
    else:
        print(f"=== {db} (not found) ===")
    print()
