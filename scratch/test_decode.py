import json

rc_raw = '"\\"@app.route(\\\'/routine\\\', methods=[\\\'GET\\\', \\\'POST\\\'])\\\\ndef view_routine():\\\\n    if \\\'user\\\' not in session:\\\\n        return redirect(url_for(\\\'home\\\'))\\\\n        \\\\n    conn = get_db_connection()\\\\n    role = session.get(\\\'role\\\')\\\\n    \\\\n    if request.method == \\\'POST\\\':\\\\n        if role != \\\'admin\\\':\\\\n            i\\"'

def decode_val(val):
    if val is None:
        return ''
    if isinstance(val, str):
        while (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            try:
                val = json.loads(val)
            except Exception:
                val = val[1:-1]
        try:
            val = val.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
        val = val.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace('\\"', '"').replace("\\'", "'")
    return val

decoded = decode_val(rc_raw)
print("Decoded output:")
print(decoded)
