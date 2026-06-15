with open('d:/AHM/AHM-Web/app.py', encoding='utf-8') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if '/student/edit-info' in line or '/admin/edit-teacher' in line or '/admin/edit-student' in line:
        print(f"Line {idx+1}: {line.strip()}")
        # Print surrounding lines
        for j in range(max(0, idx-5), min(len(lines), idx+35)):
            print(f"  {j+1}: {lines[j]}", end="")
