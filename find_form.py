import re

with open('templates/admin/student_list.html', 'r', encoding='utf-8') as f:
    content = f.read()

forms = re.findall(r'<form[^>]*action="([^"]+)"', content)
print("Forms in student_list:", forms)
