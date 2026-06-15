import json

def decode_val(val):
    if val.startswith('"') and val.endswith('"') or val.startswith("'") and val.endswith("'"):
        try:
            return eval(val)
        except Exception:
            return val[1:-1].encode('utf-8').decode('unicode_escape', errors='ignore')
    return val

for f in ["scratch/recovered_routes_1.py", "scratch/recovered_routes_8.py", "scratch/recovered_routes_9.py"]:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    decoded = decode_safely = decode_val(content)
    print(f"\n=================== DECODED {f} ===================")
    print(decoded)
