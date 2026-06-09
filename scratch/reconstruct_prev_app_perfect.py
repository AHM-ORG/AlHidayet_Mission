import json
import os

base_file = "app_recovered_text_46f71de6.py"
a712_log = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\a712927e-564c-4af2-9247-098a4b5e1dad\.system_generated\logs\transcript.jsonl"
c715_log = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"

def decode_val(val):
    if val is None:
        return ''
    if isinstance(val, str):
        while (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            try:
                val = json.loads(val)
            except Exception:
                val = val[1:-1]
        try:
            val = val.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
        # Final unescape helper
        val = val.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace('\\"', '"').replace("\\'", "'")
    return val

# Load base file
if not os.path.exists(base_file):
    print(f"Base file {base_file} not found.")
    exit(1)

with open(base_file, 'r', encoding='utf-8') as f:
    current_content = f.read().replace('\r\n', '\n')

print(f"Loaded base file. Length: {len(current_content)} chars.")

def apply_edits_from_transcript(transcript_path, current_content, label):
    if not os.path.exists(transcript_path):
        print(f"Transcript {transcript_path} not found.")
        return current_content
        
    edits = []
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                tool_calls = data.get('tool_calls', [])
                for tc in tool_calls:
                    name = tc.get('name')
                    if name in ['replace_file_content', 'multi_replace_file_content']:
                        args = tc.get('args', {})
                        if args:
                            target_file = args.get('TargetFile', '')
                            if isinstance(target_file, str):
                                if target_file.startswith('"') and target_file.endswith('"'):
                                    target_file = json.loads(target_file)
                                else:
                                    target_file = target_file.strip('"')
                                if 'app.py' in target_file:
                                    edits.append({
                                        'step': idx,
                                        'name': name,
                                        'args': args
                                    })
            except Exception:
                pass
                
    print(f"\nFound {len(edits)} edits in {label} transcript.")
    
    success_count = 0
    for edit in edits:
        step = edit['step']
        name = edit['name']
        args = edit['args']
        
        if name == 'replace_file_content':
            target = decode_val(args.get('TargetContent'))
            replacement = decode_val(args.get('value') or args.get('ReplacementContent'))
            
            if not target:
                continue
                
            target_norm = target.replace('\r\n', '\n')
            replacement_norm = replacement.replace('\r\n', '\n')
            content_norm = current_content.replace('\r\n', '\n')
            
            if target_norm in content_norm:
                current_content = content_norm.replace(target_norm, replacement_norm)
                print(f"  Step {step}: [SUCCESS] replace_file_content")
                success_count += 1
            else:
                print(f"  Step {step}: [FAILED] replace_file_content. Target sample: {repr(target_norm[:80])}")
                
        elif name == 'multi_replace_file_content':
            chunks_raw = args.get('ReplacementChunks', '[]')
            chunks = []
            if isinstance(chunks_raw, str):
                try:
                    chunks = json.loads(chunks_raw)
                except Exception:
                    pass
            else:
                chunks = chunks_raw
                
            chunk_success = 0
            for chunk_idx, chunk in enumerate(chunks):
                target = decode_val(chunk.get('TargetContent'))
                replacement = decode_val(chunk.get('ReplacementContent'))
                
                target_norm = target.replace('\r\n', '\n')
                replacement_norm = replacement.replace('\r\n', '\n')
                content_norm = current_content.replace('\r\n', '\n')
                
                if target_norm in content_norm:
                    content_norm = content_norm.replace(target_norm, replacement_norm)
                    current_content = content_norm
                    chunk_success += 1
                else:
                    print(f"    [CHUNK FAILED] Chunk {chunk_idx}. Target sample: {repr(target_norm[:80])}")
                    
            print(f"  Step {step}: [SUCCESS] multi_replace_file_content (applied {chunk_success} of {len(chunks)} chunks)")
            if chunk_success == len(chunks):
                success_count += 1
                
    print(f"Finished {label}. Successfully applied {success_count} of {len(edits)} edits.")
    return current_content

# 1. Apply a712 edits
current_content = apply_edits_from_transcript(a712_log, current_content, "a712")

# 2. Apply c715 edits
current_content = apply_edits_from_transcript(c715_log, current_content, "c715")

# Save final content
with open("app.py", "w", encoding="utf-8") as f:
    f.write(current_content)
print("\nReconstructed app.py saved successfully!")
