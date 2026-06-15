import os
import json

def search_transcript():
    log_path = r"C:\Users\mdasw\.gemini\antigravity-ide\brain\0661f064-1ede-48f6-afea-a9629608d121\.system_generated\logs\transcript.jsonl"
    if not os.path.exists(log_path):
        print(f"File not found: {log_path}")
        return
        
    with open(log_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                content = data.get('content', '')
                if 'student.xlsx' in content or 'process_data' in content:
                    print(f"Step {data.get('step_index')}: found keyword. Length of content: {len(content)}")
                    # Let's search if there are other steps
            except Exception as e:
                pass

if __name__ == '__main__':
    search_transcript()
