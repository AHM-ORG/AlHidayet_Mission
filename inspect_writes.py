import json

log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\ec1d6cd6-0cc9-466f-9483-f622985b7d6a\.system_generated\logs\transcript.jsonl"

def inspect():
    for i, line in enumerate(open(log_path, encoding="utf-8")):
        data = json.loads(line)
        if "tool_calls" in data:
            for tc in data["tool_calls"]:
                if tc.get("name") == "write_to_file":
                    args = tc.get("args", {})
                    target = args.get("TargetFile", "")
                    desc = args.get("Description", "")
                    content_len = len(args.get("CodeContent", ""))
                    print(f"Step {i}: write_to_file target={target}, desc={desc}, content_len={content_len}")

if __name__ == "__main__":
    inspect()
