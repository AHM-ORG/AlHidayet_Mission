import json
import os
from collections import Counter

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
counter = Counter()

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    counter[name] += 1
            except Exception:
                pass
                
print("Tool call counts in c715efb6-f438-4779-bf9b-2d391b3cadbc:")
for k, v in counter.items():
    print(f"  {k}: {v}")
