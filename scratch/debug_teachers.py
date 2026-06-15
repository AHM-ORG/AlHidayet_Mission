import sqlite3

def debug_teachers():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    
    print("--- ALL USERS with role = 'teacher' ---")
    users = conn.execute("SELECT id, username, role, branch FROM users WHERE role = 'teacher'").fetchall()
    for u in users:
        print(dict(u))
        
    print("\n--- ALL TEACHER_INFO records ---")
    info = conn.execute("SELECT user_id, full_name, phone_number FROM teacher_info").fetchall()
    for i in info:
        print(dict(i))
        
    print("\n--- JOINED QUERY ---")
    joined = conn.execute('''
        SELECT u.id, u.username, u.branch, ti.full_name
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.role = 'teacher'
    ''').fetchall()
    for j in joined:
        print(dict(j))
        
    conn.close()

if __name__ == '__main__':
    debug_teachers()
