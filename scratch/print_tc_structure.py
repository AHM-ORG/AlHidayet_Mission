import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                if tool_calls:
                    print(f"Step {idx} tool call name: {tool_calls[0].get('name')}")
                    print(f"Arguments keys: {list(tool_calls[0].get('arguments', {}).keys())}")
                    print(f"Arguments full: {tool_calls[0].get('arguments')}")
                    break
            except Exception as e:
                print(f"Error at step {idx}: {e}")
