import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx >= 624 and idx <= 641:
                try:
                    data = json.loads(line)
                    source = data.get('source', '')
                    step_type = data.get('type', '')
                    content = data.get('content', '')
                    
                    if source == 'MODEL' or step_type == 'PLANNER_RESPONSE':
                        print(f"\n=================== STEP {idx} (type: {step_type}) ===================")
                        print(content)
                except Exception:
                    pass
