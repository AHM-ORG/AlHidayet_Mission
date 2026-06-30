#!/usr/bin/env python
import os
import sqlite3
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_NAME = os.getenv('DATABASE_PATH', os.path.join(INSTANCE_DIR, 'users.db'))

def get_db_connection():
    # Detect if we need local SQLite or Cloud Turso database
    db_url = os.getenv('DATABASE_URL')
    db_token = os.getenv('DATABASE_AUTH_TOKEN')
    
    if db_url and (db_url.startswith("libsql://") or db_url.startswith("https://") or db_url.startswith("http://")):
        import requests
        import base64
        
        class HttpTursoConnection:
            def __init__(self, url, token):
                self.url = url.replace("libsql://", "https://")
                self.token = token
            
            def execute(self, sql, parameters=()):
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                }
                
                def _make_value(val):
                    if val is None:
                        return {"type": "null"}
                    elif isinstance(val, bool):
                        return {"type": "integer", "value": "1" if val else "0"}
                    elif isinstance(val, int):
                        return {"type": "integer", "value": str(val)}
                    elif isinstance(val, float):
                        return {"type": "float", "value": val}
                    else:
                        return {"type": "text", "value": str(val)}
                        
                stmt = {"sql": sql}
                if parameters:
                    stmt["args"] = [_make_value(val) for val in parameters]
                    
                payload = {"requests": [{"type": "execute", "stmt": stmt}]}
                res = requests.post(f"{self.url}/v2/pipeline", json=payload, headers=headers, timeout=15)
                
                if res.status_code != 200:
                    raise Exception(f"Turso Error {res.status_code}: {res.text}")
                    
                data = res.json()
                results = data.get("results", [])
                if not results:
                    return []
                    
                first_res = results[0]
                if first_res.get("type") == "error":
                    raise Exception(first_res.get("error", {}).get("message"))
                    
                response_obj = first_res.get("response", {})
                result_obj = response_obj.get("result", {})
                
                cols = [c.get("name") if isinstance(c, dict) else str(c) for c in result_obj.get("cols", [])]
                rows = []
                for r in result_obj.get("rows", []):
                    row_vals = []
                    for cell in r:
                        if isinstance(cell, dict):
                            t = cell.get("type")
                            v = cell.get("value")
                            if t == "null":
                                row_vals.append(None)
                            elif t == "integer":
                                row_vals.append(int(v))
                            elif t == "float":
                                row_vals.append(float(v))
                            else:
                                row_vals.append(v)
                        else:
                            row_vals.append(cell)
                    rows.append(dict(zip(cols, row_vals)))
                return rows
                
        return HttpTursoConnection(db_url, db_token)
    else:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

