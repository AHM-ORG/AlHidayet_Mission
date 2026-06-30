with open('app.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if '/admin/post-monthly-fees' in line or '/admin/re-trigger-monthly-fees' in line:
            print(f"{i+1}: {line.strip()}")
