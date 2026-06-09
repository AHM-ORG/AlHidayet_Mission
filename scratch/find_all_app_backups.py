import os
import re

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print(f"Listing all files in brain dir: {brain_dir}")

for root, dirs, files in os.walk(brain_dir):
    for file in files:
        if file.startswith("app") and file.endswith(".py"):
            path = os.path.join(root, file)
            print(f"Found app file: {path} ({os.path.getsize(path)} bytes)")
        elif "reconstruct" in file or "recover" in file:
            path = os.path.join(root, file)
            print(f"Found recover file: {path} ({os.path.getsize(path)} bytes)")
