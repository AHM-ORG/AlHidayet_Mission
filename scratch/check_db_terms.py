import sqlite3

def check():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    print("Distinct term names in 'marks' table:")
    terms = conn.execute("SELECT DISTINCT term_name FROM marks").fetchall()
    for t in terms:
        print(f"  - {t['term_name']}")
        
    print("\nDistinct subject names in 'marks' table:")
    subjects = conn.execute("SELECT DISTINCT subject_name FROM marks").fetchall()
    for s in subjects:
        print(f"  - {s['subject_name']}")
        
    print("\nDistinct test names in 'class_test_configs' table:")
    tests = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
    for t in tests:
        print(f"  - {t['test_name']}")
        
    # Check if there are any records
    marks_count = conn.execute("SELECT count(*) as cnt FROM marks").fetchone()['cnt']
    print(f"\nTotal marks records: {marks_count}")
    
    conn.close()

if __name__ == '__main__':
    check()
