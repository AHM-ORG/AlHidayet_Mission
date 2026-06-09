import os

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Scanning all files in brain dir for 'admin_guardian_meetings':")

found_count = 0
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file.endswith(".py") or file.endswith(".txt") or file.endswith(".jsonl"):
            path = os.path.join(root, file)
            try:
                # Read first 1MB of file or stream it to search
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if 'admin_guardian_meetings' in content:
                    print(f"  [FOUND] in {path} (size: {os.path.getsize(path)} bytes)")
                    found_count += 1
            except Exception as e:
                pass

print(f"Scan complete. Found {found_count} matching files.")
