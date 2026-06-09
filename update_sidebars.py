import glob
import re

files = glob.glob('templates/**/*.html', recursive=True)

for f in files:
    if f.endswith('set_fees.html') or f.endswith('set_salary.html'):
        continue # skip the new ones as they already have it (or we can just run it, but let's be safe)
        
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
        
    modified = False
    
    # We look for the exact <div class="sidebar-label">Cash Manager</div> and insert after it.
    if '<div class="sidebar-label">Cash Manager</div>' in content and 'Set Fees' not in content:
        content = content.replace(
            '<div class="sidebar-label">Cash Manager</div>',
            '<div class="sidebar-label">Cash Manager</div>\n                <a href="/admin/set-fees" class="sidebar-item"><i data-lucide="indian-rupee"></i> Set Fees</a>\n                <a href="/admin/set-salary" class="sidebar-item"><i data-lucide="banknote"></i> Set Salary</a>'
        )
        modified = True
        
    if modified:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print('Updated', f)
