import json
import os
import re

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
print("Scanning brain directory:", brain_dir)

if not os.path.exists(brain_dir):
    print("Brain directory does not exist.")
    exit(1)

folders = os.listdir(brain_dir)
print("Found subdirectories:", folders)

found = False
for folder in folders:
    folder_path = os.path.join(brain_dir, folder)
    if not os.path.isdir(folder_path):
        continue
        
    transcript_path = os.path.join(folder_path, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(transcript_path):
        # Try double dot backup path
        transcript_path = os.path.join(folder_path, "..system_generated", "logs", "transcript.jsonl")
        
    if not os.path.exists(transcript_path):
        continue
        
    size = os.path.getsize(transcript_path)
    print(f"\nScanning: {transcript_path} ({size} bytes)")
    
    try:
        with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  Failed to read: {e}")
        continue
        
    if 'admin_attendance' in content:
        print(f"  [MATCH] Found 'admin_attendance' inside {folder}!")
        
        # Read line by line
        with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
            for idx, line in enumerate(f):
                if 'admin_attendance' in line:
                    try:
                        data = json.loads(line)
                        tc_content = data.get('content', '')
                        if 'def admin_attendance():' in tc_content:
                            print(f"    Line {idx} matches source! Length: {len(tc_content)}")
                            out_name = f"extracted_content_{folder}_{idx}.txt"
                            with open(out_name, 'w', encoding='utf-8') as out_f:
                                out_f.write(tc_content)
                            print(f"    Saved matching source block to {out_name}")
                            found = True
                    except Exception as err:
                        print(f"    Error reading line {idx}: {err}")

if not found:
    print("\nScan complete. No matches found.")
