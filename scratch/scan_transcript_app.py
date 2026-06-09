import json
import os

path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\a712927e-564c-4af2-9247-098a4b5e1dad\.system_generated\logs\transcript.jsonl"

if not os.path.exists(path):
    print("Transcript not found.")
    exit(1)

print("Scanning transcript:", path)

with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        if 'app.py' in line:
            try:
                data = json.loads(line)
                
                # Check tool calls
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    args = tc.get('arguments', {})
                    if args and 'TargetFile' in args and 'app.py' in args['TargetFile']:
                        print(f"\nStep {idx} - Tool: {tc.get('name')}")
                        if 'TargetContent' in args:
                            print(f"  TargetContent:\n{args['TargetContent'][:300]}")
                        if 'ReplacementContent' in args:
                            print(f"  ReplacementContent:\n{args['ReplacementContent'][:300]}")
                        if 'CodeContent' in args:
                            print(f"  CodeContent:\n{args['CodeContent'][:300]}")
                            
                # Check content for view_file outputs
                content = data.get('content', '')
                if 'app.py' in content and 'def ' in content:
                    print(f"\nStep {idx} - View response (length: {len(content)})")
                    print(content[:500])
                    
            except Exception as e:
                pass
