import os
import glob

lost_found_dir = r"d:\AHM\AHM-Web\.git\lost-found\other"
print("Scanning lost-found directory for 'teacher_attendance_leaves'...")

if not os.path.exists(lost_found_dir):
    print("lost-found directory does not exist.")
    exit(1)

files = glob.glob(os.path.join(lost_found_dir, "*"))
print(f"Found {len(files)} loose files.")

found_count = 0
for idx, path in enumerate(files):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if 'teacher_attendance_leaves' in content:
            size = os.path.getsize(path)
            print(f"  Match {found_count}: {os.path.basename(path)} (size: {size} bytes)")
            found_count += 1
            # Copy to scratch
            import shutil
            shutil.copy(path, f"d:\\AHM\\AHM-Web\\scratch\\dangling_blob_{os.path.basename(path)}.py")
    except Exception as e:
        pass
        
print("Search complete.")
