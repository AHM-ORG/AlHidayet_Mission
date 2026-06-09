import sqlite3

def inspect():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in c.fetchall()]
    print("Tables:", tables)
    for table in tables:
        c.execute(f"PRAGMA table_info({table})")
        columns = c.fetchall()
        print(f"\nTable: {table}")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
    conn.close()

if __name__ == '__main__':
    inspect()
