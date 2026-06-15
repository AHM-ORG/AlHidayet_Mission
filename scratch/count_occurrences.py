with open("app_recovered_text_46f71de6.py", "r", encoding="utf-8") as f:
    content = f.read()

target = "if __name__ == '__main__':"
idx = content.find(target)
if idx != -1:
    print("Found 'if __name__' at index:", idx)
    print("Surroundings:")
    print(repr(content[idx-100:idx+150]))
else:
    print("'if __name__' not found in base file!")
