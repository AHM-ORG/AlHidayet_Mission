import os
import json

def find_script():
    log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\0661f064-1ede-48f6-afea-a9629608d121\.system_generated\logs\transcript.jsonl"
    if not os.path.exists(log_path):
        print(f"File not found: {log_path}")
        return
        
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get('step_index') == 1346:
                    print("Found step 1346!")
                    content = data.get('content', '')
                    # Write to a file
                    out_path = r"d:\AHM\AHM-Web\scratch\original_user_script.py"
                    with open(out_path, 'w', encoding='utf-8') as out_f:
                        out_f.write(content)
                    print(f"Successfully wrote code to {out_path}")
                    break
            except Exception as e:
                pass

if __name__ == '__main__':
    find_script()
