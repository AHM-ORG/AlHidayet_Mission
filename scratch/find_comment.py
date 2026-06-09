with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

target = "Get distinct options"
idx = content.find(target)
if idx != -1:
    print("Found comment at index:", idx)
    print(repr(content[idx-100:idx+200]))
else:
    print("Comment NOT found in app.py!")
