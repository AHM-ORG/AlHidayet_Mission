import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

def decode_safely(val):
    if val.startswith('"') and val.endswith('"') or val.startswith("'") and val.endswith("'"):
        try:
            return eval(val)
        except Exception:
            return val[1:-1].encode('utf-8').decode('unicode_escape', errors='ignore')
    return val

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if idx == 934:
                data = json.loads(line)
                args = data.get('tool_calls', [{}])[0].get('args', {})
                target = decode_safely(args.get('TargetContent', ''))
                replacement = decode_safely(args.get('value') or args.get('ReplacementContent', ''))
                print("Step 934 TargetContent:")
                print(repr(target))
                print("\nStep 934 ReplacementContent:")
                print(replacement)
                break
