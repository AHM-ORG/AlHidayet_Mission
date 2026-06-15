with open('d:/AHM/AHM-Web/app.py', encoding='utf-8') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if '/admin/spend' in line:
        print(f"Line {idx+1}: {line.strip()}")
        # Print surrounding lines
        for j in range(max(0, idx-10), min(len(lines), idx+30)):
            print(f"  {j+1}: {lines[j]}", end="")
