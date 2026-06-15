import sqlite3
import random

def seed():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("=== Students ===")
    students = c.execute('''
        SELECT u.id, u.username, si.full_name, si.class, si.branch 
        FROM users u 
        JOIN student_info si ON u.id = si.user_id 
        WHERE u.role='student'
    ''').fetchall()
    
    if not students:
        print("No students found in student_info!")
        conn.close()
        return
        
    for s in students:
        print(f"Student: {s['full_name']} (@{s['username']}), Class: {s['class']}, Branch: {s['branch']}")
        
    # We will seed marks for all students to have rich test data
    for student in students:
        sid = student['id']
        cls = student['class']
        
        # Check subjects for this class
        subjects = c.execute("SELECT name FROM subjects WHERE class = ?", (cls,)).fetchall()
        if not subjects:
            # Seed some default subjects for this class
            print(f"No subjects for class {cls}. Seeding default subjects...")
            for sub in ["English", "Bengali", "Arabic", "Mathematics", "Science", "G.K.", "E.V.S", "Hindi", "Art", "Physical Education", "Work Education", "Hand Writing", "Behaviour", "Attendance"]:
                c.execute("INSERT OR IGNORE INTO subjects (name, class) VALUES (?, ?)", (sub, cls))
            conn.commit()
            subjects = c.execute("SELECT name FROM subjects WHERE class = ?", (cls,)).fetchall()
            
        subject_names = list(set(sub['name'].strip().title() for sub in subjects if sub['name']))
        
        # Clear existing marks for this student
        c.execute("DELETE FROM marks WHERE student_id = ?", (sid,))
        
        inserted = 0
        
        # We will seed:
        # 1. Monthly Class Tests (Jan, Feb, Mar) out of 20
        monthly_terms = ["Monthly Test Jan", "Monthly Test Feb", "Monthly Test Mar"]
        for term in monthly_terms:
            for sub_name in subject_names:
                # Additional subjects are only final exam metrics
                if sub_name in ["Physical Education", "Work Education", "Hand Writing", "Behaviour", "Attendance"]:
                    continue
                full_marks = 20.0
                obtained = round(random.uniform(12.0, 19.0), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, term, sub_name, obtained, full_marks))
                inserted += 1

        # 2. 1st Unit (out of 50: Oral 10, Written 40)
        # 3. 2nd Unit (out of 50: Oral 10, Written 40)
        for term in ["1st Unit", "2nd Unit"]:
            for sub_name in subject_names:
                if sub_name in ["Physical Education", "Work Education", "Hand Writing", "Behaviour", "Attendance"]:
                    continue
                
                if sub_name == "Art":
                    full_marks = 50.0
                    obtained = round(random.uniform(30.0, 48.0), 1)
                    c.execute('''
                        INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                        VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                    ''', (sid, cls, term, sub_name, obtained, full_marks))
                else:
                    full_marks = 50.0
                    oral = round(random.uniform(5.0, 9.5), 1)
                    written = round(random.uniform(20.0, 38.0), 1)
                    obtained = round(oral + written, 1)
                    c.execute('''
                        INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                        VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), ?, ?, 0.0)
                    ''', (sid, cls, term, sub_name, obtained, full_marks, oral, written))
                inserted += 1

        # 4. Final Exam
        for sub_name in subject_names:
            if sub_name == "Art":
                full_marks = 100.0
                obtained = round(random.uniform(60.0, 96.0), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            elif sub_name == "Physical Education":
                full_marks = 20.0
                obtained = round(random.uniform(12.0, 19.5), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            elif sub_name == "Work Education":
                full_marks = 30.0
                obtained = round(random.uniform(18.0, 28.5), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            elif sub_name == "Hand Writing":
                full_marks = 20.0
                obtained = round(random.uniform(12.0, 19.5), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            elif sub_name == "Behaviour":
                full_marks = 20.0
                obtained = round(random.uniform(12.0, 19.5), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            elif sub_name == "Attendance":
                full_marks = 10.0
                obtained = round(random.uniform(6.0, 9.8), 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), 0.0, 0.0, 0.0)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks))
            else:
                full_marks = 100.0
                oral = round(random.uniform(10.0, 19.5), 1)
                written = round(random.uniform(40.0, 68.0), 1)
                ct = round(random.uniform(5.0, 9.5), 1)
                obtained = round(oral + written + ct, 1)
                c.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by, uploaded_at, oral_marks, written_marks, ct_marks)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'), ?, ?, ?)
                ''', (sid, cls, "Final Exam", sub_name, obtained, full_marks, oral, written, ct))
            inserted += 1
            
        print(f"Successfully seeded {inserted} marks records for student '{student['full_name']}'!")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    seed()
