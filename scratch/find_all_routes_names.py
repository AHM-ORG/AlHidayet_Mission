with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

import re
funcs = re.findall(r"def\s+(\w+)", content)
print("Functions in current app.py:")
for fn in sorted(set(funcs)):
    if 'attendance' in fn or 'leaves' in fn or 'meeting' in fn or 'marksheet' in fn:
        print(f"  {fn}")
