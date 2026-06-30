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
    
    out = extract_functions(source, ['calculate_student_fees_breakdown', 'sync_student_ledger_and_dues', 'get_fees'])
    with open('extracted2.txt', 'w', encoding='utf-8') as f:
        f.write(out)
    print("Extracted to extracted2.txt")
