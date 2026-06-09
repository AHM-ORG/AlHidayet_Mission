with open("app_reconstructed_a712.py", "r", encoding="utf-8") as f:
    content = f.read()

target = "classes = "
idx = 0
while True:
    idx = content.find(target, idx)
    if idx == -1:
        break
    print(f"Found 'classes = ' at index {idx}:")
    print(repr(content[idx:idx+150]))
    idx += len(target)
