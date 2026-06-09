import re

print("Searching app.py for render_template:")
with open("app.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if "render_template" in line:
            print(f"{idx}: {line.strip()}")
