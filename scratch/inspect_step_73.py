import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 73:
                data = json.loads(line)
                print(f"Step 73 keys: {list(data.keys())}")
                print(f"Step 73 tool calls args keys: {list(data.get('tool_calls', [{}])[0].get('args', {}).keys())}")
                args = data.get('tool_calls', [{}])[0].get('args', {})
                print(f"TargetFile: {args.get('TargetFile')}")
                print(f"Instruction: {args.get('Instruction')}")
                print(f"TargetContent length: {len(args.get('TargetContent', ''))}")
                print(f"ReplacementContent length: {len(args.get('ReplacementContent', ''))}")
                break
