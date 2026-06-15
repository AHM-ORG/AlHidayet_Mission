import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 1044:
                # Step 1044 is the VIEW_FILE tool call. Let's get the next line (Step 1045) which is the tool call output!
                # Wait, let's look at the next line
                next_line = f.readline()
                try:
                    data = json.loads(next_line)
                    content = data.get('content', '')
                    print(f"Step {idx+1} type: {data.get('type')}, status: {data.get('status')}")
                    print(f"Content length: {len(content)}")
                    
                    # Remove line numbers prefix if they exist (e.g. "1: import os", "2: ...")
                    lines = content.splitlines()
                    clean_lines = []
                    for l in lines:
                        # Pattern matching line number prefix like "123: foo"
                        # But wait, did view_file return it with prefix?
                        # Yes, the tool output prefix is "1: <original_line>".
                        # Let's strip the number and colon
                        if ':' in l:
                            parts = l.split(':', 1)
                            num_str = parts[0].strip()
                            if num_str.isdigit():
                                clean_lines.append(parts[1][1:]) # skip the leading space after colon
                            else:
                                clean_lines.append(l)
                        else:
                            clean_lines.append(l)
                            
                    clean_content = '\n'.join(clean_lines)
                    print(f"Clean content length: {len(clean_content)}")
                    
                    out_path = "d:\\AHM\\AHM-Web\\app.py"
                    with open(out_path, 'w', encoding='utf-8') as out_f:
                        out_f.write(clean_content)
                    print("Successfully wrote full clean app.py to workspace!")
                except Exception as e:
                    print(f"Error parsing next line: {e}")
                break
