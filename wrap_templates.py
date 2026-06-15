import os

def wrap_content(source_html, target_html, title, header_title, content):
    with open(source_html, 'r', encoding='utf-8') as f:
        src = f.read()
        
    head_end = src.find('</head>')
    body_start = src.find('<div class="dashboard-container">')
    main_start = src.find('<main class="main-content">')
    content_wrapper_start = src.find('<div class="content-wrapper">')
    content_wrapper_end = src.find('</main>')
    
    top = src[:content_wrapper_start]
    bottom = src[content_wrapper_end:]
    
    # Replace title
    import re
    top = re.sub(r'<title>.*?</title>', f'<title>{title}</title>', top)
    top = re.sub(r'<div class="top-bar-title">.*?</div>', f'<div class="top-bar-title">{header_title}</div>', top)
    
    # Also add tom-select css and js if not already there, actually we keep whatever is in source
    
    final_html = top + '<div class="content-wrapper">\n' + content + '\n</div>\n' + bottom
    
    with open(target_html, 'w', encoding='utf-8') as f:
        f.write(final_html)

# Read the content parts we wrote earlier
with open('templates/admin/marks_setup.html', 'r', encoding='utf-8') as f:
    setup_content_raw = f.read()
setup_content = setup_content_raw.split('{% block content %}')[1].split('{% endblock %}')[0]
setup_scripts = setup_content_raw.split('{% block scripts %}')[1].split('{% endblock %}')[0]

with open('templates/admin/marks_entry.html', 'r', encoding='utf-8') as f:
    entry_content_raw = f.read()
entry_content = entry_content_raw.split('{% block content %}')[1].split('{% endblock %}')[0]
entry_scripts = entry_content_raw.split('{% block scripts %}')[1].split('{% endblock %}')[0]

# Wrap them
wrap_content('templates/admin/input_result.html', 'templates/admin/marks_setup.html', 'Marks Setup - AHM', 'Marks Setup', setup_content + '\n' + setup_scripts)
wrap_content('templates/admin/input_result.html', 'templates/admin/marks_entry.html', 'Marks Entry - AHM', 'Marks Entry', entry_content + '\n' + entry_scripts)

print("Wrapped templates successfully.")
