with open("app_recovered_text_46f71de6.py", "r", encoding="utf-8") as f:
    content = f.read()

import re
tables = re.findall(r"CREATE TABLE IF NOT EXISTS \w+", content, re.IGNORECASE)
print("Tables in app_recovered_text_46f71de6.py:")
for t in tables:
    print("  ", t)

# Also check for leaves table definition
match = re.search(r"CREATE TABLE IF NOT EXISTS leaves.*?\)", content, re.DOTALL | re.IGNORECASE)
if match:
    print("\nLeaves table found:")
    print(match.group(0))
else:
    print("\nLeaves table NOT found by regex.")
