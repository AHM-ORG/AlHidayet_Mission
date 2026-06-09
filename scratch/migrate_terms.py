import sqlite3

def migrate():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # 1. Delete the older duplicates for student 2 (Arabic)
    print("Deleting older duplicate rows...")
    cursor.execute("DELETE FROM marks WHERE id IN (50, 60)")
    
    # 2. Update term_name to standardized values
    print("Updating 1st Term to 1st Unit...")
    cursor.execute("UPDATE marks SET term_name = '1st Unit' WHERE term_name = '1st Term'")
    
    print("Updating 2nd Term to 2nd Unit...")
    cursor.execute("UPDATE marks SET term_name = '2nd Unit' WHERE term_name = '2nd Term'")
    
    print("Updating Annual / Annual Exam to Final Exam...")
    cursor.execute("UPDATE marks SET term_name = 'Final Exam' WHERE term_name IN ('Annual', 'Annual Exam')")
    
    conn.commit()
    print("Migration completed successfully!")
    
    # Verify distinct terms remaining
    terms = cursor.execute("SELECT DISTINCT term_name FROM marks").fetchall()
    print("Remaining distinct terms in database:", terms)
    
    conn.close()

if __name__ == '__main__':
    migrate()
