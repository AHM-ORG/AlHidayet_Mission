import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
base_file = "app_recovered_text_46f71de6.py"

with open(base_file, 'r', encoding='utf-8') as f:
    base_content = f.read()

with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        if idx == 73:
            data = json.loads(line)
            args = data.get('tool_calls', [{}])[0].get('args', {})
            target = args.get('TargetContent')
            if isinstance(target, str) and target.startswith('"') and target.endswith('"'):
                target = json.loads(target)
            
            print(f"TargetContent: {repr(target)}")
            # Let's see if we can find parts of this target content in base_content
            lines = target.splitlines()
            for i, tl in enumerate(lines[:5]):
                found = tl in base_content
                print(f"  Line {i}: {repr(tl)} -> Found: {found}")
                if not found:
                    # Try to search for a substring
                    for k in range(len(tl), 5, -5):
                        sub = tl[:k]
                        if sub in base_content:
                            print(f"    Prefix found: {repr(sub)}")
                            break
            break
