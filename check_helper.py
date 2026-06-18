with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'get_teacher_allowed_subjects' in line or 'parse_teacher_qualifications' in line:
        print(f"Line {i+1}: {line.strip()}")
        # Context
        start = max(0, i - 2)
        end = min(len(lines), i + 30)
        print("--- CONTEXT ---")
        for j in range(start, end):
            print(f"{j+1}: {lines[j].rstrip()}")
        print("---------------\n")
