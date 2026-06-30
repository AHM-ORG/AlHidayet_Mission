with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
start = max(0, 14557 - 20)
end = min(len(lines), 14610)

with open('dump_billing_func.txt', 'w', encoding='utf-8') as f:
    f.writelines(lines[start:end])
print("Dumped lines 14537 to 14610")
