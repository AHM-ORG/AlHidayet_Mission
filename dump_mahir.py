import os
from app import get_db_connection

conn = get_db_connection()

# Get Mahir Rahaman's user_id
student_row = None
try:
    cursor = conn.execute("SELECT user_id FROM student_info WHERE full_name LIKE '%Mahir Rahaman%'")
    student_row = cursor.fetchone()
except Exception as e:
    print(f"Error fetching student: {e}")

if student_row:
    user_id = student_row['user_id']
    print(f"User ID: {user_id}")
    
    # Get ledger entries
    cursor = conn.execute("SELECT id, fee_type, amount, status FROM student_ledger WHERE student_id = ? ORDER BY id DESC", (user_id,))
    entries = cursor.fetchall()
    print("Ledger Entries:")
    for e in entries:
        print(dict(zip(e.keys(), e)))
else:
    print("Student not found")

conn.close()
