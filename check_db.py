import sqlite3
import os

def check_db():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(BASE_DIR, 'users.db')
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    print("Tables:", tables)
    for table in tables:
        table_name = table[0]
        print(f"\nSchema for {table_name}:")
        c.execute(f"PRAGMA table_info({table_name})")
        columns = c.fetchall()
        for col in columns:
            print(col)
    conn.close()

if __name__ == "__main__":
    check_db()
