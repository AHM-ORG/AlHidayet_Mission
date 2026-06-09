import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
edits = []

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    if name in ['replace_file_content', 'multi_replace_file_content']:
                        args = tc.get('arguments', {})
                        if args and 'TargetFile' in args and 'app.py' in args['TargetFile']:
                            edits.append({
                                'step': idx,
                                'name': name,
                                'arguments': args
                            })
            except Exception:
                pass
                
print(f"Found {len(edits)} edits targeting app.py in c715efb6-f438-4779-bf9b-2d391b3cadbc.")
for e in edits:
    print(f"  Step {e['step']} ({e['name']}) - Instruction: {e['arguments'].get('Instruction', '')[:100]}")
