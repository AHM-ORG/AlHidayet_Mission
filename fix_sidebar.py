import os
import re

template_dir = r"c:\Users\mdasw\Desktop\Ahm PAH\AlHidayet_Mission\templates"

pattern = re.compile(
    r'[ \t]*<a href="/admin/fee-matrix" class="sidebar-item \{% if request\.path == \'/admin/fee-matrix\' %\}active\{% endif %\}"><i data-lucide="table"></i> Fee Matrix</a>\s*'
    r'<a href="/admin/set-fees" class="sidebar-item \{% if request\.path == \'/admin/set-fees\' %\}active\{% endif %\}"><i data-lucide="indian-rupee"></i> Set Fees</a>'
)

replacement = r'''                <a href="/admin/fee-matrix" class="sidebar-item {% if request.path in ['/admin/fee-matrix', '/admin/set-fees', '/admin/fee_matrix'] %}active{% endif %}"><i data-lucide="table"></i> Fee Matrix & Settings</a>'''

count = 0
for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                
            new_content = pattern.sub(replacement, content)
            
            # If fee_matrix.html has a broken version or old one, I'll just regex for `<a href="/admin/fee-matrix" class="sidebar-item {% if request.path in ['/admin/fee-matrix', '/admin/set-fees', '/admin/fee_matrix'] %}active{% endif %}"><i data-lucide="table"></i> Fee Matrix & Settings</a>` and ensure it's correct.
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                count += 1
                print(f"Updated {f}")

print(f"Total updated: {count}")
