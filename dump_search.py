with open('app.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'sync_student_ledger_and_dues' in line:
            print(f"{i+1}: {line.strip()}")
