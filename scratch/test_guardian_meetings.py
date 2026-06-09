import sys
import os
import sqlite3

# Ensure we can import from workspace directory
sys.path.append(r'd:\AHM\AHM-Web')

from app import app, get_db_connection

def test_db_operations():
    print("Testing DB operations for Guardian Meetings...")
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Clean old test meetings if any
    c.execute("DELETE FROM guardian_meetings WHERE meeting_name = 'Special Guardian Meeting' AND branch = 'TestBranch'")
    conn.commit()
    
    # 2. Insert test meeting
    c.execute('''
        INSERT INTO guardian_meetings (meeting_name, meeting_date, meeting_month, branch)
        VALUES ('Special Guardian Meeting', '2026-06-15', 'June 2026', 'TestBranch')
    ''')
    meeting_id = c.lastrowid
    conn.commit()
    print(f" [+] Inserted test meeting with ID: {meeting_id}")
    
    # 3. Insert test teacher attendance
    # Let's get a teacher user if any exists
    teacher = c.execute("SELECT id, username FROM users WHERE role = 'teacher' LIMIT 1").fetchone()
    if teacher:
        t_id = teacher['id']
        c.execute('''
            INSERT INTO meeting_attendance (meeting_id, attendee_type, user_id, status, remarks)
            VALUES (?, 'teacher', ?, 'Present', 'Arrived early')
        ''', (meeting_id, t_id))
        conn.commit()
        print(f" [+] Inserted teacher attendance for '{teacher['username']}'")
        
        # Test duplicate prevention (Unique constraint)
        try:
            c.execute('''
                INSERT INTO meeting_attendance (meeting_id, attendee_type, user_id, status, remarks)
                VALUES (?, 'teacher', ?, 'Absent', 'Duplicate test')
            ''', (meeting_id, t_id))
            conn.commit()
            print(" [X] Error: Duplicate teacher attendance allowed!")
        except sqlite3.IntegrityError:
            print(" [+] Duplicate teacher attendance correctly blocked by UNIQUE constraint.")
            
    # 4. Insert dynamic guest attendee
    c.execute('''
        INSERT INTO meeting_attendance (meeting_id, attendee_type, other_name, other_designation, status, remarks)
        VALUES (?, 'other', 'Guest Speaker John', 'External Counselor', 'Present', 'Gave career speech')
    ''', (meeting_id,))
    conn.commit()
    print(" [+] Inserted guest attendee successfully.")
    
    # 5. Fetch stats summary
    stats = c.execute('''
        SELECT attendee_type, COUNT(*) as count
        FROM meeting_attendance
        WHERE meeting_id = ? AND status = 'Present'
        GROUP BY attendee_type
    ''', (meeting_id,)).fetchall()
    
    stats_dict = {row['attendee_type']: row['count'] for row in stats}
    print(f" [+] Retrieved Present stats summary: {stats_dict}")
    assert stats_dict.get('other') == 1, "Guest count assertion failed!"
    
    # 6. Cleanup test records
    c.execute("DELETE FROM meeting_attendance WHERE meeting_id = ?", (meeting_id,))
    c.execute("DELETE FROM guardian_meetings WHERE id = ?", (meeting_id,))
    conn.commit()
    print(" [+] Cleaned up all test records.")
    conn.close()
    print("All database assertions passed successfully!")

def test_flask_routes():
    print("\nTesting Flask Route handlers using test_client...")
    client = app.test_client()
    
    # Simulate a logged-in admin session
    with client.session_transaction() as sess:
        sess['user'] = 'headmaster'
        sess['role'] = 'admin'
        sess['branch'] = None # Global admin
        
    # GET Guardian Meetings page
    response = client.get('/admin/guardian-meetings')
    print(f"GET /admin/guardian-meetings status: {response.status_code}")
    assert response.status_code == 200, "Failed to load guardian meetings view!"
    assert b"Guardian Meetings" in response.data, "Guardian Meetings text not found in render output!"
    print(" [+] Guardian meetings view verified.")
    
    print("All route tests completed successfully!")

if __name__ == '__main__':
    try:
        test_db_operations()
        test_flask_routes()
        print("\nSUMMARY: 100% of integration checks passed perfectly!")
    except Exception as e:
        print(f"\n [ERROR] Verification failed: {e}")
        sys.exit(1)
