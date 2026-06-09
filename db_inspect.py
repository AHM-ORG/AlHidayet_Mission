import sqlite3
import os

def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(BASE_DIR, 'users.db')
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    
    with open('db_info.txt', 'w', encoding='utf-8') as f:
        f.write(f"Tables count: {len(tables)}\n")
        for table in tables:
            table_name = table[0]
            f.write(f"\n=========================================\n")
            f.write(f"Table: {table_name}\n")
            f.write(f"=========================================\n")
            c.execute(f"PRAGMA table_info({table_name})")
            cols = c.fetchall()
            for col in cols:
                f.write(f"  Col: {col[1]} ({col[2]}) - Default: {col[4]}, Key: {col[5]}\n")
            
            # Print sample row if any
            try:
                c.execute(f"SELECT * FROM {table_name} LIMIT 2")
                rows = c.fetchall()
                f.write(f"  Sample rows ({len(rows)}):\n")
                for r in rows:
                    f.write(f"    {r}\n")
            except Exception as e:
                f.write(f"    Error reading rows: {e}\n")
    conn.close()
    print("Done inspecting database.")

if __name__ == '__main__':
    main()
