import sqlite3

DB_NAME = "users.db"

def migrate_student_info():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    columns = [
        ("guardian_name", "TEXT"),
        ("dob", "TEXT"),
        ("section", "TEXT"),
        ("blood_group", "TEXT"),
        ("village", "TEXT"),
        ("post_office", "TEXT"),
        ("police_station", "TEXT"),
        ("district", "TEXT")
    ]
    
    for col_name, col_type in columns:
        try:
            c.execute(f"ALTER TABLE student_info ADD COLUMN {col_name} {col_type}")
            print(f"Column '{col_name}' added successfully.")
        except sqlite3.OperationalError:
            print(f"Column '{col_name}' already exists.")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate_student_info()
