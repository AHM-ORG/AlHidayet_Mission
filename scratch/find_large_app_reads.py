import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                # Find all view_file of app.py
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    if tc.get('name') == 'view_file':
                        args = tc.get('args', {})
                        path = args.get('AbsolutePath', '').strip('"')
                        if 'app.py' in path:
                            print(f"Step {idx}: view_file of app.py, lines {args.get('StartLine')} to {args.get('EndLine')}")
            except Exception:
                pass
