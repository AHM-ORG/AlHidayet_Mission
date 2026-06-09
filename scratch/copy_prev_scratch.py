import shutil
import os

src_scratch = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\scratch"
dest_scratch = r"d:\AHM\AHM-Web\scratch"

if os.path.exists(src_scratch):
    for filename in os.listdir(src_scratch):
        src_file = os.path.join(src_scratch, filename)
        dest_file = os.path.join(dest_scratch, filename)
        if os.path.isfile(src_file):
            shutil.copy(src_file, dest_file)
            print(f"Copied {filename}")
else:
    print("Source scratch directory does not exist")
