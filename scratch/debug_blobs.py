import os
import glob

lost_found_dir = r"d:\AHM\AHM-Web\.git\lost-found\other"
print("Debugging lost-found directory...")

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
        if 'admin_attendance' in content:
            size = os.path.getsize(path)
            print(f"  Match {found_count}: {os.path.basename(path)} (size: {size} bytes)")
            found_count += 1
            if found_count >= 20:
                print("Printed first 20 matches.")
                break
    except Exception as e:
        pass
        
print("Debug complete.")
