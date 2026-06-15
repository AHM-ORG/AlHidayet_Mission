import json
import os
from collections import Counter

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
targets = Counter()

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    if name in ['replace_file_content', 'write_to_file']:
                        args = tc.get('arguments', {})
                        target = args.get('TargetFile') or args.get('AbsolutePath') or args.get('path')
                        if target:
                            targets[f"{name} -> {os.path.basename(target)}"] += 1
            except Exception:
                pass
                
print("Target files modified/created in c715:")
for k, v in targets.items():
    print(f"  {k}: {v}")
