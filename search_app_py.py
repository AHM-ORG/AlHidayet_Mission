import sys

def search_app(query):
    print(f"Searching for '{query}' in app.py...")
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    matches = 0
    for idx, line in enumerate(lines):
        if query.lower() in line.lower():
            print(f"Line {idx+1}: {line.strip()}")
            matches += 1
            if matches >= 50:
                print("... truncated after 50 matches ...")
                break
    print(f"Done. Found {matches} matches.")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        search_app(sys.argv[1])
    else:
        print("Usage: python search_app_py.py <query>")
