import sqlite3
conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row

date_filter = "2026-06-02"
branch_filter = "bhogram"
class_filter = "One"

print("=== RUNNING TEACHER QUERY ===")
teachers = conn.execute('''
    SELECT u.id, u.username, ti.full_name, 'Teacher' as class, '' as roll_number, att.status, att.remarks
    FROM users u
    LEFT JOIN teacher_info ti ON u.id = ti.user_id
    LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ?
    WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
    ORDER BY COALESCE(ti.full_name, u.username)
''', (date_filter, branch_filter)).fetchall()
print(f"Teachers found: {len(teachers)}")
for t in teachers:
    print(dict(t))

print("\n=== RUNNING STUDENT QUERY FOR CLASS 'One' ===")
students = conn.execute('''
    SELECT u.id, u.username, si.full_name, si.class, si.roll_number, att.status, att.remarks
    FROM users u
    JOIN student_info si ON u.id = si.user_id
    LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ?
    WHERE u.role = 'student' AND si.branch = ? AND si.class = ?
    ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
''', (date_filter, branch_filter, class_filter)).fetchall()
print(f"Students found: {len(students)}")
for s in students[:5]:
    print(dict(s))

conn.close()
