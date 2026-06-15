import os
from dotenv import load_dotenv
from google import genai
import json

load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

csv_input = [{'ROLL': '1', 'NAME': 'Ayan  Sakib', 'GUARDIANS NAME': 'Ikbal Hussan', 'U NAME': 'AYAN  SAKIB'}, {'ROLL': '2', 'NAME': 'Mubassira parvin', 'GUARDIANS NAME': 'Mijanur', 'U NAME': 'MUBASSIRA PARVIN'}]
existing_students = ['AYAN SAKIB', 'MUBASSIRA PARVIN']

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
response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=prompt,
)
print(response.text)
