import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, 'instance', 'users.db')
if not os.path.exists(DB_NAME):
    DB_NAME = os.path.join(BASE_DIR, 'users.db')

def update_admin_email():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Update email for username 'headmaster'
    c.execute("UPDATE users SET email = ? WHERE username = ?", ('rmdaswif@gmail.com', 'headmaster'))
    conn.commit()
    
    # Verify update
    c.execute("SELECT username, email FROM users WHERE username = 'headmaster'")
    user = c.fetchone()
    print(f"Updated User: {user[0]}, New Email: {user[1]}")
    
    conn.close()

if __name__ == "__main__":
    update_admin_email()
