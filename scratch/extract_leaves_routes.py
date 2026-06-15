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
            if 'def student_attendance_leaves' in line or 'def teacher_attendance_leaves' in line:
                try:
                    data = json.loads(line)
                    print(f"Step {idx}: type={data.get('type')}, source={data.get('source')}")
                    
                    # Search in tool_calls
                    tool_calls = data.get('tool_calls', [])
                    for tc_idx, tc in enumerate(tool_calls):
                        args = tc.get('args', {})
                        rc = args.get('ReplacementContent') or args.get('value')
                        if rc:
                            rc_decoded = decode_safely(rc)
                            print(f"  Tool {tc.get('name')} (tc_idx {tc_idx}) ReplacementContent length: {len(rc_decoded)}")
                            # Save it to a file
                            out_name = f"d:\\AHM\\AHM-Web\\scratch\\recovered_code_{idx}_{tc_idx}.txt"
                            with open(out_name, 'w', encoding='utf-8') as out_f:
                                out_f.write(rc_decoded)
                            print(f"    Wrote recovered code to {out_name}!")
                except Exception as e:
                    print(f"  Error at step {idx}: {e}")
