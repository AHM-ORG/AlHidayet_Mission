import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import sqlite3
from app import app

# Create a test client
client = app.test_client()

# First, log in as headmaster
login_response = client.post('/login/admin', data={
    'username': 'headmaster',
    'password': 'admin'
}, follow_redirects=True)

print("Login Status:", login_response.status_code)

# Let's seed a test class and subject of that class so we can delete it
conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("INSERT INTO classes (name) VALUES (?)", ("TestClassForDeletion",))
class_id = cursor.lastrowid
cursor.execute("INSERT INTO subjects (name, class) VALUES (?, ?)", ("TestSub", "TestClassForDeletion"))
subject_id = cursor.lastrowid
conn.commit()
conn.close()

print(f"Inserted test class ID: {class_id}, test subject ID: {subject_id}")

# Now let's try to delete this class via AJAX
delete_response = client.post('/admin/academics-setting', data={
    'delete_class': '1',
    'class_id': str(class_id)
}, headers={
    'X-Requested-With': 'XMLHttpRequest'
})

print("Delete Class Response Status:", delete_response.status_code)
print("Delete Class Response Content-Type:", delete_response.content_type)
print("Delete Class Response Data:", delete_response.get_data(as_text=True))

# Check if both class and subject are deleted
conn = sqlite3.connect("users.db")
class_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
sub_row = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
conn.close()

if class_row is None:
    print("Class successfully deleted from DB!")
else:
    print("Class STILL EXISTS in DB!")

if sub_row is None:
    print("Class subject successfully deleted from DB!")
else:
    print("Class subject STILL EXISTS in DB!")
