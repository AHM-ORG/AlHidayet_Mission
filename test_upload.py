import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import csv
import io

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

csv_input = [{'NAME': 'Ayan  Sakib', 'D O B': '2010', 'GUARDIANS NAME': 'Ikbal Hussan'}]
existing_students = []

prompt = f"""
You are a smart data processing assistant for a school system.
I am providing you with an entire uploaded CSV file parsed as a JSON array.

1. Determine the upload type:
   - 'students' (contains full new student details like DOB, Class, Village, etc.)
   - 'update_students' (contains basic info like names, roll numbers, guardians to update existing students.)
   - 'teachers' (contains teacher qualifications, joining dates)
   - 'routine' (contains class schedule)

2. Clean, normalize, and fix the data. 
   - Fix any upper/lowercase inconsistencies.
   - CRITICAL: If this is 'update_students', match the student name from the CSV to the closest name in this list of existing students: {existing_students}. If there is a typo or case difference, replace the CSV name with the exact existing student name from the list. If you can't find a close match, leave it as is.

3. Return ONLY a valid JSON object matching this exact schema:
{{
  "upload_type": "determined_type",
  "cleaned_csv": [
      // The exact same structure as the raw CSV data, but with cleaned and corrected values.
  ]
}}

Raw Data:
{json.dumps(csv_input)}
"""
try:
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    response_text = response.text.strip()
    if response_text.startswith('```json'):
        response_text = response_text[7:-3]
    elif response_text.startswith('```'):
        response_text = response_text[3:-3]
    
    print("Response text:", response_text)
    ai_result = json.loads(response_text)
    upload_type = ai_result.get('upload_type', 'students')
    cleaned_csv = ai_result.get('cleaned_csv', csv_input)
    print("upload_type:", upload_type)
    print("cleaned_csv:", cleaned_csv)
    
    if cleaned_csv:
        smart_stream = io.StringIO()
        writer = csv.DictWriter(smart_stream, fieldnames=cleaned_csv[0].keys())
        writer.writeheader()
        writer.writerows(cleaned_csv)
        smart_stream.seek(0)
        print("smart_stream output:")
        print(smart_stream.read())
except Exception as e:
    print(f"Error: {e}")
