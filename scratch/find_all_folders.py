import os

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Folders in brain dir:")
for name in os.listdir(brain_dir):
    path = os.path.join(brain_dir, name)
    if os.path.isdir(path):
        print(f"  {name} (size: {os.path.getsize(path)})")
