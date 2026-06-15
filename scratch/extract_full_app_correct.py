import json
import os
import glob

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
transcripts = glob.glob(os.path.join(brain_dir, "**", "transcript.jsonl"), recursive=True)

print("Scanning all transcripts for large app.py occurrences...")

for path in transcripts:
    folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))
    print(f"Scanning transcript: {path}")
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            # Quick check to avoid slow json parsing
            if 'app.py' in line:
                try:
                    data = json.loads(line)
                    
                    # Check in tool_calls
                    tool_calls = data.get('tool_calls', [])
                    for tc in tool_calls:
                        name = tc.get('name')
                        args = tc.get('args') or tc.get('arguments') or {}
                        # Check TargetFile
                        target = args.get('TargetFile') or args.get('AbsolutePath') or ''
                        if isinstance(target, str) and 'app.py' in target:
                            content = args.get('CodeContent') or args.get('ReplacementContent') or args.get('value')
                            if isinstance(content, str) and content.startswith('"') and content.endswith('"'):
                                try:
                                    content = json.loads(content)
                                except Exception:
                                    pass
                            if content and len(content) > 50000:
                                print(f"  [FOUND WRITE] {name} in {folder} (step {idx}), size: {len(content)}")
                                out_name = f"d:\\AHM\\AHM-Web\\restored_app_{folder}_{idx}.py"
                                with open(out_name, 'w', encoding='utf-8') as out_f:
                                    out_f.write(content)
                                print(f"    Wrote to {out_name}!")
                                
                    # Check in content
                    content = data.get('content', '')
                    if content and ('Total Lines:' in content or 'import Flask' in content) and 'app.py' in content and len(content) > 50000:
                        print(f"  [FOUND VIEW] in {folder} (step {idx}), size: {len(content)}")
                        out_name = f"d:\\AHM\\AHM-Web\\viewed_app_{folder}_{idx}.txt"
                        with open(out_name, 'w', encoding='utf-8') as out_f:
                            out_f.write(content)
                        print(f"    Wrote to {out_name}!")
                except Exception as e:
                    pass
print("Scan complete.")
