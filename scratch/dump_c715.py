import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            source = data.get('source', '')
            step_type = data.get('type', '')
            content = data.get('content', '')
            
            if step_type == 'USER_INPUT' or source == 'USER_EXPLICIT':
                print(f"\n--- STEP {idx} (USER_INPUT) ---")
                print(content)
            elif step_type == 'PLANNER_RESPONSE' or source == 'MODEL':
                print(f"\n--- STEP {idx} (MODEL) ---")
                lines = (content or '').split('\n')
                if len(lines) > 15:
                    print('\n'.join(lines[:10]))
                    print("... [TRUNCATED] ...")
                    print('\n'.join(lines[-5:]))
                else:
                    print(content)
        except Exception as e:
            print(f"Error parsing line {idx}: {e}")
