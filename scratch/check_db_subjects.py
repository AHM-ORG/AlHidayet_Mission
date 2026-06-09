import sqlite3

def check():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    rows = c.execute("SELECT name, class FROM subjects").fetchall()
    print("=== Subjects in DB ===")
    for r in rows:
        print(r)
        
    print("\n=== Classes in DB ===")
    classes = c.execute("SELECT name FROM classes").fetchall()
    for cl in classes:
        print(cl)
        
    conn.close()

if __name__ == '__main__':
    check()
