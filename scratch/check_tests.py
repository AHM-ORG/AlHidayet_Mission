import sqlite3

def check():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    
    print("--- DISTINCT TEST NAMES FROM class_test_configs ---")
    rows = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
    for r in rows:
        print(f"Configured: '{r['test_name']}'")
        
    print("\n--- DISTINCT TERM NAMES FROM marks ---")
    rows = conn.execute("SELECT DISTINCT term_name FROM marks").fetchall()
    for r in rows:
        print(f"Marks Term: '{r['term_name']}'")
        
    conn.close()

if __name__ == "__main__":
    check()
