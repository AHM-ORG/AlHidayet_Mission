import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                # Find first view_file tool call on app.py
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    if tc.get('name') == 'view_file':
                        args = tc.get('args', {})
                        path = args.get('AbsolutePath', '').strip('"')
                        if 'app.py' in path:
                            print(f"First view_file of app.py is at Step {idx}:")
                            print(f"  AbsolutePath: {path}")
                            print(f"  StartLine: {args.get('StartLine')}, EndLine: {args.get('EndLine')}")
                            # Let's also print the output of this step!
                            # The output of step N is in step N+1
                            break
                if 'First view_file' in locals():
                    # Print next step content/output
                    f.seek(0)
                    for j, l in enumerate(f):
                        if j == idx + 1:
                            d2 = json.loads(l)
                            print(f"Output type: {d2.get('type')}, status: {d2.get('status')}")
                            content = d2.get('content', '')
                            print(f"Content sample: {content[:500]}")
                            break
                    break
            except Exception as e:
                pass
