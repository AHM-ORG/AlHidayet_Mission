import os
import zlib

def search_blobs():
    git_objects_dir = r"d:\AHM\AHM-Web\.git\objects"
    print(f"Scanning Git objects directory: {git_objects_dir} ...")
    
    found_count = 0
    for root, dirs, files in os.walk(git_objects_dir):
        for file in files:
            if len(file) == 38:
                subdir = os.path.basename(root)
                sha = subdir + file
                path = os.path.join(root, file)
                try:
                    with open(path, "rb") as f:
                        compressed_data = f.read()
                    data = zlib.decompress(compressed_data)
                    header_end = data.find(b"\x00")
                    if header_end != -1:
                        header = data[:header_end].decode("utf-8", errors="ignore")
                        content = data[header_end + 1:]
                        obj_type, obj_size = header.split(" ")
                        
                        if obj_type == "blob":
                            # Check if size is large and contains our routes
                            if int(obj_size) > 200000:
                                content_str = content.decode("utf-8", errors="ignore")
                                if "def admin_attendance():" in content_str and "def student_attendance_leaves():" in content_str:
                                    out_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\scratch\app_recovered_full.py"
                                    with open(out_path, "w", encoding="utf-8") as out:
                                        out.write(content_str)
                                    print(f"\n==========================================")
                                    print(f"FOUND FULL APP BLOB! SHA: {sha}, Size: {obj_size}")
                                    print(f"Saved to: {out_path}")
                                    print(f"==========================================\n")
                                    found_count += 1
                except Exception:
                    pass
                    
    print(f"Search complete. Found {found_count} candidate full app blobs.")

if __name__ == '__main__':
    search_blobs()
