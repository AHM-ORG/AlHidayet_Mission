import sqlite3

DB_NAME = "users.db"

def migrate():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    print("Migrating Database for Financial Management...")
    
    # 1. Add monthly_fee to student_info
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN monthly_fee REAL DEFAULT 0")
        print(" - Added monthly_fee to student_info")
    except sqlite3.OperationalError:
        print(" - monthly_fee column already exists")

    # 2. Create teacher_info table
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_info (
            user_id INTEGER PRIMARY KEY,
            salary REAL DEFAULT 0,
            qualification TEXT,
            joining_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    print(" - Ensured teacher_info table exists")
    
    conn.commit()
    conn.close()
    print("Migration Complete!")

if __name__ == '__main__':
    migrate()
