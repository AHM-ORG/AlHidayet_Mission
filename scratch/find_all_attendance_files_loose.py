import os

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Scanning all files in brain dir for any file with 'def admin_attendance':")

found = []
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file.endswith(".txt") or file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                size = os.path.getsize(path)
                if size > 10000:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    if 'def admin_attendance' in content:
                        print(f"  [FOUND] in {path} (size: {size} bytes)")
                        found.append((path, size))
            except Exception:
                pass

print(f"Scan complete. Found {len(found)} files.")
