import glob
import os

files = glob.glob("**/*.py", recursive=True)
print("Scanning all python files in workspace for 'student_attendance_leaves':")

found = []
for f in files:
    # Skip venv
    if ".venv" in f or "venv" in f:
        continue
    try:
        size = os.path.getsize(f)
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
        if 'def student_attendance_leaves' in content:
            print(f"  [FOUND] in {f} ({size} bytes)")
            found.append(f)
    except Exception:
        pass

print(f"Scan complete. Found in {len(found)} files.")
