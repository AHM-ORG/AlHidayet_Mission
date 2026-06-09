import sqlite3
import json

def inspect():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    rows = c.execute('''
        SELECT term_name, subject_name, obtained_marks, full_marks, oral_marks, written_marks, ct_marks
        FROM marks
        WHERE student_id = 2
    ''').fetchall()
    
    print("=== MARKS FOR STUDENT ID 2 ===")
    for r in rows:
        print(dict(r))
        
    conn.close()

if __name__ == '__main__':
    inspect()
