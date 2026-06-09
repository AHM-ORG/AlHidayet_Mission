import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

steps = [725, 869, 915]

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx in steps:
                try:
                    data = json.loads(line)
                    content = data.get('content', '')
                    print(f"\n=================== STEP {idx} ===================")
                    print(content)
                except Exception as e:
                    print(f"Error at step {idx}: {e}")
