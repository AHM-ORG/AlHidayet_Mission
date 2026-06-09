import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

print("=== CHECKING JINJA SYNTAX ===")
try:
    # Set up jinja environment pointing to templates directory
    env = Environment(loader=FileSystemLoader('templates'))
    env.get_template('admin/marksheet.html')
    print("No Jinja template syntax errors found in templates/admin/marksheet.html!")
except TemplateSyntaxError as e:
    print(f"Jinja Syntax Error found in {e.filename}!")
    print(f"Line Number: {e.lineno}")
    print(f"Error Message: {e.message}")
except Exception as e:
    print(f"Error loading template: {e}")
