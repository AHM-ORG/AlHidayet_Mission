import json
import os

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"
out_path = r"d:\AHM\AHM-Web\scratch_dashboard_history.txt"

with open(out_path, "w", encoding="utf-8") as out:
    for i, line in enumerate(open(log_path, encoding="utf-8")):
        data = json.loads(line)
        if "dashboard.html" in line or "dashboard_history" in line:
            out.write(f"--- STEP {i} ---\n")
            out.write(f"type: {data.get('type')}, source: {data.get('source')}\n")
            if "tool_calls" in data:
                out.write(f"tool_calls: {json.dumps(data['tool_calls'], indent=2)}\n")
            content = data.get("content", "")
            if len(content) > 1000:
                out.write(f"content length: {len(content)}\n")
                out.write(f"content start:\n{content[:1000]}\n")
                out.write(f"content end:\n{content[-1000:]}\n")
            else:
                out.write(f"content: {content}\n")
            out.write("\n\n")

print("Done! Check d:\\AHM\\AHM-Web\\scratch_dashboard_history.txt")
