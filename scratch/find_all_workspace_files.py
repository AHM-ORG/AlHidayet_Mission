import os

workspace_dir = r"d:\AHM\AHM-Web"
print("Scanning workspace for 'admin_guardian_meetings':")

found_count = 0
for root, dirs, files in os.walk(workspace_dir):
    # Skip venv and .git
    if ".venv" in root or ".git" in root or "node_modules" in root:
        continue
    for file in files:
        if file.endswith(".py") or file.endswith(".txt") or file.endswith(".html"):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if 'admin_guardian_meetings' in content:
                    print(f"  [FOUND] in {path} (size: {os.path.getsize(path)} bytes)")
                    found_count += 1
            except Exception as e:
                pass

print(f"Scan complete. Found {found_count} matching files.")
