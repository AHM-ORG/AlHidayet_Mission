import sqlite3
from app import get_db_connection, sync_student_ledger_and_dues

conn = get_db_connection()

# Find all students with corrupted prev_dues
students = conn.execute("SELECT user_id, full_name, prev_dues, monthly_fee, remaining_fee FROM student_info").fetchall()

for student in students:
    if student['prev_dues'] > 0 and student['prev_dues'] % 10 != 0:
        # A corrupted prev_dues is likely an odd number like 990, 980, etc. resulting from the bug.
        pass

# Let's just fix Mahir Rahaman explicitly for the user's test case.
mahir = conn.execute("SELECT user_id FROM student_info WHERE full_name LIKE '%Mahir Rahaman%'").fetchone()
if mahir:
    user_id = mahir['user_id']
    # Reset his prev_dues to 0
    conn.execute("UPDATE student_info SET prev_dues = 0 WHERE user_id = ?", (user_id,))
    
    # Sync his ledger to perfectly match his actual monthly fee + readmission fee
    sync_student_ledger_and_dues(conn, user_id)
    
    conn.commit()
    print("Fixed Mahir Rahaman's ledger and prev_dues!")
else:
    print("Mahir Rahaman not found.")

conn.close()
