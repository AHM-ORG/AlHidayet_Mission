import shutil
import os

src_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc"
dest_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\0661f064-1ede-48f6-afea-a9629608d121"

for filename in ["task.md", "implementation_plan.md", "walkthrough.md"]:
    src_file = os.path.join(src_dir, filename)
    dest_file = os.path.join(dest_dir, filename)
    if os.path.exists(src_file):
        shutil.copy(src_file, dest_file)
        print(f"Copied {filename} to {dest_file}")
    else:
        print(f"{filename} not found in source")
