import glob
import os

files = glob.glob('templates/**/*.html', recursive=True)

print("Checking sidebar routes in templates...")
for f in files:
    if os.path.isdir(f):
        continue
        
    content = ""
    encoding = 'utf-8'
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        try:
            with open(f, 'r', encoding='utf-16') as file:
                content = file.read()
            encoding = 'utf-16'
        except Exception:
            continue
            
    if 'class="sidebar"' in content or 'class="sidebar-item"' in content:
        # Check links
        has_admin_attendance = '/admin/attendance' in content
        has_admin_leaves = '/admin/leaves' in content
        has_teacher_leaves = '/teacher/attendance-leaves' in content
        has_student_leaves = '/student/attendance-leaves' in content
        
        print(f"File: {f} ({encoding})")
        print(f"  - Admin Attendance: {has_admin_attendance}")
        print(f"  - Admin Leaves:     {has_admin_leaves}")
        print(f"  - Teacher Leaves:   {has_teacher_leaves}")
        print(f"  - Student Leaves:   {has_student_leaves}")
