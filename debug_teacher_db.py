import csv
import io
import sqlite3
import random

def test_teacher_csv():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, security_key TEXT)")
    c.execute("CREATE TABLE teacher_info (user_id INTEGER PRIMARY KEY, full_name TEXT, phone_number TEXT, qualification TEXT, joining_date TEXT, address TEXT)")
    
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
        
    success_count = 0
    errors = []
    row_num = 1
    
    for raw_row in csv_input:
        row_num += 1
        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
        name = flexible_get(row, aliases_name)
        if not name: 
            errors.append(f"Row {row_num}: Missing Teacher Name. Skipped.")
            continue
        
        phone = flexible_get(row, aliases_phone)
        username = flexible_get(row, aliases_user)
        
        # Deduplicate by checking if teacher already exists by name
        existing_teacher = c.execute('''
            SELECT u.username FROM users u 
            JOIN teacher_info ti ON u.id = ti.user_id 
            WHERE LOWER(REPLACE(ti.full_name, ' ', '')) = ?
        ''', (name.lower().replace(' ', ''),)).fetchone()
        
        if existing_teacher:
            username = existing_teacher['username']
        elif not username:
            username = phone if phone and str(phone).strip() else name.replace(' ', '').lower() + str(random.randint(10, 99))
            
        password = flexible_get(row, aliases_pass) or 'teacher123'
        
        c.execute("INSERT OR IGNORE INTO users (username, password, role, security_key) VALUES (?, ?, ?, ?)",
                  (username, password, 'teacher', 'default-key'))
        user_id_row = c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not user_id_row: 
            errors.append(f"Row {row_num}: Failed to get user ID.")
            continue
        user_id = user_id_row['id']
        
        # Handle multiple subjects by appending them to qualification
        qual = flexible_get(row, aliases_qual)
        subject = flexible_get(row, ['SUBJECT', 'SUB', 'SUBJECTS'])
        class_name = flexible_get(row, ['CLASS', 'GRADE'])
        
        if class_name:
            qual = f"{qual} | Class: {class_name}" if qual else f"Class: {class_name}"
        if subject:
            qual = f"{qual} | Sub: {subject}" if qual else f"Sub: {subject}"
            
        # If updating an existing teacher, append the new subject and class
        if existing_teacher:
            current_qual = c.execute("SELECT qualification FROM teacher_info WHERE user_id = ?", (user_id,)).fetchone()
            if current_qual and current_qual['qualification']:
                new_additions = []
                if class_name and class_name not in current_qual['qualification']:
                    new_additions.append(f"Class: {class_name}")
                if subject and subject not in current_qual['qualification']:
                    new_additions.append(f"Sub: {subject}")
                if new_additions:
                    qual = f"{current_qual['qualification']}, " + ", ".join(new_additions)
                else:
                    qual = current_qual['qualification']
        
        c.execute('''
            INSERT OR REPLACE INTO teacher_info 
            (user_id, full_name, phone_number, qualification, joining_date, address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, name, phone, 
              qual, flexible_get(row, aliases_join), flexible_get(row, aliases_address)))
        success_count += 1

    print(f"Success Count: {success_count}")
    print(f"Errors: {errors}")
    
    # Check what was inserted
    teachers = c.execute("SELECT ti.full_name, ti.qualification FROM teacher_info ti").fetchall()
    print("Inserted Teachers:")
    for t in teachers:
        print(f"{t['full_name']} -> {t['qualification']}")

test_teacher_csv()
