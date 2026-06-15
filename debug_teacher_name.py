import csv
import io
import sqlite3

def test_teacher_csv():
    csv_data = """Teacher,Class,Subjects
ISA,NURSERY,BENGALI
ISA,ONE,"MATH, EVS"
ISA,TWO,G.K/HINDI
ISA,FIVE,EVS
SABNUR,NURSERY,"ENGLISH, B.H.W"
SABNUR,U/N,BENGALI
"""
    csv_input = list(csv.DictReader(io.StringIO(csv_data)))
    
    aliases_user = ['USERNAME', 'U NAME', 'LOGIN ID']
    aliases_pass = ['PASSWORD', 'PASS']
    aliases_name = ['NAME', 'FULL NAME', 'TEACHER NAME', 'TEACHER']
    aliases_phone = ['PHONE NUMBER', 'PHONE', 'MOBILE', 'CONTACT']
    aliases_qual = ['QUALIFICATION', 'DEGREE']
    aliases_join = ['JOINING DATE', 'JOIN DATE', 'DATE OF JOINING']
    aliases_address = ['ADDRESS', 'ADDR']
    
    def flexible_get(row, aliases):
        for alias in aliases:
            if alias in row and row[alias].strip():
                return row[alias].strip()
        return ''
        
    for raw_row in csv_input:
        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
        name = flexible_get(row, aliases_name)
        print(f"Row: {row}")
        print(f"Extracted Name: {name}")

test_teacher_csv()
