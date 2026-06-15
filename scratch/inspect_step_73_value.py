import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 73:
                data = json.loads(line)
                args = data.get('tool_calls', [{}])[0].get('args', {})
                # args keys are strings that might be wrapped in quotes
                target = args.get('TargetContent', '')
                value = args.get('value', '')
                print("TargetContent:")
                print(repr(target)[:300])
                print("Value:")
                print(repr(value)[:300])
                break
