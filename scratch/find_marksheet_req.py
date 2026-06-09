import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            source = data.get('source', '')
            step_type = data.get('type', '')
            content = data.get('content', '')
            
            if 'marksheet' in line.lower():
                print(f"Match at step {idx}: type={step_type}, source={source}")
                if step_type == 'USER_INPUT' or source == 'USER_EXPLICIT':
                    print("--- USER REQUEST ---")
                    print(content)
                    print("--------------------")
        except Exception as e:
            pass
