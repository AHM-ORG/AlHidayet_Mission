import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

print("=== CHECKING ALL TEMPLATE SYNTAX ===")
env = Environment(loader=FileSystemLoader('templates'))

templates_to_check = [
    'admin/marksheet.html',
    'admin/academics_setting.html',
    'index.html'
]

has_error = False
for t in templates_to_check:
    try:
        env.get_template(t)
        print(f"Passed: {t}")
    except TemplateSyntaxError as e:
        print(f"FAIL: Jinja Syntax Error found in {t}!")
        print(f"Line Number: {e.lineno}")
        print(f"Error Message: {e.message}")
        has_error = True
    except Exception as e:
        print(f"FAIL: Error loading template {t}: {e}")
        has_error = True

if has_error:
    sys.exit(1)
else:
    print("All template syntax checks passed successfully!")
