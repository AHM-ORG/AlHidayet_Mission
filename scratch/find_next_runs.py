import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx >= 620 and idx <= 650:
                try:
                    data = json.loads(line)
                    source = data.get('source', '')
                    step_type = data.get('type', '')
                    content = data.get('content', '')
                    
                    if step_type == 'RUN_COMMAND' or step_type == 'COMMAND_OUTPUT' or 'extract_routes' in line:
                        print(f"\n--- STEP {idx} (type: {step_type}, source: {source}) ---")
                        print(content[:500])
                except Exception:
                    pass
