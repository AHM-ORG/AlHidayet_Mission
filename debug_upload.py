import os
import csv
import io
import sqlite3

def run_test():
    # Simulate the CSV upload fallback stream
    csv_data = """NAME,CLASS,ROLL NUMBER,GUARDIANS NAME,PHONE
Ayan Sakib,10,1,Ikbal Hussan,9876543210
"""
    csv_input = list(csv.DictReader(io.StringIO(csv_data)))
    
    smart_stream = io.StringIO()
    writer = csv.DictWriter(smart_stream, fieldnames=csv_input[0].keys())
    writer.writeheader()
    writer.writerows(csv_input)
    smart_stream.seek(0)
    
    # Process it
    print("Reading smart_stream...")
    csv_input_reader = csv.DictReader(smart_stream)
    
    aliases_name = ['NAME', 'FULL NAME', 'STUDENT NAME', 'U NAME']
    aliases_phone = ['CONTACT NUM(O P)', 'CONTACT NUM(OP)', 'CONTACT NUMBER', 'PHONE', 'MOBILE', 'PHONE NUMBER', 'CONTACT']
    aliases_guardian = ['FATHERS NAME', 'FATHER NAME', 'GUARDIANS NAME', 'GUARDIAN']
    aliases_dob = ['D O B', 'DOB', 'DATE OF BIRTH']
    aliases_class = ['CLASS', 'GRADE', 'STANDARD']
    
    def flexible_get(row, aliases):
        for alias in aliases:
            if alias in row and row[alias].strip():
                return row[alias].strip()
        return ''
    
    for raw_row in csv_input_reader:
        print("Raw row:", raw_row)
        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
        print("Normalized row:", row)
        
        name = flexible_get(row, aliases_name)
        print("Name found:", name)
        if not name: 
            print("SKIPPING row because no name found!")
            continue
            
        print("Row processed successfully.")

if __name__ == '__main__':
    run_test()
