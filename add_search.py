import re

files_to_update = [
    'templates/admin/get_fees.html',
    'templates/admin/set_salary.html',
    'templates/admin/id_card.html',
    'templates/admin/marksheet.html',
    'templates/admin/set_fees.html',
    'templates/admin/student_promotion.html',
    'templates/admin/input_result.html'
]

css_link = '    <link href="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/css/tom-select.css" rel="stylesheet">\n'
js_link = '    <script src="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/js/tom-select.complete.min.js"></script>\n'
init_script = '''
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            document.querySelectorAll('select.search-select').forEach((el)=>{
                new TomSelect(el,{
                    create: false,
                    sortField: {
                        field: "text",
                        direction: "asc"
                    }
                });
            });
        });
    </script>
'''

for filepath in files_to_update:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Add CSS if not present
        if 'tom-select.css' not in content:
            content = content.replace('</head>', f'{css_link}</head>')
            
        # Add JS if not present
        if 'tom-select.complete.min.js' not in content:
            content = content.replace('</body>', f'{js_link}{init_script}</body>')
            
        # Add class to select elements
        selects_to_target = ['student_id', 'teacher_id', 'branch', 'class', 'from_class', 'to_class', 'subject']
        for sel in selects_to_target:
            # We look for <select name="X" ...> and add class="search-select" if not there
            # Since HTML can have various spaces, regex is better
            pattern = re.compile(rf'(<select\s+[^>]*name=[\'"]{sel}[\'"][^>]*)>', re.IGNORECASE)
            
            def replacer(match):
                tag = match.group(1)
                if 'class=' in tag:
                    if 'search-select' not in tag:
                        tag = re.sub(r'class=[\'"]([^\'"]+)[\'"]', r'class="\1 search-select"', tag)
                else:
                    tag += ' class="search-select"'
                return tag + '>'
                
            content = pattern.sub(replacer, content)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Successfully updated {filepath}")
    except FileNotFoundError:
        print(f"File not found: {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")