def main():
    now = datetime.datetime.now()
    month = now.strftime('%B')
    year = now.strftime('%Y')
    
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Starting Monthly Billing Worker for {month} {year}...")
    
    conn = get_db_connection()
    is_cloud = not hasattr(conn, 'row_factory')
    
    try:
        # Check active students
        if is_cloud:
            students = conn.execute('''
                SELECT u.id, si.*
                FROM users u
                JOIN student_info si ON u.id = si.user_id
                WHERE u.role = 'student'
            ''')
            
            # Fetch transport settings
            trans_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1")
            flat_transport_fee = float(trans_row[0]['flat_rate']) if trans_row else 400.0
            
            billed_count = 0
            for student in students:
                student_id = student['id']
                class_name = student['class']
                branch = student['branch'] or 'bhogram'
                take_school = int(student['take_school'] or 0)
                take_coaching = int(student['take_coaching'] or 0)
                take_day_hostel = int(student['take_day_hostel'] or 0)
                take_car = int(student['take_car'] or 0)
                
                # Check duplicate billing
                already_billed = conn.execute('''
                    SELECT id FROM student_ledger 
                    WHERE student_id = ? AND month = ? AND year = ? AND fee_type LIKE 'Monthly%'
                ''', (student_id, month, year))
                if already_billed:
                    continue
                    
                school_fee = 0.0
                coaching_fee = 0.0
                hostel_fee = 0.0
                car_fee = 0.0
                
                if int(student['is_custom_fee'] or 0) == 1:
                    has_custom_components = any([
                        float(student.get('tuition_fee') or 0.0) > 0.0,
                        float(student.get('room_rent') or 0.0) > 0.0,
                        float(student.get('coaching_combo_fee') or 0.0) > 0.0,
                        float(student.get('transport_fee') or 0.0) > 0.0
                    ])
                    if has_custom_components:
                        school_fee = float(student.get('tuition_fee') or 0.0) if take_school else 0.0
                        coaching_fee = float(student.get('coaching_combo_fee') or 0.0) if take_coaching else 0.0
                        hostel_fee = float(student.get('room_rent') or 0.0) if take_day_hostel else 0.0
                        car_fee = float(student.get('transport_fee') or 0.0) if take_car else 0.0
                        if take_car and car_fee == 0.0:
                            car_fee = flat_transport_fee
                    else:
                        flat_fee = float(student.get('monthly_fee') or 0.0)
                        if take_school:
                            school_fee = flat_fee
                        elif take_day_hostel:
                            hostel_fee = flat_fee
                        elif take_coaching:
                            coaching_fee = flat_fee
                        else:
                            school_fee = flat_fee
                        if take_car:
                            car_fee = flat_transport_fee
                else:
                    matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower()))
                    if matrix:
                        m_row = matrix[0]
                        if take_school:
                            school_fee = float(m_row['school_monthly'] or 0.0)
                        if take_coaching:
                            coaching_fee = float(m_row['coaching_monthly'] or 0.0)
                        if take_day_hostel:
                            hostel_fee = float(m_row['hostel_monthly'] or 0.0)
                    else:
                        cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower()))
                        if cls_row:
                            c_row = cls_row[0]
                            if take_school:
                                school_fee = float(c_row['monthly_fee'] or 0.0)
                            if take_coaching:
                                coaching_fee = float(c_row['monthly_fee_coaching'] or 0.0)
                            if take_day_hostel:
                                hostel_fee = float(c_row['hostel_fee'] or 0.0)
                    if take_car:
                        car_fee = flat_transport_fee
                        
                total_due = school_fee + coaching_fee + hostel_fee + car_fee
                if total_due <= 0.0:
                    continue
                    
                # Insert billing logs and ledger rows
                line_items = []
                if school_fee > 0.0:
                    line_items.append(('Monthly Tuition Fee', school_fee))
                if coaching_fee > 0.0:
                    line_items.append(('Monthly Coaching Fee', coaching_fee))
                if hostel_fee > 0.0:
                    line_items.append(('Monthly Hostel Fee', hostel_fee))
                if car_fee > 0.0:
                    line_items.append(('Monthly Transport Fee', car_fee))
                    
                for fee_type, amount in line_items:
                    conn.execute('''
                        INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                        VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                    ''', (student_id, fee_type, amount, month, year, branch))
                    
                    conn.execute('''
                        INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                        VALUES (?, 'Charge', ?, ?, ?, ?, ?)
                    ''', (student_id, fee_type, amount, month, year, branch))
                    
                conn.execute('''
                    UPDATE student_info
                    SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
                    WHERE user_id = ?
                ''', (total_due, student_id))
                billed_count += 1
                
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cloud DB billing complete. Billed {billed_count} active student(s).")
        else:
            # Local SQLite database
            c = conn.cursor()
            
            # Fetch transport settings
            trans_row = c.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
            flat_transport_fee = float(trans_row['flat_rate']) if trans_row else 400.0
            
            students = c.execute('''
                SELECT u.id, si.*
                FROM users u
                JOIN student_info si ON u.id = si.user_id
                WHERE u.role = 'student'
            ''').fetchall()
            
            billed_count = 0
            for student in students:
                student_id = student['id']
                class_name = student['class']
                branch = student['branch'] or 'bhogram'
                take_school = student['take_school'] or 0
                take_coaching = student['take_coaching'] or 0
                take_day_hostel = student['take_day_hostel'] or 0
                take_car = student['take_car'] or 0
                
                # Check duplicate billing
                already_billed = c.execute('''
                    SELECT id FROM student_ledger 
                    WHERE student_id = ? AND month = ? AND year = ? AND fee_type LIKE 'Monthly%'
                ''', (student_id, month, year)).fetchone()
                if already_billed:
                    continue
                    
                school_fee = 0.0
                coaching_fee = 0.0
                hostel_fee = 0.0
                car_fee = 0.0
                
                if student['is_custom_fee']:
                    has_custom_components = any([
                        float(student.get('tuition_fee') or 0.0) > 0.0,
                        float(student.get('room_rent') or 0.0) > 0.0,
                        float(student.get('coaching_combo_fee') or 0.0) > 0.0,
                        float(student.get('transport_fee') or 0.0) > 0.0
                    ])
                    if has_custom_components:
                        school_fee = float(student.get('tuition_fee') or 0.0) if take_school else 0.0
                        coaching_fee = float(student.get('coaching_combo_fee') or 0.0) if take_coaching else 0.0
                        hostel_fee = float(student.get('room_rent') or 0.0) if take_day_hostel else 0.0
                        car_fee = float(student.get('transport_fee') or 0.0) if take_car else 0.0
                        if take_car and car_fee == 0.0:
                            car_fee = flat_transport_fee
                    else:
                        flat_fee = float(student.get('monthly_fee') or 0.0)
                        if take_school:
                            school_fee = flat_fee
                        elif take_day_hostel:
                            hostel_fee = flat_fee
                        elif take_coaching:
                            coaching_fee = flat_fee
                        else:
                            school_fee = flat_fee
                        if take_car:
                            car_fee = flat_transport_fee
                else:
                    matrix = c.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
                    if matrix:
                        if take_school:
                            school_fee = float(matrix['school_monthly'] or 0.0)
                        if take_coaching:
                            coaching_fee = float(matrix['coaching_monthly'] or 0.0)
                        if take_day_hostel:
                            hostel_fee = float(matrix['hostel_monthly'] or 0.0)
                    else:
                        cls_row = c.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
                        if cls_row:
                            if take_school:
                                school_fee = float(cls_row['monthly_fee'] or 0.0)
                            if take_coaching:
                                coaching_fee = float(cls_row['monthly_fee_coaching'] or 0.0)
                            if take_day_hostel:
                                hostel_fee = float(cls_row['hostel_fee'] or 0.0)
                    if take_car:
                        car_fee = flat_transport_fee
                        
                total_due = school_fee + coaching_fee + hostel_fee + car_fee
                if total_due <= 0.0:
                    continue
                    
                line_items = []
                if school_fee > 0.0:
                    line_items.append(('Monthly Tuition Fee', school_fee))
                if coaching_fee > 0.0:
                    line_items.append(('Monthly Coaching Fee', coaching_fee))
                if hostel_fee > 0.0:
                    line_items.append(('Monthly Hostel Fee', hostel_fee))
                if car_fee > 0.0:
                    line_items.append(('Monthly Transport Fee', car_fee))
                    
                for fee_type, amount in line_items:
                    c.execute('''
                        INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                        VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                    ''', (student_id, fee_type, amount, month, year, branch))
                    
                    c.execute('''
                        INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                        VALUES (?, 'Charge', ?, ?, ?, ?, ?)
                    ''', (student_id, fee_type, amount, month, year, branch))
                    
                c.execute('''
                    UPDATE student_info
                    SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
                    WHERE user_id = ?
                ''', (total_due, student_id))
                billed_count += 1
                
            conn.commit()
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Local SQLite billing complete. Billed {billed_count} active student(s).")
            
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CRITICAL ERROR running billing: {e}")
        if not is_cloud:
            conn.rollback()
    finally:
        if not is_cloud:
            conn.close()

if __name__ == '__main__':
    main()
