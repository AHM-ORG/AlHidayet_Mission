import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if '/admin/marksheet' in line:
                try:
                    data = json.loads(line)
                    # If it's a RUN_COMMAND tool call, print the command
                    tool_calls = data.get('tool_calls', [])
                    for tc in tool_calls:
                        if tc.get('name') == 'run_command':
                            args = tc.get('args', {})
                            cmd = args.get('CommandLine', '').strip('"')
                            print(f"Step {idx}: RUN_COMMAND -> {cmd}")
                except Exception:
                    pass
