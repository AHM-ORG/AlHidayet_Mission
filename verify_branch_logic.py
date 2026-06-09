import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(DB_NAME):
    DB_NAME = os.path.join(BASE_DIR, 'users.db')

def verify():
    print("=== STARTING AHM BRANCH SCORING INTEGRITY VERIFICATION ===")
    
    if not os.path.exists(DB_NAME):
        print(f"Error: Database {DB_NAME} not found.")
        return
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check altered tables for branch column
    tables_to_check = ['users', 'student_info', 'expenses', 'notices', 'applications']
    all_ok = True
    
    for table in tables_to_check:
        try:
            c.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in c.fetchall()]
            if 'branch' in columns:
                print(f"[OK] Table '{table}' has the 'branch' column. Columns: {columns}")
            else:
                print(f"[FAIL] Table '{table}' is MISSING the 'branch' column! Columns: {columns}")
                all_ok = False
        except Exception as e:
            print(f"[ERROR] Failed to read schema of table '{table}': {str(e)}")
            all_ok = False
            
    print("\n--- Current Administrators in Database ---")
    try:
        c.execute("SELECT id, username, role, branch FROM users WHERE role = 'admin'")
        admins = c.fetchall()
        for admin in admins:
            print(f"Admin ID: {admin[0]}, Username: {admin[1]}, Role: {admin[2]}, Branch: {admin[3]}")
    except Exception as e:
        print(f"[ERROR] Failed to query users: {str(e)}")
        all_ok = False
        
    conn.close()
    
    if all_ok:
        print("\n=== VERIFICATION SUCCESSFUL: ALL DATABASE SCHEMAS MATCH ===\n")
    else:
        print("\n=== VERIFICATION FAILED: PLEASE CORRECT SCHEMAS ===\n")

if __name__ == "__main__":
    verify()
