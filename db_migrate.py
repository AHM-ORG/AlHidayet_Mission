import sqlite3

DB_NAME = "users.db"

def add_email_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        print("Column 'email' added successfully.")
    except sqlite3.OperationalError as e:
        print(f"Error (might already exist): {e}")
    
    # Set default email for existing users
    c.execute("UPDATE users SET email = 'admin@ahm.com' WHERE username = 'headmaster'")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_email_column()
