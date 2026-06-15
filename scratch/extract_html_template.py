import os
import json
import re

def extract_html():
    log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\0661f064-1ede-48f6-afea-a9629608d121\.system_generated\logs\transcript.jsonl"
    if not os.path.exists(log_path):
        print(f"File not found: {log_path}")
        return
        
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get('step_index') == 1346:
                    content = data.get('content', '')
                    idx = content.find("<!DOCTYPE html>")
                    if idx != -1:
                        end_idx = content.find("</html>", idx)
                        if end_idx != -1:
                            html_content = content[idx:end_idx+7]
                            out_path = r"d:\AHM\AHM-Web\scratch\original_template.html"
                            with open(out_path, 'w', encoding='utf-8') as out_f:
                                out_f.write(html_content)
                            print(f"Successfully wrote HTML template to {out_path}")
                            return
                    print("Could not find HTML template in content.")
                    break
            except Exception as e:
                pass

if __name__ == '__main__':
    extract_html()
