import json
import re

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\..system_generated\logs\transcript.jsonl"
# Let's also check if parent folder path has double dots or single dot
# C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl
log_path_corrected = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"

def recover():
    found_content = None
    for line in open(log_path_corrected, encoding="utf-8"):
        data = json.loads(line)
        content = data.get("content", "")
        if "Total Lines: 503" in content and "Showing lines 1 to 503" in content:
            found_content = content
            break
            
    if not found_content:
        # Let's search for "Total Lines: 503" without "Showing lines 1 to 503"
        for line in open(log_path_corrected, encoding="utf-8"):
            data = json.loads(line)
            content = data.get("content", "")
            if "Total Lines: 503" in content:
                found_content = content
                break

    if not found_content:
        print("Failed to find the 503-line dashboard step in the logs.")
        return

    # Let's parse the lines
    restored_lines = []
    lines = found_content.splitlines()
    for l in lines:
        match = re.match(r"^\s*(\d+):\s?(.*)$", l)
        if match:
            line_num = int(match.group(1))
            line_content = match.group(2)
            # Ensure list is large enough
            while len(restored_lines) < line_num:
                restored_lines.append("")
            restored_lines[line_num - 1] = line_content

    # Write to a test file first
    out_path = r"d:\AHM\AHM-Web\templates\dashboard.html"
    # We will write to a temp file, then we can copy it over once approved
    temp_out_path = r"d:\AHM\AHM-Web\templates\dashboard_restored.html"
    with open(temp_out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(restored_lines) + "\n")
    print(f"Successfully recovered {len(restored_lines)} lines to {temp_out_path}")

if __name__ == "__main__":
    recover()
