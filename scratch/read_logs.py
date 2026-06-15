import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\952f7da3-fe2f-4157-9443-ac7f656a9fba\.system_generated\logs\transcript.jsonl"
steps = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            step_idx = data.get('step_index')
            if step_idx is not None and step_idx >= 520:
                steps.append(data)
        except Exception as e:
            pass

print("--- Step Details ---")
for step in steps:
    stype = step.get('type')
    src = step.get('source')
    idx = step.get('step_index')
    content = step.get('content', '')
    if len(content) > 200:
        content = content[:200] + "..."
    # Print tool calls if any
    tool_calls = step.get('tool_calls', [])
    tcall_str = ""
    if tool_calls:
        tcall_str = f" | Tools: {[t.get('name') for t in tool_calls]}"
    print(f"[{idx}] {src} ({stype}): {content}{tcall_str}")
