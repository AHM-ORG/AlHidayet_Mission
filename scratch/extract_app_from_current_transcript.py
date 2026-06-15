import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
print("Scanning current transcript for def marksheet():")

with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            
            # Search content
            content = data.get('content', '')
            if 'def marksheet():' in content:
                print(f"Match in step {idx} content! Length: {len(content)}")
                
            # Search tool calls
            tool_calls = data.get('tool_calls', [])
            for tc in tool_calls:
                args = tc.get('arguments', {})
                if args:
                    for k, v in args.items():
                        if isinstance(v, str) and 'def marksheet():' in v:
                            print(f"Match in tool call step {idx} arg! Key: {k}, Length: {len(v)}")
                            
            # Search output
            output = data.get('output', '')
            if isinstance(output, str) and 'def marksheet():' in output:
                print(f"Match in step {idx} output! Length: {len(output)}")
                
        except Exception as e:
            pass

print("Scan complete.")
