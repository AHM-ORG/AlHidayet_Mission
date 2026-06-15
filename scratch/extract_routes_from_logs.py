import os
import json

base_dir = r"C:\Users\mdasw\.gemini"
print(f"Scanning all transcript logs in: {base_dir} ...")

match_idx = 1
for root, dirs, files in os.walk(base_dir):
    for file in files:
        if file == 'transcript.jsonl':
            lf = os.path.join(root, file)
            try:
                with open(lf, 'r', encoding='utf-8', errors='ignore') as f:
                    for idx, line in enumerate(f):
                        if "def admin_attendance" in line or "def student_attendance_leaves" in line:
                            try:
                                data = json.loads(line)
                                # Check tool calls
                                tool_calls = data.get("tool_calls", [])
                                for tc in tool_calls:
                                    args = tc.get("args", {})
                                    rep_content = args.get("ReplacementContent", "") or args.get("CodeContent", "")
                                    if rep_content and "def admin_attendance" in rep_content:
                                        out_path = f"C:\\Users\\mdasw\\.gemini\\antigravity-ide\\brain\\c715efb6-f438-4779-bf9b-2d391b3cadbc\\scratch\\recovered_routes_{match_idx}.py"
                                        with open(out_path, "w", encoding="utf-8") as out:
                                            out.write(rep_content)
                                        print(f" [+] Found non-truncated code in tool call args of {lf} at line {idx+1}. Saved to {out_path}")
                                        match_idx += 1
                                        
                                # Check step content
                                content = data.get("content", "")
                                if "def admin_attendance" in content and len(content) > 2000 and "truncated" not in content:
                                    out_path = f"C:\\Users\\mdasw\\.gemini\\antigravity-ide\\brain\\c715efb6-f438-4779-bf9b-2d391b3cadbc\\scratch\\recovered_routes_text_{match_idx}.py"
                                    with open(out_path, "w", encoding="utf-8") as out:
                                        out.write(content)
                                    print(f" [+] Found non-truncated code in step content of {lf} at line {idx+1}. Saved to {out_path}")
                                    match_idx += 1
                            except Exception:
                                pass
            except Exception as e:
                pass

print(f"Scanning complete. Saved {match_idx-1} files.")
