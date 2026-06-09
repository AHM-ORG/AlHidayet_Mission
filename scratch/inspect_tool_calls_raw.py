import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
count = 0

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    args = tc.get('arguments')
                    if args:
                        print(f"Step {idx} ({name}): type of args = {type(args)}")
                        print(f"  args keys: {list(args.keys()) if isinstance(args, dict) else args}")
                        count += 1
                        if count >= 10:
                            break
                if count >= 10:
                    break
            except Exception as e:
                print(f"Error at step {idx}: {e}")
