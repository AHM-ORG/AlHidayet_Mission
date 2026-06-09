with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("--- save_bulk_marks DETAIL ---")
for idx in range(1712, 1800):
    if idx < len(lines):
        print(f"{idx+1}: {lines[idx].rstrip()}")
print("------------------------------")
