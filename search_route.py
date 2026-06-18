with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("--- DASHBOARD ROUTE DETAIL ---")
for idx in range(855, 940):
    if idx < len(lines):
        print(f"{idx+1}: {lines[idx].rstrip()}")
print("------------------------------")
