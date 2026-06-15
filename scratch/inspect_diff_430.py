with open("extracted_content_a712927e-564c-4af2-9247-098a4b5e1dad_430.txt", "r", encoding="utf-8") as f:
    content = f.read()

print("File size:", len(content))
lines = content.splitlines()
print("Number of lines:", len(lines))
# Let's count lines starting with '+'
plus_lines = [l for l in lines if l.startswith('+')]
print("Number of added lines (+):", len(plus_lines))
# Find functions defined with '+'
import re
funcs = re.findall(r"\+\s*def\s+(\w+)", content)
print("Functions defined in diff:")
for fn in funcs:
    print(f"  {fn}")
