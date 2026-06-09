import json
import os

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\c715efb6-f438-4779-bf9b-2d391b3cadbc\.system_generated\logs\transcript.jsonl"
base_file = "app_recovered_text_46f71de6.py"

if not os.path.exists(transcript_path):
    print("Transcript not found.")
    exit(1)
if not os.path.exists(base_file):
    print("Base file not found.")
    exit(1)

with open(base_file, 'r', encoding='utf-8') as f:
    current_content = f.read()

print(f"Base file loaded. Length: {len(current_content)} chars.")

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
                            # Try to decode if it is a JSON string
                            if target_file.startswith('"') and target_file.endswith('"'):
                                try:
                                    target_file = json.loads(target_file)
                                except Exception:
                                    target_file = target_file.strip('"')
                            if 'app.py' in target_file:
                                edits.append({
                                    'step': idx,
                                    'name': name,
                                    'args': args
                                })
        except Exception as e:
            pass

print(f"Found {len(edits)} edits targeting app.py in transcript.")

def decode_val(val):
    if val is None:
        return ''
    if isinstance(val, str):
        if val.startswith('"') and val.endswith('"') or val.startswith("'") and val.endswith("'"):
            try:
                return json.loads(val)
            except Exception:
                try:
                    # Try double decode/eval safely or string strip
                    return json.loads('"' + val[1:-1] + '"')
                except Exception:
                    return val.strip('"').strip("'")
        # Handle string with literal escapes
        try:
            # If it contains escapes, try wrapping and loading as json string
            if '\\' in val:
                return json.loads('"' + val.replace('"', '\\"') + '"')
        except Exception:
            pass
    return val

success_count = 0
for edit in edits:
    step = edit['step']
    name = edit['name']
    args = edit['args']
    
    print(f"\nApplying edit from Step {step} ({name})...")
    
    if name == 'replace_file_content':
        target = decode_val(args.get('TargetContent'))
        replacement = decode_val(args.get('value') or args.get('ReplacementContent'))
        
        if not target:
            print("  [ERROR] TargetContent is empty.")
            continue
            
        # Normalize line endings
        target_norm = target.replace('\r\n', '\n')
        replacement_norm = replacement.replace('\r\n', '\n')
        content_norm = current_content.replace('\r\n', '\n')
        
        if target_norm in content_norm:
            content_norm = content_norm.replace(target_norm, replacement_norm)
            current_content = content_norm
            print("  [SUCCESS] Replacement applied successfully!")
            success_count += 1
        else:
            # Let's check if there's a minor whitespace discrepancy
            target_strip = target_norm.strip()
            # Try a fuzzy replace
            print("  [ERROR] TargetContent not found in current content.")
            print(f"  Target sample (first 100 chars): {repr(target_norm[:100])}")
            
    elif name == 'multi_replace_file_content':
        # Let's handle multi-replace chunks if they are stored in chunks key
        chunks_raw = args.get('ReplacementChunks', '[]')
        chunks = []
        if isinstance(chunks_raw, str):
            try:
                chunks = json.loads(chunks_raw)
            except Exception:
                pass
        else:
            chunks = chunks_raw
            
        print(f"  Multi-replace has {len(chunks)} chunks.")
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
                print(f"    [CHUNK ERROR] Chunk {chunk_idx} target not found.")
                
        print(f"  [SUCCESS] Applied {chunk_success} of {len(chunks)} chunks.")
        if chunk_success == len(chunks):
            success_count += 1

print(f"\nReconstruction complete. Applied {success_count} of {len(edits)} edits successfully.")

# Write the final reconstructed file
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(current_content)
print("Saved final result to app.py!")
