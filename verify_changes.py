import sqlite3
import json
import os

def verify():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(BASE_DIR, 'users.db')
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Check if table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='applications'")
    if c.fetchone():
        print("[OK] Applications table exists.")
    else:
        print("[FAIL] Applications table missing.")
        return

    # Simulate a form submission
    test_data = {"full_name": "Test Student", "branch": "bhogram", "class_applied": "X"}
    c.execute("INSERT INTO applications (type, data) VALUES (?, ?)", ("Admission Form", json.dumps(test_data)))
    conn.commit()
    print("[OK] Test application inserted.")

    # Check if we can read it back
    c.execute("SELECT * FROM applications ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row and json.loads(row[3])['full_name'] == "Test Student":
        print("[OK] Read back application data successfully.")
    else:
        print("[FAIL] Failed to read back application data.")

    conn.close()

if __name__ == "__main__":
    verify()
