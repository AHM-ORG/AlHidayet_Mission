import glob
import re

# All HTML templates with sidebar
files = glob.glob('templates/**/*.html', recursive=True) + glob.glob('templates/*.html')

# The new sidebar-header content - clickable logo linking to home
new_header = '''<div class="sidebar-header">
                <a href="/" style="display:flex; align-items:center; gap:10px; text-decoration:none; color:inherit;">
                    <img src="{{ logo_url }}" alt="AHM" style="width:36px; height:36px; border-radius:8px; object-fit:cover;">
                    <span style="font-weight:700; font-size:14px;">Al Hidayet Mission</span>
                </a>
            </div>'''

count = 0
for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'sidebar-header' not in content:
            continue
        
        # Pattern 1: <div class="sidebar-header">...</div> (multi-line with content)
        # Pattern 2: <div class="sidebar-header"></div> (empty, single line)
        
        # Replace all sidebar-header blocks
        # Match from <div class="sidebar-header"> to its closing </div>
        pattern = r'<div class="sidebar-header">.*?</div>'
        
        new_content = re.sub(pattern, new_header, content, count=1, flags=re.DOTALL)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            count += 1
            print(f"Updated: {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")

print(f"\nTotal files updated: {count}")
