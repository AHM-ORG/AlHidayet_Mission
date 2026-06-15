import subprocess
import glob
import os

hashes = [os.path.basename(p) for p in glob.glob('.git/lost-found/other/*')]

print(f"Scanning {len(hashes)} dangling git objects...")

for h in hashes:
    # Check object type
    try:
        obj_type = subprocess.check_output(['git', 'cat-file', '-t', h]).decode().strip()
    except Exception:
        continue
        
    if obj_type in ['commit', 'tree']:
        try:
            # Try to show app.py in this commit/tree
            content = subprocess.check_output(['git', 'show', f"{h}:app.py"], stderr=subprocess.DEVNULL)
            size = len(content)
            # Decode to check contents
            text = content.decode('utf-8', errors='ignore')
            if 'def admin_attendance():' in text:
                print(f"\n[FOUND] Match in {obj_type} {h}!")
                print(f"  Size of app.py: {size} bytes")
                # Write to restored_app.py
                with open('restored_app.py', 'wb') as f:
                    f.write(content)
                print("  Saved as restored_app.py!")
        except Exception as e:
            pass
            
print("\nScan completed.")
