import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 1036:
                data = json.loads(line)
                args = data.get('tool_calls', [{}])[0].get('args', {})
                print(f"Step 1036 name: {data.get('tool_calls', [{}])[0].get('name')}")
                print(f"Step 1036 keys: {list(args.keys())}")
                for k, v in args.items():
                    print(f"  {k}: length {len(str(v))} - sample: {str(v)[:300]}")
                break
