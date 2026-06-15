import sqlite3

def inspect():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Check marks schema
    print("=== Table Schema (marks) ===")
    cursor = c.execute("PRAGMA table_info(marks)")
    for col in cursor.fetchall():
        print(dict(col))
        
    # Check some student records
    print("\n=== Sample Marks Records ===")
    rows = c.execute("SELECT * FROM marks LIMIT 10").fetchall()
    for r in rows:
        print(dict(r))
        
    conn.close()

if __name__ == '__main__':
    inspect()
