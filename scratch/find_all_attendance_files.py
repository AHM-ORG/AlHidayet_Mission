import os

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Scanning all files in brain dir for non-truncated admin_attendance:")

found = []
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file.endswith(".txt") or file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                size = os.path.getsize(path)
                if size > 10000: # only look at files > 10KB to find the full code
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    if 'def admin_attendance' in content and 'def teacher_attendance_leaves' in content and 'truncated' not in content:
                        print(f"  [FOUND] in {path} (size: {size} bytes)")
                        found.append((path, size))
            except Exception:
                pass

if found:
    found.sort(key=lambda x: x[1], reverse=True)
    print(f"\nBest match: {found[0][0]} ({found[0][1]} bytes)")
else:
    print("No non-truncated files found.")
