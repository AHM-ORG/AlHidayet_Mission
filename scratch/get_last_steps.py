import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
    print(f"Total lines: {len(lines)}")
    # Print the last 40 lines of the transcript
    start = max(0, len(lines) - 40)
    for idx in range(start, len(lines)):
        try:
            data = json.loads(lines[idx])
            source = data.get('source', '')
            step_type = data.get('type', '')
            content = data.get('content', '')
            print(f"\n=================== STEP {idx} (type: {step_type}, source: {source}) ===================")
            print(content[:2000]) # Limit to 2000 chars per step to not truncate tool output
        except Exception as e:
            print(f"Error parsing line {idx}: {e}")
