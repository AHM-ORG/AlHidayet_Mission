import glob
import re

files = glob.glob('templates/**/*.html', recursive=True)

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
        
    modified = False
    
    # Simple replaces for common patterns
    replaces = [
        ('{{ student.username }}', '{{ student.full_name or student.username }}'),
        ('{{ student.username|upper }}', '{{ (student.full_name or student.username)|upper }}'),
        ('{{ student.username|title }}', '{{ (student.full_name or student.username)|title }}'),
        ('{{ s.username }}', '{{ s.full_name or s.username }}'),
    ]
    
    for old, new in replaces:
        if old in content:
            # For edit_student.html we should NOT replace the value attribute of the username input
            if f.endswith('edit_student.html') and 'value="{{ student.username }}"' in content:
                # Be more precise
                pass
            content = content.replace(old, new)
            modified = True
            
    # Fix back the value="{{ student.username }}" if it was replaced in edit_student.html
    if f.endswith('edit_student.html') and modified:
        content = content.replace('value="{{ student.full_name or student.username }}"', 'value="{{ student.username }}"')
        
    if modified:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print('Updated', f)

