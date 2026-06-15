import glob
import os

files = glob.glob('templates/**/*.html', recursive=True)

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
        
    if '<aside class="sidebar">' not in content:
        continue
        
    modified = False
    
    # For Admin
    admin_insert = '<a href="/admin/marks-setup" class="sidebar-item"><i data-lucide="settings"></i> Marks Setup</a>'
    if 'Academics</div>' in content and admin_insert not in content:
        content = content.replace(
            '<div class="sidebar-label">Academics</div>',
            '<div class="sidebar-label">Academics</div>\n                ' + admin_insert
        )
        modified = True
        
    # For Teacher
    teacher_insert = '<a href="/admin/marks-setup" class="sidebar-item"><i data-lucide="settings"></i> Marks Setup</a>'
    if 'Academic Tools</div>' in content and teacher_insert not in content:
        content = content.replace(
            '<div class="sidebar-label">Academic Tools</div>',
            '<div class="sidebar-label">Academic Tools</div>\n                ' + teacher_insert
        )
        modified = True

    if modified:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print('Updated sidebar in', f)
