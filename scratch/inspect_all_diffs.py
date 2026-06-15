import glob
import os
import re

files = glob.glob("extracted_content_*.txt")
for f in files:
    size = os.path.getsize(f)
    print(f"\nFile: {f} ({size} bytes)")
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()
    
    # Find any line that matches 'def func(' or '+ def func(' or '123: def func('
    funcs = re.findall(r"(?:\+|:\s*|\b)def\s+(\w+)", content)
    print("  Functions:")
    for fn in set(funcs):
        print(f"    {fn}")
