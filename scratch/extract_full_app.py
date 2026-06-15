import json
import os
import glob

brain_dir = r"C:\Users\mdasw\.gemini\antigravity-ide\brain"
transcripts = glob.glob(os.path.join(brain_dir, "**", "transcript.jsonl"), recursive=True)

print("Scanning all transcripts for app.py occurrences...")

for path in transcripts:
    folder = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            if 'app.py' in line:
                try:
                    data = json.loads(line)
                    # Check in tool_calls
                    tool_calls = data.get('tool_calls', [])
                    for tc in tool_calls:
                        args = tc.get('arguments', {})
                        if args and 'TargetFile' in args and 'app.py' in args['TargetFile']:
                            content = args.get('CodeContent') or args.get('ReplacementContent')
                            if content and len(content) > 100000:
                                print(f"\n[FOUND WRITE] {tc.get('name')} in {folder} (step {idx}), size: {len(content)}")
                                with open('restored_app.py', 'w', encoding='utf-8') as out_f:
                                    out_f.write(content)
                                print("  Wrote to restored_app.py!")
                                
                    # Check in content
                    content = data.get('content', '')
                    if 'Total Lines:' in content and 'app.py' in content and len(content) > 100000:
                        print(f"\n[FOUND VIEW] in {folder} (step {idx}), size: {len(content)}")
                        # Let's save it
                        with open(f'viewed_app_{folder}_{idx}.txt', 'w', encoding='utf-8') as out_f:
                            out_f.write(content)
                        print(f"  Wrote to viewed_app_{folder}_{idx}.txt!")
                except Exception as e:
                    pass
