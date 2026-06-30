import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_NAME = os.path.join(INSTANCE_DIR, 'users.db')

def migrate_db():
    print(f"Connecting to {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    columns_to_add = [
        ('financial_aid_monthly', 'REAL DEFAULT 0.0'),
        ('financial_aid_readmission', 'REAL DEFAULT 0.0'),
        ('financial_aid_admission', 'REAL DEFAULT 0.0')
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE student_info ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col_name} already exists.")
            else:
                print(f"Error adding {col_name}: {e}")
                
    conn.commit()
    conn.close()
    print("Done.")

if __name__ == '__main__':
    migrate_db()
