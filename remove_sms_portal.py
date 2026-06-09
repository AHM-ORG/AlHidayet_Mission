import glob
import re

for f in glob.glob('templates/**/*.html', recursive=True):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    modified = False
    
    # Sometimes it has a link or span inside it, or just different whitespace.
    # We will search for 'SMS PORTAL' and if it is within a sidebar-header we can remove it.
    if 'SMS PORTAL' in content:
        # A simple string replace since there might be whitespace issues.
        # But wait, looking at dashboard.html, it could be:
        # <div class="sidebar-header">
        #     SMS PORTAL
        # </div>
        # Let's replace the whole block using regex:
        content, count = re.subn(r'<div class="sidebar-header">\s*SMS PORTAL\s*</div>', '<div class="sidebar-header"></div>', content)
        if count > 0:
            modified = True
            
        # Also just in case there's an exact match without whitespace
        content, count = re.subn(r'SMS PORTAL', '', content)
        if count > 0:
            modified = True
            
    if modified:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print('Updated', f)
