import os
import glob

lost_found_dir = r"d:\AHM\AHM-Web\.git\lost-found\other"
print("Scanning lost-found directory fuzzily...")

if not os.path.exists(lost_found_dir):
    print("lost-found directory does not exist.")
    exit(1)

files = glob.glob(os.path.join(lost_found_dir, "*"))
print(f"Found {len(files)} loose files.")

matches = []
for path in files:
    try:
        size = os.path.getsize(path)
        if size > 150000 and size < 250000: # app.py size is between 150KB and 250KB
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if 'def admin_attendance' in content:
                print(f"  [FOUND MATCH] {os.path.basename(path)}: size={size} bytes")
                matches.append((path, size))
    except Exception as e:
        pass

if matches:
    matches.sort(key=lambda x: x[1], reverse=True)
    best = matches[0][0]
    print(f"\nRestoring app.py from best fuzzy blob: {best} ({matches[0][1]} bytes)")
    import shutil
    shutil.copy(best, "d:\\AHM\\AHM-Web\\app.py")
    print("Successfully restored app.py fuzzily!")
else:
    print("No matching large blobs with admin_attendance found.")
