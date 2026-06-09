import sqlite3
import os

DB_NAME = 'users.db'

def migrate_db():
    print(f"Connecting to {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        print("Dropping recent exams and marks tables...")
        cursor.execute("DROP TABLE IF EXISTS marks")
        cursor.execute("DROP TABLE IF EXISTS exams")

        print("Creating new multi-subject marks table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                term_name TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                obtained_marks REAL NOT NULL,
                full_marks REAL NOT NULL,
                uploaded_by INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users (id),
                FOREIGN KEY (uploaded_by) REFERENCES users (id),
                UNIQUE(student_id, term_name, subject_name)
            )
        ''')

        conn.commit()
        print("Migration completed successfully.")
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_db()
