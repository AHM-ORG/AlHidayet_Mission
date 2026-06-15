import sqlite3

def main():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    tables_to_check = ['users', 'student_info', 'expenses', 'applications', 'notices', 'pending_media', 'teacher_info', 'class_routine', 'classes']
    
    print("=== BRANCH VALUES BY TABLE ===")
    for table in tables_to_check:
        try:
            c.execute(f"PRAGMA table_info({table})")
            cols = [col[1] for col in c.fetchall()]
            if 'branch' in cols:
                c.execute(f"SELECT DISTINCT branch, COUNT(*) FROM {table} GROUP BY branch")
                rows = c.fetchall()
                print(f"Table: {table}")
                for row in rows:
                    print(f"  Branch: {row[0]!r} (Count: {row[1]})")
            else:
                print(f"Table: {table} has no 'branch' column.")
        except Exception as e:
            print(f"Error checking table {table}: {e}")
            
    conn.close()

if __name__ == '__main__':
    main()
