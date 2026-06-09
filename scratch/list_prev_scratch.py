import os

prev_scratch = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\scratch"
print("Files in previous scratch directory:")

if os.path.exists(prev_scratch):
    files = os.listdir(prev_scratch)
    for f in sorted(files):
        path = os.path.join(prev_scratch, f)
        if os.path.isfile(path):
            print(f"  {f} ({os.path.getsize(path)} bytes)")
else:
    print("Previous scratch directory does not exist.")
