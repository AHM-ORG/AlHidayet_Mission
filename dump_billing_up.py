with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
start = max(0, 14500)
end = min(len(lines), 14536)

with open('dump_billing_func_up.txt', 'w', encoding='utf-8') as f:
    f.writelines(lines[start:end])
print("Dumped lines 14500 to 14536")
