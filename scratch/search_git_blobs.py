import os
import glob

lost_found_dir = r"d:\AHM\AHM-Web\.git\lost-found\other"
print("Scanning lost-found directory:", lost_found_dir)

if not os.path.exists(lost_found_dir):
    print("lost-found directory does not exist. Let's look inside loose objects.")
    # Let's search inside git objects directly
    git_objects_dir = r"d:\AHM\AHM-Web\.git\objects"
    # We can write a script to check that too
    exit(1)

files = glob.glob(os.path.join(lost_found_dir, "*"))
print(f"Found {len(files)} loose files in lost-found/other.")

found_blobs = []
for path in files:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if 'def student_attendance_leaves' in content and 'def teacher_attendance_leaves' in content:
            size = os.path.getsize(path)
            print(f"  [MATCH] Found in {os.path.basename(path)} (size: {size} bytes)")
            found_blobs.append((path, size))
    except Exception as e:
        pass

# Copy the largest matching blob to app.py
if found_blobs:
    # Sort by size descending
    found_blobs.sort(key=lambda x: x[1], reverse=True)
    best_blob = found_blobs[0][0]
    best_size = found_blobs[0][1]
    print(f"\nRestoring app.py from best blob: {best_blob} ({best_size} bytes)")
    import shutil
    shutil.copy(best_blob, "d:\\AHM\\AHM-Web\\app.py")
    print("Successfully restored app.py!")
else:
    print("No matching dangling blobs containing the routes were found.")
