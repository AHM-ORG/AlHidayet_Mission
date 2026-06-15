import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 620:
                # Find the next line (Step 621)
                next_line = f.readline()
                try:
                    data = json.loads(next_line)
                    print(f"Step {idx+1} type={data.get('type')}, status={data.get('status')}")
                    print(data.get('content', ''))
                except Exception as e:
                    print(f"Error parsing step 621: {e}")
                break
