with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

def get_context(line_num):
    start = max(0, line_num - 5)
    end = min(len(lines), line_num + 5)
    return "".join(lines[start:end])

line_nums = [4538, 5460, 6477, 6742, 10897, 10949, 11186, 11213, 11258, 11583, 14560, 14736]
for n in line_nums:
    print(f"\n--- Line {n} ---")
    print(get_context(n-1))
