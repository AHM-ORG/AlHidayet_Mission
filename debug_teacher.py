import os
import csv
import io
import sqlite3
import random

def run_test():
    csv_data = """NAME,PHONE,QUALIFICATION,JOINING DATE
Teacher One,9876543210,B.Ed,2023-01-01
"""
    csv_input = list(csv.DictReader(io.StringIO(csv_data)))
    
    smart_stream = io.StringIO()
    writer = csv.DictWriter(smart_stream, fieldnames=csv_input[0].keys())
    writer.writeheader()
    writer.writerows(csv_input)
    smart_stream.seek(0)
    
    csv_input_reader = csv.DictReader(smart_stream)
    
    aliases_user = ['USERNAME', 'U NAME', 'LOGIN ID']
    aliases_pass = ['PASSWORD', 'PASS']
    aliases_name = ['NAME', 'FULL NAME', 'TEACHER NAME']
    aliases_phone = ['PHONE NUMBER', 'PHONE', 'MOBILE', 'CONTACT']
    aliases_qual = ['QUALIFICATION', 'DEGREE']
    aliases_join = ['JOINING DATE', 'JOIN DATE', 'DATE OF JOINING']
    aliases_address = ['ADDRESS', 'ADDR']
    
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
        if not name: 
            print("SKIPPING: no name")
            continue
            
        phone = flexible_get(row, aliases_phone)
        username = flexible_get(row, aliases_user)
        print("Username initially:", username)
        
        if not username:
            username = phone if phone and str(phone).strip() else name.replace(' ', '').lower() + str(random.randint(10, 99))
            
        password = flexible_get(row, aliases_pass) or 'teacher123'
        
        print("Final Username:", username)
        print("Final Password:", password)
        print("Ready to insert.")

if __name__ == '__main__':
    run_test()
