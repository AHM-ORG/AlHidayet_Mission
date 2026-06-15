import json
import os
import re

transcript_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\a712927e-564c-4af2-9247-098a4b5e1dad\.system_generated\logs\transcript.jsonl"
base_file = "app_recovered_text_46f71de6.py"

if not os.path.exists(transcript_path):
    print("Transcript not found.")
    exit(1)
if not os.path.exists(base_file):
    print("Base file not found.")
    exit(1)

# Read base file content
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
                    args = tc.get('arguments', {})
                    if args and 'TargetFile' in args and 'app.py' in args['TargetFile']:
                        edits.append({
                            'step': idx,
                            'name': name,
                            'arguments': args
                        })
        except Exception:
            pass

print(f"Found {len(edits)} edits targeting app.py.")

# Apply edits one by one
success_count = 0
for edit in edits:
    step = edit['step']
    name = edit['name']
    args = edit['arguments']
    
    print(f"\nApplying edit from Step {step} ({name})...")
    
    if name == 'replace_file_content':
        target = args.get('TargetContent')
        replacement = args.get('ReplacementContent')
        if not target or not replacement:
            print("  [ERROR] Missing target or replacement content.")
            continue
            
        if target in current_content:
            current_content = current_content.replace(target, replacement)
            print("  [SUCCESS] Replacement applied successfully!")
            success_count += 1
        else:
            print("  [WARNING] TargetContent not found in current content.")
            # Let's inspect why: might be whitespace issues, let's normalize carriage returns
            target_norm = target.replace('\r\n', '\n')
            current_norm = current_content.replace('\r\n', '\n')
            if target_norm in current_norm:
                current_norm = current_norm.replace(target_norm, replacement.replace('\r\n', '\n'))
                current_content = current_norm
                print("  [SUCCESS] Replacement applied successfully after CRLF normalization!")
                success_count += 1
            else:
                print("  [ERROR] Could not match target content even after normalization.")
                
    elif name == 'multi_replace_file_content':
        chunks = args.get('ReplacementChunks', [])
        print(f"  Multi-replace has {len(chunks)} chunks.")
        chunk_success = 0
        for chunk_idx, chunk in enumerate(chunks):
            target = chunk.get('TargetContent')
            replacement = chunk.get('ReplacementContent')
            if target in current_content:
                current_content = current_content.replace(target, replacement)
                chunk_success += 1
            else:
                target_norm = target.replace('\r\n', '\n')
                current_norm = current_content.replace('\r\n', '\n')
                if target_norm in current_norm:
                    current_norm = current_norm.replace(target_norm, replacement.replace('\r\n', '\n'))
                    current_content = current_norm
                    chunk_success += 1
        print(f"  [SUCCESS] Applied {chunk_success} of {len(chunks)} chunks.")
        if chunk_success == len(chunks):
            success_count += 1

print(f"\nReconstruction complete. Applied {success_count} of {len(edits)} edits successfully.")

# Write the final reconstructed file
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(current_content)
print("Saved final result to app.py!")
