with open("scratch/recovered_routes_1.py", "r", encoding="utf-8") as f:
    content = f.read()

import json
def decode_val(val):
    if val.startswith('"') and val.endswith('"') or val.startswith("'") and val.endswith("'"):
        try:
            return eval(val)
        except Exception:
            return val[1:-1].encode('utf-8').decode('unicode_escape', errors='ignore')
    return val

decoded = decode_val(content)
lines = decoded.splitlines()
print("Decoded recovered_routes_1.py length in chars:", len(decoded))
print("Decoded recovered_routes_1.py number of lines:", len(lines))
print("Last 10 lines of decoded recovered_routes_1.py:")
for l in lines[-10:]:
    print(l)
