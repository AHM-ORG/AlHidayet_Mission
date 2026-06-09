import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if 'def student_attendance_leaves' in line or 'def teacher_attendance_leaves' in line:
                try:
                    data = json.loads(line)
                    print(f"Step {idx}: type={data.get('type')}, source={data.get('source')}")
                    # Let's search inside the keys of the JSON object
                    content = data.get('content', '')
                    if content:
                        print(f"  content: {content[:300]}")
                    tool_calls = data.get('tool_calls', [])
                    for tc in tool_calls:
                        print(f"  tool call: {tc.get('name')}")
                        args = tc.get('args', {})
                        for k, v in args.items():
                            if 'student_attendance_leaves' in str(v):
                                print(f"    arg {k} (len {len(str(v))}): {str(v)[:300]}")
                except Exception as e:
                    print(f"  Error: {e}")
