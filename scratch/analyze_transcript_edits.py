import os
import json

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
print(f"Analyzing transcript: {transcript_path} ...")

if not os.path.exists(transcript_path):
    print("Transcript not found.")
    exit(1)

with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            tool_calls = data.get('tool_calls', [])
            if tool_calls:
                for tc_idx, tc in enumerate(tool_calls):
                    name = tc.get('name')
                    if name in ['replace_file_content', 'multi_replace_file_content', 'write_to_file']:
                        args = tc.get('args', {})
                        tf = args.get('TargetFile', '')
                        if 'app.py' in str(tf):
                            # Print summary
                            print(f"Step {idx} tc {tc_idx}: name={name}")
                            if name == 'replace_file_content':
                                target = args.get('TargetContent', '')
                                replacement = args.get('ReplacementContent', '') or args.get('value', '')
                                print(f"  Target size: {len(str(target))}, Replacement size: {len(str(replacement))}")
                                # Print first/last 40 chars of replacement
                                print(f"  Start: {repr(str(replacement)[:60])}")
                                print(f"  End: {repr(str(replacement)[-60:])}")
                            elif name == 'multi_replace_file_content':
                                chunks = args.get('ReplacementChunks', [])
                                if isinstance(chunks, str):
                                    try:
                                        chunks = json.loads(chunks)
                                    except Exception:
                                        pass
                                print(f"  Chunks count: {len(chunks)}")
                                for c_idx, chunk in enumerate(chunks):
                                    t = chunk.get('TargetContent', '')
                                    r = chunk.get('ReplacementContent', '')
                                    print(f"    Chunk {c_idx}: target_len={len(str(t))}, rep_len={len(str(r))}")
                                    print(f"      Start: {repr(str(r)[:50])}")
                            elif name == 'write_to_file':
                                code = args.get('CodeContent', '')
                                print(f"  CodeContent size: {len(str(code))}")
        except Exception as e:
            pass
