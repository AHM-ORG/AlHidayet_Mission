with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

for func in ['admin_guardian_meetings', 'guardian_meeting_attendance', 'student_attendance_leaves', 'teacher_attendance_leaves', 'submit_application']:
    found = func in content
    print(f"{func}: {'FOUND' if found else 'NOT FOUND'}")
    if found:
        # Print function signature and first few lines of the function
        idx = content.find(f"def {func}")
        print("  Signature:", content[idx:content.find('\n', idx)])
