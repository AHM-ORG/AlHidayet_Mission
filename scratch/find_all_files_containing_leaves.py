import glob
import os

files = glob.glob("*.py") + glob.glob("*.txt")
found = []
for f in files:
    if os.path.isfile(f):
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            if 'CREATE TABLE IF NOT EXISTS leaves' in content or 'CREATE TABLE IF NOT EXISTS guardian_meetings' in content:
                found.append(f)
        except Exception:
            pass

print("Files containing leaves or guardian_meetings table definition:")
for f in found:
    print(f"  {f} ({os.path.getsize(f)} bytes)")
