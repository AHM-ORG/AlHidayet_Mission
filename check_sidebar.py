import re
with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

hrefs = re.findall(r'href="(/[^"]+)"', content)
sidebar_hrefs = [h for h in hrefs if h.startswith('/admin/') or h.startswith('/teacher/') or h.startswith('/student/') or h in ['/dashboard', '/register', '/routine', '/logout']]
print('Sidebar links found:')
for h in sorted(set(sidebar_hrefs)):
    print(f'  {h}')