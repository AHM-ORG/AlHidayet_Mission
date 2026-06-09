import os

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Scanning brain directory...")
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file.endswith((".py", ".txt", ".json", ".jsonl", ".md")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if "admin_guardian_meetings" in content:
                    print(f"Match: {path} ({len(content)} bytes)")
            except Exception as e:
                pass
print("Scan complete.")
