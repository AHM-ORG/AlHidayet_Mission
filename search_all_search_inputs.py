import os

for root, dirs, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if 'placeholder="Search' in content or "placeholder='Search" in content or 'type="text"' in content:
                    print(f"File: {filepath}")
                    for i, line in enumerate(content.splitlines()):
                        if 'placeholder=' in line or 'type="text"' in line or 'Search' in line:
                            if 'input' in line or 'search' in line.lower():
                                print(f"  {i+1}: {line.strip()}")
            except Exception as e:
                pass
