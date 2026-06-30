import ast

def extract_function(source, func_name):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return f"Syntax error in parsing."
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            # We can get line numbers
            start = node.lineno
            end = node.end_lineno
            lines = source.split('\n')[start-1:end]
            return '\n'.join(lines)
    return f"Function '{func_name}' not found."

if __name__ == "__main__":
    with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
        source = f.read()
    
    print("----- def reset_student_fee -----")
    print(extract_function(source, 'reset_student_fee'))
    
    print("\n----- def audit_report -----")
    print(extract_function(source, 'audit_report'))
