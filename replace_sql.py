import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the simple select with a join query
old_query = "SELECT id, username FROM users WHERE role = 'student'"
new_query = "SELECT u.id, u.username, si.full_name, si.roll_number, si.class FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'"

content = content.replace(old_query, new_query)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated app.py")
