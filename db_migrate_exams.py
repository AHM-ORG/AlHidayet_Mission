import sqlite3
import os

DB_NAME = 'users.db'

def migrate_db():
    print(f"Connecting to {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        print("Creating exams table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                section TEXT,
                term_name TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                full_marks INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subject_id) REFERENCES subjects (id)
            )
        ''')

        # Check if marks table exists and rename it to marks_old
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='marks'")
        if cursor.fetchone():
            print("Renaming existing marks table to marks_old...")
            cursor.execute("DROP TABLE IF EXISTS marks_old")
            cursor.execute("ALTER TABLE marks RENAME TO marks_old")

        print("Creating new marks table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                exam_id INTEGER NOT NULL,
                obtained_marks REAL NOT NULL,
                uploaded_by INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users (id),
                FOREIGN KEY (exam_id) REFERENCES exams (id),
                FOREIGN KEY (uploaded_by) REFERENCES users (id),
                UNIQUE(student_id, exam_id)
            )
        ''')

        print("Creating teacher_assignments table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teacher_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES users (id),
                FOREIGN KEY (subject_id) REFERENCES subjects (id),
                UNIQUE(teacher_id, class_name, subject_id)
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
