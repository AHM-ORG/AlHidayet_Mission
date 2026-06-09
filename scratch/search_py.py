import os

files = ['app.py', 'app_may8.py', 'app_recovered_e054b07e.py', 'app_recovered_text_46f71de6.py', 'app_recovered_text_54b8dcb8.py', 'app_recovered_text_e054b07e.py']
encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1']

for f in files:
    if not os.path.exists(f):
        continue
    size = os.path.getsize(f)
    print(f"\n=== File: {f} (size: {size} bytes) ===")
    
    for enc in encodings:
        try:
            with open(f, 'r', encoding=enc) as file:
                content = file.read()
            print(f"  [{enc}] SUCCESS. Length: {len(content)} chars.")
            if 'def ' in content:
                print(f"    Found 'def '. Definitions matching keywords:")
                lines = content.split('\n')
                matches = [line.strip() for line in lines if 'def ' in line and ('dashboard' in line or 'login' in line or 'attendance' in line or 'init' in line)]
                for m in matches[:10]:
                    print(f"      {m}")
        except Exception as e:
            print(f"  [{enc}] ERROR: {type(e).__name__}: {str(e)[:100]}")
