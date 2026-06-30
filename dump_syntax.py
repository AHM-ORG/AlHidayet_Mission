import traceback
try:
    with open('app.py', 'r', encoding='utf-8') as f:
        source = f.read()
    compile(source, 'app.py', 'exec')
    with open('dump_syntax.txt', 'w') as f:
        f.write('NO SYNTAX ERROR')
except Exception as e:
    with open('dump_syntax.txt', 'w') as f:
        f.write(traceback.format_exc())
