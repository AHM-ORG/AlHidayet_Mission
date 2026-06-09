with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

def print_context(keyword, before=5, after=35):
    for i, line in enumerate(lines):
        if keyword in line:
            print(f"Line {i+1}: {line.strip()}")
            start = max(0, i - before)
            end = min(len(lines), i + after)
            print("--- CONTEXT ---")
            for j in range(start, end):
                print(f"{j+1}: {lines[j].rstrip()}")
            print("---------------\n")

print_context("@app.route('/admin/save-bulk-marks'")
print_context("@app.route('/admin/input-result'")
