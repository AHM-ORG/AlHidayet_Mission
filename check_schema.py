import sqlite3
import sys

def check_schema():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(student_info)")
    columns = [col[1] for col in cursor.fetchall()]
    print(columns)
    conn.close()

if __name__ == '__main__':
    check_schema()
