with open('schema.json', 'r', encoding='utf-16le') as f:
    content = f.read()

with open('schema_utf8.json', 'w', encoding='utf-8') as f:
    f.write(content)

print("Schema converted to UTF-8 successfully.")
