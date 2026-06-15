import sqlite3
try:
    conn = sqlite3.connect('d:/AHM/AHM-Web/users.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, username, email, phone, role FROM users WHERE role='admin'").fetchall()
    print("Found admin users:")
    for r in rows:
        print(dict(r))
except Exception as e:
    print("Error:", e)
