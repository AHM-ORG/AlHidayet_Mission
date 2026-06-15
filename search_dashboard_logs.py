import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"

def scan():
    for i, line in enumerate(open(log_path, encoding="utf-8")):
        data = json.loads(line)
        # Check if dashboard.html is mentioned
        if "dashboard.html" in line:
            print(f"Step {i}: type={data.get('type')}, source={data.get('source')}, content_len={len(data.get('content', ''))}")
            # If there's a tool_call, print it
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if "dashboard.html" in json.dumps(tc):
                        print(f"  Tool Call: {tc.get('name')} (args keys: {list(tc.get('args', {}).keys())})")

if __name__ == "__main__":
    scan()
