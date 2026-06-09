import sqlite3
import os

DB_NAME = "users.db"

def run_migration():
    print(f"Connecting to database {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. Create class_test_configs table
    print("Creating class_test_configs table...")
    c.execute('''
        CREATE TABLE IF NOT EXISTS class_test_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            full_marks REAL NOT NULL,
            UNIQUE(test_name, class_name, subject_name)
        )
    ''')
    
    # 2. Add allow_marksheet and allow_admit columns to student_info
    print("Altering student_info table to add permissions columns...")
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN allow_marksheet INTEGER DEFAULT 0")
        print("Added column 'allow_marksheet'.")
    except sqlite3.OperationalError as e:
        print(f"Column 'allow_marksheet' might already exist: {e}")
        
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN allow_admit INTEGER DEFAULT 0")
        print("Added column 'allow_admit'.")
    except sqlite3.OperationalError as e:
        print(f"Column 'allow_admit' might already exist: {e}")
        
    conn.commit()
    conn.close()
    print("Migration finished successfully.")

if __name__ == '__main__':
    run_migration()
