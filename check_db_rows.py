import sqlite3
import os

def check_db_rows():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, 'instance', 'users.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(BASE_DIR, 'users.db')
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("=== TEACHERS ===")
    teachers = c.execute('SELECT id, username, email FROM users WHERE role="teacher"').fetchall()
    for t in teachers:
        print(dict(t))
        
    print("\n=== TEACHER INFO ===")
    t_info = c.execute('SELECT * FROM teacher_info').fetchall()
    for ti in t_info:
        print(dict(ti))
        
    print("\n=== SUBJECTS ===")
    subjects = c.execute('SELECT * FROM subjects').fetchall()
    for s in subjects:
        print(dict(s))
        
    print("\n=== TEACHER SUBJECTS ===")
    t_sub = c.execute('SELECT * FROM teacher_subjects').fetchall()
    for ts in t_sub:
        print(dict(ts))
        
    print("\n=== CLASS ROUTINE ===")
    routine = c.execute('SELECT * FROM class_routine').fetchall()
    for r in routine:
        print(dict(r))
        
    conn.close()

if __name__ == '__main__':
    check_db_rows()
