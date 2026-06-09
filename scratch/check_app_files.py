import glob
import os
import re

files = glob.glob("app*.py")
print(f"Found app files: {files}")

for filename in files:
    size = os.path.getsize(filename)
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    lines = content.splitlines()
    print(f"\nFile: {filename} ({size} bytes, {len(lines)} lines)")
    
    # Find all route decorators
    routes = re.findall(r"@app\.route\('([^']+)'", content)
    print(f"  Routes ({len(routes)}): {routes[:15]}")
    if len(routes) > 15:
        print(f"  ... and {len(routes)-15} more")
    
    # Check for specific functions
    for func in ['admin_guardian_meetings', 'guardian_meeting_attendance', 'student_attendance_leaves', 'teacher_attendance_leaves', 'submit_application']:
        if f"def {func}" in content:
            print(f"  [FOUND] def {func}")
        else:
            print(f"  [MISSING] def {func}")
