import urllib.request
import urllib.parse
import sqlite3
import json

def test_apply():
    url = 'http://127.0.0.1:5001/submit-application'
    
    # Form data matching teacher joining request
    data = {
        'form_type': 'Teacher Joining Form',
        'full_name': 'Dr. Alan Turing',
        'dob': '1912-06-23',
        'gender': 'Male',
        'email': 'alan.turing@hidayet.edu.in',
        'phone_no': '9876543210',
        'aadhar_no': '123456789012',
        'qualification': 'Ph.D. in Computer Science',
        'specialization': 'Mathematics & Cryptography',
        'experience_years': '10',
        'prev_school': 'Princeton University',
        'experience_details': 'Pioneered theoretical computer science and formal computational models.',
        'branch': 'Bhogram',
        'expected_salary': '85000',
        'village': 'Bletchley Park',
        'po': 'Milton Keynes',
        'ps': 'Buckinghamshire',
        'dist': 'London',
        'state': 'West Bengal',
        'pin': '700001'
    }
    
    encoded_data = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, method='POST')
    
    try:
        response = urllib.request.urlopen(req)
        print("HTTP Status Code:", response.getcode())
        print("Redirected URL:", response.geturl())
        
        # Verify in DB
        conn = sqlite3.connect('users.db')
        conn.row_factory = sqlite3.Row
        
        # Find latest application
        row = conn.execute("SELECT * FROM applications ORDER BY id DESC LIMIT 1").fetchone()
        
        print("\n--- DATABASE VERIFICATION ---")
        if row:
            row_dict = dict(row)
            print("Row ID:", row_dict['id'])
            print("Form Type:", row_dict['type'])
            print("Status:", row_dict['status'])
            print("Branch Resolved in DB:", row_dict['branch'])
            print("Submitted At:", row_dict['submitted_at'])
            
            payload = json.loads(row_dict['data'])
            print("\nSerialized JSON Payload details:")
            print("  - Candidate Name:", payload.get('full_name'))
            print("  - Email:", payload.get('email'))
            print("  - Phone:", payload.get('phone_no'))
            print("  - Aadhaar:", payload.get('aadhar_no'))
            print("  - Qualification:", payload.get('qualification'))
            print("  - Specialization:", payload.get('specialization'))
            print("  - Total Experience:", payload.get('experience_years'), "Years")
            print("  - Expected Salary: INR", payload.get('expected_salary'))
            print("  - Preferred Branch:", payload.get('branch'))
            print("  - Village/Street:", payload.get('village'))
            
            # Clean up the test row
            conn.execute("DELETE FROM applications WHERE id = ?", (row_dict['id'],))
            conn.commit()
            print("\nTest verification record successfully cleaned up from database.")
        else:
            print("Error: No applications found in database.")
            
        conn.close()
    except Exception as e:
        print("Application post request failed:", e)

if __name__ == '__main__':
    test_apply()
