import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                print(f"Step {idx} keys: {list(data.keys())}")
                print(f"  type: {data.get('type')}, source: {data.get('source')}")
                if 'tool_calls' in data:
                    print(f"  tool_calls: {data['tool_calls']}")
                if idx >= 5:
                    break
            except Exception as e:
                print(f"Error at step {idx}: {e}")
