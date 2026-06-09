import glob
import re

files_to_update = glob.glob('templates/**/*.html', recursive=True)

css_link = '    <link href="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/css/tom-select.css" rel="stylesheet">\n'
js_link = '    <script src="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/js/tom-select.complete.min.js"></script>\n'
init_script = '''
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            document.querySelectorAll('select').forEach((el)=>{
                if (!el.classList.contains('search-select')) {
                    el.classList.add('search-select');
                }
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
            
        modified = False
        
        # Check if it has a select tag
        if '<select' in content.lower():
            # Add CSS if not present
            if 'tom-select.css' not in content:
                content = content.replace('</head>', f'{css_link}</head>')
                modified = True
                
            # Add JS if not present
            if 'tom-select.complete.min.js' not in content:
                content = content.replace('</body>', f'{js_link}{init_script}</body>')
                modified = True
                
            if modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Successfully updated {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")
