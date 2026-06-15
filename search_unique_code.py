import os

for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py') or file.endswith('.html'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if 'unique_code' in content:
                    print(f"File: {filepath}")
                    for i, line in enumerate(content.splitlines()):
                        if 'unique_code' in line:
                            print(f"  {i+1}: {line.strip()}")
            except Exception as e:
                pass
