import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
edits = []

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    if name in ['replace_file_content', 'write_to_file', 'multi_replace_file_content']:
                        args = tc.get('args', {})
                        if args:
                            target_file = args.get('TargetFile') or args.get('AbsolutePath') or ''
                            # Strip quotes from target_file if they exist
                            target_file = target_file.strip('"')
                            edits.append({
                                'step': idx,
                                'name': name,
                                'file': os.path.basename(target_file),
                                'full_path': target_file,
                                'instruction': args.get('Instruction', '').strip('"')
                            })
            except Exception as e:
                pass
                
print(f"Found {len(edits)} write/replace edits in c715efb6-f438-4779-bf9b-2d391b3cadbc:")
for e in edits:
    print(f"  Step {e['step']} ({e['name']}) -> {e['file']} - {e['instruction'][:100]}")
