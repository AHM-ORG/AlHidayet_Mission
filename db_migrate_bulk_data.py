import sqlite3

DB_NAME = "users.db"

def migrate_bulk_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    print("Starting bulk data migration...")

    # 1. Update student_info table
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN mothers_name TEXT")
        print("Column 'mothers_name' added to student_info.")
    except sqlite3.OperationalError as e:
        print(f"Notice: {e}")
        
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN date_of_admission TEXT")
        print("Column 'date_of_admission' added to student_info.")
    except sqlite3.OperationalError as e:
        print(f"Notice: {e}")

    # 2. Create teacher_info table
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            full_name TEXT NOT NULL,
            phone_number TEXT,
            qualification TEXT,
            joining_date TEXT,
            address TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    print("Table 'teacher_info' ensured.")

    # 3. Create class_routine table
    c.execute('''
        CREATE TABLE IF NOT EXISTS class_routine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch TEXT,
            class_name TEXT,
            day TEXT,
            start_time TEXT,
            end_time TEXT,
            subject TEXT,
            teacher_name TEXT
        )
    ''')
    print("Table 'class_routine' ensured.")

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate_bulk_data()
