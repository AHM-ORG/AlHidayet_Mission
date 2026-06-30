import ast

def extract_functions(source, func_names):
    try:
        tree = ast.parse(source)
    except Exception as e:
        return f"Parse error: {e}"
    
    extracted = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in func_names:
            start = node.lineno
            if node.decorator_list:
                start = node.decorator_list[0].lineno
            end = node.end_lineno
            lines = source.split('\n')[start-1:end]
            extracted.append('\n'.join(lines))
    return '\n\n'.join(extracted) if extracted else "Functions not found"

if __name__ == "__main__":
    with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
        source = f.read()
    
    # We need to find the function decorated with @app.before_request
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.value.id == 'app' and decorator.attr == 'before_request':
                    funcs.append(node.name)
    
    print("Before request functions:", funcs)
    out = extract_functions(source, funcs)
    with open('extracted_before.txt', 'w', encoding='utf-8') as f:
        f.write(out)
