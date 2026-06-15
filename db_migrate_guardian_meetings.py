import sqlite3

DB_NAME = "users.db"

def run_migration():
    print("Connecting to database...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    print("Creating 'guardian_meetings' table...")
    c.execute('''
        CREATE TABLE IF NOT EXISTS guardian_meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_name TEXT NOT NULL,
            meeting_date TEXT NOT NULL,
            meeting_month TEXT NOT NULL,
            branch TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    print("Creating 'meeting_attendance' table...")
    c.execute('''
        CREATE TABLE IF NOT EXISTS meeting_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            attendee_type TEXT NOT NULL,
            user_id INTEGER,
            other_name TEXT,
            other_designation TEXT,
            status TEXT NOT NULL,
            remarks TEXT,
            FOREIGN KEY (meeting_id) REFERENCES guardian_meetings (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(meeting_id, attendee_type, user_id)
        )
    ''')
    
    conn.commit()
    print("Migration completed successfully!")
    conn.close()

if __name__ == "__main__":
    run_migration()
