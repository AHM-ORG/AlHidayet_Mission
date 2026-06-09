import json
import re

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"

def extract():
    fragments = {}
    for i, line in enumerate(open(log_path, encoding="utf-8")):
        data = json.loads(line)
        content = data.get("content", "")
        if "dashboard.html" in line and data.get("type") == "VIEW_FILE":
            print(f"Step {i}: content length = {len(content)}")
            # Let's parse lines in content
            lines = content.splitlines()
            for l in lines:
                match = re.match(r"^\s*(\d+):\s?(.*)$", l)
                if match:
                    line_num = int(match.group(1))
                    line_content = match.group(2)
                    if line_num not in fragments:
                        fragments[line_num] = []
                    fragments[line_num].append((i, line_content))

    # Let's see what lines we have
    missing = []
    restored = {}
    for line_num in range(1, 504):
        if line_num in fragments:
            # Take the version from the earliest step or latest step? Let's print if there are multiple versions
            versions = fragments[line_num]
            # Prioritize steps before the checkout (Step 445 is checkout)
            valid_versions = [v for v in versions if v[0] < 445]
            if not valid_versions:
                valid_versions = versions
            
            # Let's take the latest valid version
            restored[line_num] = valid_versions[-1][1]
        else:
            missing.append(line_num)
            
    print(f"Total lines restored: {len(restored)}, missing: {len(missing)}")
    if missing:
        print(f"Missing lines: {missing[:50]} ...")
        
    # Write what we restored to templates/dashboard_stitched.html
    out_path = r"d:\AHM\AHM-Web\templates\dashboard_stitched.html"
    with open(out_path, "w", encoding="utf-8") as f:
        for line_num in range(1, 504):
            f.write(restored.get(line_num, f"<!-- MISSING LINE {line_num} -->") + "\n")
            
    print(f"Wrote stitched file to {out_path}")

if __name__ == "__main__":
    extract()
