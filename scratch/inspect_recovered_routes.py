import glob
import os
import re

files = sorted(glob.glob("scratch/recovered_routes_*.py"))
print(f"Found {len(files)} recovered routes files.")

for f in files:
    size = os.path.getsize(f)
    with open(f, 'r', encoding='utf-8', errors='ignore') as file:
        content = file.read()
    
    # Print the first line or first function definition
    funcs = re.findall(r"def\s+(\w+)", content)
    print(f"\nFile: {f} ({size} bytes)")
    print(f"  Functions: {funcs}")
    print("  First 150 chars:")
    print(repr(content[:150]))
