import json
import re

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"

def main():
    lines = {}
    active_file = None
    
    with open(log_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            data = json.loads(line)
            content = data.get("content", "")
            
            # Identify active file from tool calls
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                args = tc.get("args", {})
                path = args.get("TargetFile") or args.get("AbsolutePath")
                if path:
                    if "dashboard.html" in path:
                        active_file = "dashboard.html"
                    else:
                        active_file = "other"
            
            # Identify active file from content
            if "File Path:" in content:
                m = re.search(r"File Path:\s*`?file:///([^`\n]+)`?", content)
                if m:
                    path = m.group(1)
                    if "dashboard.html" in path:
                        active_file = "dashboard.html"
                    else:
                        active_file = "other"
            
            # If active file is dashboard.html, parse line contents
            if active_file == "dashboard.html":
                for l in content.splitlines():
                    match = re.match(r"^\s*(\d+):\s?(.*)$", l)
                    if match:
                        line_num = int(match.group(1))
                        line_content = match.group(2)
                        lines[line_num] = line_content

    print(f"Total lines found for dashboard.html: {len(lines)}")
    missing = [i for i in range(1, 504) if i not in lines]
    print(f"Missing lines: {missing}")
    
    # Save the recovered lines to a file
    restored = []
    for i in range(1, 504):
        if i in lines:
            restored.append(lines[i])
        else:
            restored.append(f"<!-- MISSING LINE {i} -->")
            
    with open("templates/dashboard_restored_clean.html", "w", encoding="utf-8") as out:
        out.write("\n".join(restored) + "\n")
    print("Clean restored dashboard saved to templates/dashboard_restored_clean.html")

if __name__ == "__main__":
    main()
