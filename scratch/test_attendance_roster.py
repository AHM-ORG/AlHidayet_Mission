import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

client = app.test_client()

# First, log in as headmaster
login_response = client.post('/login/admin', data={
    'username': 'headmaster',
    'password': 'admin'
}, follow_redirects=True)

print("Login Status:", login_response.status_code)

# 1. Test Student Roster loading for Class 'One' at 'bhogram' branch
student_response = client.get('/admin/attendance?branch=bhogram&role_filter=student&class_filter=One')
print("Student Page Status:", student_response.status_code)
html_student = student_response.get_data(as_text=True)

# Look for student names and roll numbers in the table
has_students_count = "Showing 17 records" in html_student or "Raihana Parvin" in html_student
print("Is student roster successfully loaded in HTML?", has_students_count)

# 2. Test Teacher Roster loading
teacher_response = client.get('/admin/attendance?branch=bhogram&role_filter=teacher')
print("Teacher Page Status:", teacher_response.status_code)
html_teacher = teacher_response.get_data(as_text=True)

# Look for teacher names in the table
has_teachers_count = "Showing 10 records" in html_teacher or "AJINUR" in html_teacher
print("Is teacher roster successfully loaded in HTML?", has_teachers_count)
