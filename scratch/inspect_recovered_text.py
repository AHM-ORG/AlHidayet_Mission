with open("app_recovered_text_e054b07e.py", "r", encoding="utf-8") as f:
    lines = [f.readline() for _ in range(50)]

print("First 50 lines of app_recovered_text_e054b07e.py:")
for idx, line in enumerate(lines):
    print(f"{idx+1}: {repr(line)}")
