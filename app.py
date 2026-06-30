import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, send_from_directory
import sqlite3
import json
import random
import string
import smtplib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from functools import wraps
from dotenv import load_dotenv
import csv
import io
from google import genai
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    import razorpay
except ImportError:
    razorpay = None

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    TEMPLATES_AUTO_RELOAD=True
)
app.jinja_env.auto_reload = True

@app.template_filter('clean_name')
def clean_name_filter(s):
    if not s:
        return ""
    # Strip any trailing/embedded digits and format as title case
    cleaned = "".join(c for c in str(s) if not c.isdigit()).replace('_', ' ').replace('-', ' ').strip().title()
    return cleaned if cleaned else s

@app.template_filter('normalize_class')
def normalize_class_filter(s):
    return normalize_class_name(s)

@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        if e.code != 500:
            return e
    return internal_server_error(e)

@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    err_msg = ""
    tb_str = ""
    original = getattr(e, 'original_exception', None) or e
    err_msg = str(original)
    try:
        if hasattr(original, '__traceback__') and original.__traceback__:
            tb_str = "".join(traceback.format_exception(type(original), original, original.__traceback__))
        else:
            tb_str = traceback.format_exc()
    except Exception:
        tb_str = "Traceback unavailable"
        
    try:
        import threading
        # Safely resolve destination email without throwing on database downtime
        try:
            dest_email = get_school_setting('log_destination_email', 'missionalhidayet@gmail.com')
        except Exception:
            dest_email = 'missionalhidayet@gmail.com'

        username = session.get('user', 'Anonymous')
        role = session.get('role', 'Unknown')
        branch = session.get('branch', 'Not set')
        ip = request.remote_addr if request else 'Unknown'
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        subject = f"AHM Critical 500 Error: {err_msg[:50]}"
        body = f"""Institute Activity Log Info:
----------------------------
Action: 500 Internal Server Error
User: {username} ({role})
Branch: {branch}
IP Address: {ip}
Timestamp: {timestamp}

URL: {request.url}
Method: {request.method}
Error: {err_msg}

Traceback:
{tb_str}
----------------------------"""
        # Send raw email directly to the destination logs recipient in background thread
        threading.Thread(target=_send_email_raw, args=(subject, body, dest_email), daemon=True).start()
    except Exception as email_err:
        print(f" [ERROR MAIL] Failed to queue error email: {email_err}")

    return render_template('error_500.html'), 500

# Intercept database errors even when debug mode is enabled, to render the maintenance page and send email alerts.
original_handle_user_exception = app.handle_user_exception

def custom_handle_user_exception(e):
    original_err = getattr(e, 'original_exception', None) or e
    if isinstance(original_err, sqlite3.Error):
        return internal_server_error(e)
    return original_handle_user_exception(e)

app.handle_user_exception = custom_handle_user_exception

# Database Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_NAME = os.getenv('DATABASE_PATH', os.path.join(INSTANCE_DIR, 'users.db'))

DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE_AUTH_TOKEN = os.getenv('DATABASE_AUTH_TOKEN')

# Create persistent session for Turso cloud DB to keep TCP/TLS connections alive
import requests
turso_session = requests.Session()

def consolidate_databases():
    if DATABASE_URL and (DATABASE_URL.startswith("libsql://") or DATABASE_URL.startswith("https://") or DATABASE_URL.startswith("http://")):
        print(" [DB CONSOLIDATION] Skipping local database consolidation for cloud database.")
        return
    import shutil
    base_users_db = os.path.join(BASE_DIR, 'users.db')
    
    # 1. Ensure instance directory exists
    if not os.path.exists(INSTANCE_DIR):
        try:
            os.makedirs(INSTANCE_DIR)
        except Exception as e:
            print(f" [DB MIGRATE ERROR] Failed to create instance folder: {e}")
            return
        
    # 2. If old users.db exists in BASE_DIR, move it to the instance folder
    if os.path.exists(base_users_db):
        target_db = os.path.join(INSTANCE_DIR, 'users.db')
        if not os.path.exists(target_db):
            print(f" [DB MIGRATE] Moving {base_users_db} to {target_db}")
            try:
                shutil.move(base_users_db, target_db)
            except Exception as e:
                print(f" [DB MIGRATE ERROR] Failed to move users.db: {e}")
                try:
                    shutil.copy2(base_users_db, target_db)
                    os.remove(base_users_db)
                except Exception as e2:
                    print(f" [DB MIGRATE ERROR] Copy fallback failed: {e2}")

    # 3. Consolidate school.db and ahm.db
    target_db_path = DB_NAME
    for old_db_name in ['school.db', 'ahm.db']:
        old_db_path = os.path.join(BASE_DIR, old_db_name)
        if not os.path.exists(old_db_path):
            old_db_path = os.path.join(INSTANCE_DIR, old_db_name)
            
        if os.path.exists(old_db_path):
            print(f" [DB CONSOLIDATION] Found old database to merge: {old_db_path}")
            try:
                src_conn = sqlite3.connect(old_db_path)
                src_cursor = src_conn.cursor()
                src_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                tables = src_cursor.fetchall()
                src_conn.close()
                
                if tables:
                    dest_conn = sqlite3.connect(target_db_path)
                    dest_cursor = dest_conn.cursor()
                    
                    escaped_path = old_db_path.replace("'", "''")
                    dest_cursor.execute(f"ATTACH DATABASE '{escaped_path}' AS src_db")
                    
                    for table_name, create_sql in tables:
                        dest_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
                        if not dest_cursor.fetchone():
                            print(f" [DB CONSOLIDATION] Creating table {table_name} in target database")
                            dest_cursor.execute(create_sql)
                        
                        print(f" [DB CONSOLIDATION] Merging rows for table {table_name}")
                        try:
                            dest_cursor.execute(f"INSERT OR IGNORE INTO {table_name} SELECT * FROM src_db.{table_name}")
                        except Exception as insert_err:
                            print(f" [DB CONSOLIDATION ERROR] Insert failed for {table_name}: {insert_err}")
                            
                    dest_conn.commit()
                    dest_cursor.execute("DETACH DATABASE src_db")
                    dest_conn.close()
                    
                migrated_path = old_db_path + ".migrated"
                if os.path.exists(migrated_path):
                    try:
                        os.remove(migrated_path)
                    except Exception:
                        pass
                try:
                    os.rename(old_db_path, migrated_path)
                except Exception as rename_err:
                    print(f" [DB CONSOLIDATION ERROR] Rename failed for {old_db_path}: {rename_err}")
                print(f" [DB CONSOLIDATION] Successfully merged and renamed {old_db_path} to {migrated_path}")
                
            except Exception as merge_err:
                print(f" [DB CONSOLIDATION ERROR] Failed to merge {old_db_name}: {merge_err}")

# Execute database migration and consolidation
# consolidate_databases() # Moved to bottom to prevent WSGI hangs

def migrate_student_info_schema():
    conn = get_db_connection()
    c = conn.cursor()
    new_cols = [
        ("unique_code", "TEXT"),
        ("hostel_fee", "REAL DEFAULT 0.0"),
        ("session", "TEXT"),
        ("mode_of_admission", "TEXT"),
        ("father_qualification", "TEXT"),
        ("father_occupation", "TEXT"),
        ("father_monthly_income", "TEXT"),
        ("mother_qualification", "TEXT"),
        ("mother_occupation", "TEXT"),
        ("mother_monthly_income", "TEXT"),
        ("nationality", "TEXT"),
        ("religion", "TEXT"),
        ("gender", "TEXT"),
        ("caste", "TEXT"),
        ("whatsapp_no", "TEXT"),
        ("previous_class", "TEXT"),
        ("prev_marks_percentage", "TEXT"),
        ("identification_mark", "TEXT"),
        ("attached_documents", "TEXT"),
        ("coaching_opted", "INTEGER DEFAULT 0"),
        ("car_opted", "INTEGER DEFAULT 0"),
        ("sl_no", "TEXT"),
        ("take_school", "INTEGER DEFAULT 1"),
        ("take_coaching", "INTEGER DEFAULT 0"),
        ("take_day_hostel", "INTEGER DEFAULT 0"),
        ("take_car", "INTEGER DEFAULT 0"),
        ("admission_fee", "REAL DEFAULT 0.0"),
        ("readmission_fee", "REAL DEFAULT 0.0"),
        ("is_custom_fee", "INTEGER DEFAULT 0"),
        ("enrollment_type", "TEXT DEFAULT 'Day School Only'"),
        ("hostel_room", "TEXT"),
        ("hostel_wing", "TEXT"),
        ("coaching_batch", "TEXT"),
        ("coaching_subject", "TEXT"),
        ("tuition_fee", "REAL DEFAULT 0.0"),
        ("transport_fee", "REAL DEFAULT 0.0"),
        ("lab_library_fee", "REAL DEFAULT 0.0"),
        ("academic_discount", "REAL DEFAULT 0.0"),
        ("room_rent", "REAL DEFAULT 0.0"),
        ("mess_food_charges", "REAL DEFAULT 0.0"),
        ("utility_cost", "REAL DEFAULT 0.0"),
        ("security_deposit", "REAL DEFAULT 0.0"),
        ("coaching_combo_fee", "REAL DEFAULT 0.0"),
        ("study_material_charges", "REAL DEFAULT 0.0"),
        ("exam_test_series_fee", "REAL DEFAULT 0.0"),
        ("combo_discount", "REAL DEFAULT 0.0"),
        ("school_tax_rate", "REAL DEFAULT 0.0"),
        ("hostel_tax_rate", "REAL DEFAULT 0.05"),
        ("coaching_tax_rate", "REAL DEFAULT 0.0"),
        ("month_end_billing_count", "INTEGER DEFAULT 0"),
        ("year_end_billing_count", "INTEGER DEFAULT 0"),
        ("prev_dues", "REAL DEFAULT 0.0"),
        ("financial_aid_monthly", "REAL DEFAULT 0.0"),
        ("financial_aid_readmission", "REAL DEFAULT 0.0"),
        ("financial_aid_admission", "REAL DEFAULT 0.0")
    ]
    added_prev_dues = False
    added_fin_aid = False
    for col_name, col_type in new_cols:
        try:
            c.execute(f"ALTER TABLE student_info ADD COLUMN {col_name} {col_type}")
            print(f" [DB MIGRATE] Added column {col_name} to student_info")
            if col_name == "prev_dues":
                added_prev_dues = True
            if col_name == "financial_aid_monthly":
                added_fin_aid = True
        except sqlite3.OperationalError:
            pass # column already exists
            
    if added_fin_aid:
        # Migrate old Custom Fees to Reductions
        try:
            students = c.execute("SELECT * FROM student_info WHERE is_custom_fee = 1").fetchall()
            for row in students:
                student_dict = dict(row)
                # Temporarily set is_custom_fee to 0 to get the Base Fixed Fee
                student_dict['is_custom_fee'] = 0
                bd = calculate_student_fees_breakdown(student_dict, conn=conn)
                base_monthly = float(bd.get('total_fee') or 0.0)
                
                # We need to get the base readmission fee
                # Using similar logic as in update_total_due
                take_coaching = int(student_dict.get('take_coaching') or 0)
                take_day_hostel = int(student_dict.get('take_day_hostel') or 0)
                
                base_readm = 0.0
                matrix = c.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
                if matrix:
                    if take_day_hostel:
                        base_readm = float(matrix['hostel_readmission'] or 0.0)
                    elif take_coaching:
                        base_readm = float(matrix['coaching_readmission'] or 0.0)
                    else:
                        base_readm = float(matrix['school_readmission'] or 0.0)
                else:
                    cls_row = c.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
                    if cls_row:
                        if take_day_hostel:
                            base_readm = float(cls_row['readmission_fee_hostel'] or 0.0)
                        elif take_coaching:
                            base_readm = float(cls_row['readmission_fee_coaching'] or 0.0)
                        else:
                            base_readm = float(cls_row['readmission_fee_school'] or 0.0)
                
                old_monthly = float(row['monthly_fee'] or 0.0)
                old_readm = float(row['readmission_fee'] or 0.0)
                
                # Reduction = Base - Old
                red_monthly = max(0, base_monthly - old_monthly)
                red_readm = max(0, base_readm - old_readm)
                
                # If old was higher than base, then reduction is 0. 
                # (You shouldn't use financial aid to *increase* fees, but if it happened, old custom fees were higher).
                
                c.execute("""
                    UPDATE student_info 
                    SET financial_aid_monthly = ?, financial_aid_readmission = ?, is_custom_fee = 0 
                    WHERE user_id = ?
                """, (red_monthly, red_readm, row['user_id']))
                
            print(f" [DB MIGRATE] Migrated {len(students)} custom fee students to Financial Aid system.")
        except Exception as e:
            print(f" [DB MIGRATE ERROR] Financial Aid migration failed: {e}")

    if added_prev_dues:
        try:
            c.execute('''
                UPDATE student_info
                SET prev_dues = ROUND(
                    COALESCE(remaining_fee, 0.0) 
                    - (COALESCE(monthly_fee, 0.0) * COALESCE(month_end_billing_count, 0)) 
                    - (COALESCE(readmission_fee, 0.0) * COALESCE(year_end_billing_count, 0))
                    + COALESCE((SELECT SUM(amount) FROM fees WHERE student_id = user_id AND status = 'Paid'), 0.0),
                    2
                )
            ''')
            print(" [DB MIGRATE] Populated prev_dues retrospectively for existing students.")
        except Exception as e:
            print(f" [DB MIGRATE ERROR] Retrospective prev_dues calculation failed: {e}")
            
    conn.commit()
    conn.close()

def migrate_staff_and_expense_recipient_schema():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                staff_type TEXT NOT NULL,
                salary REAL DEFAULT 0.0,
                phone_number TEXT,
                branch TEXT
            )
        ''')
        try:
            c.execute("ALTER TABLE expenses ADD COLUMN recipient_type TEXT")
            print(" [DB MIGRATE] Added recipient_type to expenses")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE expenses ADD COLUMN recipient_id INTEGER")
            print(" [DB MIGRATE] Added recipient_id to expenses")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
        print(" [DB MIGRATE] Staff and expense recipient migrations completed.")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Staff and expense recipient migration failed: {e}")

# migrate_student_info_schema() was called here, but moved to run after init_db() on startup to support blank databases.

def update_bhogram_class_fees():
    return



def migrate_class_teachers_and_complaints_schema():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS class_teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                class_name TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                complaint_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print(" [DB MIGRATE] Class teachers and complaints migrations completed.")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Class teachers/complaints migration failed: {e}")

# migrate_class_teachers_and_complaints_schema() # Moved to bottom

def normalize_class_name(name):
    if not name:
        return ""
    name_str = str(name).strip().lower()
    if name_str.startswith("class "):
        name_str = name_str[6:].strip()
        
    mapping = {
        'nursery': 'Nursery',
        'nuesery': 'Nursery',
        'u/n': 'Upper Nursery',
        'un': 'Upper Nursery',
        'u-n': 'Upper Nursery',
        'kg': 'Upper Nursery',
        'upper nursery': 'Upper Nursery',
        'one': 'I', '1': 'I', 'i': 'I',
        'two': 'II', '2': 'II', 'ii': 'II',
        'three': 'III', '3': 'III', 'iii': 'III',
        'four': 'IV', '4': 'IV', 'iv': 'IV',
        'five': 'V', '5': 'V', 'v': 'V',
        'six': 'VI', '6': 'VI', 'vi': 'VI', 'siz': 'VI',
        'seven': 'VII', '7': 'VII', 'vii': 'VII',
        'eight': 'VIII', '8': 'VIII', 'viii': 'VIII',
        'nine': 'IX', '9': 'IX', 'ix': 'IX',
        'ten': 'X', '10': 'X', 'x': 'X'
    }
    return mapping.get(name_str, name.strip())



def get_class_sort_key(name):
    if not name:
        return 999
    name_lower = str(name).strip().lower()
    order = {
        'nursery': 1,
        'upper nursery': 2,
        'u/n': 2,
        'un': 2,
        'u-n': 2,
        'kg': 2,
        'i': 3,
        'one': 3,
        'ii': 4,
        'two': 4,
        'iii': 5,
        'three': 5,
        'iv': 6,
        'four': 6,
        'v': 7,
        'five': 7,
        'vi': 8,
        'six': 8,
        'vii': 9,
        'seven': 9,
        'viii': 10,
        'eight': 10,
        'ix': 11,
        'nine': 11,
        'x': 12,
        'ten': 12
    }
    return order.get(name_lower, 100 + len(name_lower))


def sync_classes(conn):
    try:
        # Check if is_hidden column exists. If not, add it
        cursor = conn.execute("PRAGMA table_info(classes)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'is_hidden' not in columns:
            conn.execute("ALTER TABLE classes ADD COLUMN is_hidden INTEGER DEFAULT 0")
            conn.commit()
    except sqlite3.OperationalError:
        pass
    
    # Ensure standard classes are seeded for branch 'bhogram' and 'surangapur'
    standard_classes = ['Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI']
    for branch_name in ['bhogram', 'surangapur']:
        for cls in standard_classes:
            exist = conn.execute("SELECT id FROM classes WHERE name = ? AND branch = ?", (cls, branch_name)).fetchone()
            if not exist:
                conn.execute("""
                    INSERT INTO classes (name, branch, is_hidden, admission_fee, monthly_fee, hostel_fee)
                    VALUES (?, ?, 1, 0.0, 0.0, 0.0)
                """, (cls, branch_name))
    conn.commit()

    # Get distinct classes and branches from student_info
    student_classes = conn.execute("SELECT DISTINCT class, branch FROM student_info WHERE class IS NOT NULL AND class != ''").fetchall()
    
    active_pairs = set()
    for row in student_classes:
        cls_name = normalize_class_name(row['class'])
        branch = row['branch'] or 'bhogram'
        active_pairs.add((cls_name.lower(), branch.lower()))
        
        # Check if this class exists in the database
        exist = conn.execute("SELECT id FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
        if not exist:
            # Auto-insert new active class
            conn.execute("""
                INSERT INTO classes (name, branch, is_hidden, admission_fee, monthly_fee, hostel_fee)
                VALUES (?, ?, 0, 0.0, 0.0, 0.0)
            """, (cls_name, branch))
        else:
            # Mark it as active (unhidden)
            conn.execute("UPDATE classes SET is_hidden = 0 WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch))
            
    # Mark all classes without active students as hidden
    all_db_classes = conn.execute("SELECT id, name, branch FROM classes").fetchall()
    for row in all_db_classes:
        cls_name = row['name']
        branch = row['branch']
        if (cls_name.lower(), branch.lower()) not in active_pairs:
            conn.execute("UPDATE classes SET is_hidden = 1 WHERE id = ?", (row['id'],))
            
    conn.commit()


def get_active_classes(conn, branch=None):
    try:
        if branch:
            rows = conn.execute("SELECT DISTINCT name FROM classes WHERE is_hidden = 0 AND LOWER(branch) = LOWER(?)", (branch,)).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT name FROM classes WHERE is_hidden = 0").fetchall()
        names = [r['name'] for r in rows]
        return sorted(names, key=get_class_sort_key)
    except sqlite3.OperationalError:
        return []


def get_all_classes(conn, branch=None):
    try:
        if branch:
            rows = conn.execute("SELECT DISTINCT name FROM classes WHERE LOWER(branch) = LOWER(?)", (branch,)).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT name FROM classes").fetchall()
        names = [r['name'] for r in rows]
        if not names:
            return ['Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI']
        return sorted(names, key=get_class_sort_key)
    except sqlite3.OperationalError:
        return ['Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI']




def normalize_subject_name(name):
    if not name:
        return ""
    name = str(name).strip().lower().replace('.', '')
    aliases = {
        'math': 'mathematics',
        'evs': 'science',
        'gk': 'general knowledge',
        'general knowledge': 'general knowledge',
        'islamic studies': 'islamic studies',
        'bhw': 'islamic studies',
        'ehw': 'islamic studies',
        'history': 'history',
        'geography': 'geography',
        'bengali': 'bengali',
        'english': 'english',
        'arabic': 'arabic',
        'hindi': 'hindi',
    }
    name_clean = " ".join(name.split())
    return aliases.get(name_clean, name_clean)


def calculate_student_fees_breakdown(student, conn=None):
    """
    Returns a dictionary of line items and aggregated component totals:
    - tuition_fee, transport_fee, lab_library_fee, academic_discount
    - room_rent, mess_food_charges, utility_cost, security_deposit
    - coaching_combo_fee, study_material_charges, exam_test_series_fee, combo_discount
    - school_tax_rate, hostel_tax_rate, coaching_tax_rate
    - school_revenue, hostel_revenue, coaching_revenue, tax_amount, total_fee
    """
    # 1. Checkbox configurations
    take_school = int(student.get('take_school') if student.get('take_school') is not None else 1)
    take_coaching = int(student.get('take_coaching') or 0)
    take_day_hostel = int(student.get('take_day_hostel') or 0)
    take_car = int(student.get('take_car') or 0)
    
    cls_name = student.get('class')
    branch = student.get('branch') or 'bhogram'
    
    tuition = 0.0
    transport = 0.0
    lab_lib = 0.0
    acad_disc = 0.0
    school_tax_rate = 0.0
    
    room_rent = 0.0
    mess = 0.0
    utility = 0.0
    deposit = 0.0
    hostel_tax_rate = 0.05
    
    coaching_combo = 0.0
    materials = 0.0
    exams = 0.0
    combo_disc = 0.0
    coaching_tax_rate = 0.0

    if cls_name:
        try:
            close_conn = False
            active_conn = conn
            if active_conn is None:
                active_conn = get_db_connection()
                active_conn.row_factory = sqlite3.Row
                close_conn = True
            
            if take_school:
                school_struct = active_conn.execute('''
                    SELECT * FROM fee_structures 
                    WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?) AND enrollment_type = 'Day School Only'
                ''', (cls_name, branch)).fetchone()
                if school_struct:
                    tuition = float(school_struct['tuition_fee'] or 0.0)
                    transport = float(school_struct['transport_fee'] or 0.0)
                    lab_lib = float(school_struct['lab_library_fee'] or 0.0)
                    acad_disc = float(school_struct['academic_discount'] or 0.0)
                    school_tax_rate = float(school_struct['school_tax_rate'] or 0.0)
                else:
                    matrix = active_conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
                    if matrix: tuition = float(matrix['school_fee'] or 0.0)
            
            if take_day_hostel:
                hostel_struct = active_conn.execute('''
                    SELECT * FROM fee_structures 
                    WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?) AND enrollment_type = 'Day Hostel Only'
                ''', (cls_name, branch)).fetchone()
                if hostel_struct:
                    room_rent = float(hostel_struct['room_rent'] or 0.0)
                    mess = float(hostel_struct['mess_food_charges'] or 0.0)
                    utility = float(hostel_struct['utility_cost'] or 0.0)
                    deposit = float(hostel_struct['security_deposit'] or 0.0)
                    hostel_tax_rate = float(hostel_struct['hostel_tax_rate'] or 0.05)
                else:
                    matrix = active_conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
                    if matrix: room_rent = float(matrix['hostel_fee'] or 0.0)
                    
            if take_coaching:
                coaching_struct = active_conn.execute('''
                    SELECT * FROM fee_structures 
                    WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?) AND enrollment_type = 'School + Coaching'
                ''', (cls_name, branch)).fetchone()
                if coaching_struct:
                    coaching_combo = float(coaching_struct['coaching_combo_fee'] or 0.0)
                    materials = float(coaching_struct['study_material_charges'] or 0.0)
                    exams = float(coaching_struct['exam_test_series_fee'] or 0.0)
                    combo_disc = float(coaching_struct['combo_discount'] or 0.0)
                    coaching_tax_rate = float(coaching_struct['coaching_tax_rate'] or 0.0)
                else:
                    matrix = active_conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
                    if matrix: coaching_combo = float(matrix['coaching_fee'] or 0.0)
                    
            if close_conn:
                active_conn.close()
        except Exception as e:
            print(f"Error loading fee structure from DB: {e}")

    # Sum component totals
    school_total = tuition + transport + lab_lib - acad_disc
    hostel_total = room_rent + mess + utility + deposit
    coaching_total = coaching_combo + materials + exams - combo_disc
    
    total = school_total + hostel_total + coaching_total
    
    if take_car:
        total += 400.0
        school_total += 400.0
        
    # Apply Financial Aid Monthly Reduction
    fin_aid = float(student.get('financial_aid_monthly') or 0.0)
    total = max(0.0, total - fin_aid)

    # Component Tax calculations
    school_tax = school_total * (school_tax_rate / (1.0 + school_tax_rate))
    hostel_tax = hostel_total * (hostel_tax_rate / (1.0 + hostel_tax_rate))
    coaching_tax = coaching_total * (coaching_tax_rate / (1.0 + coaching_tax_rate))
    
    school_net = school_total - school_tax
    hostel_net = hostel_total - hostel_tax
    coaching_net = coaching_total - coaching_tax
    
    return {
        'tuition_fee': tuition,
        'transport_fee': transport,
        'lab_library_fee': lab_lib,
        'academic_discount': acad_disc,
        'room_rent': room_rent,
        'mess_food_charges': mess,
        'utility_cost': utility,
        'security_deposit': deposit,
        'coaching_combo_fee': coaching_combo,
        'study_material_charges': materials,
        'exam_test_series_fee': exams,
        'combo_discount': combo_disc,
        'school_tax_rate': school_tax_rate,
        'hostel_tax_rate': hostel_tax_rate,
        'coaching_tax_rate': coaching_tax_rate,
        'school_revenue': school_net,
        'hostel_revenue': hostel_net,
        'coaching_revenue': coaching_net,
        'tax_amount': school_tax + hostel_tax + coaching_tax,
        'financial_aid_monthly': fin_aid,
        'total_fee': total
    }

def get_enrollment_type_from_checkboxes(take_school, take_coaching, take_day_hostel):
    if take_day_hostel:
        return 'Day Hostel Only'
    elif take_school and take_coaching:
        return 'School + Coaching'
    else:
        return 'Day School Only'

def calculate_default_monthly_fee(class_name, mode_of_admission, coaching_opted=False, car_opted=False, branch='bhogram', conn=None):
    cls = normalize_class_name(class_name)
    mode = str(mode_of_admission).strip().lower()
    
    take_school = 1
    take_coaching = 0
    take_day_hostel = 0
    
    if 'day hostel' in mode or mode == 'day hostel' or 'hostel' in mode:
        take_school = 0
        take_day_hostel = 1
    elif 'coaching' in mode or coaching_opted:
        take_school = 1
        take_coaching = 1
        
    fake_student = {
        'class': cls,
        'branch': branch,
        'take_school': take_school,
        'take_coaching': take_coaching,
        'take_day_hostel': take_day_hostel,
        'take_car': 1 if car_opted else 0
    }
    
    breakdown = calculate_student_fees_breakdown(fake_student, conn=conn)
    return breakdown['total_fee']

def resolve_student_default_fees(students, conn):
    resolved = []
    for s in students:
        s_dict = dict(s)
        if not s_dict.get('is_custom_fee'):
            bd = calculate_student_fees_breakdown({
                'class': s_dict.get('class'),
                'branch': s_dict.get('branch') or 'bhogram',
                'take_school': s_dict.get('take_school') if s_dict.get('take_school') is not None else 1,
                'take_coaching': s_dict.get('take_coaching') or 0,
                'take_day_hostel': s_dict.get('take_day_hostel') or 0,
                'take_car': s_dict.get('take_car') or 0,
                'is_custom_fee': 0
            }, conn)
            s_dict['monthly_fee'] = bd['total_fee']
            
            cls_name = s_dict.get('class')
            branch = s_dict.get('branch') or 'bhogram'
            a_fee = 0.0
            r_fee = 0.0
            if cls_name:
                cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
                if cls_row:
                    if s_dict.get('take_day_hostel'):
                        a_fee = cls_row['admission_fee_hostel'] if cls_row else 0.0
                        r_fee = cls_row['readmission_fee_hostel'] if cls_row else 0.0
                    elif s_dict.get('take_coaching'):
                        a_fee = cls_row['admission_fee_coaching'] if cls_row else 0.0
                        r_fee = cls_row['readmission_fee_coaching'] if cls_row else 0.0
                    elif s_dict.get('take_school') if s_dict.get('take_school') is not None else 1:
                        a_fee = cls_row['admission_fee'] if cls_row else 0.0
                        r_fee = cls_row['readmission_fee_school'] if cls_row else 0.0
            s_dict['admission_fee'] = a_fee
            s_dict['readmission_fee'] = r_fee
        resolved.append(s_dict)
    return resolved


def adjust_dues_for_enrollment_change(conn, user_id, old_type, new_type):
    """
    Automated background calculation that adjusts the ledger if a student switches categories mid-month.
    """
    from datetime import datetime
    import calendar
    
    if old_type == new_type:
        return
        
    student = conn.execute("SELECT * FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
    if not student:
        return
        
    now = datetime.now()
    day = now.day
    _, total_days = calendar.monthrange(now.year, now.month)
    
    remaining_days = total_days - day + 1
    if remaining_days <= 0:
        return
        
    old_student_fake = dict(student)
    old_student_fake['enrollment_type'] = old_type
    old_breakdown = calculate_student_fees_breakdown(old_student_fake)
    old_monthly_fee = old_breakdown['total_fee']
    old_daily_rate = old_monthly_fee / total_days
    
    new_student_fake = dict(student)
    new_student_fake['enrollment_type'] = new_type
    new_breakdown = calculate_student_fees_breakdown(new_student_fake)
    new_monthly_fee = new_breakdown['total_fee']
    new_daily_rate = new_monthly_fee / total_days
    
    adjustment = (new_daily_rate - old_daily_rate) * remaining_days
    adjustment = round(adjustment, 2)
    
    if adjustment != 0.0:
        conn.execute('''
            UPDATE student_info
            SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
            WHERE user_id = ?
        ''', (adjustment, user_id))
        
        print(f" [PRO-RATA ADJUSTMENT] Student {user_id} switched from '{old_type}' to '{new_type}'. Adjusted remaining dues by ₹{adjustment} (for {remaining_days}/{total_days} days remaining).")
        send_activity_notification("Pro-Rata Fee Adjustment", f"Adjusted remaining dues for Student ID {user_id} by ₹{adjustment} due to enrollment change from '{old_type}' to '{new_type}' mid-month.")

def allocate_payment_components(conn, student_id, paid_amount):
    """
    Allocates paid_amount to school_revenue, hostel_revenue, coaching_revenue, tax_amount, and readmission_revenue
    by tracing the student's unpaid ledger entries that will be paid off by this amount.
    """
    student = conn.execute("SELECT * FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
    if not student:
        return float(paid_amount), 0.0, 0.0, 0.0, 0.0, 'Day School Only'
        
    student_dict = dict(student)
    e_type = student_dict.get('enrollment_type') or 'Day School Only'
    
    # Fetch student's unpaid ledger entries
    unpaid_entries = conn.execute('''
        SELECT id, amount, fee_type, branch 
        FROM student_ledger 
        WHERE student_id = ? AND status = 'Unpaid/Pending'
        ORDER BY id ASC
    ''', (student_id,)).fetchall()
    
    school_rev = 0.0
    hostel_rev = 0.0
    coaching_rev = 0.0
    readmission_rev = 0.0
    tax_amt = 0.0
    
    remaining_payment = float(paid_amount)
    
    # We will compute breakdown to get tax rates
    breakdown = calculate_student_fees_breakdown(student_dict)
    hostel_tax_rate = breakdown.get('hostel_tax_rate', 0.05)
    
    for entry in unpaid_entries:
        if remaining_payment <= 0:
            break
            
        entry_amount = float(entry['amount'])
        allocated_amount = min(remaining_payment, entry_amount)
        remaining_payment -= allocated_amount
        
        fee_type = entry['fee_type']
        
        if fee_type == 'Re-admission Fee':
            readmission_rev += allocated_amount
        elif fee_type == 'Monthly Hostel Fee':
            tax = allocated_amount * (hostel_tax_rate / (1.0 + hostel_tax_rate))
            tax_amt += tax
            hostel_rev += (allocated_amount - tax)
        elif fee_type == 'Monthly Coaching Fee':
            coaching_rev += allocated_amount
        elif fee_type in ['Monthly Tuition Fee', 'Monthly Transport Fee', 'Admission Fee']:
            school_rev += allocated_amount
        else:
            school_rev += allocated_amount
            
    # If there is any remaining payment (overpayment beyond current unpaid ledger),
    # allocate it using the standard proportional breakdown on the monthly fees
    if remaining_payment > 0:
        total_monthly = breakdown['total_fee']
        if total_monthly > 0.0:
            ratio = remaining_payment / total_monthly
            
            school_total_comp = (breakdown['tuition_fee'] + breakdown['transport_fee'] + breakdown['lab_library_fee'] - breakdown['academic_discount'])
            hostel_total_comp = (breakdown['room_rent'] + breakdown['mess_food_charges'] + breakdown['utility_cost'] + breakdown['security_deposit'])
            coaching_total_comp = (breakdown['coaching_combo_fee'] + breakdown['study_material_charges'] + breakdown['exam_test_series_fee'] - breakdown['combo_discount'])
            
            school_share = school_total_comp * ratio
            hostel_share = hostel_total_comp * ratio
            coaching_share = coaching_total_comp * ratio
            
            school_tax_rate = breakdown['school_tax_rate']
            hostel_tax_rate = breakdown['hostel_tax_rate']
            coaching_tax_rate = breakdown['coaching_tax_rate']
            
            school_tax = school_share * (school_tax_rate / (1.0 + school_tax_rate))
            hostel_tax = hostel_share * (hostel_tax_rate / (1.0 + hostel_tax_rate))
            coaching_tax = coaching_share * (coaching_tax_rate / (1.0 + coaching_tax_rate))
            
            tax_amt += (school_tax + hostel_tax + coaching_tax)
            school_rev += (school_share - school_tax)
            hostel_rev += (hostel_share - hostel_tax)
            coaching_rev += (coaching_share - coaching_tax)
            
            if student_dict.get('take_car'):
                car_share = 400.0 * ratio
                school_rev += car_share
        else:
            school_rev += remaining_payment
            
    return round(school_rev, 2), round(hostel_rev, 2), round(coaching_rev, 2), round(tax_amt, 2), round(readmission_rev, 2), e_type






VALID_ROLES = {'admin', 'teacher', 'student'}
PRIVATE_PATH_PREFIXES = ('/dashboard', '/admin', '/upload', '/profile')
PASSWORD_HASH_PREFIXES = ('scrypt:', 'pbkdf2:', 'argon2:')
ADMIN_SECURITY_KEY = os.getenv('ADMIN_SECURITY_KEY') or os.getenv('REGISTRATION_SECURITY_KEY')
DEFAULT_ADMIN_PASSWORD = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin123')

# Email Configuration
SENDER_EMAIL = os.getenv('MAIL_USERNAME', "missionalhidayet@gmail.com")
SENDER_PASSWORD = os.getenv('MAIL_PASSWORD', "kvmwecfrzqbnrbxb")
MAIL_SERVER = os.getenv('MAIL_SERVER', "smtp.gmail.com")
MAIL_PORT = os.getenv('MAIL_PORT')  # will be parsed dynamically inside send_otp_email
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'false').lower() == 'true'
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'true').lower() == 'true'
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')

# Helper: Real Email Sender for OTP (HTTP API to bypass port blocking)
def _send_otp_email_sync(to_email, otp):
    subject = "AHM Login Verification Code"
    body = f"<p>Your OTP Verification Code is: <strong>{otp}</strong></p><p>Do not share this code with anyone.</p>"
    
    brevo_api_key = os.getenv('BREVO_API_KEY')
    if not brevo_api_key:
        print(f" [EMAIL ERROR] BREVO_API_KEY missing in .env! OTP code is: {otp}")
        return False
        
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "Mission Al Hidayet", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": body
    }
    
    try:
        print(f" [EMAIL] Sending OTP via Brevo API to {to_email}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [201, 202, 200]:
            print(f" [EMAIL SENT] OTP {otp} sent successfully to {to_email}")
            return True
        else:
            print(f" [EMAIL ERROR] Brevo API rejected email: {response.text}")
            return False
    except Exception as e:
        print(f" [EMAIL ERROR] Failed to send OTP to {to_email} via Brevo HTTP API: {e}")
        return False

import threading

def send_otp_email(to_email, otp):
    print(f" [EMAIL QUEUED] Queueing OTP email delivery to {to_email} in background thread...")
    threading.Thread(target=_send_otp_email_sync, args=(to_email, otp), daemon=True).start()
    return True

def _send_email_raw(subject, body, to_email="missionalhidayet@gmail.com"):
    brevo_api_key = os.getenv('BREVO_API_KEY')
    if not brevo_api_key:
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }
    # Wrap standard text body in HTML tags if it isn't already
    html_content = body if "<" in body else f"<pre>{body}</pre>"
    payload = {
        "sender": {"name": "Mission Al Hidayet", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [201, 202, 200]:
            return True
        else:
            print(f" [EMAIL ERROR] Connection failed (Brevo API): {response.text}")
            return False
    except Exception as e:
        print(f" [EMAIL ERROR] Connection failed to Brevo API: {e}")
        return False

def _send_activity_email_sync(subject, body):
    dest_email = get_school_setting('log_destination_email', 'missionalhidayet@gmail.com')
    # Try sending the email
    success = _send_email_raw(subject, body, to_email=dest_email)
    
    if success:
        print(f" [EMAIL SENT] Activity notification sent successfully to {dest_email}")
        
        # Flush any previously failed pending logs
        try:
            conn = get_db_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT,
                    body TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            pending = conn.execute("SELECT id, subject, body FROM pending_activity_logs ORDER BY id ASC").fetchall()
            if pending:
                print(f" [EMAIL QUEUE] Found {len(pending)} pending failed activity logs. Retrying...")
                for row in pending:
                    pid, psub, pbody = row[0], row[1], row[2]
                    if _send_email_raw(psub, pbody, to_email=dest_email):
                        conn.execute("DELETE FROM pending_activity_logs WHERE id = ?", (pid,))
                        conn.commit()
                        print(f" [EMAIL QUEUE] Successfully retried and sent pending log ID {pid}")
                    else:
                        print(f" [EMAIL QUEUE] Retry failed for pending log ID {pid}. Stopping queue flush.")
                        break
            conn.close()
        except Exception as db_err:
            print(f" [EMAIL QUEUE ERROR] Error flushing pending activity logs: {db_err}")
        return True
    else:
        # Save to database to retry later
        try:
            conn = get_db_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT,
                    body TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute("INSERT INTO pending_activity_logs (subject, body) VALUES (?, ?)", (subject, body))
            conn.commit()
            conn.close()
            print(" [EMAIL QUEUE] Network unreachable/error. Saved activity email to pending database queue for later retry.")
        except Exception as db_err:
            print(f" [EMAIL QUEUE ERROR] Failed to save pending activity log to DB: {db_err}")
        return False

def send_activity_notification(action, details):
    username = session.get('user', 'Anonymous')
    role = session.get('role', 'Unknown')
    branch = session.get('branch', 'Not set')
    ip = request.remote_addr if request else 'Unknown'
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    subject = f"AHM Activity Notification: {action}"
    body = f"""Institute Activity Log Info:
----------------------------
Action: {action}
User: {username} ({role})
Branch: {branch}
IP Address: {ip}
Timestamp: {timestamp}

Details:
{details}
----------------------------"""
    dest_email = get_school_setting('log_destination_email', 'missionalhidayet@gmail.com')
    print(f" [EMAIL QUEUED] Queueing Activity email delivery for '{action}' to {dest_email}...")
    threading.Thread(target=_send_activity_email_sync, args=(subject, body), daemon=True).start()
    return True

def _send_review_otp_email_sync(to_email, otp):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print(f" [EMAIL ERROR] Missing email credentials. Review OTP code is: {otp}")
        return False
        
    subject = "AHM Review Submission Verification Code"
    body = f"Your Review Verification Code is: {otp}\n\nVerify your email to complete submitting your review."
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    server_host = MAIL_SERVER
    port_env = MAIL_PORT
    use_ssl = MAIL_USE_SSL
    use_tls = MAIL_USE_TLS
    
    if port_env:
        try:
            port = int(port_env)
        except ValueError:
            port = 465 if use_ssl else (587 if use_tls else 25)
    else:
        port = 465 if use_ssl else (587 if use_tls else 25)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(server_host, port, timeout=10) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(server_host, port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        print(f" [EMAIL SENT] Review OTP {otp} sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f" [EMAIL ERROR] Failed to send Review OTP {otp} to {to_email}: {e}")
        # fallback
        if server_host == 'smtp.gmail.com':
            fallback_port = 587 if port == 465 else 465
            fallback_ssl = (fallback_port == 465)
            try:
                if fallback_ssl:
                    with smtplib.SMTP_SSL('smtp.gmail.com', fallback_port, timeout=10) as server:
                        server.login(SENDER_EMAIL, SENDER_PASSWORD)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP('smtp.gmail.com', fallback_port, timeout=10) as server:
                        server.starttls()
                        server.login(SENDER_EMAIL, SENDER_PASSWORD)
                        server.send_message(msg)
                return True
            except Exception as fb_e:
                print(f"Fallback failed: {fb_e}")
        return False

def send_review_otp_email(to_email, otp):
    threading.Thread(target=_send_review_otp_email_sync, args=(to_email, otp), daemon=True).start()
    return True

def _send_notification_email_sync(to_email, subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print(f" [EMAIL ERROR] Missing email credentials for notification: {to_email}")
        return False
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    server_host = MAIL_SERVER
    port_env = MAIL_PORT
    use_ssl = MAIL_USE_SSL
    use_tls = MAIL_USE_TLS
    
    if port_env:
        try:
            port = int(port_env)
        except ValueError:
            port = 465 if use_ssl else (587 if use_tls else 25)
    else:
        port = 465 if use_ssl else (587 if use_tls else 25)

    try:
        print(f" [EMAIL] Attempting connection to {server_host}:{port} (SSL={use_ssl}, TLS={use_tls}) for notification...")
        if use_ssl:
            with smtplib.SMTP_SSL(server_host, port, timeout=10) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(server_host, port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        print(f" [EMAIL SENT] Status notification email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f" [EMAIL ERROR] Failed to send status notification to {to_email} via {server_host}:{port}: {e}")
        
        # Fallback for Gmail
        if server_host == 'smtp.gmail.com':
            fallback_port = 587 if port == 465 else 465
            fallback_ssl = (fallback_port == 465)
            print(f" [EMAIL FALLBACK] Attempting automatic fallback connection to smtp.gmail.com:{fallback_port}...")
            try:
                if fallback_ssl:
                    with smtplib.SMTP_SSL('smtp.gmail.com', fallback_port, timeout=10) as server:
                        server.login(SENDER_EMAIL, SENDER_PASSWORD)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP('smtp.gmail.com', fallback_port, timeout=10) as server:
                        server.starttls()
                        server.login(SENDER_EMAIL, SENDER_PASSWORD)
                        server.send_message(msg)
                print(f" [EMAIL SENT] Status notification sent successfully to {to_email} via fallback")
                return True
            except Exception as fallback_err:
                print(f" [EMAIL ERROR] Fallback failed for status notification to {to_email}: {fallback_err}")
        return False

def send_notification_email(to_email, subject, body):
    print(f" [EMAIL QUEUED] Queueing notification email delivery to {to_email} in background thread...")
    threading.Thread(target=_send_notification_email_sync, args=(to_email, subject, body), daemon=True).start()
    return True


def send_otp_sms(phone_number, otp):
    """
    Draft SMS Sender for OTP.
    To use this, you need to buy SMS credits from an SMS Gateway provider.
    Recommended providers:
    1. Fast2SMS (https://www.fast2sms.com/) - Simple and cheap for India.
    2. MSG91 (https://msg91.com/) - Reliable enterprise service in India.
    3. Twilio (https://www.twilio.com/) - Best international provider.
    
    Example implementation using Fast2SMS:
    import requests
    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "variables_values": otp,
        "route": "otp",
        "numbers": phone_number
    }
    headers = {
        "authorization": "YOUR_FAST2SMS_API_KEY"
    }
    response = requests.post(url, data=payload, headers=headers)
    return response.json().get('return', False)
    """
    print(f" [SMS SENT] OTP {otp} sent to phone number {phone_number}")
    return True

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def generate_unique_student_code(c):
    while True:
        code = "AHM-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not c.execute("SELECT user_id FROM student_info WHERE unique_code = ?", (code,)).fetchone():
            return code

def get_db_connection():
    from flask import g, has_request_context
    if has_request_context() and 'db_conn' in g:
        return g.db_conn

    if DATABASE_URL and (DATABASE_URL.startswith("libsql://") or DATABASE_URL.startswith("https://") or DATABASE_URL.startswith("http://")):
        import base64
        import requests
        
        class HttpLibsqlRow:
            def __init__(self, cols, row_values):
                self._row = tuple(row_values)
                self._columns = cols
            def __getitem__(self, key):
                if isinstance(key, str):
                    try:
                        return self._row[self._columns.index(key)]
                    except ValueError:
                        raise KeyError(key)
                return self._row[key]
            def keys(self):
                return self._columns
            def __iter__(self):
                return iter(self._row)
            def __len__(self):
                return len(self._row)

        class HttpLibsqlCursor:
            def __init__(self, connection):
                self._connection = connection
                self._results = []
                self._idx = 0
                self.description = None
                self.lastrowid = None
                self.rowcount = -1

            def execute(self, sql, parameters=()):
                self._results, self.description, self.lastrowid, self.rowcount = self._connection._execute_http(sql, parameters)
                self._idx = 0
                return self

            def executemany(self, sql, seq_of_parameters):
                for parameters in seq_of_parameters:
                    self.execute(sql, parameters)
                return self

            def fetchone(self):
                if self._idx < len(self._results):
                    row = self._results[self._idx]
                    self._idx += 1
                    return row
                return None

            def fetchall(self):
                res = self._results[self._idx:]
                self._idx = len(self._results)
                return res

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.close()

            def __iter__(self):
                while True:
                    row = self.fetchone()
                    if row is None:
                        break
                    yield row

        class HttpLibsqlConnection:
            def __init__(self, database_url, auth_token):
                self.database_url = database_url
                self.auth_token = auth_token
                self.row_factory = None
                self.http_url = database_url.replace("libsql://", "https://")
                if not self.http_url.startswith("https://") and not self.http_url.startswith("http://"):
                    self.http_url = "https://" + self.http_url
                self.baton = None
                self.in_transaction = False

            def cursor(self):
                return HttpLibsqlCursor(self)

            def execute(self, sql, parameters=()):
                sql_upper = sql.strip().upper()
                is_write = any(sql_upper.startswith(prefix) for prefix in ["INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"])
                if is_write and not self.in_transaction:
                    self._execute_http("BEGIN")
                    self.in_transaction = True

                cursor = self.cursor()
                cursor.execute(sql, parameters)
                return cursor

            def executemany(self, sql, seq_of_parameters):
                sql_upper = sql.strip().upper()
                is_write = any(sql_upper.startswith(prefix) for prefix in ["INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"])
                if is_write and not self.in_transaction:
                    self._execute_http("BEGIN")
                    self.in_transaction = True

                cursor = self.cursor()
                cursor.executemany(sql, seq_of_parameters)
                return cursor

            def executescript(self, sql_script):
                if not self.in_transaction:
                    self._execute_http("BEGIN")
                    self.in_transaction = True
                cursor = self.cursor()
                for statement in sql_script.split(';'):
                    if statement.strip():
                        cursor.execute(statement)
                return cursor

            def commit(self):
                if self.in_transaction:
                    try:
                        self._execute_http("COMMIT")
                    finally:
                        self.in_transaction = False

            def rollback(self):
                if self.in_transaction:
                    try:
                        self._execute_http("ROLLBACK")
                    finally:
                        self.in_transaction = False

            def close(self):
                if self.in_transaction:
                    try:
                        self._execute_http("ROLLBACK")
                    except Exception:
                        pass
                    self.in_transaction = False
                
                if self.baton:
                    try:
                        headers = {
                            "Authorization": f"Bearer {self.auth_token}",
                            "Content-Type": "application/json"
                        }
                        url = f"{self.http_url.rstrip('/')}/v2/pipeline"
                        payload = {
                            "baton": self.baton,
                            "requests": [{"type": "close"}]
                        }
                        turso_session.post(url, json=payload, headers=headers, timeout=5)
                    except Exception:
                        pass
                    self.baton = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    self.rollback()
                else:
                    self.commit()
                self.close()

            def _execute_http_internal(self, sql, parameters=()):
                def _make_value(val):
                    if val is None:
                        return {"type": "null"}
                    elif isinstance(val, bool):
                        return {"type": "integer", "value": "1" if val else "0"}
                    elif isinstance(val, int):
                        return {"type": "integer", "value": str(val)}
                    elif isinstance(val, float):
                        return {"type": "float", "value": val}
                    elif isinstance(val, (bytes, bytearray)):
                        return {"type": "blob", "value": base64.b64encode(val).decode('utf-8')}
                    else:
                        return {"type": "text", "value": str(val)}
                
                stmt = {"sql": sql}
                if isinstance(parameters, dict):
                    named_args = []
                    for name, val in parameters.items():
                        name_str = str(name)
                        if not name_str.startswith((':', '@', '$')):
                            name_str = ':' + name_str
                        named_args.append({
                            "name": name_str,
                            "value": _make_value(val)
                        })
                    stmt["named_args"] = named_args
                else:
                    args = [_make_value(val) for val in parameters]
                    stmt["args"] = args

                payload = {
                    "requests": [
                        {
                            "type": "execute",
                            "stmt": stmt
                        }
                    ]
                }
                if self.baton:
                    payload["baton"] = self.baton
                
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                }
                
                proxies = {
                    "http": os.environ.get("http_proxy"),
                    "https": os.environ.get("https_proxy")
                }
                
                url = f"{self.http_url.rstrip('/')}/v2/pipeline"
                
                max_retries = 3
                retry_delay = 1.0
                response = None
                
                import time
                import requests
                for attempt in range(max_retries):
                    try:
                        response = turso_session.post(url, json=payload, headers=headers, proxies=proxies, timeout=15)
                        if response.status_code in [429, 500, 502, 503, 504]:
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                        break
                    except requests.exceptions.RequestException as e:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            raise sqlite3.DatabaseError(f"Turso HTTP connection failed after {max_retries} retries: {str(e)}")
                            
                if response.status_code != 200:
                    raise sqlite3.DatabaseError(f"Turso HTTP error {response.status_code}: {response.text}")
                    
                data = response.json()
                self.baton = data.get("baton")
                
                results = data.get("results", [])
                if not results:
                    raise sqlite3.DatabaseError(f"Turso response missing results: {data}")
                    
                first_res = results[0]
                if first_res.get("type") == "error":
                    err_msg = first_res.get("error", {}).get("message", "Unknown database error")
                    raise sqlite3.OperationalError(f"Database error: {err_msg}")
                    
                response_obj = first_res.get("response", {})
                if response_obj.get("type") == "error":
                    err_msg = response_obj.get("error", {}).get("message", "Unknown query error")
                    raise sqlite3.OperationalError(f"Query error: {err_msg}")
                    
                result_obj = response_obj.get("result", {})
                
                raw_cols = result_obj.get("cols", [])
                cols = []
                for c in raw_cols:
                    if isinstance(c, dict):
                        cols.append(c.get("name", ""))
                    else:
                        cols.append(str(c))
                        
                description = [(name, None, None, None, None, None, None) for name in cols] if cols else None
                
                raw_rows = result_obj.get("rows", [])
                rows = []
                for row in raw_rows:
                    parsed_row_values = []
                    for cell in row:
                        if isinstance(cell, dict):
                            t = cell.get("type")
                            v = cell.get("value")
                            if t == "null":
                                parsed_row_values.append(None)
                            elif t == "integer":
                                parsed_row_values.append(int(v) if v is not None else None)
                            elif t == "float":
                                parsed_row_values.append(float(v) if v is not None else None)
                            elif t == "text":
                                parsed_row_values.append(str(v) if v is not None else None)
                            elif t == "blob":
                                parsed_row_values.append(base64.b64decode(v) if v is not None else None)
                            else:
                                parsed_row_values.append(v)
                        else:
                            parsed_row_values.append(cell)
                    rows.append(HttpLibsqlRow(cols, parsed_row_values))
                    
                affected_row_count = result_obj.get("affected_row_count", -1)
                last_insert_rowid = result_obj.get("last_insert_rowid")
                if last_insert_rowid is not None:
                    try:
                        last_insert_rowid = int(last_insert_rowid)
                    except ValueError:
                        pass
                        
                return rows, description, last_insert_rowid, affected_row_count

            def _execute_http(self, sql, parameters=()):
                try:
                    return self._execute_http_internal(sql, parameters)
                except Exception as e:
                    err_str = str(e)
                    if "stream not found" in err_str and self.baton:
                        print(" [Turso HTTP Connection] Stream expired/not found. Retrying query with a fresh stream...")
                        self.baton = None
                        self.in_transaction = False
                        try:
                            return self._execute_http_internal(sql, parameters)
                        except Exception:
                            self.baton = None
                            self.in_transaction = False
                            raise
                    else:
                        self.baton = None
                        self.in_transaction = False
                        raise

        conn = HttpLibsqlConnection(DATABASE_URL, DATABASE_AUTH_TOKEN)
    else:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
    
    from flask import g, has_request_context
    if has_request_context():
        g.db_conn = conn
        if 'db_connections' not in g:
            g.db_connections = []
        g.db_connections.append(conn)
        
    return conn


@app.teardown_appcontext
def teardown_db_connections(exception):
    from flask import g, has_request_context
    if has_request_context() and 'db_connections' in g:
        for conn in g.db_connections:
            try:
                conn.close()
            except Exception:
                pass

def sync_teacher_assigned_classes_string_from_db(conn, teacher_id):
    # Fetch all current assignments for the teacher from teacher_subjects
    rows = conn.execute('''
        SELECT ts.class_name as class, s.name as subject_name
        FROM teacher_subjects ts
        JOIN subjects s ON ts.subject_id = s.id
        WHERE ts.teacher_id = ?
        ORDER BY ts.class_name, s.name
    ''', (teacher_id,)).fetchall()
    
    if not rows:
        new_val = None
    else:
        entries = []
        for r in rows:
            entries.append(f"Class {r['class']}: {r['subject_name']}")
        new_val = ", ".join(entries)
        
    conn.execute("UPDATE teacher_info SET assigned_classes = ? WHERE user_id = ?", (new_val, teacher_id))

def sync_teacher_subjects_from_string(conn, teacher_id, assigned_classes_str):
    teacher_row = conn.execute("SELECT username FROM users WHERE id = ?", (teacher_id,)).fetchone()
    if not teacher_row:
        return
    teacher_username = teacher_row['username']
    
    import re
    valid_assignments = set()
    if assigned_classes_str:
        parts = [p.strip() for p in assigned_classes_str.split(',')]
        for part in parts:
            match = re.match(r'^Class\s+(.*?):\s+(.*)$', part, re.IGNORECASE)
            if match:
                class_name = match.group(1).strip()
                subject_name = match.group(2).strip()
                valid_assignments.add((class_name.lower(), subject_name.lower(), class_name, subject_name))

    # Update teacher_subjects
    conn.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (teacher_id,))
    for c_lower, s_lower, orig_c, orig_s in valid_assignments:
        subj_row = conn.execute("SELECT id FROM subjects WHERE LOWER(name) = ?", (s_lower,)).fetchone()
        if subj_row:
            try:
                conn.execute("INSERT INTO teacher_subjects (teacher_id, class_name, subject_id) VALUES (?, ?, ?)", (teacher_id, orig_c, subj_row['id']))
            except Exception:
                pass
        
    # Cascade to class_routine
    teacher_name_row = conn.execute('''
        SELECT COALESCE(ti.full_name, u.username) as name
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.id = ?
    ''', (teacher_id,)).fetchone()
    
    if teacher_name_row:
        t_name = teacher_name_row['name']
        routines = conn.execute("SELECT id, class_name, subject FROM class_routine WHERE LOWER(teacher_name) = LOWER(?)", (t_name,)).fetchall()
        for r in routines:
            rc = r['class_name'].strip().lower() if r['class_name'] else ''
            rs = r['subject'].strip().lower() if r['subject'] else ''
            
            found = False
            for vc, vs, _, _ in valid_assignments:
                if vc == rc and vs == rs:
                    found = True
                    break
            if not found:
                conn.execute("DELETE FROM class_routine WHERE id = ?", (r['id'],))

def add_teacher_assigned_classes_string(conn, teacher_id, class_name, subject_name):
    sync_teacher_assigned_classes_string_from_db(conn, teacher_id)

def remove_teacher_assigned_classes_string(conn, teacher_id, class_name, subject_name):
    # Backward compatible placeholder, callers will delete first then rebuild
    sync_teacher_assigned_classes_string_from_db(conn, teacher_id)

def get_month_sort_key(name):
    if not name:
        return 999
    name_lower = name.lower()
    months_order = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    for idx, month in enumerate(months_order):
        if month in name_lower:
            return idx
    import re
    num_match = re.search(r'\d+', name)
    if num_match:
        return 100 + int(num_match.group())
    return 200
MONTHS_MAP = {
    'january': 'Jan', 'jan': 'Jan',
    'february': 'Feb', 'feb': 'Feb',
    'march': 'Mar', 'mar': 'Mar',
    'april': 'Apr', 'apr': 'Apr',
    'may': 'May',
    'june': 'Jun', 'jun': 'Jun',
    'july': 'Jul', 'jul': 'Jul',
    'august': 'Aug', 'aug': 'Aug',
    'september': 'Sep', 'sep': 'Sep',
    'october': 'Oct', 'oct': 'Oct',
    'november': 'Nov', 'nov': 'Nov',
    'december': 'Dec', 'dec': 'Dec'
}

def normalize_monthly_test_name(term_name):
    if not term_name:
        return term_name
    import re
    term_lower = term_name.lower().strip()
    for month_key, month_abbr in MONTHS_MAP.items():
        if re.search(r'\b' + re.escape(month_key) + r'\b', term_lower):
            return f"Monthly Test {month_abbr}"
    return term_name.strip()

def sync_and_normalize_monthly_tests(conn):
    cursor = conn.cursor()
    
    def get_normalized_name(term_name):
        return normalize_monthly_test_name(term_name)

    # 1. Normalize test names in class_subjects table
    distinct_configs = cursor.execute("SELECT DISTINCT term_name FROM class_subjects").fetchall()
    for row in distinct_configs:
        orig = row['term_name']
        if orig:
            norm = get_normalized_name(orig)
            if norm != orig:
                cursor.execute("UPDATE OR REPLACE class_subjects SET term_name = ? WHERE term_name = ?", (norm, orig))
            
    # 2. Normalize term names in marks table
    distinct_marks_terms = cursor.execute("SELECT DISTINCT term_name FROM marks").fetchall()
    for row in distinct_marks_terms:
        orig = row['term_name']
        if orig:
            norm = get_normalized_name(orig)
            if norm != orig:
                cursor.execute("UPDATE OR REPLACE marks SET term_name = ? WHERE term_name = ?", (norm, orig))
            
    # Helper to check if a term is a monthly test
    def is_monthly_test_local(term_name):
        if not term_name:
            return False
        term_lower = term_name.lower()
        for month_abbr in MONTHS_MAP.values():
            if f"monthly test {month_abbr.lower()}" in term_lower:
                return True
        return 'monthly' in term_lower or 'class test' in term_lower or 'test' in term_lower

    # Clean up monthly tests for art subjects (configs & marks) in batch if they exist
    if cursor.execute("SELECT 1 FROM class_subjects WHERE LOWER(subject_name) LIKE '%art%' AND (LOWER(term_name) LIKE '%monthly%' OR LOWER(term_name) LIKE '%class test%' OR LOWER(term_name) LIKE '%test%') LIMIT 1").fetchone():
        cursor.execute("DELETE FROM class_subjects WHERE LOWER(subject_name) LIKE '%art%' AND (LOWER(term_name) LIKE '%monthly%' OR LOWER(term_name) LIKE '%class test%' OR LOWER(term_name) LIKE '%test%')")
        
    has_art_marks = cursor.execute("""
        SELECT 1 FROM marks 
        WHERE LOWER(subject_name) LIKE '%art%' 
          AND (LOWER(term_name) LIKE '%monthly%' 
               OR LOWER(term_name) LIKE '%class test%' 
               OR LOWER(term_name) LIKE '%test%')
        LIMIT 1
    """).fetchone()
    if has_art_marks:
        cursor.execute("""
            DELETE FROM marks 
            WHERE LOWER(subject_name) LIKE '%art%' 
              AND (LOWER(term_name) LIKE '%monthly%' 
                   OR LOWER(term_name) LIKE '%class test%' 
                   OR LOWER(term_name) LIKE '%test%')
        """)

    # 3. Auto-insert configs for monthly tests in marks table lacking configs
    # Fetch all existing configs into a set for O(1) lookup
    existing_configs = set()
    for r in cursor.execute("SELECT term_name, class_name, subject_name FROM class_subjects").fetchall():
        if r[0] and r[1] and r[2]:
            existing_configs.add((r[0].strip().lower(), r[1].strip().lower(), r[2].strip().lower()))

    # Fetch candidate monthly tests marks rows
    marks_tests = cursor.execute("""
        SELECT DISTINCT term_name, class_name, subject_name, full_marks 
        FROM marks
        WHERE LOWER(subject_name) NOT LIKE '%art%'
          AND (LOWER(term_name) LIKE '%monthly%' 
               OR LOWER(term_name) LIKE '%class test%' 
               OR LOWER(term_name) LIKE '%test%')
    """).fetchall()

    to_insert = []
    inserted_keys = set()
    for row in marks_tests:
        term = row['term_name']
        cls = row['class_name']
        sub = row['subject_name']
        if not term or not cls or not sub:
            continue
            
        normalized_term = get_normalized_name(term)
        key = (normalized_term.strip().lower(), cls.strip().lower(), sub.strip().lower())
        
        if key not in existing_configs and key not in inserted_keys:
            fm = row['full_marks'] if row['full_marks'] is not None else 20.0
            to_insert.append((cls, sub, normalized_term, fm))
            inserted_keys.add(key)
            
    if to_insert:
        cursor.executemany('''
            INSERT INTO class_subjects (class_name, subject_name, term_name, full_marks)
            VALUES (?, ?, ?, ?)
        ''', to_insert)
                
    conn.commit()




def get_razorpay_client():
    if not razorpay or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return None
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def check_password_strength(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if len(password) > 32:
        return False, "Password cannot be longer than 32 characters."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    special_chars = "!@#$%^&*(),.?\":{}|<>"
    if not any(c in special_chars for c in password):
        return False, f"Password must contain at least one special character (e.g. {special_chars})."
    return True, ""

def is_password_hash(value):
    return bool(value) and value.startswith(PASSWORD_HASH_PREFIXES)

def hash_password(raw_password):
    return generate_password_hash(raw_password)

def verify_password(stored_password, candidate_password):
    if not stored_password or not candidate_password:
        return False
    if is_password_hash(stored_password):
        return check_password_hash(stored_password, candidate_password)
    return hmac.compare_digest(stored_password, candidate_password)

def migrate_plaintext_passwords(cursor):
    users = cursor.execute("SELECT id, password FROM users").fetchall()
    for user in users:
        user_id = user['id'] if isinstance(user, sqlite3.Row) else user[0]
        stored_password = user['password'] if isinstance(user, sqlite3.Row) else user[1]
        if stored_password and not is_password_hash(stored_password):
            cursor.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (hash_password(stored_password), user_id)
            )

def upgrade_password_hash(conn, user_id, stored_password, raw_password):
    if stored_password and not is_password_hash(stored_password):
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(raw_password), user_id)
        )
        conn.commit()

def is_safe_next_url(target):
    return bool(target) and target.startswith('/') and not target.startswith('//')

def get_session_user():
    username = session.get('user')
    role = session.get('role')
    if not username or role not in VALID_ROLES:
        return None

    conn = get_db_connection()
    user = conn.execute(
        "SELECT id, username, role, branch FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()

    if not user or user['role'] != role:
        session.clear()
        return None
    return user

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not get_session_user():
            flash('Please login to continue.')
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for('login', user_type='student', next=next_url))
        return view(*args, **kwargs)
    return wrapped_view

def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = get_session_user()
            if not user:
                flash('Please login to continue.')
                next_url = request.full_path if request.query_string else request.path
                return redirect(url_for('login', user_type='student', next=next_url))
            if user['role'] not in allowed_roles:
                flash('You do not have permission to access that page.')
                return redirect(url_for('dashboard'))
            return view(*args, **kwargs)
        return wrapped_view
    return decorator

@app.before_request
def protect_private_paths():
    if request.endpoint == 'static':
        return None
    user = get_session_user()
    if request.path.startswith(PRIVATE_PATH_PREFIXES) and not user:
        flash('Please login to continue.')
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('login', user_type='student', next=next_url))
    return None

def generate_skeleton_html(path):
    p = path.lower()
    
    # 1. Auth & Login/Register Cards Archetype
    if any(x in p for x in ['/login', '/register', '/forgot', '/reset']):
        content = """
        <!-- Auth Page Form Skeleton -->
        <div id="ahm-skeleton-auth" style="display: flex; flex: 1; justify-content: center; align-items: center; background-color: #f8fafc; padding: 20px; border-radius: 12px;">
            <div style="width: 100%; max-width: 440px; background: white; border-radius: 16px; border: 1px solid #e2e8f0; padding: 40px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05); display: flex; flex-direction: column; gap: 25px;">
                <!-- Card Header Logo & Title -->
                <div style="display: flex; flex-direction: column; align-items: center; gap: 12px; margin-bottom: 10px;">
                    <div class="skeleton-pulse" style="width: 70px; height: 70px; background: #e2e8f0; border-radius: 50%;"></div>
                    <div class="skeleton-pulse" style="width: 150px; height: 24px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 220px; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <!-- Form Inputs Placeholders -->
                <div style="display: flex; flex-direction: column; gap: 18px;">
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div class="skeleton-pulse" style="width: 80px; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="width: 100%; height: 44px; background: #e2e8f0; border-radius: 8px;"></div>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div class="skeleton-pulse" style="width: 80px; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="width: 100%; height: 44px; background: #e2e8f0; border-radius: 8px;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 5px;">
                        <div class="skeleton-pulse" style="width: 100px; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    </div>
                </div>
                <!-- Button Placeholder -->
                <div class="skeleton-pulse" style="width: 100%; height: 48px; background: #cbd5e1; border-radius: 8px; margin-top: 10px;"></div>
            </div>
        </div>
        """
        
    # 2. Services Archetype
    elif '/services' in p:
        content = """
        <!-- Services Page Skeleton -->
        <div id="ahm-skeleton-services" style="display: flex; flex-direction: column; gap: 30px; flex: 1;">
            <!-- Title Area Banner -->
            <div style="text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; margin-bottom: 10px;">
                <div class="skeleton-pulse" style="width: 250px; height: 32px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 400px; height: 16px; background: #f1f5f9; border-radius: 4px;"></div>
            </div>
            <!-- 6 Card Grid -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; flex: 1;">
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 12px;"></div>
                    <div class="skeleton-pulse" style="width: 180px; height: 22px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
            </div>
        </div>
        """
        
    # 3. Gallery Archetype
    elif '/gallery' in p:
        content = """
        <!-- Gallery Page Skeleton -->
        <div id="ahm-skeleton-gallery" style="display: flex; flex-direction: column; gap: 25px; flex: 1;">
            <!-- Banner Frame -->
            <div class="skeleton-pulse" style="width: 100%; height: 180px; background: #e2e8f0; border-radius: 12px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 10px;">
                <div style="width: 200px; height: 26px; background: #cbd5e1; border-radius: 6px;"></div>
                <div style="width: 300px; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
            </div>
            <!-- Branch Label -->
            <div class="skeleton-pulse" style="width: 250px; height: 24px; background: #e2e8f0; border-radius: 6px; margin-top: 10px;"></div>
            <!-- Grid of items -->
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 20px;">
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
                <div class="skeleton-pulse" style="height: 180px; background: #e2e8f0; border-radius: 12px;"></div>
            </div>
        </div>
        """
        
    # 4. Grid / Tables / Bulk Marks Archetype
    elif any(x in p for x in ['/bulk-marks', '/fees', '/transaction', '/payment', '/routine', '/marks', '/class-tests', '/exams']):
        content = """
        <!-- Table Grid & Bulk Marks Page Skeleton -->
        <div id="ahm-skeleton-grid" style="display: flex; flex-direction: column; gap: 20px; flex: 1;">
            <!-- Filters / Top Navigation bar -->
            <div style="display: flex; gap: 15px; align-items: center; background: white; border: 1px solid #eef2f6; border-radius: 8px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.01);">
                <div class="skeleton-pulse" style="width: 120px; height: 35px; background: #e2e8f0; border-radius: 6px;"></div>
                <div class="skeleton-pulse" style="width: 150px; height: 35px; background: #e2e8f0; border-radius: 6px;"></div>
                <div class="skeleton-pulse" style="width: 150px; height: 35px; background: #e2e8f0; border-radius: 6px;"></div>
                <div class="skeleton-pulse" style="width: 100px; height: 35px; background: #e2e8f0; border-radius: 6px; margin-left: auto;"></div>
            </div>
            <!-- Grid Table Shell -->
            <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); display: flex; flex-direction: column; gap: 15px; flex: 1; overflow: hidden;">
                <!-- Header row -->
                <div style="display: grid; grid-template-columns: 80px 180px repeat(4, 1fr); gap: 15px; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px;">
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="height: 18px; background: #cbd5e1; border-radius: 4px;"></div>
                </div>
                <!-- Data lines placeholder -->
                <div style="display: flex; flex-direction: column; gap: 18px; flex: 1; overflow: hidden;">
                    <div style="display: grid; grid-template-columns: 80px 180px repeat(4, 1fr); gap: 15px; border-bottom: 1px solid #f8fafc; padding-bottom: 10px;">
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 80px 180px repeat(4, 1fr); gap: 15px; border-bottom: 1px solid #f8fafc; padding-bottom: 10px;">
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 80px 180px repeat(4, 1fr); gap: 15px; border-bottom: 1px solid #f8fafc; padding-bottom: 10px;">
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: 80px 180px repeat(4, 1fr); gap: 15px; border-bottom: 1px solid #f8fafc; padding-bottom: 10px;">
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 14px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                        <div class="skeleton-pulse" style="height: 28px; background: #f1f5f9; border-radius: 4px;"></div>
                    </div>
                </div>
            </div>
        </div>
        """
        
    # 5. Landing / Home Page Archetype
    elif p == '/' or p == '/home' or not p:
        content = """
        <!-- Landing Page Skeleton -->
        <div id="ahm-skeleton-home" style="display: flex; flex-direction: column; gap: 30px; flex: 1; overflow: hidden;">
            <!-- Large Hero Banner -->
            <div class="skeleton-pulse" style="width: 100%; height: 320px; background: #e2e8f0; border-radius: 12px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 15px;">
                <div style="width: 50%; height: 32px; background: #cbd5e1; border-radius: 8px;"></div>
                <div style="width: 35%; height: 18px; background: #cbd5e1; border-radius: 6px;"></div>
                <div style="width: 120px; height: 40px; background: #cbd5e1; border-radius: 20px; margin-top: 10px;"></div>
            </div>
            <!-- Three grid cards below hero -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 50%;"></div>
                    <div class="skeleton-pulse" style="width: 70%; height: 20px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 50%;"></div>
                    <div class="skeleton-pulse" style="width: 70%; height: 20px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
                <div style="background: white; border: 1px solid #eef2f6; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                    <div class="skeleton-pulse" style="width: 50px; height: 50px; background: #e2e8f0; border-radius: 50%;"></div>
                    <div class="skeleton-pulse" style="width: 70%; height: 20px; background: #e2e8f0; border-radius: 6px;"></div>
                    <div class="skeleton-pulse" style="width: 100%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                    <div class="skeleton-pulse" style="width: 90%; height: 14px; background: #f1f5f9; border-radius: 4px;"></div>
                </div>
            </div>
        </div>
        """
        
    # 6. Standard Dashboard / catch-all private subpages archetype
    else:
        content = """
        <!-- Dashboard / Private Subpages Skeleton Layout -->
        <div id="ahm-skeleton-dashboard" style="display: flex; flex: 1; gap: 20px;">
            <!-- Sidebar Skeleton -->
            <div class="skeleton-sidebar" style="width: 240px; display: flex; flex-direction: column; gap: 15px; padding-top: 10px;">
                <div class="skeleton-pulse" style="width: 100%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 90%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 95%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 85%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 90%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 75%; height: 42px; background: #e2e8f0; border-radius: 8px;"></div>
            </div>
            <!-- Main Content Skeleton -->
            <div style="flex: 1; display: flex; flex-direction: column; gap: 20px;">
                <!-- Metrics Dashboard Row -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px;">
                    <div class="skeleton-pulse" style="height: 120px; background: #e2e8f0; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="width: 40%; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
                        <div style="width: 70%; height: 28px; background: #cbd5e1; border-radius: 6px;"></div>
                    </div>
                    <div class="skeleton-pulse" style="height: 120px; background: #e2e8f0; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="width: 40%; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
                        <div style="width: 70%; height: 28px; background: #cbd5e1; border-radius: 6px;"></div>
                    </div>
                    <div class="skeleton-pulse" style="height: 120px; background: #e2e8f0; border-radius: 12px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="width: 40%; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
                        <div style="width: 70%; height: 28px; background: #cbd5e1; border-radius: 6px;"></div>
                    </div>
                </div>
                <!-- Main body big card layout -->
                <div class="skeleton-pulse" style="flex: 1; min-height: 250px; background: #e2e8f0; border-radius: 12px; padding: 25px; display: flex; flex-direction: column; gap: 15px;">
                    <div style="width: 200px; height: 22px; background: #cbd5e1; border-radius: 6px;"></div>
                    <div style="width: 100%; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
                    <div style="width: 95%; height: 14px; background: #cbd5e1; border-radius: 4px;"></div>
                </div>
            </div>
        </div>
        """
        
    wrapper = f"""
    <div id="ahm-skeleton-loader" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: #f6f8fb;
        z-index: 999999;
        display: flex;
        flex-direction: column;
        padding: 20px;
        box-sizing: border-box;
        transition: opacity 0.3s ease-out, visibility 0.3s ease-out;
    ">
        <!-- Header Skeleton -->
        <div style="display: flex; justify-content: space-between; align-items: center; height: 60px; margin-bottom: 25px; border-bottom: 2px solid #eef6f7; padding-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div class="skeleton-pulse" style="width: 40px; height: 40px; background: #e2e8f0; border-radius: 8px;"></div>
                <div class="skeleton-pulse" style="width: 160px; height: 24px; background: #e2e8f0; border-radius: 6px;"></div>
            </div>
            <div style="display: flex; gap: 15px; align-items: center;">
                <div class="skeleton-pulse" style="width: 80px; height: 35px; background: #e2e8f0; border-radius: 20px;"></div>
                <div class="skeleton-pulse" style="width: 35px; height: 35px; background: #e2e8f0; border-radius: 50%;"></div>
            </div>
        </div>
        {content}
    </div>
    """
    return wrapper

@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    
    if response.content_type and response.content_type.startswith('text/html'):
        response.headers.setdefault('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        response.headers.setdefault('Pragma', 'no-cache')
        
        if response.status_code == 200:
            try:
                data = response.get_data(as_text=True)
                
                # 1. Inject Styles in <head>
                css_inject = """
                <style>
                    @keyframes skeleton-glow {
                        0% { opacity: 0.6; }
                        50% { opacity: 1; }
                        100% { opacity: 0.6; }
                    }
                    .skeleton-pulse {
                        animation: skeleton-glow 1.5s ease-in-out infinite;
                    }
                    @media (max-width: 768px) {
                        .skeleton-sidebar {
                            display: none !important;
                        }
                    }
                </style>
                """
                
                # 2. Generate Page-Specific Skeleton HTML inside <body>
                skeleton_html = generate_skeleton_html(request.path)
                
                # 3. Inject JS to hide loader smoothly
                js_inject = """
                <script>
                    (function() {
                        function hideSkeleton() {
                            var loader = document.getElementById('ahm-skeleton-loader');
                            if (loader) {
                                loader.style.opacity = '0';
                                loader.style.visibility = 'hidden';
                                setTimeout(function() {
                                    if (loader.parentNode) {
                                        loader.parentNode.removeChild(loader);
                                    }
                                }, 300);
                            }
                        }
                        if (document.readyState === 'complete') {
                            hideSkeleton();
                        } else {
                            window.addEventListener('load', hideSkeleton);
                            setTimeout(hideSkeleton, 1500);
                        }
                    })();
                </script>
                """
                
                import re
                
                # Inject CSS in head
                head_match = re.search(r'(</head>)', data, re.IGNORECASE)
                if head_match:
                    data = data.replace(head_match.group(1), css_inject + "\n" + head_match.group(1))
                    
                # Inject HTML in body
                body_match = re.search(r'(<body[^>]*>)', data, re.IGNORECASE)
                if body_match:
                    data = data.replace(body_match.group(1), body_match.group(1) + "\n" + skeleton_html)
                    
                # Inject JS in body close
                close_body_match = re.search(r'(</body>)', data, re.IGNORECASE)
                if close_body_match:
                    data = data.replace(close_body_match.group(1), js_inject + "\n" + close_body_match.group(1))
                    
                response.set_data(data)
            except Exception as e:
                print(f" [SKELETON INJECTION ERROR] Failed to inject loader: {e}")
                
    if request.is_secure or app.config.get('SESSION_COOKIE_SECURE'):
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response

def seed_default_subjects(conn):
    """
    Auto-populates the subjects table with default subjects for classes that exist in the classes table,
    and removes subjects/routines/assignments for classes that no longer exist.
    """
    return



def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # One-time database reset for starting from scratch
    import os
    cleaned_flag = os.path.join(app.root_path, 'ahm.db.cleaned_v5')
    if not os.path.exists(cleaned_flag):
        try:
            reset_statements = [
                "DROP TABLE IF EXISTS subjects",
                "DROP TABLE IF EXISTS teacher_subjects",
                "DROP TABLE IF EXISTS teacher_assignments",
                "DROP TABLE IF EXISTS class_subjects",
                "DROP TABLE IF EXISTS class_test_configs",
                "DELETE FROM classes",
                "DELETE FROM class_teachers",
                "DELETE FROM marks",
                "DELETE FROM class_routine",
                "DELETE FROM exam_locks",
                "DELETE FROM exam_schedules"
            ]
            for stmt in reset_statements:
                try:
                    c.execute(stmt)
                except Exception as stmt_err:
                    print(f" [DB RESET STMT WARNING] Statement '{stmt}' failed (safe to ignore if table doesn't exist): {stmt_err}")
            conn.commit()
            with open(cleaned_flag, 'w') as f:
                f.write('cleaned')
            print(" [DB RESET] Database tables purged successfully for starting from zero.")
        except Exception as reset_err:
            print(f" [DB RESET ERROR] {reset_err}")
            conn.rollback()
            
    # Tables creation
    c.execute('''
        CREATE TABLE IF NOT EXISTS custom_class_fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch TEXT DEFAULT 'bhogram',
            class_name TEXT NOT NULL,
            fee_type TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            security_key TEXT NOT NULL,
            branch TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS student_info (
            user_id INTEGER PRIMARY KEY,
            branch TEXT,
            class TEXT,
            roll_number TEXT,
            aadhaar_number TEXT,
            phone_number TEXT,
            guardian_name TEXT,
            mothers_name TEXT,
            full_name TEXT,
            dob TEXT,
            section TEXT,
            blood_group TEXT,
            village TEXT,
            post_office TEXT,
            police_station TEXT,
            district TEXT,
            date_of_admission TEXT,
            photo_path TEXT,
            bank_details TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            term_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            obtained_marks REAL NOT NULL,
            full_marks REAL NOT NULL,
            oral_marks REAL DEFAULT 0.0,
            written_marks REAL DEFAULT 0.0,
            ct_marks REAL DEFAULT 0.0,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (uploaded_by) REFERENCES users (id),
            UNIQUE(student_id, term_name, subject_name)
        )
    ''')
    # Migration: add is_absent flag to marks table (safe to run multiple times)
    try:
        c.execute("ALTER TABLE marks ADD COLUMN is_absent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            amount REAL,
            month TEXT,
            year TEXT,
            status TEXT DEFAULT 'Pending',
            paid_at TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            staff_type TEXT NOT NULL,
            salary REAL DEFAULT 0.0,
            phone_number TEXT,
            branch TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL,
            category TEXT,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            branch TEXT,
            proof_path TEXT,
            recipient_type TEXT,
            recipient_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id),
            UNIQUE(teacher_id, class_name, subject_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS class_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            term_name TEXT NOT NULL,
            full_marks REAL,
            oral_limit REAL,
            written_limit REAL,
            ct_limit REAL,
            UNIQUE(class_name, subject_name, term_name)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id),
            UNIQUE(teacher_id, class_name, subject_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            data TEXT,
            status TEXT DEFAULT 'Pending',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            branch TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            branch TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            branch TEXT,
            category TEXT,
            filename TEXT,
            status TEXT DEFAULT 'Pending',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            drive_file_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            full_name TEXT NOT NULL,
            phone_number TEXT,
            qualification TEXT,
            joining_date TEXT,
            address TEXT,
            photo_path TEXT,
            aadhaar_number TEXT,
            assigned_classes TEXT,
            bank_details TEXT,
            teacher_type TEXT DEFAULT 'Regular Class',
            cv_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    try:
        c.execute("ALTER TABLE teacher_info ADD COLUMN cv_path TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS class_routine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch TEXT,
            class_name TEXT,
            day TEXT,
            start_time TEXT,
            end_time TEXT,
            subject TEXT,
            teacher_name TEXT
        )
    ''')

    try:
        c.execute("ALTER TABLE notices ADD COLUMN photo_path TEXT")
    except sqlite3.OperationalError:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS exam_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch TEXT NOT NULL,
            class_name TEXT NOT NULL,
            term_name TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0,
            UNIQUE(branch, class_name, term_name)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS question_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL,
            term_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            drive_file_id TEXT,
            FOREIGN KEY (uploaded_by) REFERENCES users (id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS exam_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL,
            term_name TEXT NOT NULL,
            branch TEXT NOT NULL,
            schedule_image TEXT,
            schedule_text TEXT,
            UNIQUE(class_name, term_name, branch)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS visitor_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_name TEXT NOT NULL,
            visitor_email TEXT,
            review_text TEXT NOT NULL,
            rating INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_approved INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    c.execute('SELECT COUNT(*) FROM visitor_reviews')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO visitor_reviews (visitor_name, review_text, rating) VALUES (?, ?, ?)",
                  ("Ananya Sharma", "Bhogram Al-Hidayet Mission is a fantastic school. The academic rigor combined with great extracurriculars is amazing.", 5))
        c.execute("INSERT INTO visitor_reviews (visitor_name, review_text, rating) VALUES (?, ?, ?)",
                  ("Rajesh Patel", "Very supportive staff and excellent learning environment. Highly recommended for secondary education.", 5))
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS managing_committee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            designation TEXT NOT NULL,
            order_num INTEGER DEFAULT 0
        )
    ''')
    c.execute('SELECT COUNT(*) FROM managing_committee')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO managing_committee (name, designation, order_num) VALUES (?, ?, ?)",
                  ("Majidur Rahman Chowdhury", "Secretary", 1))
        c.execute("INSERT INTO managing_committee (name, designation, order_num) VALUES (?, ?, ?)",
                  ("Habibur Rahman (Ripon)", "President", 2))
    
    # Class Test Configs table is deprecated and removed
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            branch TEXT NOT NULL,
            admission_fee REAL DEFAULT 0.0,
            admission_fee_coaching REAL DEFAULT 0.0,
            admission_fee_hostel REAL DEFAULT 0.0,
            readmission_fee_school REAL DEFAULT 0.0,
            readmission_fee_coaching REAL DEFAULT 0.0,
            readmission_fee_hostel REAL DEFAULT 0.0,
            monthly_fee REAL DEFAULT 0.0,
            monthly_fee_coaching REAL DEFAULT 0.0,
            hostel_fee REAL DEFAULT 0.0,
            UNIQUE(name, branch)
        )
    ''')
    
    # Migrations for classes table to support branch and hostel_fee columns
    c.execute("PRAGMA table_info(classes)")
    columns = [col[1] for col in c.fetchall()]
    if 'branch' not in columns:
        try:
            c.execute("ALTER TABLE classes RENAME TO classes_old")
            c.execute('''
                CREATE TABLE classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    admission_fee REAL DEFAULT 0.0,
                    admission_fee_coaching REAL DEFAULT 0.0,
                    admission_fee_hostel REAL DEFAULT 0.0,
                    readmission_fee_school REAL DEFAULT 0.0,
                    readmission_fee_coaching REAL DEFAULT 0.0,
                    readmission_fee_hostel REAL DEFAULT 0.0,
                    monthly_fee REAL DEFAULT 0.0,
                    monthly_fee_coaching REAL DEFAULT 0.0,
                    hostel_fee REAL DEFAULT 0.0,
                    UNIQUE(name, branch)
                )
            ''')
            # Copy data for bhogram branch
            c.execute('''
                INSERT INTO classes (name, branch, admission_fee, monthly_fee, hostel_fee)
                SELECT name, 'bhogram', COALESCE(admission_fee, 0.0), COALESCE(monthly_fee, 0.0), 0.0 FROM classes_old
            ''')
            c.execute("DROP TABLE classes_old")
        except Exception as e:
            print(f" [DB MIGRATE] Classes migration failed: {e}")

    # Default fees and classes seeding disabled (start from zero classes)
    pass

    # Registration Documents table
    c.execute('''
        CREATE TABLE IF NOT EXISTS registration_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            file_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('SELECT COUNT(*) FROM registration_documents')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO registration_documents (title, description, file_path) VALUES (?, ?, ?)",
                  ("Society Registration Certificate", "Official registration document of the Bhogram Al-Hidayet Educational Society.", "static/uploads/documents/sample_society_cert.pdf"))
        c.execute("INSERT INTO registration_documents (title, description, file_path) VALUES (?, ?, ?)",
                  ("School Affiliation Board Certificate", "Board of Secondary Education affiliation authorization certificate.", "static/uploads/documents/sample_affiliation.pdf"))
            
    # Dynamic Alter Statements for Schema Migrations
    for table in ['users', 'expenses', 'notices', 'applications']:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN branch TEXT")
            print(f" [DB MIGRATE] Added branch column to {table}")
        except sqlite3.OperationalError:
            pass # Column already exists

    # Migration for expenses to support proof_path
    try:
        c.execute("ALTER TABLE expenses ADD COLUMN proof_path TEXT")
        print(" [DB MIGRATE] Added proof_path column to expenses")
    except sqlite3.OperationalError:
        pass # Column already exists

    # Migration for subjects to support full_marks
    try:
        c.execute("ALTER TABLE subjects ADD COLUMN full_marks REAL DEFAULT 100.0")
        print(" [DB MIGRATE] Added full_marks column to subjects table")
    except sqlite3.OperationalError:
        pass

    # Migration for subjects to support term-specific full marks
    c.execute("PRAGMA table_info(subjects)")
    cols = [col[1] for col in c.fetchall()]
    if 'full_marks_1st' not in cols:
        try:
            c.execute("ALTER TABLE subjects ADD COLUMN full_marks_1st REAL DEFAULT 50.0")
            c.execute("ALTER TABLE subjects ADD COLUMN full_marks_2nd REAL DEFAULT 50.0")
            c.execute("ALTER TABLE subjects ADD COLUMN full_marks_annual REAL DEFAULT 100.0")
            c.execute("UPDATE subjects SET full_marks_1st = COALESCE(full_marks, 100.0) / 2.0, full_marks_2nd = COALESCE(full_marks, 100.0) / 2.0, full_marks_annual = COALESCE(full_marks, 100.0)")
            print(" [DB MIGRATE] Added term-specific full marks columns and backfilled them from existing full_marks")
        except Exception as e:
            print(f" [DB MIGRATE] Failed term-specific marks migration: {e}")

    # Migration for subjects to support custom component-level term marks
    for col_name in ['oral_marks_1st', 'written_marks_1st', 'oral_marks_2nd', 'written_marks_2nd', 'oral_marks_annual', 'written_marks_annual', 'ct_marks_annual']:
        if col_name not in cols:
            try:
                c.execute(f"ALTER TABLE subjects ADD COLUMN {col_name} REAL DEFAULT NULL")
                print(f" [DB MIGRATE] Added {col_name} column to subjects table")
            except sqlite3.OperationalError:
                pass

    # Migrations for student_info to support fees & permissions
    for col, col_type in [('monthly_fee', 'REAL DEFAULT 0.0'), ('hostel_fee', 'REAL DEFAULT 0.0'), ('allow_marksheet', 'INTEGER DEFAULT 0'), ('allow_admit', 'INTEGER DEFAULT 0')]:
        try:
            c.execute(f"ALTER TABLE student_info ADD COLUMN {col} {col_type}")
            print(f" [DB MIGRATE] Added column {col} to student_info table")
        except sqlite3.OperationalError:
            pass # already exists

    # Migrations for student_info/teacher_info to support photos
    for table in ['student_info', 'teacher_info']:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN photo_path TEXT")
            print(f" [DB MIGRATE] Added column photo_path to {table} table")
        except sqlite3.OperationalError:
            pass # already exists

    # Migrate student_info for bank_details
    try:
        c.execute("ALTER TABLE student_info ADD COLUMN bank_details TEXT")
        print(" [DB MIGRATE] Added bank_details column to student_info")
    except sqlite3.OperationalError:
        pass

    # Migrate users for email, security_key, and branch columns
    for col, col_type in [('email', 'TEXT'), ('security_key', 'TEXT'), ('branch', 'TEXT')]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            print(f" [DB MIGRATE] Added column {col} to users table")
        except sqlite3.OperationalError:
            pass # already exists

    # Migrate users for phone column
    try:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        print(" [DB MIGRATE] Added phone column to users table")
    except sqlite3.OperationalError:
        pass

    # Migrate users for temp_password column
    try:
        c.execute("ALTER TABLE users ADD COLUMN temp_password TEXT")
        print(" [DB MIGRATE] Added temp_password column to users table")
    except sqlite3.OperationalError:
        pass

    # Migrate visitor_reviews columns
    try:
        c.execute("ALTER TABLE visitor_reviews ADD COLUMN visitor_email TEXT")
        print(" [DB MIGRATE] Added visitor_email column to visitor_reviews")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE visitor_reviews ADD COLUMN sort_order INTEGER DEFAULT 0")
        print(" [DB MIGRATE] Added sort_order column to visitor_reviews")
    except sqlite3.OperationalError:
        pass

    # Migrate classes table for additional fee columns
    for col in ['admission_fee_coaching', 'admission_fee_hostel', 'readmission_fee_school', 'readmission_fee_coaching', 'readmission_fee_hostel', 'monthly_fee_coaching']:
        try:
            c.execute(f"ALTER TABLE classes ADD COLUMN {col} REAL DEFAULT 0.0")
            print(f" [DB MIGRATE] Added {col} column to classes")
        except sqlite3.OperationalError:
            pass

    # Migrate teacher_info for missing columns
    for col in ['full_name', 'phone_number', 'address', 'aadhaar_number', 'assigned_classes', 'bank_details']:
        try:
            c.execute(f"ALTER TABLE teacher_info ADD COLUMN {col} TEXT")
            print(f" [DB MIGRATE] Added {col} column to teacher_info")
        except sqlite3.OperationalError:
            pass

    try:
        c.execute("ALTER TABLE teacher_info ADD COLUMN salary REAL DEFAULT 0.0")
        print(" [DB MIGRATE] Added salary column to teacher_info")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE teacher_info ADD COLUMN remaining_salary REAL DEFAULT 0.0")
        print(" [DB MIGRATE] Added remaining_salary column to teacher_info")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE student_info ADD COLUMN remaining_fee REAL DEFAULT 0.0")
        print(" [DB MIGRATE] Added remaining_fee column to student_info")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE teacher_info ADD COLUMN teacher_type TEXT DEFAULT 'Regular Class'")
        print(" [DB MIGRATE] Added teacher_type column to teacher_info")
    except sqlite3.OperationalError:
        pass

    # Ensure attendance table exists and has attendance_type column with proper UNIQUE constraint
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                remarks TEXT,
                attendance_type TEXT DEFAULT 'regular',
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, date, attendance_type)
            )
        ''')
        print(" [DB MIGRATE] Created attendance table with multiple attendance types support")
    else:
        # Check if attendance_type exists in the columns
        c.execute("PRAGMA table_info(attendance)")
        columns_list = [col[1] for col in c.fetchall()]
        if 'attendance_type' not in columns_list:
            try:
                c.execute("ALTER TABLE attendance RENAME TO attendance_old")
                c.execute('''
                    CREATE TABLE attendance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        date TEXT NOT NULL,
                        status TEXT NOT NULL,
                        remarks TEXT,
                        attendance_type TEXT DEFAULT 'regular',
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        UNIQUE(user_id, date, attendance_type)
                    )
                ''')
                c.execute('''
                    INSERT INTO attendance (user_id, role, date, status, remarks, attendance_type)
                    SELECT user_id, role, date, status, remarks, 'regular' FROM attendance_old
                ''')
                c.execute("DROP TABLE attendance_old")
                print(" [DB MIGRATE] Migrated attendance table to support multiple attendance types")
            except Exception as e:
                print(f" [DB MIGRATE] Failed migrating attendance: {e}")

    # Migrations for marks table components
    for col, col_type in [('oral_marks', 'REAL DEFAULT 0.0'), ('written_marks', 'REAL DEFAULT 0.0'), ('ct_marks', 'REAL DEFAULT 0.0')]:
        try:
            c.execute(f"ALTER TABLE marks ADD COLUMN {col} {col_type}")
            print(f" [DB MIGRATE] Added column {col} to marks table")
        except sqlite3.OperationalError:
            pass # already exists

    # Migration for question_papers to support drive_file_id
    try:
        c.execute("ALTER TABLE question_papers ADD COLUMN drive_file_id TEXT")
        print(" [DB MIGRATE] Added drive_file_id column to question_papers")
    except sqlite3.OperationalError:
        pass # already exists

    try:
        c.execute('''
            UPDATE question_papers 
            SET drive_file_id = (
                SELECT drive_file_id 
                FROM drive_mappings 
                WHERE drive_mappings.filename = question_papers.filepath
            )
            WHERE drive_file_id IS NULL
        ''')
        print(" [DB MIGRATE] Backfilled drive_file_id from drive_mappings for question_papers")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Failed backfilling drive_file_id: {e}")

    # Seed notices if notices table is empty
    c.execute("SELECT COUNT(*) FROM notices")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO notices (content, branch) VALUES (?, 'bhogram')", 
                  ("Parent-Teacher Meeting (PTM) is scheduled on Saturday, June 20 at 10:00 AM in the assembly hall.",))
        c.execute("INSERT INTO notices (content, branch) VALUES (?, 'bhogram')", 
                  ("School uniforms have been distributed. Students can collect theirs from room 3 during lunch break.",))
            
    # Default Admin
    c.execute('SELECT * FROM users WHERE username = ?', ('headmaster',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)',
                  ('headmaster', 'rmdaswif@gmail.com', hash_password(DEFAULT_ADMIN_PASSWORD), 'admin', ADMIN_SECURITY_KEY or 'admin-created'))

    # New Admin with 2FA email
    c.execute('SELECT * FROM users WHERE username = ?', ('ahm_admin_2fa',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)',
                  ('ahm_admin_2fa', 'mdaswifr@gmail.com', hash_password('AhmAdmin#2026_Secure!'), 'admin', ADMIN_SECURITY_KEY or 'admin-created'))

    # Second New Admin with 2FA email (v2)
    c.execute('SELECT * FROM users WHERE username = ?', ('ahm_admin_2fa_v2',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)',
                  ('ahm_admin_2fa_v2', 'mdaswifr@gmail.com', hash_password('AhmAdmin#2026_SecureV2!'), 'admin', ADMIN_SECURITY_KEY or 'admin-created'))


    c.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_type TEXT NOT NULL,
            recipient_id INTEGER,
            recipient_name TEXT NOT NULL,
            father_name TEXT,
            class_name TEXT,
            section TEXT,
            roll_number TEXT,
            title TEXT NOT NULL,
            subtitle TEXT,
            reason_text TEXT NOT NULL,
            position_text TEXT,
            event_name TEXT,
            congrats_text TEXT,
            date_text TEXT,
            signature_text TEXT,
            branch TEXT,
            theme_style TEXT DEFAULT 'classic',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # School settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS school_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
        )
    ''')
    c.execute("INSERT OR IGNORE INTO school_settings (setting_key, setting_value) VALUES ('coaching_class_time', '3:00 PM - 5:00 PM')")
    c.execute("INSERT OR IGNORE INTO school_settings (setting_key, setting_value) VALUES ('log_destination_email', 'missionalhidayet@gmail.com')")

    migrate_plaintext_passwords(c)
    seed_default_subjects(conn)

    # Normalize existing branch values to lowercase
    for table in ['users', 'student_info', 'expenses', 'notices', 'applications', 'pending_media', 'staff', 'certificates']:
        try:
            c.execute(f"UPDATE {table} SET branch = LOWER(branch) WHERE branch IS NOT NULL")
        except Exception:
            pass
    
    try:
        sync_classes(conn)
    except Exception as e:
        print(f" [DB MIGRATE ERROR] sync_classes failed on init_db: {e}")

    conn.commit()
    conn.close()

# Global cache for settings and committee info to minimize cloud DB roundtrips
_settings_cache = {}
_cache_expiry = 0.0
_committee_cache = None
_committee_cache_expiry = 0.0

def get_school_setting(key, default_value):
    import time
    global _settings_cache, _cache_expiry
    now = time.time()
    if now < _cache_expiry and key in _settings_cache:
        return _settings_cache[key]
        
    conn = get_db_connection()
    c = conn.cursor()
    try:
        row = c.execute("SELECT setting_value FROM school_settings WHERE setting_key = ?", (key,)).fetchone()
        val = row['setting_value'] if row else default_value
    except Exception:
        val = default_value
    conn.close()
    
    _settings_cache[key] = val
    if now >= _cache_expiry:
        _cache_expiry = now + 60.0  # Keep cached items for up to 60 seconds
    return val

def set_school_setting(key, value):
    global _settings_cache
    _settings_cache[key] = value
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO school_settings (setting_key, setting_value) VALUES (?, ?)", (key, value))
        conn.commit()
    except Exception as e:
        print(f" [DB ERROR] Failed to save setting {key}: {e}")
    conn.close()

def migrate_pending_media_drive_id():
    conn = get_db_connection()
    c = conn.cursor()
    # 1. Add drive_file_id to pending_media for existing dbs
    try:
        c.execute("ALTER TABLE pending_media ADD COLUMN drive_file_id TEXT")
        print(" [DB MIGRATE] Added column drive_file_id to pending_media")
    except sqlite3.OperationalError:
        pass
        
    # 2. Create drive_mappings table
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS drive_mappings (
                filename TEXT PRIMARY KEY,
                drive_file_id TEXT NOT NULL
            )
        ''')
        print(" [DB MIGRATE] Created drive_mappings table")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Failed to create drive_mappings: {e}")
        
    conn.commit()
    conn.close()

def migrate_question_papers_to_drive():
    import mimetypes
    upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'question_papers')
    if not os.path.exists(upload_folder):
        return
        
    try:
        files = os.listdir(upload_folder)
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Failed to list question papers for migration: {e}")
        return
        
    for filename in files:
        local_path = os.path.join(upload_folder, filename)
        if os.path.isdir(local_path):
            continue
            
        mime_type, _ = mimetypes.guess_type(local_path)
        if not mime_type:
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
        print(f" [DB MIGRATE] Migrating question paper to Google Drive: {filename}")
        drive_file_id = upload_file_to_drive_and_map(
            local_path, 
            filename, 
            mime_type, 
            folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_QUESTION_PAPERS')
        )
        if drive_file_id:
            import time
            for attempt in range(5):
                try:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE question_papers SET drive_file_id = ? WHERE filepath = ?", (drive_file_id, filename))
                    conn.commit()
                    conn.close()
                    break
                except sqlite3.OperationalError as oe:
                    if "locked" in str(oe).lower():
                        time.sleep(1)
                    else:
                        break
                except Exception:
                    break

# Cache variables for Google Drive access token
cached_drive_access_token = None
cached_drive_token_expiry = None

import threading
_drive_token_lock = threading.Lock()

def get_drive_access_token():
    global cached_drive_access_token, cached_drive_token_expiry
    
    # Check if cached token is still valid (fast exit without lock)
    if cached_drive_access_token and cached_drive_token_expiry:
        if datetime.now(timezone.utc) < cached_drive_token_expiry:
            return None if cached_drive_access_token == "FAILED" else cached_drive_access_token
            
    with _drive_token_lock:
        # Re-check under lock in case another thread updated it while we were waiting
        if cached_drive_access_token and cached_drive_token_expiry:
            if datetime.now(timezone.utc) < cached_drive_token_expiry:
                return None if cached_drive_access_token == "FAILED" else cached_drive_access_token
                
        client_id = os.getenv('GOOGLE_DRIVE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_DRIVE_CLIENT_SECRET')
        refresh_token = os.getenv('GOOGLE_DRIVE_REFRESH_TOKEN')
        
        if not client_id or not client_secret or not refresh_token:
            return None
            
        url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        try:
            import requests
            res = requests.post(url, data=payload, timeout=10)
            if res.status_code == 200:
                token_data = res.json()
                cached_drive_access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in', 3600)
                # 60 seconds buffer before expiration
                cached_drive_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
                return cached_drive_access_token
            else:
                print(f" [GOOGLE DRIVE AUTH ERROR] {res.status_code}: {res.text}")
                # Don't cache failure for too long during debugging
                cached_drive_access_token = "FAILED"
                cached_drive_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=10)
        except Exception as e:
            print(f" [GOOGLE DRIVE AUTH EXCEPTION] {e}")
            # Don't cache failure for too long during debugging
            cached_drive_access_token = "FAILED"
            cached_drive_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=10)
        return None


def upload_to_google_drive(file_bytes, file_name, mime_type, folder_id=None):
    access_token = get_drive_access_token()
    if not access_token:
        print(" [GOOGLE DRIVE] Credentials not configured or failed to refresh access token.")
        return None
        
    metadata = {
        "name": file_name
    }
    
    parent_id = folder_id or os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    if parent_id:
        metadata["parents"] = [parent_id]
        
    import json
    import requests
    
    files = {
        'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
        'file': (file_name, file_bytes, mime_type)
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id"
    
    try:
        res = requests.post(url, headers=headers, files=files, timeout=30)
        if res.status_code == 200:
            file_id = res.json().get('id')
            print(f" [GOOGLE DRIVE] File uploaded successfully. File ID: {file_id}")
            return file_id
        else:
            print(f" [GOOGLE DRIVE UPLOAD ERROR] {res.status_code}: {res.text}")
    except Exception as e:
        print(f" [GOOGLE DRIVE UPLOAD EXCEPTION] {e}")
    return None

def delete_from_google_drive(file_id):
    access_token = get_drive_access_token()
    if not access_token:
        print(" [GOOGLE DRIVE] Access token not available for deletion.")
        return False
        
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    try:
        import requests
        res = requests.delete(url, headers=headers, timeout=10)
        if res.status_code == 204:
            print(f" [GOOGLE DRIVE] File {file_id} deleted successfully.")
            return True
        elif res.status_code == 404:
            print(f" [GOOGLE DRIVE] File {file_id} already deleted from Drive. Skipping.")
            return True
        else:
            print(f" [GOOGLE DRIVE DELETE ERROR] {res.status_code}: {res.text}")
    except Exception as e:
        print(f" [GOOGLE DRIVE DELETE EXCEPTION] {e}")
    return False

def find_file_in_google_drive(filename):
    access_token = get_drive_access_token()
    if not access_token:
        print(" [GOOGLE DRIVE] Access token not available for find_file_in_google_drive.")
        return None
        
    import urllib.parse
    import requests
    
    # Escape single quotes in filenames for Google Drive API query syntax
    escaped_filename = filename.replace("'", "\\'")
    q = f"name = '{escaped_filename}' and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(q)}&fields=files(id,mimeType,name)"
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            files_list = res.json().get('files', [])
            if files_list:
                file_id = files_list[0].get('id')
                print(f" [GOOGLE DRIVE] Found file '{filename}' on Drive with ID: {file_id}")
                return file_id
        else:
            print(f" [GOOGLE DRIVE FIND ERROR] {res.status_code}: {res.text}")
    except Exception as e:
        print(f" [GOOGLE DRIVE FIND EXCEPTION] {e}")
    return None

def upload_file_to_drive_and_map(local_path, filename, mime_type, folder_id=None, conn=None):
    drive_file_id = None
    if os.path.exists(local_path):
        try:
            with open(local_path, 'rb') as f:
                file_bytes = f.read()
            drive_file_id = upload_to_google_drive(file_bytes, filename, mime_type, folder_id=folder_id)
        except Exception as e:
            print(f"Error uploading file {filename} to Google Drive: {e}")
            
    if drive_file_id:
        if conn is not None:
            try:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO drive_mappings (filename, drive_file_id) VALUES (?, ?)", (filename, drive_file_id))
                if os.path.exists(local_path):
                    os.remove(local_path)
                print(f" [GOOGLE DRIVE] File {filename} successfully uploaded and mapped to {drive_file_id} using active connection. Local file deleted.")
            except Exception as e:
                print(f"Error saving drive mapping using active connection: {e}")
        else:
            import time
            db_saved = False
            for attempt in range(5):
                try:
                    new_conn = get_db_connection()
                    c = new_conn.cursor()
                    c.execute("INSERT OR REPLACE INTO drive_mappings (filename, drive_file_id) VALUES (?, ?)", (filename, drive_file_id))
                    new_conn.commit()
                    new_conn.close()
                    db_saved = True
                    break
                except sqlite3.OperationalError as oe:
                    if "locked" in str(oe).lower():
                        print(f" [GOOGLE DRIVE] Database locked on attempt {attempt+1} when saving mapping for {filename}, retrying in 1s...")
                        time.sleep(1)
                    else:
                        print(f"Error saving drive mapping: {oe}")
                        break
                except Exception as e:
                    print(f"Error saving drive mapping: {e}")
                    break
                    
            if db_saved:
                try:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    print(f" [GOOGLE DRIVE] File {filename} successfully uploaded and mapped to {drive_file_id}. Local file deleted.")
                except Exception as e:
                    print(f"Error removing local file: {e}")
            
    return drive_file_id

def delete_old_mapped_file(file_path):
    if not file_path:
        return
    filename = os.path.basename(file_path)
    try:
        conn = get_db_connection()
        c = conn.cursor()
        row = c.execute("SELECT drive_file_id FROM drive_mappings WHERE filename = ?", (filename,)).fetchone()
        drive_file_id = None
        if row and row['drive_file_id']:
            drive_file_id = row['drive_file_id']
            c.execute("DELETE FROM drive_mappings WHERE filename = ?", (filename,))
        conn.commit()
        conn.close()
        
        if drive_file_id:
            delete_from_google_drive(drive_file_id)
    except Exception as e:
        print(f" [GOOGLE DRIVE DELETE ERROR] Failed to delete old mapped file {filename}: {e}")

# Google Drive View and Intercept Routes
@app.route('/drive/view/<file_id>')
def drive_view(file_id):
    access_token = get_drive_access_token()
    if not access_token:
        return "Google Drive is not configured.", 500
        
    import requests
    
    metadata_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=mimeType,name"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    mime_type = "application/octet-stream"
    filename = "download"
    try:
        meta_res = requests.get(metadata_url, headers=headers, timeout=10)
        if meta_res.status_code == 200:
            meta = meta_res.json()
            mime_type = meta.get('mimeType', mime_type)
            filename = meta.get('name', filename)
    except Exception as e:
        print(f" [GOOGLE DRIVE VIEW METADATA ERROR] {e}")
        
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    
    try:
        drive_res = requests.get(download_url, headers=headers, stream=True, timeout=30)
        if drive_res.status_code != 200:
            return f"Failed to fetch file from Google Drive: {drive_res.status_code}", drive_res.status_code
            
        def generate():
            for chunk in drive_res.iter_content(chunk_size=4096):
                yield chunk
                
        return Response(generate(), mimetype=mime_type, headers={
            "Content-Disposition": f"inline; filename=\"{filename}\""
        })
    except Exception as e:
        return f"Error streaming file from Google Drive: {str(e)}", 500

# Cache for missing files in Google Drive to prevent repeat slow lookups
# We reset it occasionally or just remove it to force re-checks if there was a temporary network error
missing_drive_files = set()

@app.route('/media/<path:filepath>')
@app.route('/static/uploads/<path:filepath>')
def serve_static_upload(filepath):
    filename = os.path.basename(filepath)
    # Removing the aggressive global missing cache check temporarily so it retries Drive
    # if filename in missing_drive_files:
    #     return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filepath)

    # 1. Fast path: check if local file exists
    local_path = os.path.join(app.root_path, 'static', 'uploads', filepath)
    if os.path.exists(local_path):
        return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filepath)
        
    # Check if Google Drive is configured and authenticated
    access_token_available = (get_drive_access_token() is not None)
    if not access_token_available:
        # Graceful fallback: return local directory send which will return 404
        missing_drive_files.add(filename)
        return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filepath)

    # 2. Local file missing: check DB mapping
    drive_file_id = None

    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Check in pending_media (approved items)
        row = c.execute("SELECT drive_file_id FROM pending_media WHERE filename = ?", (filename,)).fetchone()
        if row and row['drive_file_id']:
            drive_file_id = row['drive_file_id']
        else:
            # Check in general drive_mappings
            row2 = c.execute("SELECT drive_file_id FROM drive_mappings WHERE filename = ?", (filename,)).fetchone()
            if row2:
                drive_file_id = row2['drive_file_id']
        conn.close()
    except Exception as e:
        print(f"Error checking drive mapping for {filename}: {e}")

    if drive_file_id:
        res = drive_view(drive_file_id)
        if isinstance(res, tuple) and len(res) > 1 and res[1] >= 400:
            # If Google Drive view fails (due to auth/revoked token or deleted file on Drive), fall through to 404
            pass
        else:
            return res
        
    # 3. Dynamic Google Drive lookup fallback
    drive_file_id = find_file_in_google_drive(filename)
    if drive_file_id:
        import time
        # Save recovered mapping
        for attempt in range(5):
            try:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO drive_mappings (filename, drive_file_id) VALUES (?, ?)", (filename, drive_file_id))
                conn.commit()
                conn.close()
                break
            except sqlite3.OperationalError as oe:
                if "locked" in str(oe).lower():
                    time.sleep(1)
                else:
                    break
            except Exception:
                break
        res = drive_view(drive_file_id)
        if isinstance(res, tuple) and len(res) > 1 and res[1] >= 400:
            pass
        else:
            return res
        
    # 4. Fallback to send_from_directory (returns 404 since file does not exist)
    missing_drive_files.add(filename)
    return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filepath)


def migrate_and_normalize_database_classes():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 1. Migrate the 'classes' table.
        # Fetch existing classes.
        classes_rows = c.execute("SELECT id, name, branch, admission_fee, admission_fee_coaching, admission_fee_hostel, readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel, monthly_fee, monthly_fee_coaching, hostel_fee FROM classes").fetchall()
        merged_classes = {}
        for row in classes_rows:
            norm_name = normalize_class_name(row[1])
            branch = row[2]
            key = (norm_name, branch)
            if key not in merged_classes:
                merged_classes[key] = list(row)
                merged_classes[key][1] = norm_name
            else:
                existing = merged_classes[key]
                # Merge fees by keeping the highest / non-zero value
                for i in range(3, len(row)):
                    if row[i] is not None:
                        val = float(row[i])
                        if existing[i] is None or val > float(existing[i]):
                            existing[i] = val
                            
        # Delete old and insert normalized
        c.execute("DELETE FROM classes")
        for key, val in merged_classes.items():
            c.execute("""
                INSERT OR REPLACE INTO classes (
                    name, branch, admission_fee, admission_fee_coaching, admission_fee_hostel,
                    readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                    monthly_fee, monthly_fee_coaching, hostel_fee
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, val[1:])
            
        # 2. Migrate standard tables
        tables_to_migrate = [
            ('student_info', 'class'),
            ('marks', 'class_name'),
            ('class_routine', 'class_name'),
            ('exam_locks', 'class_name'),
            ('question_papers', 'class_name'),
            ('exam_schedules', 'class_name'),
            ('certificates', 'class_name'),
            ('teacher_subjects', 'class_name'),
            ('class_subjects', 'class_name'),
            ('teacher_assignments', 'class_name')
        ]
        
        for table, col in tables_to_migrate:
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not c.fetchone():
                continue
                
            distinct_rows = c.execute(f"SELECT DISTINCT {col} FROM {table}").fetchall()
            for row in distinct_rows:
                val = row[0]
                if val:
                    norm = normalize_class_name(val)
                    if norm != val:
                        c.execute(f"UPDATE OR REPLACE {table} SET {col} = ? WHERE {col} = ?", (norm, val))
                        
        # 3. Re-sync teacher assigned classes string
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teacher_info'")
        if c.fetchone():
            teachers = c.execute("SELECT user_id FROM teacher_info").fetchall()
            for t in teachers:
                try:
                    sync_teacher_assigned_classes_string_from_db(conn, t[0])
                except Exception as sync_ex:
                    print(f"Error syncing teacher assigned classes for {t[0]}: {sync_ex}")
                    
        conn.commit()
        conn.close()
        print(" [DB MIGRATE] Normalized all class fields successfully.")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Database normalization failed: {e}")

def is_db_initialized(conn):
    try:
        c = conn.cursor()
        res = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        return res is not None
    except Exception:
        return False

# Initialize DB and run migrations
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    try:
        print(" [DB INIT] Running database initialization and safe migrations...")
        init_db()
        migrate_student_info_schema()
        migrate_staff_and_expense_recipient_schema()
        migrate_and_normalize_database_classes()
        migrate_pending_media_drive_id()
        migrate_question_papers_to_drive()
    except Exception as e:
        print(f" [DB INIT ERROR] Failed to initialize database on startup: {e}")

def migrate_manual_financial_schema():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE student_info ADD COLUMN remaining_fee REAL DEFAULT 0.0")
            print(" [DB MIGRATE] Added remaining_fee column to student_info")
        except sqlite3.OperationalError:
            pass
        except Exception as ex:
            print(f" [DB MIGRATE] remaining_fee column check error: {ex}")
        try:
            c.execute("ALTER TABLE teacher_info ADD COLUMN remaining_salary REAL DEFAULT 0.0")
            print(" [DB MIGRATE] Added remaining_salary column to teacher_info")
        except sqlite3.OperationalError:
            pass
        except Exception as ex:
            print(f" [DB MIGRATE] remaining_salary column check error: {ex}")
        try:
            c.execute("ALTER TABLE staff ADD COLUMN remaining_salary REAL DEFAULT 0.0")
            print(" [DB MIGRATE] Added remaining_salary column to staff")
        except sqlite3.OperationalError:
            pass
        except Exception as ex:
            print(f" [DB MIGRATE] remaining_salary column check on staff error: {ex}")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Failed to run migrate_manual_financial_schema: {e}")

if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    migrate_manual_financial_schema()

def migrate_fees_and_structures_schema():
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # 1. Create fee_structures table
        c.execute('''
            CREATE TABLE IF NOT EXISTS fee_structures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                branch TEXT NOT NULL,
                enrollment_type TEXT NOT NULL,
                tuition_fee REAL DEFAULT 0.0,
                transport_fee REAL DEFAULT 0.0,
                lab_library_fee REAL DEFAULT 0.0,
                academic_discount REAL DEFAULT 0.0,
                room_rent REAL DEFAULT 0.0,
                mess_food_charges REAL DEFAULT 0.0,
                utility_cost REAL DEFAULT 0.0,
                security_deposit REAL DEFAULT 0.0,
                coaching_combo_fee REAL DEFAULT 0.0,
                study_material_charges REAL DEFAULT 0.0,
                exam_test_series_fee REAL DEFAULT 0.0,
                combo_discount REAL DEFAULT 0.0,
                school_tax_rate REAL DEFAULT 0.0,
                hostel_tax_rate REAL DEFAULT 0.05,
                coaching_tax_rate REAL DEFAULT 0.0,
                UNIQUE(class_name, branch, enrollment_type)
            )
        ''')
        
        # 2. Add columns to fees table
        fees_cols = [
            ("school_revenue", "REAL DEFAULT 0.0"),
            ("hostel_revenue", "REAL DEFAULT 0.0"),
            ("coaching_revenue", "REAL DEFAULT 0.0"),
            ("tax_amount", "REAL DEFAULT 0.0"),
            ("enrollment_type", "TEXT")
        ]
        for col_name, col_type in fees_cols:
            try:
                c.execute(f"ALTER TABLE fees ADD COLUMN {col_name} {col_type}")
                print(f" [DB MIGRATE] Added column {col_name} to fees")
            except sqlite3.OperationalError:
                pass
                
        # 3. Seed fee_structures table from classes table if empty
        res = c.execute("SELECT COUNT(*) FROM fee_structures").fetchone()
        if res and res[0] == 0:
            print(" [DB MIGRATE] Seeding default fee_structures from classes table...")
            classes_rows = c.execute("SELECT * FROM classes").fetchall()
            for cls in classes_rows:
                c_name = cls['name']
                branch = cls['branch']
                m_fee = float(cls['monthly_fee'] or 0.0)
                m_fee_coaching = float(cls['monthly_fee_coaching'] or 0.0)
                h_fee = float(cls['hostel_fee'] or 0.0)
                
                # 1. Day School Only
                c.execute('''
                    INSERT OR IGNORE INTO fee_structures (
                        class_name, branch, enrollment_type, tuition_fee, school_tax_rate
                    ) VALUES (?, ?, 'Day School Only', ?, 0.0)
                ''', (c_name, branch, m_fee))
                
                # 2. Day Hostel Only
                c.execute('''
                    INSERT OR IGNORE INTO fee_structures (
                        class_name, branch, enrollment_type, room_rent, hostel_tax_rate
                    ) VALUES (?, ?, 'Day Hostel Only', ?, 0.05)
                ''', (c_name, branch, h_fee))
                
                # 3. School + Coaching
                c.execute('''
                    INSERT OR IGNORE INTO fee_structures (
                        class_name, branch, enrollment_type, tuition_fee, coaching_combo_fee, combo_discount, school_tax_rate, coaching_tax_rate
                    ) VALUES (?, ?, 'School + Coaching', ?, ?, 0.0, 0.0, 0.0)
                ''', (c_name, branch, m_fee, m_fee_coaching))
                
                # 4. Hostel Only (or School + Hostel)
                c.execute('''
                    INSERT OR IGNORE INTO fee_structures (
                        class_name, branch, enrollment_type, tuition_fee, room_rent, school_tax_rate, hostel_tax_rate
                    ) VALUES (?, ?, 'Hostel Only (or School + Hostel)', ?, ?, 0.0, 0.05)
                ''', (c_name, branch, m_fee, h_fee))
                
        conn.commit()
        conn.close()
        print(" [DB MIGRATE] fee_structures table initialized and seeded.")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] migrate_fees_and_structures_schema failed: {e}")

if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    migrate_fees_and_structures_schema()



# Clean up temporary debug files
import os
for f in ['debug_classes_subjects.txt', 'debug_classes_subjects_updated.txt']:
    if os.path.exists(f):
        try:
            os.remove(f)
        except Exception:
            pass




try:
    import update_sidebars_mc
    update_sidebars_mc.run_update()
except Exception as e:
    print(f" [SIDEBAR UPDATE ERROR] {e}")

# Upload Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_BASE

# Branch Configuration
BRANCHES = ['bhogram']
CATEGORIES = ['photos', 'videos']

# Branding Configuration
LOGO_URL = "https://i.postimg.cc/rpQPT9pk/logo-(1).jpg"
ESTD_YEAR = "2010"

@app.context_processor
def inject_branding():
    def parse_bank_details(bank_details_str):
        if not bank_details_str:
            return {'bank_name': '', 'branch_name': '', 'account_no': '', 'ifsc_code': ''}
        try:
            data = json.loads(bank_details_str)
            if isinstance(data, dict):
                return {
                    'bank_name': data.get('bank_name', ''),
                    'branch_name': data.get('branch_name', ''),
                    'account_no': data.get('account_no', ''),
                    'ifsc_code': data.get('ifsc_code', '')
                }
        except:
            pass
        return {'bank_name': bank_details_str, 'branch_name': '', 'account_no': '', 'ifsc_code': ''}

    global _committee_cache, _committee_cache_expiry
    import time
    now = time.time()

    if _committee_cache is None or now >= _committee_cache_expiry:
        conn = get_db_connection()
        try:
            committee = [dict(row) for row in conn.execute("SELECT * FROM managing_committee ORDER BY order_num ASC, id ASC").fetchall()]
        except sqlite3.OperationalError:
            committee = []
        conn.close()
        _committee_cache = committee
        _committee_cache_expiry = now + 60.0  # Cache for 60 seconds
    else:
        committee = _committee_cache

    coaching_time = get_school_setting('coaching_class_time', '3:00 PM - 5:00 PM')

    conn = get_db_connection()
    branch_filter = session.get('branch')
    try:
        active_cls = get_active_classes(conn, branch=branch_filter)
        all_cls = get_all_classes(conn, branch=branch_filter)
    except Exception:
        active_cls = []
        all_cls = ['Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI']
    finally:
        conn.close()

    return dict(
        logo_url=LOGO_URL, 
        estd_year=ESTD_YEAR, 
        role=session.get('role'),
        user_branch=session.get('branch') or 'bhogram',
        parse_bank_details=parse_bank_details,
        managing_committee=committee,
        coaching_class_time=coaching_time,
        global_classes=active_cls,
        all_classes=all_cls,
        normalize_class_name=normalize_class_name
    )

# Folder Creation Helper
def create_folders():
    for branch in BRANCHES:
        for category in CATEGORIES:
            path = os.path.join(UPLOAD_BASE, branch, category)
            os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'temp'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'proofs'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'student_photos'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'teacher_photos'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'cvs'), exist_ok=True)

create_folders()

def parse_teacher_qualifications(qual_str):
    """
    Parses qualification string like:
    'Class: NURSERY | Sub: BENGALI, Class: ONE, Sub: MATH, EVS, Class: TWO, Sub: G.K/HINDI, Class: FIVE'
    Returns a list of dicts: [{'class': 'I', 'subjects': ['Bengali', 'Math', 'EVS']}, ...] using standard normalized class names.
    """
    if not qual_str:
        return []
    
    import re
    class_norm = {
        'NURSERY': 'Nursery',
        'UN': 'KG',
        'U/N': 'KG',
        'KG': 'KG',
        'ONE': 'I',
        'I': 'I',
        'TWO': 'II',
        'II': 'II',
        'THREE': 'III',
        'III': 'III',
        'FOUR': 'IV',
        'IV': 'IV',
        'FIVE': 'V',
        'V': 'V',
        'SIX': 'VI',
        'VI': 'VI',
        'SEVEN': 'VII',
        'VII': 'VII',
        'EIGHT': 'VIII',
        'VIII': 'VIII',
        'NINE': 'IX',
        'IX': 'IX',
        'TEN': 'X',
        'X': 'X'
    }
    
    sub_norm = {
        'MATH': 'Mathematics',
        'MATHEMATICS': 'Mathematics',
        'BENGALI': 'Bengali',
        'ENGLISH': 'English',
        'EVS': 'Science',
        'EVS/ARABIC': ['Science', 'Arabic'],
        'EVS/ ARABIC': ['Science', 'Arabic'],
        'ARABIC/ G.K': ['Arabic', 'General Knowledge'],
        'G.K/ARABIC': ['General Knowledge', 'Arabic'],
        'G.K/HINDI': ['General Knowledge', 'Hindi'],
        'HIST/GEO': ['History', 'Geography'],
        'ARABIC': 'Arabic',
        'ISLAMIC STUDIES': 'Islamic Studies',
        'G.K': 'General Knowledge',
        'GENERAL KNOWLEDGE': 'General Knowledge',
        'B.H.W': 'Islamic Studies',
        'E.H.W': 'Islamic Studies',
    }
    
    parts = re.split(r'(?i)Class\s*:\s*', qual_str)
    assignments = []
    
    for part in parts:
        if not part.strip():
            continue
        
        class_part = part
        sub_part = ""
        
        sub_match = re.search(r'(?i)[|,\s]*Sub\s*:\s*(.*)', part)
        if sub_match:
            sub_part = sub_match.group(1)
            class_part = part[:sub_match.start()]
        
        class_name = class_part.strip().replace('|', '').replace(',', '').strip().upper()
        normalized_class = class_norm.get(class_name)
        if not normalized_class:
            for k, v in class_norm.items():
                if k in class_name:
                    normalized_class = v
                    break
        
        if not normalized_class:
            continue
            
        subjects = []
        if sub_part:
            sub_raw_list = re.split(r'[,\n]+', sub_part)
            for s in sub_raw_list:
                s_clean = s.strip().upper()
                if not s_clean:
                    continue
                mapped = sub_norm.get(s_clean)
                if mapped:
                    if isinstance(mapped, list):
                        subjects.extend(mapped)
                    else:
                        subjects.append(mapped)
                else:
                    subjects.append(s.strip().title())
        
        assignments.append({
            'class': normalized_class,
            'subjects': list(set(subjects)) if subjects else ["English", "Bengali", "Mathematics", "Science"]
        })
        
    return assignments

def get_teacher_allowed_subjects(conn, username):
    """
    Returns a list of dicts: [{'branch': branch, 'class': cls, 'name': sub}]
    """
    allowed_subjects = []
    
    teacher_info = conn.execute('''
        SELECT ti.full_name, u.id 
        FROM users u 
        JOIN teacher_info ti ON u.id = ti.user_id 
        WHERE u.username = ?
    ''', (username,)).fetchone()
    
    if teacher_info:
        teacher_id = teacher_info['id']
        
        # 1. Fetch teacher assignments from teacher_subjects table
        ts_rows = conn.execute('''
            SELECT ts.class_name, s.name as subject_name
            FROM teacher_subjects ts
            JOIN subjects s ON ts.subject_id = s.id
            WHERE ts.teacher_id = ?
        ''', (teacher_id,)).fetchall()
        
        teacher_user = conn.execute("SELECT branch FROM users WHERE id = ?", (teacher_id,)).fetchone()
        branch = teacher_user['branch'] if (teacher_user and teacher_user['branch']) else 'bhogram'
        
        for r in ts_rows:
            allowed_subjects.append({
                'branch': branch,
                'class': r['class_name'],
                'name': r['subject_name']
            })
            
        # 2. Add special subjects ONLY for Class Teachers
        ct_rows = conn.execute('''
            SELECT class_name FROM class_teachers WHERE teacher_id = ?
        ''', (teacher_id,)).fetchall()
        
        special_subjects = ['Behaviour', 'Work Education', 'Physical Education', 'Attendance', 'Hand Writing']
        for ct in ct_rows:
            cls_name = ct['class_name']
            for special in special_subjects:
                exists = any(x['branch'] == branch and x['class'] == cls_name and x['name'] == special for x in allowed_subjects)
                if not exists:
                    allowed_subjects.append({
                        'branch': branch,
                        'class': cls_name,
                        'name': special
                    })
                    
    return allowed_subjects

def get_db_class_names(selected_class):
    norm = normalize_class_name(selected_class)
    mapping = {
        'I': ['I', 'One', 'ONE', 'i', 'one', '1'],
        'II': ['II', 'Two', 'TWO', 'ii', 'two', '2'],
        'III': ['III', 'Three', 'THREE', 'iii', 'three', '3'],
        'IV': ['IV', 'Four', 'FOUR', 'iv', 'four', '4'],
        'V': ['V', 'Five', 'FIVE', 'v', 'five', '5'],
        'VI': ['VI', 'Six', 'SIX', 'vi', 'six', '6', 'siz', 'SIZ', 'Siz'],
        'VII': ['VII', 'Seven', 'SEVEN', 'vii', 'seven', '7'],
        'VIII': ['VIII', 'Eight', 'EIGHT', 'viii', 'eight', '8'],
        'IX': ['IX', 'Nine', 'NINE', 'ix', 'nine', '9'],
        'X': ['X', 'Ten', 'TEN', 'x', 'ten', '10'],
        'Upper Nursery': ['Upper Nursery', 'KG', 'U/N', 'UN', 'U-N', 'kg', 'u/n', 'un', 'u-n', 'Kg'],
        'Nursery': ['Nursery', 'NURSERY', 'nursery', 'Nuesery', 'nuesery']
    }
    if norm in mapping:
        return mapping[norm]
    
    val = str(selected_class).strip()
    return list({val, val.lower(), val.upper(), val.title()})


def get_all_academic_terms(conn):
    class_tests_rows = conn.execute("SELECT DISTINCT term_name FROM class_subjects").fetchall()
    all_terms = ['1st Unit', '2nd Unit', 'Final Exam'] + [r['term_name'] for r in class_tests_rows if r['term_name']]
    seen = set()
    return [x for x in all_terms if not (x in seen or seen.add(x))]


# --- ROUTES ---


@app.route('/')
def home():
    conn = get_db_connection()
    classes = conn.execute("SELECT * FROM classes ORDER BY id").fetchall()
    
    # build fee_data dict
    fee_data = {}
    for c_row in classes:
        fee_data[c_row['name']] = {
            'admission_fee': c_row['admission_fee'],
            'admission_fee_coaching': c_row['admission_fee_coaching'],
            'admission_fee_hostel': c_row['admission_fee_hostel'],
            'readmission_fee_school': c_row['readmission_fee_school'],
            'readmission_fee_coaching': c_row['readmission_fee_coaching'],
            'readmission_fee_hostel': c_row['readmission_fee_hostel'],
            'monthly_fee': c_row['monthly_fee'],
            'monthly_fee_coaching': c_row['monthly_fee_coaching'],
            'hostel_fee': c_row['hostel_fee']
        }

    registration_documents = conn.execute("SELECT * FROM registration_documents ORDER BY id").fetchall()
    routine_list = [dict(row) for row in conn.execute("SELECT * FROM class_routine").fetchall()]
    reviews = conn.execute("SELECT * FROM visitor_reviews WHERE is_approved = 1 ORDER BY sort_order ASC, id DESC LIMIT 6").fetchall()
    
    # Query notices and compute is_new flag
    notices_raw = conn.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()
    notices = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in notices_raw:
        n_dict = dict(row)
        is_new = False
        if n_dict.get('created_at'):
            try:
                created_str = n_dict['created_at'].split('.')[0]
                created_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
                # Threshold of 48 hours (172800 seconds)
                if (now - created_dt).total_seconds() < 48 * 3600:
                    is_new = True
            except Exception as e:
                print(f"Error parsing date {n_dict['created_at']}: {e}")
        n_dict['is_new'] = is_new
        notices.append(n_dict)

    # Query teachers
    teachers = [dict(row) for row in conn.execute("SELECT * FROM teacher_info WHERE full_name IS NOT NULL AND full_name != ''").fetchall()]
    
    all_terms = get_all_academic_terms(conn)
    
    # Get fee matrix data for dynamic homepage fee table
    fee_matrix_data = conn.execute("SELECT * FROM fee_matrix ORDER BY id").fetchall()
    
    # Get custom class fees
    custom_class_fees_data = conn.execute("SELECT * FROM custom_class_fees ORDER BY created_at DESC").fetchall()
    
    conn.close()
    return render_template('index.html', 
                           classes=classes, 
                           fee_data=fee_data,
                           fee_matrix_data=fee_matrix_data,
                           custom_class_fees_data=custom_class_fees_data,
                           registration_documents=registration_documents, 
                           routine_list=routine_list, 
                           reviews=reviews,
                           notices=notices,
                           teachers=teachers,
                           all_terms=all_terms)




@app.route('/submit-review', methods=['POST'])
def submit_review():
    visitor_name = request.form.get('visitor_name', '').strip()
    review_text = request.form.get('review_text', '').strip()
    rating = int(request.form.get('rating', 5))
    
    if visitor_name and review_text:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO visitor_reviews (visitor_name, visitor_email, review_text, rating, is_approved, sort_order)
            VALUES (?, NULL, ?, ?, 1, 0)
        ''', (visitor_name, review_text, rating))
        conn.commit()
        conn.close()
        flash('Thank you! Your feedback has been submitted successfully.')
    else:
        flash('Failed to submit review: Name and Feedback are required.')
    return redirect(url_for('home'))

@app.route('/verify-review-otp', methods=['GET', 'POST'])
def verify_review_otp():
    pending = session.get('pending_review')
    if not pending:
        flash('No pending review submission found or session expired.')
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        user_otp = request.form.get('otp', '').strip()
        if user_otp == pending.get('otp'):
            # Insert into database as verified and approved
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO visitor_reviews (visitor_name, visitor_email, review_text, rating, is_approved, sort_order)
                VALUES (?, ?, ?, ?, 1, 0)
            ''', (pending['visitor_name'], pending['visitor_email'], pending['review_text'], pending['rating']))
            conn.commit()
            conn.close()
            
            session.pop('pending_review', None)
            flash('Thank you! Your feedback has been verified and submitted successfully.')
            return redirect(url_for('home'))
        else:
            flash('Invalid verification code! Please try again.')
            
    return render_template('verify_review_otp.html', email=pending.get('visitor_email'))

@app.route('/resend-review-otp')
def resend_review_otp():
    pending = session.get('pending_review')
    if not pending:
        flash('No pending review submission found.')
        return redirect(url_for('home'))
        
    otp = str(random.randint(100000, 999999))
    pending['otp'] = otp
    session['pending_review'] = pending
    
    send_review_otp_email(pending['visitor_email'], otp)
    flash('A new verification code has been sent to your email.')
    return redirect(url_for('verify_review_otp'))

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/gallery')
def gallery():
    gallery_data = {}
    db_media = []
    try:
        conn = get_db_connection()
        db_media = conn.execute(
            "SELECT branch, category, filename, drive_file_id FROM pending_media WHERE status = 'Approved'"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"Error reading media from database: {e}")

    added_filenames = set()
    for branch in BRANCHES:
        gallery_data[branch] = {}
        for category in CATEGORIES:
            gallery_data[branch][category] = []

    for row in db_media:
        branch = row['branch']
        category = row['category']
        filename = row['filename']
        drive_file_id = row['drive_file_id']
        
        if branch in gallery_data and category in gallery_data[branch]:
            if filename not in added_filenames:
                added_filenames.add(filename)
                clean_title = filename.split('_')[-1].split('.')[0].replace('-', ' ').replace('_', ' ').strip().title()
                if drive_file_id:
                    url = url_for('drive_view', file_id=drive_file_id)
                else:
                    url = url_for('static', filename=f'uploads/{branch}/{category}/{filename}')
                gallery_data[branch][category].append({
                    'filename': filename,
                    'url': url,
                    'drive_file_id': drive_file_id,
                    'clean_title': clean_title
                })

    for branch in BRANCHES:
        for category in CATEGORIES:
            path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
            if os.path.exists(path):
                try:
                    for filename in os.listdir(path):
                        if filename not in added_filenames:
                            added_filenames.add(filename)
                            clean_title = filename.split('_')[-1].split('.')[0].replace('-', ' ').replace('_', ' ').strip().title()
                            url = url_for('static', filename=f'uploads/{branch}/{category}/{filename}')
                            gallery_data[branch][category].append({
                                'filename': filename,
                                'url': url,
                                'drive_file_id': None,
                                'clean_title': clean_title
                            })
                except Exception as e:
                    print(f"Error listing folder {path}: {e}")

    return render_template('gallery.html', content=gallery_data)

@app.route('/branches')
def branch_selection():
    session['selected_branch'] = 'bhogram'
    return redirect(url_for('home'))

@app.route('/branch/<branch_name>')
def set_branch(branch_name):
    session['selected_branch'] = 'bhogram'
    return redirect(url_for('home'))

@app.route('/login/<user_type>', methods=['GET', 'POST'])
def login(user_type):
    if request.method == 'POST':
        # Step 1: Check Username & Password
        if 'otp_verified' not in session:
            username = request.form['username']
            password = request.form['password']
            next_url = request.args.get('next')
            
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

            if user and verify_password(user['password'], password):
                upgrade_password_hash(conn, user['id'], user['password'], password)
                
                # Fetch branch if user is student
                branch = user['branch']
                if user['role'] == 'student':
                    student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
                    if student:
                        branch = student['branch']
                if branch:
                    branch = branch.lower()
                conn.close()
                
                # Turn on two-factor authentication ONLY for Admin (if not disabled by env)
                if user['role'] == 'admin':
                    if os.getenv('DISABLE_2FA', 'false').lower() == 'true':
                        # Bypass 2FA completely
                        session.clear()
                        session.permanent = True
                        session['user'] = user['username']
                        session['role'] = user['role']
                        session['branch'] = branch
                        flash('Login Successful (2FA Bypassed)!')
                        if is_safe_next_url(next_url):
                            return redirect(next_url)
                        return redirect(url_for('dashboard'))

                    session.clear()
                    session['temp_user'] = {
                        'id': user['id'],
                        'username': user['username'],
                        'role': user['role'],
                        'branch': branch
                    }
                    session['next_url'] = next_url
                    
                    email = user['email']
                    phone = user['phone']
                    
                    otp = generate_otp()
                    session['otp'] = otp
                    
                    if email and not phone:
                        session['otp_method'] = 'email'
                        session['otp_email'] = email
                        send_otp_email(email, otp)
                        flash('OTP sent to your registered email.')
                    elif phone and not email:
                        session['otp_method'] = 'phone'
                        session['otp_phone'] = phone
                        send_otp_sms(phone, otp)
                        flash('OTP sent to your registered phone number.')
                    elif email and phone:
                        session['otp_method'] = 'email'
                        session['otp_email'] = email
                        session['otp_phone'] = phone
                        send_otp_email(email, otp)
                        flash('OTP sent to your registered email.')
                    else:
                        # Fallback if neither email nor phone is found
                        session.clear()
                        flash('Error: Admin account has no registered email or phone for Two-Factor Authentication.')
                        return redirect(url_for('login', user_type=user_type))
                        
                    return redirect(url_for('verify_otp', context='login'))
                
                # Normal Login for Teachers and Students (No 2FA)
                session.clear()
                session.permanent = True
                session['user'] = user['username']
                session['role'] = user['role']
                session['branch'] = branch
                flash('Login Successful!')
                if is_safe_next_url(next_url):
                    return redirect(next_url)
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                flash('Invalid Username or Password!')
            
    return render_template('login.html', user_type=user_type)

@app.route('/resend-otp/<context>')
def resend_otp(context):
    if 'otp' not in session:
        flash('Session expired. Please start over.')
        if context == 'login':
            return redirect(url_for('login', user_type='student'))
        return redirect(url_for('register' if context == 'register' else 'forgot_password'))
        
    otp = generate_otp()
    session['otp'] = otp
    method = session.get('otp_method', 'email')
    
    if method == 'phone' and session.get('otp_phone'):
        if send_otp_sms(session['otp_phone'], otp):
            flash('A new code has been sent to your phone number.')
        else:
            flash('Failed to resend code via SMS. Check system logs.')
    else:
        email = session.get('otp_email')
        if email and send_otp_email(email, otp):
            flash('A new code has been sent to your email.')
        else:
            flash('Failed to resend code via email. Check system logs.')
            
    return redirect(url_for('verify_otp', context=context))

@app.route('/switch-2fa/<method>')
def switch_2fa(method):
    if 'temp_user' in session and session.get('otp'):
        otp = session['otp']
        if method == 'phone' and session.get('otp_phone'):
            session['otp_method'] = 'phone'
            send_otp_sms(session['otp_phone'], otp)
            flash('OTP code sent to your registered phone number.')
        elif method == 'email' and session.get('otp_email'):
            session['otp_method'] = 'email'
            send_otp_email(session['otp_email'], otp)
            flash('OTP code sent to your registered email.')
        return redirect(url_for('verify_otp', context='login'))
    flash('Session expired. Please login again.')
    return redirect(url_for('home'))

@app.route('/verify-otp/<context>', methods=['GET', 'POST'])
def verify_otp(context):
    if request.method == 'POST':
        user_otp = request.form['otp']
        generated_otp = session.get('otp')

        if user_otp == generated_otp:
            # Success
            session.pop('otp', None)
            if context == 'login':
                temp_user = session.get('temp_user')
                if temp_user:
                    next_url = session.get('next_url')
                    
                    conn = get_db_connection()
                    user = conn.execute("SELECT id, role, branch FROM users WHERE username = ?", (temp_user['username'],)).fetchone()
                    branch = None
                    if user:
                        branch = user['branch']
                        if user['role'] == 'student':
                            student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
                            if student:
                                branch = student['branch']
                    if branch:
                        branch = branch.lower()
                    conn.close()
                    
                    session.clear()
                    session.permanent = True
                    session['user'] = temp_user['username']
                    session['role'] = temp_user['role']
                    session['branch'] = branch
                    flash('Login Successful!')
                    if is_safe_next_url(next_url):
                        return redirect(next_url)
                    return redirect(url_for('dashboard'))
                else:
                    flash('Session expired. Please login again.')
                    return redirect(url_for('home'))
                    
            elif context == 'forgot_password':
                session['reset_verified'] = True
                return redirect(url_for('reset_new_password'))
        else:
            flash('Invalid OTP! Please try again.')
    
    # Determine what to display on the verification screen
    method = session.get('otp_method', 'email')
    if method == 'phone':
        target = session.get('otp_phone')
    else:
        target = session.get('otp_email')
        
    return render_template('verify_otp.html', email=target, context=context)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        security_key = request.form['security_key']

        is_strong, error_msg = check_password_strength(password)
        if not is_strong:
            flash(error_msg)
            return render_template('register.html')

        if role not in {'student', 'teacher'}:
            flash('Invalid account type.')
            return render_template('register.html')

        if not ADMIN_SECURITY_KEY:
            flash('Public registration is not enabled. Please contact admin.')
            return render_template('register.html')

        if not hmac.compare_digest(security_key, ADMIN_SECURITY_KEY):
            flash('Invalid security key.')
            return render_template('register.html')

        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                      (username, email, hash_password(password), role, 'verified'))
            user_id = c.lastrowid
            
            if role == 'student':
                # Extract student info safely
                info = {
                    'branch': request.form.get('branch'),
                    'class': normalize_class_name(request.form.get('class')),
                    'roll_number': request.form.get('roll_number'),
                    'guardian_name': request.form.get('guardian_name'),
                    'dob': request.form.get('dob'),
                    'section': request.form.get('section'),
                    'blood_group': request.form.get('blood_group'),
                    'village': request.form.get('village'),
                    'post_office': request.form.get('post_office'),
                    'police_station': request.form.get('police_station'),
                    'district': request.form.get('district'),
                    'phone_number': request.form.get('phone_number')
                }

                unique_code = generate_unique_student_code(c)
                
                c.execute('''
                    INSERT INTO student_info (user_id, branch, class, roll_number, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number, unique_code)
                    VALUES (:user_id, :branch, :class, :roll_number, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number, :unique_code)
                ''', {**info, 'user_id': user_id, 'unique_code': unique_code})
                
                try:
                    sync_student_ledger_and_dues(conn, user_id)
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to sync student ledger and dues in register: {e}")
                
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login', user_type='student'))
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                flash(f'Registration error: {str(e)}')
            else:
                flash('Username already exists!')
        except Exception as e:
            flash(f'Registration error: {str(e)}')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        mobile = request.form.get('mobile', '').strip()
        dob = request.form.get('dob', '').strip()
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user:
            if user['role'] == 'student':
                email = user['email']
                if email and email.strip() and '@' in email and not (mobile and dob):
                    # Student has an email, send Email OTP
                    otp = generate_otp()
                    if send_otp_email(email, otp):
                        session['otp'] = otp
                        session['otp_method'] = 'email'
                        session['otp_email'] = email
                        session['reset_user_id'] = user['id']
                        conn.close()
                        return render_template('verify_otp.html', email=email, context='forgot_password')
                    else:
                        flash('Failed to send OTP. Check system logs.')
                        conn.close()
                        return render_template('forgot_password.html')
                else:
                    # Fallback to Mobile & DOB verification for students without email
                    if mobile and dob:
                        student = conn.execute(
                            "SELECT * FROM student_info WHERE user_id = ? AND phone_number = ? AND dob = ?",
                            (user['id'], mobile, dob)
                        ).fetchone()
                        conn.close()
                        if student:
                            session['reset_verified'] = True
                            session['reset_user_id'] = user['id']
                            return redirect(url_for('reset_new_password'))
                        else:
                            flash('Mobile number or Date of Birth does not match our records!')
                            return render_template('forgot_password.html', is_student=True, username=username)
                    else:
                        # Render mobile and dob input form for student
                        conn.close()
                        return render_template('forgot_password.html', is_student=True, username=username)
            else:
                # Teachers/Admins: Send Email OTP
                email = user['email']
                if not email:
                    flash('No email found for this user. Cannot send OTP.')
                    conn.close()
                    return render_template('forgot_password.html')

                otp = generate_otp()
                if send_otp_email(email, otp):
                    session['otp'] = otp
                    session['otp_method'] = 'email'
                    session['otp_email'] = email
                    session['reset_user_id'] = user['id']
                    conn.close()
                    return render_template('verify_otp.html', email=email, context='forgot_password')
                else:
                    flash('Failed to send OTP. Check system logs.')
                    conn.close()
        else:
            flash('User not found!')
            conn.close()

    return render_template('forgot_password.html')

@app.route('/forgot-username', methods=['GET', 'POST'])
def forgot_username():
    username = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()

        if not name or not mobile:
            flash('Please enter your full name and mobile number.')
            return render_template('forgot_username.html')

        conn = get_db_connection()
        user = conn.execute('''
            SELECT u.username
            FROM users u
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE (
                LOWER(COALESCE(si.full_name, ti.full_name, u.username)) = LOWER(?)
                OR LOWER(REPLACE(COALESCE(si.full_name, ti.full_name, u.username), ' ', '')) = LOWER(REPLACE(?, ' ', ''))
            )
            AND COALESCE(si.phone_number, ti.phone_number, '') = ?
            LIMIT 1
        ''', (name, name, mobile)).fetchone()
        conn.close()

        if user:
            username = user['username']
        else:
            flash('No matching account found. Please check the details or contact admin.')

    return render_template('forgot_username.html', username=username)

@app.route('/reset-new-password', methods=['GET', 'POST'])
def reset_new_password():
    if not session.get('reset_verified'):
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        is_strong, error_msg = check_password_strength(new_password)
        if not is_strong:
            flash(error_msg)
            return render_template('reset_password.html')
            
        user_id = session.get('reset_user_id')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_password), user_id))
        conn.commit()
        conn.close()
        
        session.pop('reset_verified', None)
        session.pop('reset_user_id', None)
        flash('Password Reset Successfully! Please Login.')
        return redirect(url_for('login', user_type='student'))

    return render_template('reset_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if 'user' in session:
        role = session['role']
        username = session['user']
        
        conn = get_db_connection()
        c = conn.cursor()

        student_info = None
        student_marks = None
        all_users = None
        all_notices = None
        pending_forms = None
        pending_gallery = None
        pending_edit = None
        pending_profile_edits = None
        display_name = username
        admin_complaints = None
        student_complaints = None

        if role == 'admin':
            try:
                with open("debug_sync.txt", "w") as dbg_f:
                    dbg_student = c.execute("SELECT * FROM student_info WHERE user_id = 2").fetchone()
                    dbg_f.write(f"student_info: {dict(dbg_student) if dbg_student else 'None'}\n")
                    dbg_ledger = c.execute("SELECT * FROM student_ledger WHERE student_id = 2").fetchall()
                    dbg_f.write(f"student_ledger: {[dict(r) for r in dbg_ledger]}\n")
                    dbg_classes = c.execute("SELECT * FROM classes WHERE LOWER(branch) = 'bhogram'").fetchall()
                    dbg_f.write(f"classes: {[dict(r) for r in dbg_classes]}\n")
                    dbg_matrix = c.execute("SELECT * FROM fee_matrix WHERE branch = 'bhogram'").fetchall()
                    dbg_f.write(f"fee_matrix: {[dict(r) for r in dbg_matrix]}\n")
            except Exception as dbg_e:
                with open("debug_sync.txt", "w") as dbg_f:
                    dbg_f.write(f"error: {dbg_e}\n")
            if session.get('branch'):
                # Branch Admin (Manager)
                all_users = c.execute('''
                    SELECT u.id, u.username, u.email, u.role 
                    FROM users u
                    LEFT JOIN student_info si ON u.id = si.user_id
                    WHERE si.branch = ? COLLATE NOCASE OR u.role = 'teacher' OR u.username = ?
                ''', (session['branch'], username)).fetchall()
                
                all_notices = c.execute('''
                    SELECT * FROM notices 
                    WHERE branch IS NULL OR branch = ? COLLATE NOCASE
                    ORDER BY created_at DESC
                ''', (session['branch'],)).fetchall()
                
                pending_forms = c.execute('''
                    SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                    FROM applications a 
                    LEFT JOIN users u ON a.user_id = u.id 
                    WHERE a.branch = ? COLLATE NOCASE AND a.type NOT IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                    ORDER BY a.submitted_at DESC
                ''', (session['branch'],)).fetchall()
                
                pending_profile_edits = c.execute('''
                    SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                    FROM applications a 
                    LEFT JOIN users u ON a.user_id = u.id 
                    WHERE a.branch = ? COLLATE NOCASE AND a.type IN ('student_info_edit', 'teacher_info_edit', 'student_password_change') AND a.status = 'Pending'
                    ORDER BY a.submitted_at DESC
                ''', (session['branch'],)).fetchall()
                
                pending_gallery = c.execute('''
                    SELECT pm.*, u.username 
                    FROM pending_media pm 
                    JOIN users u ON pm.user_id = u.id 
                    WHERE pm.status = 'Pending' AND pm.branch = ? COLLATE NOCASE
                    ORDER BY pm.submitted_at DESC
                ''', (session['branch'],)).fetchall()

                admin_complaints = c.execute('''
                    SELECT c.*, COALESCE(si.full_name, u_s.username) as student_name, 
                           COALESCE(ti.full_name, u_t.username) as teacher_name,
                           si.branch as branch
                    FROM complaints c
                    JOIN users u_s ON c.student_id = u_s.id
                    JOIN users u_t ON c.teacher_id = u_t.id
                    LEFT JOIN student_info si ON u_s.id = si.user_id
                    LEFT JOIN teacher_info ti ON u_t.id = ti.user_id
                    WHERE si.branch = ? COLLATE NOCASE
                    ORDER BY c.created_at DESC
                ''', (session['branch'],)).fetchall()
            else:
                # Super Admin
                all_users = c.execute("SELECT id, username, email, role FROM users").fetchall()
                all_notices = c.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()
                
                pending_forms = c.execute('''
                    SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                    FROM applications a 
                    LEFT JOIN users u ON a.user_id = u.id 
                    WHERE a.type NOT IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                    ORDER BY a.submitted_at DESC
                ''').fetchall()
                
                pending_profile_edits = c.execute('''
                    SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                    FROM applications a 
                    LEFT JOIN users u ON a.user_id = u.id 
                    WHERE a.type IN ('student_info_edit', 'teacher_info_edit', 'student_password_change') AND a.status = 'Pending'
                    ORDER BY a.submitted_at DESC
                ''').fetchall()
                
                pending_gallery = c.execute('''
                    SELECT pm.*, u.username 
                    FROM pending_media pm 
                    JOIN users u ON pm.user_id = u.id 
                    WHERE pm.status = 'Pending'
                    ORDER BY pm.submitted_at DESC
                ''').fetchall()

                admin_complaints = c.execute('''
                    SELECT c.*, COALESCE(si.full_name, u_s.username) as student_name, 
                           COALESCE(ti.full_name, u_t.username) as teacher_name,
                           si.branch as branch
                    FROM complaints c
                    JOIN users u_s ON c.student_id = u_s.id
                    JOIN users u_t ON c.teacher_id = u_t.id
                    LEFT JOIN student_info si ON u_s.id = si.user_id
                    LEFT JOIN teacher_info ti ON u_t.id = ti.user_id
                    ORDER BY c.created_at DESC
                ''').fetchall()

        elif role == 'student':
            student_info = c.execute('''
                SELECT si.*, u.email 
                FROM student_info si 
                JOIN users u ON si.user_id = u.id 
                WHERE u.username = ?
            ''', (username,)).fetchone()
            if student_info and student_info['full_name']:
                display_name = student_info['full_name']

            student_marks = c.execute('''
                SELECT m.*, u.username as teacher_name 
                FROM marks m 
                JOIN users u ON m.uploaded_by = u.id 
                WHERE m.student_id = (SELECT id FROM users WHERE username = ?)
                ORDER BY m.uploaded_at DESC LIMIT 5
            ''', (username,)).fetchall()
            
            all_notices = c.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 3").fetchall()
            pending_edit = c.execute('''
                SELECT * FROM applications 
                WHERE user_id = (SELECT id FROM users WHERE username = ?) AND type = 'student_info_edit' AND status = 'Pending'
            ''', (username,)).fetchone()

            student_complaints = c.execute('''
                SELECT c.*, COALESCE(ti.full_name, u.username) as teacher_name
                FROM complaints c
                JOIN users u ON c.teacher_id = u.id
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                WHERE c.student_id = (SELECT id FROM users WHERE username = ?)
                ORDER BY c.created_at DESC
            ''', (username,)).fetchall()

        elif role == 'teacher':
            pending_edit = c.execute('''
                SELECT * FROM applications 
                WHERE user_id = (SELECT id FROM users WHERE username = ?) AND type = 'teacher_info_edit' AND status = 'Pending'
            ''', (username,)).fetchone()
            
            teacher_info = c.execute('''
                SELECT ti.* 
                FROM teacher_info ti 
                JOIN users u ON ti.user_id = u.id 
                WHERE u.username = ?
            ''', (username,)).fetchone()
            if teacher_info and teacher_info['full_name']:
                display_name = teacher_info['full_name']

        # Files logic
        content = {}
        allowed_branches = [session['branch']] if session.get('branch') else BRANCHES
        for branch in allowed_branches:
            content[branch] = {}
            for category in CATEGORIES:
                path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
                files = os.listdir(path) if os.path.exists(path) else []
                content[branch][category] = files
        
        conn.close()
        return render_template('dashboard.html', 
                               role=role, 
                               content=content, 
                               username=username,
                               display_name=display_name,
                               student_info=student_info,
                               student_marks=student_marks,
                               all_users=all_users,
                               all_notices=all_notices,
                               pending_forms=pending_forms,
                               pending_gallery=pending_gallery,
                               pending_edit=pending_edit,
                               pending_profile_edits=pending_profile_edits,
                               admin_complaints=admin_complaints,
                               student_complaints=student_complaints)
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    user = get_session_user()
    conn = get_db_connection()
    user_row = conn.execute(
        "SELECT email FROM users WHERE id = ?",
        (user['id'],)
    ).fetchone()
    conn.close()
    return render_template('profile.html', user_email=user_row['email'] if user_row else '')

@app.route('/profile/update-security', methods=['POST'])
@login_required
def update_profile_security():
    user = get_session_user()
    action = request.form.get('action')
    current_password = request.form.get('current_password', '')

    conn = get_db_connection()
    user_row = conn.execute(
        "SELECT id, email, password FROM users WHERE id = ?",
        (user['id'],)
    ).fetchone()

    if not user_row or not verify_password(user_row['password'], current_password):
        conn.close()
        flash('Current password is incorrect.')
        return redirect(url_for('profile'))

    if action == 'change_password':
        new_password = request.form.get('new_password', '')
        is_strong, error_msg = check_password_strength(new_password)
        if not is_strong:
            conn.close()
            flash(error_msg)
            return redirect(url_for('profile'))
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_password), user['id']))
        flash('Password updated successfully.')
    elif action == 'update_email':
        new_email = request.form.get('new_email', '').strip()
        if '@' not in new_email:
            conn.close()
            flash('Please enter a valid email address.')
            return redirect(url_for('profile'))
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (new_email, user['id']))
        flash('Email updated successfully.')
    else:
        flash('Unknown profile action.')

    conn.commit()
    conn.close()
    return redirect(url_for('profile'))

@app.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    user = get_session_user()
    file = request.files.get('avatar')
    if not file or file.filename == '':
        flash('Please select an image to upload.')
        return redirect(url_for('profile'))

    filename = secure_filename(file.filename)
    if not filename:
        flash('Invalid image filename.')
        return redirect(url_for('profile'))

    old_avatar = session.get('avatar_url')
    if old_avatar:
        try:
            delete_old_mapped_file(os.path.basename(old_avatar))
        except Exception as e:
            print(f"Error deleting old avatar: {e}")

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    saved_name = f"{user['id']}_{timestamp}_{filename}"
    avatar_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')
    os.makedirs(avatar_folder, exist_ok=True)
    local_path = os.path.join(avatar_folder, saved_name)
    file.save(local_path)
    upload_file_to_drive_and_map(local_path, saved_name, file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_AVATARS'))
    session['avatar_url'] = url_for('static', filename=f'uploads/avatars/{saved_name}')
    flash('Profile photo uploaded successfully.')
    return redirect(url_for('profile'))

@app.route('/admission-form')
def admission_form():
    return render_template('application_form.html')

@app.route('/submit-application', methods=['POST'])
def submit_application():
    form_data = request.form.to_dict()
    form_data['attached_documents'] = request.form.getlist('attached_documents')
    form_type = form_data.get('form_type', 'Admission Form')
    
    if form_type == 'Admission Form':
        uploaded_documents = {}
        doc_fields = {
            'Birth Certificate': 'file_birth_certificate',
            'Aadhaar Card': 'file_aadhaar_card',
            'Profile Photo': 'file_one_photo',
            'Bank Passbook': 'file_bank_passbook',
            'T.C Certificate': 'file_tc_certificate'
        }
        for doc_name, input_name in doc_fields.items():
            if doc_name in form_data['attached_documents']:
                file_obj = request.files.get(input_name)
                if file_obj and file_obj.filename != '':
                    filename = secure_filename(file_obj.filename)
                    if filename:
                        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'documents')
                        os.makedirs(upload_dir, exist_ok=True)
                        timestamp = int(datetime.now(timezone.utc).timestamp())
                        saved_filename = f"{input_name}_{timestamp}_{filename}"
                        local_path = os.path.join(upload_dir, saved_filename)
                        file_obj.save(local_path)
                        upload_file_to_drive_and_map(local_path, saved_filename, file_obj.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_DOCUMENTS'))
                        uploaded_documents[doc_name] = f"uploads/documents/{saved_filename}"
        form_data['uploaded_documents'] = uploaded_documents

    if form_type == 'Teacher Joining Form':
        cv_file = request.files.get('cv_file')
        if not cv_file or cv_file.filename == '':
            flash('Error: CV file is required.')
            return redirect(url_for('register') + '?type=teacher')
            
        filename = secure_filename(cv_file.filename)
        if not filename:
            flash('Error: Invalid CV filename.')
            return redirect(url_for('register') + '?type=teacher')
            
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'cvs')
        os.makedirs(upload_dir, exist_ok=True)
        timestamp = int(datetime.now(timezone.utc).timestamp())
        saved_filename = f"cv_{timestamp}_{filename}"
        local_path = os.path.join(upload_dir, saved_filename)
        cv_file.save(local_path)
        upload_file_to_drive_and_map(local_path, saved_filename, cv_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_CV'))
        form_data['cv_path'] = f"uploads/cvs/{saved_filename}"
    
    user_id = None
    if 'user' in session:
        conn = get_db_connection()
        res = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
        if res: user_id = res['id']
        conn.close()

    # Extract and normalize branch from form data
    branch = 'bhogram'

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO applications (user_id, type, data, branch)
        VALUES (?, ?, ?, ?)
    ''', (user_id, form_type, json.dumps(form_data), branch))
    conn.commit()
    conn.close()
    
    flash('Your application has been submitted successfully!')
    return redirect(url_for('home'))

@app.route('/admin/applications')
def admin_applications():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        if session.get('branch'):
            applications = conn.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                WHERE a.branch = ? COLLATE NOCASE AND a.type NOT IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                ORDER BY a.submitted_at DESC
            ''', (session['branch'],)).fetchall()
        else:
            applications = conn.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                WHERE a.type NOT IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                ORDER BY a.submitted_at DESC
            ''').fetchall()
        conn.close()
        return render_template('admin/application_list.html', applications=applications)
    return redirect(url_for('home'))

@app.route('/admin/profile-edits')
def admin_profile_edits():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        logo_url = conn.execute("SELECT content FROM settings WHERE key='logo_url'").fetchone()
        logo_url = logo_url[0] if logo_url else None
        if session.get('branch'):
            applications = conn.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                WHERE a.branch = ? COLLATE NOCASE AND a.type IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                ORDER BY a.submitted_at DESC
            ''', (session['branch'],)).fetchall()
        else:
            applications = conn.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                WHERE a.type IN ('student_info_edit', 'teacher_info_edit', 'student_password_change')
                ORDER BY a.submitted_at DESC
            ''').fetchall()
        conn.close()
        return render_template('admin/profile_edit_list.html', applications=applications, role=session['role'], logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/view-form/<int:form_id>')
def view_form(form_id):
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        form = conn.execute("SELECT * FROM applications WHERE id = ?", (form_id,)).fetchone()
        
        if form:
            if session.get('branch') and (form['branch'] or '').lower() != session['branch'].lower():
                conn.close()
                flash('Permission denied: This application belongs to another campus.')
                return redirect(url_for('dashboard'))
            data = json.loads(form['data'])
            
            current_info = None
            if form['type'] in ['student_info_edit', 'student_password_change']:
                row = conn.execute("SELECT u.username, si.* FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.id = ?", (form['user_id'],)).fetchone()
                current_info = dict(row) if row else None
            elif form['type'] == 'teacher_info_edit':
                row = conn.execute("SELECT * FROM teacher_info WHERE user_id = ?", (form['user_id'],)).fetchone()
                current_info = dict(row) if row else None
                
            conn.close()
            return render_template('admin_form_view.html', form=form, data=data, current_info=current_info)
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/admin/form-action/<int:form_id>/<action>', methods=['POST'])
def form_action(form_id, action):
    if 'user' in session and session['role'] == 'admin':
        status = 'Accepted' if action == 'approve' else 'Rejected'
        conn = get_db_connection()
        
        # Initialize variables for email notification
        email_username = None
        email_temp_password = None
        email_unique_code = None
        
        # Fetch the application details
        form = conn.execute("SELECT * FROM applications WHERE id = ?", (form_id,)).fetchone()
        if not form:
            conn.close()
            flash('Application not found.')
            return redirect(url_for('admin_applications'))
            
        # Check permissions for Branch Admin
        if session.get('branch') and (form['branch'] or '').lower() != session['branch'].lower():
            conn.close()
            flash('Permission denied: This application belongs to another campus.')
            return redirect(url_for('dashboard'))

        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, form_id))
        
        if status == 'Accepted' and form['type'] == 'student_info_edit':
            try:
                data = json.loads(form['data'])
                # Fetch current class
                row = conn.execute("SELECT class FROM student_info WHERE user_id = ?", (form['user_id'],)).fetchone()
                class_name = row['class'] if row else 'Nursery'
                
                session_val = data.get('session', '2026').strip()
                mode_of_admission = data.get('mode_of_admission', 'School').strip()
                father_qualification = data.get('father_qualification', '').strip()
                father_occupation = data.get('father_occupation', '').strip()
                father_monthly_income = data.get('father_monthly_income', '').strip()
                mother_qualification = data.get('mother_qualification', '').strip()
                mother_occupation = data.get('mother_occupation', '').strip()
                mother_monthly_income = data.get('mother_monthly_income', '').strip()
                nationality = data.get('nationality', 'Indian').strip()
                religion = data.get('religion', '').strip()
                gender = data.get('gender', '').strip()
                caste = data.get('caste', '').strip()
                whatsapp_no = data.get('whatsapp_no', '').strip()
                previous_class = data.get('previous_class', '').strip()
                prev_marks_percentage = data.get('prev_marks_percentage', '').strip()
                identification_mark = data.get('identification_mark', '').strip()
                sl_no = data.get('sl_no', '').strip()
                
                attached_list = data.get('attached_documents', [])
                uploaded_docs = data.get('uploaded_documents', {})
                attached_documents = json.dumps({'attached': attached_list, 'files': uploaded_docs})
                    
                take_school = data.get('take_school', 1)
                take_coaching = data.get('take_coaching', 0)
                take_day_hostel = data.get('take_day_hostel', 0)
                take_car = data.get('take_car', 0)
                
                coaching_opted = 1 if take_coaching else 0
                car_opted = 1 if take_car else 0
                mode_of_admission = 'Day Hostel' if take_day_hostel else ('School with Coaching' if take_coaching else 'School')
                
                monthly_fee = calculate_default_monthly_fee(class_name, mode_of_admission, coaching_opted == 1, car_opted == 1, branch=form['branch'] or 'bhogram', conn=conn)
                
                admission_fee = data.get('admission_fee')
                readmission_fee = data.get('readmission_fee')
                if admission_fee is None or readmission_fee is None:
                    adm_def = 0.0
                    readm_def = 0.0
                    try:
                        cls_norm = normalize_class_name(class_name)
                        row_class = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_norm, form['branch'] or 'bhogram')).fetchone()
                        if row_class:
                            if take_day_hostel:
                                adm_def = float(row_class['admission_fee_hostel'] or 0.0)
                                readm_def = float(row_class['readmission_fee_hostel'] or 0.0)
                            elif take_coaching:
                                adm_def = float(row_class['admission_fee_coaching'] or 0.0)
                                readm_def = float(row_class['readmission_fee_coaching'] or 0.0)
                            elif take_school:
                                adm_def = float(row_class['admission_fee'] or 0.0)
                                readm_def = float(row_class['readmission_fee_school'] or 0.0)
                    except Exception as ex:
                        print(f"Error computing default admission fees: {ex}")
                    if admission_fee is None: admission_fee = adm_def
                    if readmission_fee is None: readmission_fee = readm_def

                conn.execute('''
                    UPDATE student_info SET
                        full_name = ?, guardian_name = ?, mothers_name = ?, phone_number = ?, dob = ?,
                        section = ?, blood_group = ?, aadhaar_number = ?, village = ?, post_office = ?,
                        police_station = ?, district = ?, bank_details = ?,
                        session = ?, mode_of_admission = ?, father_qualification = ?, father_occupation = ?, father_monthly_income = ?,
                        mother_qualification = ?, mother_occupation = ?, mother_monthly_income = ?, nationality = ?, religion = ?,
                        gender = ?, caste = ?, whatsapp_no = ?, previous_class = ?, prev_marks_percentage = ?, identification_mark = ?,
                        attached_documents = ?, coaching_opted = ?, car_opted = ?, monthly_fee = ?, sl_no = ?,
                        take_school = ?, take_coaching = ?, take_day_hostel = ?, take_car = ?,
                        admission_fee = ?, readmission_fee = ?
                    WHERE user_id = ?
                ''', (
                    data.get('full_name'), data.get('guardian_name'), data.get('mothers_name'),
                    data.get('phone_number'), data.get('dob'), data.get('section'),
                    data.get('blood_group'), data.get('aadhaar_number'), data.get('village'),
                    data.get('post_office'), data.get('police_station'), data.get('district'),
                    data.get('bank_details'),
                    session_val, mode_of_admission, father_qualification, father_occupation, father_monthly_income,
                    mother_qualification, mother_occupation, mother_monthly_income, nationality, religion,
                    gender, caste, whatsapp_no, previous_class, prev_marks_percentage, identification_mark,
                    attached_documents, coaching_opted, car_opted, monthly_fee, sl_no,
                    take_school, take_coaching, take_day_hostel, take_car,
                    admission_fee, readmission_fee,
                    form['user_id']
                ))
            except Exception as e:
                print(f" [EDIT REQUEST ERROR] Failed to apply edit: {e}")
        elif status == 'Accepted' and form['type'] == 'student_password_change':
            try:
                data = json.loads(form['data'])
                new_password = data.get('new_password')
                conn.execute("UPDATE users SET password = ?, temp_password = NULL WHERE id = ?", (hash_password(new_password), form['user_id']))
            except Exception as e:
                print(f" [PASSWORD CHANGE ERROR] Failed to apply password change: {e}")
        elif status == 'Accepted' and form['type'] == 'teacher_info_edit':
            try:
                data = json.loads(form['data'])
                conn.execute('''
                    UPDATE teacher_info SET
                        full_name = ?, phone_number = ?, qualification = ?, address = ?,
                        aadhaar_number = ?, bank_details = ?
                    WHERE user_id = ?
                ''', (
                    data.get('full_name'), data.get('phone_number'), data.get('qualification'),
                    data.get('address'), data.get('aadhaar_number'), data.get('bank_details'),
                    form['user_id']
                ))
            except Exception as e:
                print(f" [EDIT REQUEST ERROR] Failed to apply teacher edit: {e}")
        elif status == 'Accepted' and form['type'] == 'Teacher Joining Form':
            try:
                data = json.loads(form['data'])
                email = data.get('email', '').strip()
                full_name = data.get('full_name', '').strip()
                phone_number = data.get('phone_no', '').strip()
                qualification = data.get('qualification', '').strip()
                branch = form['branch'] or data.get('branch', 'bhogram')
                aadhaar_number = data.get('aadhar_no', '').strip()
                cv_path = data.get('cv_path', '').strip()
                teacher_type = data.get('teacher_type', 'Regular Class').strip()
                
                # Check bank details inputs and serialize
                bank_name = data.get('bank_name', '').strip()
                branch_name = data.get('branch_name', '').strip()
                account_no = data.get('account_no', '').strip()
                ifsc_code = data.get('ifsc_code', '').strip()
                bank_details = None
                if bank_name or branch_name or account_no or ifsc_code:
                    bank_details = json.dumps({
                        'bank_name': bank_name,
                        'branch_name': branch_name,
                        'account_no': account_no,
                        'ifsc_code': ifsc_code
                    })

                # Determine address
                address_parts = [
                    data.get('village', ''),
                    data.get('po', ''),
                    data.get('ps', ''),
                    data.get('dist', ''),
                    data.get('state', ''),
                    data.get('pin', '')
                ]
                address = ', '.join([p.strip() for p in address_parts if p.strip()])
                
                # Generate unique username
                base_username = email.split('@')[0] if email else 'teacher'
                base_username = "".join(c for c in base_username if c.isalnum()).lower()
                username = base_username
                counter = 1
                while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Generate temporary password
                temp_password = 'teacher' + ''.join(random.choices(string.digits, k=6))
                
                # Insert into users
                c = conn.cursor()
                c.execute('''
                    INSERT INTO users (username, email, password, role, security_key, temp_password, branch)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (username, email, hash_password(temp_password), 'teacher', 'verified', temp_password, branch))
                user_id = c.lastrowid
                
                # Insert into teacher_info
                joining_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                c.execute('''
                    INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address, aadhaar_number, bank_details, teacher_type, cv_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, full_name, phone_number, qualification, joining_date, address, aadhaar_number, bank_details, teacher_type, cv_path))
                
                # Update application's user_id with the new user_id so it links!
                c.execute("UPDATE applications SET user_id = ? WHERE id = ?", (user_id, form_id))
                
                email_username = username
                email_temp_password = temp_password
                
                flash(f'Teacher account created successfully! Username: {username}, Temp Password: {temp_password}')
            except Exception as e:
                print(f" [TEACHER APPROVAL ERROR] Failed to create teacher: {e}")
                flash(f"Error creating teacher account: {str(e)}")
        elif status == 'Accepted' and form['type'] == 'Admission Form':
            try:
                data = json.loads(form['data'])
                full_name = data.get('full_name', '').strip()
                dob = data.get('dob', '').strip()
                gender = data.get('gender', '').strip()
                blood_group = data.get('blood_group', '').strip()
                religion = data.get('religion', '').strip()
                nationality = data.get('nationality', 'Indian').strip()
                aadhaar_number = data.get('aadhar_no', '').strip()
                
                # Parse bank details and serialize
                bank_name = data.get('bank_name', '').strip()
                branch_name = data.get('branch_name', '').strip()
                account_no = data.get('account_no', '').strip()
                ifsc_code = data.get('ifsc_code', '').strip()
                bank_details = None
                if bank_name or branch_name or account_no or ifsc_code:
                    bank_details = json.dumps({
                        'bank_name': bank_name,
                        'branch_name': branch_name,
                        'account_no': account_no,
                        'ifsc_code': ifsc_code
                    })
                
                branch = form['branch'] or data.get('branch', 'bhogram')
                class_applied = normalize_class_name(data.get('class_applied', '').strip())
                prev_school = data.get('prev_school', '').strip()
                father_name = data.get('father_name', '').strip()
                mother_name = data.get('mother_name', '').strip()
                father_occupation = data.get('father_occupation', '').strip()
                guardian_phone = data.get('guardian_phone', '').strip()
                alt_phone = data.get('alt_phone', '').strip()
                
                village = data.get('village', '').strip()
                po = data.get('po', '').strip()
                ps = data.get('ps', '').strip()
                dist = data.get('dist', '').strip()
                state = data.get('state', '').strip()
                pin = data.get('pin', '').strip()
                
                # Generate unique username
                first_name = full_name.split()[0] if full_name else 'student'
                first_name = "".join(c for c in first_name if c.isalnum()).lower()
                base_username = f"{first_name}"
                username = base_username
                counter = 1
                while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Generate temporary password
                temp_password = 'student' + ''.join(random.choices(string.digits, k=6))
                
                # Generate unique student code
                unique_code = generate_unique_student_code(conn.cursor())
                
                # Insert into users
                c = conn.cursor()
                c.execute('''
                    INSERT INTO users (username, email, password, role, security_key, temp_password, branch)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (username, '', hash_password(temp_password), 'student', 'verified', temp_password, branch))
                user_id = c.lastrowid
                
                # Extract new fields
                session_val = data.get('session', '2026').strip()
                mode_of_admission = data.get('mode_of_admission', 'School').strip()
                father_qualification = data.get('father_qualification', '').strip()
                father_monthly_income = data.get('father_monthly_income', '').strip()
                mother_qualification = data.get('mother_qualification', '').strip()
                mother_occupation = data.get('mother_occupation', '').strip()
                mother_monthly_income = data.get('mother_monthly_income', '').strip()
                caste = data.get('caste', '').strip()
                whatsapp_no = data.get('whatsapp_no', '').strip()
                previous_class = data.get('previous_class', '').strip()
                prev_marks_percentage = data.get('prev_marks_percentage', '').strip()
                identification_mark = data.get('identification_mark', '').strip()
                sl_no = data.get('sl_no', '').strip()
                
                attached_list = data.get('attached_documents', [])
                uploaded_docs = data.get('uploaded_documents', {})
                attached_documents = json.dumps({'attached': attached_list, 'files': uploaded_docs})
                    
                coaching_opted = 1 if 'coaching' in mode_of_admission.lower() else 0
                car_opted = 1 if (data.get('car_opted') == 'Yes' or mode_of_admission == 'School+Car') else 0
                
                monthly_fee = calculate_default_monthly_fee(class_applied, mode_of_admission, coaching_opted == 1, car_opted == 1, branch=branch, conn=conn)

                # Insert into student_info
                date_of_admission = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                c.execute('''
                    INSERT INTO student_info (
                        user_id, branch, class, roll_number, aadhaar_number, phone_number, guardian_name, 
                        mothers_name, full_name, dob, section, blood_group, village, post_office, 
                        police_station, district, date_of_admission, bank_details, unique_code,
                        session, mode_of_admission, father_qualification, father_occupation, father_monthly_income,
                        mother_qualification, mother_occupation, mother_monthly_income, nationality, religion,
                        gender, caste, whatsapp_no, previous_class, prev_marks_percentage, identification_mark,
                        attached_documents, coaching_opted, car_opted, monthly_fee, sl_no
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, branch, class_applied, '', aadhaar_number, guardian_phone, father_name, 
                    mother_name, full_name, dob, '', blood_group, village, po, 
                    ps, dist, date_of_admission, bank_details, unique_code,
                    session_val, mode_of_admission, father_qualification, father_occupation, father_monthly_income,
                    mother_qualification, mother_occupation, mother_monthly_income, nationality, religion,
                    gender, caste, whatsapp_no, previous_class, prev_marks_percentage, identification_mark,
                    attached_documents, coaching_opted, car_opted, monthly_fee, sl_no
                ))
                
                # Update application's user_id with the new user_id so it links!
                c.execute("UPDATE applications SET user_id = ? WHERE id = ?", (user_id, form_id))
                
                try:
                    sync_student_ledger_and_dues(conn, user_id)
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to sync student ledger and dues on approval: {e}")
                
                email_username = username
                email_temp_password = temp_password
                email_unique_code = unique_code
                
                flash(f'Student account created successfully! Username: {username}, Temp Password: {temp_password}, Registration Code: {unique_code}')
            except Exception as e:
                print(f" [STUDENT APPROVAL ERROR] Failed to create student: {e}")
                flash(f"Error creating student account: {str(e)}")

        # --- SEND EMAIL NOTIFICATION ---
        to_email = None
        recipient_name = "User"
        
        try:
            data = json.loads(form['data'])
            if data.get('email'):
                to_email = data.get('email').strip()
            elif data.get('email_id'):
                to_email = data.get('email_id').strip()
            
            if data.get('full_name'):
                recipient_name = data.get('full_name').strip()
        except Exception:
            data = {}
            
        if not to_email and form['user_id']:
            user_row = conn.execute("SELECT email, username FROM users WHERE id = ?", (form['user_id'],)).fetchone()
            if user_row:
                if user_row['email']:
                    to_email = user_row['email'].strip()
                if recipient_name == "User":
                    recipient_name = user_row['username']
                    
        if to_email:
            subject = f"Al Hidayet Mission - Application {status}"
            body = f"Hello {recipient_name},\n\n"
            
            if form['type'] == 'Teacher Joining Form':
                if status == 'Accepted':
                    body += f"Congratulations! Your application to join Al Hidayet Mission as a teacher has been accepted.\n\n"
                    body += f"Your teacher account details are:\n"
                    body += f"Username: {email_username}\n"
                    body += f"Temporary Password: {email_temp_password}\n\n"
                    body += f"Please log in and update your password immediately."
                else:
                    body += f"Thank you for your interest in Al Hidayet Mission. We regret to inform you that your application has been rejected."
            
            elif form['type'] == 'Admission Form':
                if status == 'Accepted':
                    body += f"Congratulations! Your admission request for Al Hidayet Mission has been accepted.\n\n"
                    body += f"Your student account details are:\n"
                    body += f"Username: {email_username}\n"
                    body += f"Temporary Password: {email_temp_password}\n"
                    body += f"Registration Code: {email_unique_code}\n\n"
                    body += f"Please log in to your student portal using these credentials."
                else:
                    body += f"We regret to inform you that your admission request for Al Hidayet Mission has been rejected."
            
            elif form['type'] in ['student_info_edit', 'teacher_info_edit']:
                if status == 'Accepted':
                    body += f"Your request to update your profile information has been approved and applied successfully."
                else:
                    body += f"Your request to update your profile information has been rejected by the administrator."
                    
            elif form['type'] == 'student_password_change':
                if status == 'Accepted':
                    body += f"Your request to reset/change your password has been approved and updated successfully."
                else:
                    body += f"Your request to reset/change your password has been rejected by the administrator."
            
            else:
                body += f"Your application of type '{form['type']}' has been reviewed by the administrator and status is updated to: {status}."
                
            body += f"\n\nRegards,\nBhogram Al-Hidayet Mission"
            
            send_notification_email(to_email, subject, body)
        # --- END SEND EMAIL NOTIFICATION ---

        try:
            sync_classes(conn)
        except Exception as e:
            print(f" [DB MIGRATE ERROR] sync_classes failed in form_action: {e}")

        conn.commit()
        conn.close()
        flash(f'Application {status}!')
    return redirect(url_for('admin_applications'))

@app.route('/admin/delete-application/<int:form_id>', methods=['POST'])
def delete_application(form_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        
        # Check permissions and retrieve data for file deletion
        form = conn.execute("SELECT branch, data FROM applications WHERE id = ?", (form_id,)).fetchone()
        if session.get('branch'):
            if not form or (form['branch'] or '').lower() != session['branch'].lower():
                conn.close()
                flash('Permission denied: This application belongs to another campus.')
                return redirect(url_for('admin_applications'))

        # Delete any uploaded files from Google Drive/disk
        if form and form['data']:
            try:
                import json
                data = json.loads(form['data'])
                if data.get('cv_path'):
                    delete_old_mapped_file(data['cv_path'])
                uploaded_docs = data.get('uploaded_documents') or {}
                for doc_path in uploaded_docs.values():
                    delete_old_mapped_file(doc_path)
            except Exception as e:
                print(f"Error cleaning up application files: {e}")

        conn.execute("DELETE FROM applications WHERE id = ?", (form_id,))
        conn.commit()
        conn.close()
        flash('Admission request deleted successfully.')
    else:
        flash('Access denied.')
    return redirect(url_for('admin_applications'))

@app.route('/admin/post-notice', methods=['POST'])
def post_notice():
    if 'user' in session and session['role'] == 'admin':
        content = request.form['content'].strip()
        
        photo_path = None
        if 'notice_photo' in request.files:
            file = request.files['notice_photo']
            if file and file.filename != '':
                import time
                filename = secure_filename(f"{int(time.time())}_{file.filename}")
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'notices')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                photo_path = filename
        
        conn = get_db_connection()
        conn.execute("INSERT INTO notices (content, branch, photo_path) VALUES (?, 'bhogram', ?)", (content, photo_path))
        conn.commit()
        send_activity_notification("Post Notice", f"Posted notice: '{content[:100]}...' (attachment: {photo_path or 'None'}).")
        conn.close()
        flash('Notice posted successfully!')
    return redirect(url_for('dashboard'))

@app.route('/admin/delete-notice/<int:notice_id>', methods=['POST'])
def delete_notice(notice_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        
        # Check branch permission if branch admin
        notice = conn.execute("SELECT branch, content FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if session.get('branch'):
            if not notice or notice['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: Notice belongs to another campus.')
                return redirect(url_for('dashboard'))
                
        conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
        conn.commit()
        if notice:
            send_activity_notification("Delete Notice", f"Deleted notice ID {notice_id}: '{notice['content'][:100]}...'")
        conn.close()
        flash('Notice deleted successfully!')
    else:
        flash('Access denied.')
    return redirect(url_for('dashboard'))

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        try:
            user_row = conn.execute("SELECT username, role FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user_row:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return {'status': 'error', 'message': 'User not found'}
                flash('User not found.')
                return redirect(request.referrer or url_for('dashboard'))

            admin_id_row = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
            admin_id = admin_id_row['id'] if admin_id_row else 1

            # Delete/update child rows first to satisfy foreign key constraints
            conn.execute("DELETE FROM student_info WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM teacher_info WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (user_id,))
            conn.execute("DELETE FROM teacher_assignments WHERE teacher_id = ?", (user_id,))
            conn.execute("DELETE FROM class_teachers WHERE teacher_id = ?", (user_id,))
            conn.execute("DELETE FROM marks WHERE student_id = ?", (user_id,))
            conn.execute("UPDATE marks SET uploaded_by = ? WHERE uploaded_by = ?", (admin_id, user_id))
            conn.execute("DELETE FROM fees WHERE student_id = ?", (user_id,))
            conn.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM pending_media WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM meeting_attendance WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM complaints WHERE student_id = ? OR teacher_id = ?", (user_id, user_id))
            conn.execute("UPDATE question_papers SET uploaded_by = ? WHERE uploaded_by = ?", (admin_id, user_id))
            conn.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
            
            # Finally delete the user parent record
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            try:
                sync_classes(conn)
            except Exception as e:
                print(f" [DB MIGRATE ERROR] sync_classes failed in delete_user: {e}")
            conn.commit()
            
            send_activity_notification("Delete User", f"Deleted user ID {user_id} (username: '{user_row[0]}', role: '{user_row[1]}').")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'status': 'success'}
            flash('User deleted successfully!')
        except Exception as e:
            conn.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'status': 'error', 'message': f"Database error: {str(e)}"}
            flash(f"Database error: {str(e)}", 'error')
        finally:
            conn.close()
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {'status': 'error', 'message': 'Permission denied'}
        flash('Permission denied.')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/reset-password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user' in session and session['role'] == 'admin':
        new_password = 'mission' + ''.join(random.choices(string.digits, k=6))
        conn = get_db_connection()
        user_row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.execute("UPDATE users SET password = ?, temp_password = ? WHERE id = ?", (hash_password(new_password), new_password, user_id))
        conn.commit()
        conn.close()
        if user_row:
            send_activity_notification("Reset User Password", f"Reset password for user ID {user_id} (username: '{user_row[0]}'). Temporary password: '{new_password}'.")
        flash(f'Password reset successfully. Temporary password: {new_password}')
    next_endpoint = request.form.get('next')
    if next_endpoint == 'teacher_list':
        return redirect(url_for('teacher_list'))
    if next_endpoint == 'student_list':
        return redirect(url_for('student_list'))
    return redirect(url_for('dashboard'))

@app.route('/admin/change-password/<int:user_id>', methods=['POST'])
@login_required
def change_password_directory(user_id):
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    new_password = request.form.get('new_password', '').strip()
    is_strong, error_msg = check_password_strength(new_password)
    if not is_strong:
        flash(error_msg)
        return redirect(request.referrer or url_for('student_list'))
        
    conn = get_db_connection()
    target_user = conn.execute("SELECT username, role, branch FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target_user:
        conn.close()
        flash('User not found.')
        return redirect(request.referrer or url_for('student_list'))
        
    if user['role'] == 'admin':
        # Admin changes it directly
        conn.execute("UPDATE users SET password = ?, temp_password = NULL WHERE id = ?", (hash_password(new_password), user_id))
        conn.commit()
        send_activity_notification("Change User Password", f"Admin changed password directly for user ID {user_id} (username: '{target_user['username']}').")
        conn.close()
        flash(f"Password for {target_user['username']} updated successfully!")
    else:
        # Teacher requesting password change for a student
        if target_user['role'] != 'student':
            conn.close()
            flash('Access denied: Teachers can only request password changes for students.')
            return redirect(request.referrer or url_for('student_list'))
            
        existing = conn.execute("SELECT id FROM applications WHERE user_id = ? AND type = 'student_password_change' AND status = 'Pending'", (user_id,)).fetchone()
        if existing:
            conn.close()
            flash('A password change request is already pending for this student.')
            return redirect(request.referrer or url_for('student_list'))
            
        app_data = json.dumps({'new_password': new_password})
        conn.execute('''
            INSERT INTO applications (user_id, type, data, status, branch)
            VALUES (?, 'student_password_change', ?, 'Pending', ?)
        ''', (user_id, app_data, target_user['branch'] or 'bhogram'))
        conn.commit()
        send_activity_notification("Password Change Request", f"Teacher requested password change for user ID {user_id} (username: '{target_user['username']}'). Request is pending admin approval.")
        conn.close()
        flash('Password change request submitted successfully! Awaiting Admin approval.')
        
    return redirect(request.referrer or url_for('student_list'))

@app.route('/admin/media-action/<int:media_id>/<action>', methods=['POST'])
@app.route('/admin/gallery-action/<int:media_id>/<action>', methods=['POST'])
def media_action(media_id, action):
    if 'user' in session and session['role'] == 'admin':
        status = 'Approved' if action == 'approve' else 'Rejected'
        conn = get_db_connection()
        c = conn.cursor()
        media = c.execute("SELECT * FROM pending_media WHERE id = ?", (media_id,)).fetchone()
        
        if media:
            branch = media['branch']
            category = media['category']
            filename = media['filename']
            
            import shutil
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', filename)
            
            if status == 'Approved':
                drive_file_id = None
                if os.path.exists(temp_path):
                    try:
                        import mimetypes
                        mime_type, _ = mimetypes.guess_type(temp_path)
                        if not mime_type:
                            mime_type = "application/octet-stream"
                        drive_file_id = upload_file_to_drive_and_map(temp_path, filename, mime_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_GALLERY'), conn=conn)
                    except Exception as e:
                        print(f"Error uploading approved file to Google Drive: {e}")
                
                if drive_file_id:
                    c.execute("UPDATE pending_media SET status = 'Approved', drive_file_id = ? WHERE id = ?", (drive_file_id, media_id))
                    flash('Media approved and uploaded directly to Google Drive!')
                else:
                    dest_folder = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
                    dest_path = os.path.join(dest_folder, filename)
                    if os.path.exists(temp_path):
                        try:
                            os.makedirs(dest_folder, exist_ok=True)
                            shutil.move(temp_path, dest_path)
                        except Exception as e:
                            print(f"Error moving approved file locally: {e}")
                    c.execute("UPDATE pending_media SET status = 'Approved' WHERE id = ?", (media_id,))
                    flash('Media approved and stored locally.')
            else:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e:
                        print(f"Error removing rejected file: {e}")
                c.execute("UPDATE pending_media SET status = 'Rejected' WHERE id = ?", (media_id,))
            
            conn.commit()
            send_activity_notification("Media Action", f"Media '{filename}' for branch '{branch}', category '{category}' was {status} by admin.")
            flash(f'Media {status}!')
        else:
            flash('Media record not found.')
        conn.close()
    else:
        flash('Unauthorized')
    return redirect(url_for('dashboard'))

@app.route('/admin/delete-gallery-item', methods=['POST'])
def delete_gallery_item():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json() or {}
    branch = data.get('branch')
    category = data.get('category')
    filename = data.get('filename')

    if not branch or not category or not filename:
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    # Prevent directory traversal
    filename = secure_filename(filename)
    if not filename or branch not in BRANCHES or category not in CATEGORIES:
        return jsonify({'success': False, 'message': 'Invalid parameters'}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category, filename)
    
    deleted_from_disk = False
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            deleted_from_disk = True
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to delete file from disk: {str(e)}'}), 500
    
    deleted_from_drive = False
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Gather all unique drive file IDs associated with this filename
        drive_file_ids = set()
        
        row = c.execute("SELECT drive_file_id FROM pending_media WHERE filename = ?", (filename,)).fetchone()
        if row and row['drive_file_id']:
            drive_file_ids.add(row['drive_file_id'])
            
        row2 = c.execute("SELECT drive_file_id FROM drive_mappings WHERE filename = ?", (filename,)).fetchone()
        if row2 and row2['drive_file_id']:
            drive_file_ids.add(row2['drive_file_id'])
            
        # Clean up database records first to prevent concurrent double-deletion and release the DB lock
        c.execute("DELETE FROM drive_mappings WHERE filename = ?", (filename,))
        c.execute("DELETE FROM pending_media WHERE filename = ?", (filename,))
        conn.commit()
        conn.close()
        
        # Delete each unique file from Google Drive once
        for drive_file_id in drive_file_ids:
            if delete_from_google_drive(drive_file_id):
                deleted_from_drive = True
    except Exception as e:
        print(f"Error deleting media record/mapping: {e}")

    send_activity_notification("Delete Gallery Item", f"Gallery item '{filename}' for branch '{branch}', category '{category}' was deleted by admin.")
    return jsonify({'success': True, 'message': 'Gallery item deleted successfully', 'deleted_from_disk': deleted_from_disk})

@app.route('/admin/run-sidebar-update')
@login_required
@roles_required('admin')
def run_sidebar_update():
    import io
    import sys
    from contextlib import redirect_stdout
    
    f = io.StringIO()
    with redirect_stdout(f):
        try:
            import importlib
            import update_sidebars_mc
            importlib.reload(update_sidebars_mc)
            update_sidebars_mc.run_update()
        except Exception as e:
            print(f"Error: {e}")
            
    return f.getvalue()


@app.route('/admin/managing-committee')
@login_required
@roles_required('admin')
def admin_managing_committee():
    conn = get_db_connection()
    committee = conn.execute("SELECT * FROM managing_committee ORDER BY order_num ASC, id ASC").fetchall()
    conn.close()
    return render_template('admin/managing_committee.html', committee=committee)

@app.route('/admin/managing-committee/add', methods=['POST'])
@login_required
@roles_required('admin')
def add_managing_committee():
    name = request.form.get('name', '').strip()
    designation = request.form.get('designation', '').strip()
    order_num = request.form.get('order_num', '0').strip()
    try:
        order_num = int(order_num)
    except ValueError:
        order_num = 0
    
    if name and designation:
        global _committee_cache
        _committee_cache = None  # Invalidate cache
        conn = get_db_connection()
        conn.execute("INSERT INTO managing_committee (name, designation, order_num) VALUES (?, ?, ?)",
                     (name, designation, order_num))
        conn.commit()
        conn.close()
        flash('Member added successfully.')
    else:
        flash('Name and designation are required.')
    return redirect(url_for('admin_managing_committee'))

@app.route('/admin/managing-committee/edit/<int:member_id>', methods=['POST'])
@login_required
@roles_required('admin')
def edit_managing_committee(member_id):
    name = request.form.get('name', '').strip()
    designation = request.form.get('designation', '').strip()
    order_num = request.form.get('order_num', '0').strip()
    try:
        order_num = int(order_num)
    except ValueError:
        order_num = 0
        
    if name and designation:
        global _committee_cache
        _committee_cache = None  # Invalidate cache
        conn = get_db_connection()
        conn.execute("UPDATE managing_committee SET name = ?, designation = ?, order_num = ? WHERE id = ?",
                     (name, designation, order_num, member_id))
        conn.commit()
        conn.close()
        flash('Member updated successfully.')
    else:
        flash('Name and designation are required.')
    return redirect(url_for('admin_managing_committee'))

@app.route('/admin/managing-committee/delete/<int:member_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_managing_committee(member_id):
    global _committee_cache
    _committee_cache = None  # Invalidate cache
    conn = get_db_connection()
    conn.execute("DELETE FROM managing_committee WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()
    flash('Member deleted successfully.')
    return redirect(url_for('admin_managing_committee'))


@app.route('/admin/reviews')
@login_required
@roles_required('admin')
def admin_reviews():
    conn = get_db_connection()
    reviews = conn.execute("SELECT * FROM visitor_reviews ORDER BY sort_order ASC, id DESC").fetchall()
    conn.close()
    return render_template('admin/reviews.html', reviews=reviews)

@app.route('/admin/reviews/add', methods=['POST'])
@login_required
@roles_required('admin')
def add_review():
    visitor_name = request.form.get('visitor_name', '').strip()
    visitor_email = request.form.get('visitor_email', '').strip()
    rating = request.form.get('rating', '5')
    review_text = request.form.get('review_text', '').strip()
    sort_order = request.form.get('sort_order', '0').strip()
    try:
        rating = int(rating)
    except ValueError:
        rating = 5
    try:
        sort_order = int(sort_order)
    except ValueError:
        sort_order = 0
    
    if visitor_name and review_text:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO visitor_reviews (visitor_name, visitor_email, rating, review_text, is_approved, sort_order)
            VALUES (?, ?, ?, ?, 1, ?)
        ''', (visitor_name, visitor_email, rating, review_text, sort_order))
        conn.commit()
        conn.close()
        flash('Review added successfully.')
    else:
        flash('Visitor name and feedback text are required.')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/reviews/edit/<int:review_id>', methods=['POST'])
@login_required
@roles_required('admin')
def edit_review(review_id):
    visitor_name = request.form.get('visitor_name', '').strip()
    visitor_email = request.form.get('visitor_email', '').strip()
    rating = request.form.get('rating', '5')
    review_text = request.form.get('review_text', '').strip()
    sort_order = request.form.get('sort_order', '0').strip()
    try:
        rating = int(rating)
    except ValueError:
        rating = 5
    try:
        sort_order = int(sort_order)
    except ValueError:
        sort_order = 0
        
    if visitor_name and review_text:
        conn = get_db_connection()
        conn.execute('''
            UPDATE visitor_reviews 
            SET visitor_name = ?, visitor_email = ?, rating = ?, review_text = ?, sort_order = ?
            WHERE id = ?
        ''', (visitor_name, visitor_email, rating, review_text, sort_order, review_id))
        conn.commit()
        conn.close()
        flash('Review updated successfully.')
    else:
        flash('Visitor name and feedback text are required.')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/reviews/toggle/<int:review_id>', methods=['POST'])
@login_required
@roles_required('admin')
def toggle_review(review_id):
    conn = get_db_connection()
    review = conn.execute("SELECT is_approved FROM visitor_reviews WHERE id = ?", (review_id,)).fetchone()
    if review:
        new_status = 0 if review['is_approved'] == 1 else 1
        conn.execute("UPDATE visitor_reviews SET is_approved = ? WHERE id = ?", (new_status, review_id))
        conn.commit()
        flash('Review visibility status updated.')
    else:
        flash('Review not found.')
    conn.close()
    return redirect(url_for('admin_reviews'))

@app.route('/admin/reviews/delete/<int:review_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_review(review_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM visitor_reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash('Review deleted successfully.')
    return redirect(url_for('admin_reviews'))


@app.route('/admin/student-list')
def student_list():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        if session.get('branch'):
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.*
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.branch = ?
                ORDER BY si.class, si.roll_number
            ''', (session['branch'],)).fetchall()
        else:
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.*
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student'
                ORDER BY si.class, si.roll_number
            ''').fetchall()
        teachers = conn.execute('''
            SELECT u.id, u.username, u.email, u.temp_password, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date, ti.address,
                   ti.aadhaar_number, ti.assigned_classes, ti.bank_details
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()

        complaints_rows = conn.execute('''
            SELECT c.*, COALESCE(ti.full_name, u.username) as teacher_name
            FROM complaints c
            JOIN users u ON c.teacher_id = u.id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
        ''').fetchall()
        complaints_by_student = {}
        for cr in complaints_rows:
            sid = cr['student_id']
            if sid not in complaints_by_student:
                complaints_by_student[sid] = []
            complaints_by_student[sid].append({
                'id': cr['id'],
                'teacher_name': cr['teacher_name'],
                'complaint_text': cr['complaint_text'],
                'created_at': cr['created_at']
            })
        
        teacher_classes = set()
        if session['role'] == 'teacher':
            allowed = get_teacher_allowed_subjects(conn, session['username'])
            teacher_classes = {normalize_class_name(x['class']) for x in allowed if x.get('class')}
        
        # Convert sqlite3.Row to dict to make it mutable/sortable, resolve defaults, and attach complaints
        students_resolved = resolve_student_default_fees(students, conn)
        students_list = []
        for sd in students_resolved:
            sd['complaints'] = complaints_by_student.get(sd['id'], [])
            students_list.append(sd)
        
        if session['role'] == 'teacher':
            students_list = [s for s in students_list if normalize_class_name(s.get('class')) in teacher_classes]
        
        def get_student_sort_key(student):
            cls_idx = get_class_sort_key(student['class'])
            roll = student['roll_number']
            if not roll:
                roll_idx = 999999
            else:
                try:
                    import re
                    match = re.search(r'\d+', str(roll))
                    roll_idx = int(match.group()) if match else 999999
                except Exception:
                    roll_idx = 999999
            return (cls_idx, roll_idx)
            
        students_list.sort(key=get_student_sort_key)
        students = students_list

        students_by_class = {}
        class_display_map = {
            'nursery': 'Nursery',
            'nuesery': 'Nursery',
            'u/n': 'Upper Nursery', 'un': 'Upper Nursery', 'u-n': 'Upper Nursery', 'kg': 'Upper Nursery', 'upper nursery': 'Upper Nursery',
            'one': 'I', 'i': 'I', '1': 'I',
            'two': 'II', 'ii': 'II', '2': 'II',
            'three': 'III', 'iii': 'III', '3': 'III',
            'four': 'IV', 'iv': 'IV', '4': 'IV',
            'five': 'V', 'v': 'V', '5': 'V',
            'six': 'VI', 'vi': 'VI', '6': 'VI', 'siz': 'VI'
        }
        for student in students:
            raw_cls = student['class'] or 'Unassigned'
            cls = class_display_map.get(raw_cls.strip().lower(), raw_cls)
            if cls not in students_by_class:
                students_by_class[cls] = []
            students_by_class[cls].append(student)
            
        conn.close()
        return render_template('admin/student_list.html', students=students, students_by_class=students_by_class, teachers=teachers, role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/print-students')
def print_students():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        class_name = request.args.get('class', 'All')
        conn = get_db_connection()
        if session.get('branch'):
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.full_name, si.branch, si.class, si.roll_number, si.unique_code,
                       si.guardian_name, si.dob, si.section, si.blood_group, si.village, si.post_office, si.police_station, 
                       si.district, si.phone_number, si.aadhaar_number, si.mothers_name, si.date_of_admission, si.monthly_fee,
                       si.allow_marksheet, si.allow_admit, si.bank_details, si.sl_no, si.session, si.mode_of_admission,
                       si.father_qualification, si.father_occupation, si.father_monthly_income, si.mother_qualification,
                       si.mother_occupation, si.mother_monthly_income, si.nationality, si.religion, si.gender, si.caste,
                       si.whatsapp_no, si.previous_class, si.prev_marks_percentage, si.identification_mark,
                       si.attached_documents, si.coaching_opted, si.car_opted
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.branch = ?
            ''', (session['branch'],)).fetchall()
        else:
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.full_name, si.branch, si.class, si.roll_number, si.unique_code,
                       si.guardian_name, si.dob, si.section, si.blood_group, si.village, si.post_office, si.police_station, 
                       si.district, si.phone_number, si.aadhaar_number, si.mothers_name, si.date_of_admission, si.monthly_fee,
                       si.allow_marksheet, si.allow_admit, si.bank_details, si.sl_no, si.session, si.mode_of_admission,
                       si.father_qualification, si.father_occupation, si.father_monthly_income, si.mother_qualification,
                       si.mother_occupation, si.mother_monthly_income, si.nationality, si.religion, si.gender, si.caste,
                       si.whatsapp_no, si.previous_class, si.prev_marks_percentage, si.identification_mark,
                       si.attached_documents, si.coaching_opted, si.car_opted
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student'
            ''').fetchall()
            
        teacher_classes = set()
        if session['role'] == 'teacher':
            allowed = get_teacher_allowed_subjects(conn, session['username'])
            teacher_classes = {normalize_class_name(x['class']) for x in allowed if x.get('class')}
            
        conn.close()

        students_list = [dict(s) for s in students]
        if session['role'] == 'teacher':
            students_list = [s for s in students_list if normalize_class_name(s.get('class')) in teacher_classes]

        class_display_map = {
            'nursery': 'Nursery', 'nuesery': 'Nursery',
            'u/n': 'Upper Nursery', 'un': 'Upper Nursery', 'u-n': 'Upper Nursery', 'kg': 'Upper Nursery', 'upper nursery': 'Upper Nursery',
            'one': 'I', 'i': 'I', '1': 'I',
            'two': 'II', 'ii': 'II', '2': 'II',
            'three': 'III', 'iii': 'III', '3': 'III',
            'four': 'IV', 'iv': 'IV', '4': 'IV',
            'five': 'V', 'v': 'V', '5': 'V',
            'six': 'VI', 'vi': 'VI', '6': 'VI', 'siz': 'VI'
        }
        
        filtered_students = []
        for s in students_list:
            raw_cls = s.get('class') or 'Unassigned'
            norm_cls = class_display_map.get(raw_cls.strip().lower(), raw_cls)
            if class_name == 'All' or norm_cls == class_name:
                s['class'] = norm_cls
                filtered_students.append(s)
                
        def get_student_sort_key(student):
            cls_idx = get_class_sort_key(student['class'])
            roll = student['roll_number']
            if not roll: roll_idx = 999999
            else:
                try:
                    import re
                    match = re.search(r'\d+', str(roll))
                    roll_idx = int(match.group()) if match else 999999
                except Exception:
                    roll_idx = 999999
            return (cls_idx, roll_idx)
            
        filtered_students.sort(key=get_student_sort_key)
        
        return render_template('admin/print_students.html', students=filtered_students, class_name=class_name)
    return redirect(url_for('home'))

@app.route('/admin/print-teachers')
def print_teachers():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        teachers = conn.execute('''
            SELECT u.id, u.username, u.email, u.temp_password, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date, ti.address,
                   ti.aadhaar_number, ti.assigned_classes, ti.bank_details
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        conn.close()
        return render_template('admin/print_teachers.html', teachers=teachers)
    return redirect(url_for('home'))

@app.route('/admin/update-student-permission', methods=['POST'])
def update_student_permission():
    if 'user' in session and session['role'] == 'admin':
        try:
            data = request.get_json()
            student_id = data.get('student_id')
            perm_type = data.get('type')  # 'marksheet' or 'admit'
            value = int(data.get('value', 0))  # 1 or 0
            
            if not student_id or perm_type not in ['marksheet', 'admit']:
                return jsonify({'success': False, 'error': 'Invalid parameters'}), 400
                
            column = 'allow_marksheet' if perm_type == 'marksheet' else 'allow_admit'
            
            conn = get_db_connection()
            conn.execute(f"UPDATE student_info SET {column} = ? WHERE user_id = ?", (value, student_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'Unauthorized'}), 403

@app.route('/admin/add-student-manual', methods=['GET', 'POST'])
def add_student_manual():
    if 'user' in session and session['role'] == 'admin':
        if request.method == 'POST':
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']

            is_strong, error_msg = check_password_strength(password)
            if not is_strong:
                flash(error_msg)
                branch_filter = session.get('branch') or 'bhogram'
                conn = get_db_connection()
                classes = [dict(row) for row in conn.execute("SELECT * FROM classes WHERE LOWER(branch) = LOWER(?)", (branch_filter,)).fetchall()]
                conn.close()
                return render_template('admin/add_student.html', classes=classes, branch_filter=branch_filter)

            role = 'student'
            security_key = 'admin-created'

            conn = get_db_connection()
            try:
                # Insert into users
                conn.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                          (username, email, hash_password(password), role, security_key))
                user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Get bank details inputs and serialize them
                bank_name = request.form.get('bank_name', '').strip()
                branch_name = request.form.get('branch_name', '').strip()
                account_no = request.form.get('account_no', '').strip()
                ifsc_code = request.form.get('ifsc_code', '').strip()
                bank_details = None
                if bank_name or branch_name or account_no or ifsc_code:
                    bank_details = json.dumps({
                        'bank_name': bank_name,
                        'branch_name': branch_name,
                        'account_no': account_no,
                        'ifsc_code': ifsc_code
                    })

                info = {
                    'branch': request.form.get('branch'),
                    'class': normalize_class_name(request.form.get('class')),
                    'roll_number': request.form.get('roll_number'),
                    'full_name': request.form.get('full_name'),
                    'guardian_name': request.form.get('guardian_name'),
                    'dob': request.form.get('dob'),
                    'section': request.form.get('section'),
                    'blood_group': request.form.get('blood_group'),
                    'village': request.form.get('village'),
                    'post_office': request.form.get('post_office'),
                    'police_station': request.form.get('police_station'),
                    'district': request.form.get('district'),
                    'phone_number': request.form.get('phone_number'),
                    'aadhaar_number': request.form.get('aadhaar_number'),
                    'mothers_name': request.form.get('mothers_name'),
                    'date_of_admission': request.form.get('date_of_admission'),
                    'monthly_fee': 0.0,
                    'financial_aid_monthly': float(request.form.get('financial_aid_monthly') or 0.0),
                    'financial_aid_readmission': float(request.form.get('financial_aid_readmission') or 0.0),
                    'prev_dues': float(request.form.get('prev_dues') or 0),
                    'bank_details': bank_details,
                    'session': request.form.get('session'),
                    'mode_of_admission': 'Day Hostel' if request.form.get('take_day_hostel') else ('School with Coaching' if request.form.get('take_coaching') else 'School'),
                    'father_qualification': request.form.get('father_qualification'),
                    'father_occupation': request.form.get('father_occupation'),
                    'father_monthly_income': request.form.get('father_monthly_income'),
                    'mother_qualification': request.form.get('mother_qualification'),
                    'mother_occupation': request.form.get('mother_occupation'),
                    'mother_monthly_income': request.form.get('mother_monthly_income'),
                    'nationality': request.form.get('nationality', 'Indian'),
                    'religion': request.form.get('religion'),
                    'gender': request.form.get('gender'),
                    'caste': request.form.get('caste'),
                    'whatsapp_no': request.form.get('whatsapp_no'),
                    'previous_class': request.form.get('previous_class'),
                    'prev_marks_percentage': request.form.get('prev_marks_percentage'),
                    'identification_mark': request.form.get('identification_mark'),
                    'attached_documents': ', '.join(request.form.getlist('attached_documents')),
                    'coaching_opted': 1 if request.form.get('take_coaching') else 0,
                    'car_opted': 1 if request.form.get('take_car') else 0,
                    'take_school': 1 if request.form.get('take_school') else 0,
                    'take_coaching': 1 if request.form.get('take_coaching') else 0,
                    'take_day_hostel': 1 if request.form.get('take_day_hostel') else 0,
                    'take_car': 1 if request.form.get('take_car') else 0,
                    'admission_fee': float(request.form.get('admission_fee') or 0),
                    'readmission_fee': float(request.form.get('readmission_fee') or 0),
                    'sl_no': request.form.get('sl_no', '').strip(),
                    'enrollment_type': get_enrollment_type_from_checkboxes(
                        1 if request.form.get('take_school') else 0,
                        1 if request.form.get('take_coaching') else 0,
                        1 if request.form.get('take_day_hostel') else 0
                    ),
                    'hostel_room': request.form.get('hostel_room', '').strip() or None,
                    'hostel_wing': request.form.get('hostel_wing', '').strip() or None,
                    'coaching_batch': request.form.get('coaching_batch', '').strip() or None,
                    'coaching_subject': request.form.get('coaching_subject', '').strip() or None,
                    'tuition_fee': float(request.form.get('tuition_fee') or 0.0),
                    'transport_fee': float(request.form.get('transport_fee') or 0.0),
                    'lab_library_fee': float(request.form.get('lab_library_fee') or 0.0),
                    'academic_discount': float(request.form.get('academic_discount') or 0.0),
                    'room_rent': float(request.form.get('room_rent') or 0.0),
                    'mess_food_charges': float(request.form.get('mess_food_charges') or 0.0),
                    'utility_cost': float(request.form.get('utility_cost') or 0.0),
                    'security_deposit': float(request.form.get('security_deposit') or 0.0),
                    'coaching_combo_fee': float(request.form.get('coaching_combo_fee') or 0.0),
                    'study_material_charges': float(request.form.get('study_material_charges') or 0.0),
                    'exam_test_series_fee': float(request.form.get('exam_test_series_fee') or 0.0),
                    'combo_discount': float(request.form.get('combo_discount') or 0.0),
                    'school_tax_rate': float(request.form.get('school_tax_rate') or 0.0),
                    'hostel_tax_rate': float(request.form.get('hostel_tax_rate') or 0.05),
                    'coaching_tax_rate': float(request.form.get('coaching_tax_rate') or 0.0)
                }

                bd = calculate_student_fees_breakdown({
                    'class': info['class'],
                    'branch': info['branch'],
                    'enrollment_type': info['enrollment_type'],
                    'take_car': info['take_car'],
                    'tuition_fee': info['tuition_fee'],
                    'transport_fee': info['transport_fee'],
                    'lab_library_fee': info['lab_library_fee'],
                    'academic_discount': info['academic_discount'],
                    'room_rent': info['room_rent'],
                    'mess_food_charges': info['mess_food_charges'],
                    'utility_cost': info['utility_cost'],
                    'security_deposit': info['security_deposit'],
                    'coaching_combo_fee': info['coaching_combo_fee'],
                    'study_material_charges': info['study_material_charges'],
                    'exam_test_series_fee': info['exam_test_series_fee'],
                    'combo_discount': info['combo_discount'],
                    'school_tax_rate': info['school_tax_rate'],
                    'hostel_tax_rate': info['hostel_tax_rate'],
                    'coaching_tax_rate': info['coaching_tax_rate']
                }, conn)
                info['monthly_fee'] = bd['total_fee']

                unique_code = generate_unique_student_code(conn)
                
                conn.execute('''
                    INSERT INTO student_info (
                        user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, 
                        village, post_office, police_station, district, phone_number, unique_code, aadhaar_number, 
                        mothers_name, date_of_admission, monthly_fee, prev_dues, bank_details,
                        session, mode_of_admission, father_qualification, father_occupation, father_monthly_income,
                        mother_qualification, mother_occupation, mother_monthly_income, nationality, religion,
                        gender, caste, whatsapp_no, previous_class, prev_marks_percentage, identification_mark,
                        attached_documents, coaching_opted, car_opted, sl_no,
                        take_school, take_coaching, take_day_hostel, take_car, admission_fee, readmission_fee,
                        enrollment_type, hostel_room, hostel_wing, coaching_batch, coaching_subject,
                        tuition_fee, transport_fee, lab_library_fee, academic_discount,
                        room_rent, mess_food_charges, utility_cost, security_deposit,
                        coaching_combo_fee, study_material_charges, exam_test_series_fee, combo_discount,
                        school_tax_rate, hostel_tax_rate, coaching_tax_rate, financial_aid_monthly, financial_aid_readmission
                    )
                    VALUES (
                        :user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, 
                        :village, :post_office, :police_station, :district, :phone_number, :unique_code, :aadhaar_number, 
                        :mothers_name, :date_of_admission, :monthly_fee, :prev_dues, :bank_details,
                        :session, :mode_of_admission, :father_qualification, :father_occupation, :father_monthly_income,
                        :mother_qualification, :mother_occupation, :mother_monthly_income, :nationality, :religion,
                        :gender, :caste, :whatsapp_no, :previous_class, :prev_marks_percentage, :identification_mark,
                        :attached_documents, :coaching_opted, :car_opted, :sl_no,
                        :take_school, :take_coaching, :take_day_hostel, :take_car, :admission_fee, :readmission_fee,
                        :enrollment_type, :hostel_room, :hostel_wing, :coaching_batch, :coaching_subject,
                        :tuition_fee, :transport_fee, :lab_library_fee, :academic_discount,
                        :room_rent, :mess_food_charges, :utility_cost, :security_deposit,
                        :coaching_combo_fee, :study_material_charges, :exam_test_series_fee, :combo_discount,
                        :school_tax_rate, :hostel_tax_rate, :coaching_tax_rate, :financial_aid_monthly, :financial_aid_readmission
                    )
                ''', {**info, 'user_id': user_id, 'unique_code': unique_code})
                
                try:
                    bill_admission_fee(conn, user_id, info['class'], info['branch'], info['take_coaching'], info['take_day_hostel'], info['admission_fee'])
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to auto-bill admission fee: {e}")
                
                try:
                    sync_student_ledger_and_dues(conn, user_id)
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to sync student dues: {e}")
                
                try:
                    sync_classes(conn)
                except Exception as e:
                    print(f" [DB MIGRATE ERROR] sync_classes failed in add_student_manual: {e}")
                conn.commit()
                flash('Student added manually successfully!')
                return redirect(url_for('student_list'))
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                    flash(f'Error adding student: {str(e)}')
                else:
                    flash('Username already exists!')
            except Exception as e:
                flash(f'Error adding student: {str(e)}')
            finally:
                conn.close()

        branch_filter = session.get('branch') or 'bhogram'
        conn = get_db_connection()
        classes = [dict(row) for row in conn.execute("SELECT * FROM classes WHERE LOWER(branch) = LOWER(?)", (branch_filter,)).fetchall()]
        conn.close()
        return render_template('admin/add_student.html', classes=classes, branch_filter=branch_filter)
    return redirect(url_for('home'))

@app.route('/admin/edit-student/<int:user_id>', methods=['GET', 'POST'])
def edit_student(user_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        
        if request.method == 'POST':
            # Update user info
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form.get('password', '').strip()
            
            try:
                if password:
                    conn.execute("UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?", 
                                 (username, email, hash_password(password), user_id))
                else:
                    conn.execute("UPDATE users SET username = ?, email = ? WHERE id = ?", 
                                 (username, email, user_id))
                
                # Get bank details inputs and serialize them
                bank_name = request.form.get('bank_name', '').strip()
                branch_name = request.form.get('branch_name', '').strip()
                account_no = request.form.get('account_no', '').strip()
                ifsc_code = request.form.get('ifsc_code', '').strip()
                bank_details = None
                if bank_name or branch_name or account_no or ifsc_code:
                    bank_details = json.dumps({
                        'bank_name': bank_name,
                        'branch_name': branch_name,
                        'account_no': account_no,
                        'ifsc_code': ifsc_code
                    })

                old_student_data = conn.execute("SELECT enrollment_type, take_school, take_coaching, take_day_hostel FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                if old_student_data:
                    old_type = get_enrollment_type_from_checkboxes(
                        old_student_data['take_school'],
                        old_student_data['take_coaching'],
                        old_student_data['take_day_hostel']
                    )
                else:
                    old_type = 'Day School Only'

                print("====== EDIT STUDENT FORM DATA ======")
                print(request.form)
                print("====================================")
                # Update student_info
                info = {
                    'branch': request.form.get('branch'),
                    'class': normalize_class_name(request.form.get('class')),
                    'roll_number': request.form.get('roll_number'),
                    'full_name': request.form.get('full_name'),
                    'guardian_name': request.form.get('guardian_name'),
                    'dob': request.form.get('dob'),
                    'section': request.form.get('section'),
                    'blood_group': request.form.get('blood_group'),
                    'village': request.form.get('village'),
                    'post_office': request.form.get('post_office'),
                    'police_station': request.form.get('police_station'),
                    'district': request.form.get('district'),
                    'phone_number': request.form.get('phone_number'),
                    'aadhaar_number': request.form.get('aadhaar_number'),
                    'mothers_name': request.form.get('mothers_name'),
                    'date_of_admission': request.form.get('date_of_admission'),
                    'monthly_fee': 0.0,
                    'financial_aid_monthly': float(request.form.get('financial_aid_monthly') or 0.0),
                    'financial_aid_readmission': float(request.form.get('financial_aid_readmission') or 0.0),
                    'prev_dues': float(request.form.get('prev_dues') or 0),
                    'bank_details': bank_details,
                    'session': request.form.get('session'),
                    'mode_of_admission': 'Day Hostel' if request.form.get('take_day_hostel') else ('School with Coaching' if request.form.get('take_coaching') else 'School'),
                    'father_qualification': request.form.get('father_qualification'),
                    'father_occupation': request.form.get('father_occupation'),
                    'father_monthly_income': request.form.get('father_monthly_income'),
                    'mother_qualification': request.form.get('mother_qualification'),
                    'mother_occupation': request.form.get('mother_occupation'),
                    'mother_monthly_income': request.form.get('mother_monthly_income'),
                    'nationality': request.form.get('nationality', 'Indian'),
                    'religion': request.form.get('religion'),
                    'gender': request.form.get('gender'),
                    'caste': request.form.get('caste'),
                    'whatsapp_no': request.form.get('whatsapp_no'),
                    'previous_class': request.form.get('previous_class'),
                    'prev_marks_percentage': request.form.get('prev_marks_percentage'),
                    'identification_mark': request.form.get('identification_mark'),
                    'attached_documents': ', '.join(request.form.getlist('attached_documents')),
                    'coaching_opted': 1 if (request.form.get('take_coaching') or request.form.get('force_take_coaching') == '1') else 0,
                    'car_opted': 1 if request.form.get('take_car') else 0,
                    'take_school': 1 if request.form.get('take_school') else 0,
                    'take_coaching': 1 if (request.form.get('take_coaching') or request.form.get('force_take_coaching') == '1') else 0,
                    'take_day_hostel': 1 if request.form.get('take_day_hostel') else 0,
                    'take_car': 1 if request.form.get('take_car') else 0,
                    'admission_fee': float(request.form.get('admission_fee') or 0),
                    'readmission_fee': float(request.form.get('readmission_fee') or 0),
                    'sl_no': request.form.get('sl_no', '').strip(),
                    'enrollment_type': get_enrollment_type_from_checkboxes(
                        1 if request.form.get('take_school') else 0,
                        1 if (request.form.get('take_coaching') or request.form.get('force_take_coaching') == '1') else 0,
                        1 if request.form.get('take_day_hostel') else 0
                    ),
                    'hostel_room': request.form.get('hostel_room', '').strip() or None,
                    'hostel_wing': request.form.get('hostel_wing', '').strip() or None,
                    'coaching_batch': request.form.get('coaching_batch', '').strip() or None,
                    'coaching_subject': request.form.get('coaching_subject', '').strip() or None,
                    'tuition_fee': float(request.form.get('tuition_fee') or 0.0),
                    'transport_fee': float(request.form.get('transport_fee') or 0.0),
                    'lab_library_fee': float(request.form.get('lab_library_fee') or 0.0),
                    'academic_discount': float(request.form.get('academic_discount') or 0.0),
                    'room_rent': float(request.form.get('room_rent') or 0.0),
                    'mess_food_charges': float(request.form.get('mess_food_charges') or 0.0),
                    'utility_cost': float(request.form.get('utility_cost') or 0.0),
                    'security_deposit': float(request.form.get('security_deposit') or 0.0),
                    'coaching_combo_fee': float(request.form.get('coaching_combo_fee') or 0.0),
                    'study_material_charges': float(request.form.get('study_material_charges') or 0.0),
                    'exam_test_series_fee': float(request.form.get('exam_test_series_fee') or 0.0),
                    'combo_discount': float(request.form.get('combo_discount') or 0.0),
                    'school_tax_rate': float(request.form.get('school_tax_rate') or 0.0),
                    'hostel_tax_rate': float(request.form.get('hostel_tax_rate') or 0.05),
                    'coaching_tax_rate': float(request.form.get('coaching_tax_rate') or 0.0)
                }

                bd = calculate_student_fees_breakdown({
                    'class': info['class'],
                    'branch': info['branch'],
                    'enrollment_type': info['enrollment_type'],
                    'take_car': info['take_car'],
                    'tuition_fee': info['tuition_fee'],
                    'transport_fee': info['transport_fee'],
                    'lab_library_fee': info['lab_library_fee'],
                    'academic_discount': info['academic_discount'],
                    'room_rent': info['room_rent'],
                    'mess_food_charges': info['mess_food_charges'],
                    'utility_cost': info['utility_cost'],
                    'security_deposit': info['security_deposit'],
                    'coaching_combo_fee': info['coaching_combo_fee'],
                    'study_material_charges': info['study_material_charges'],
                    'exam_test_series_fee': info['exam_test_series_fee'],
                        'combo_discount': info['combo_discount'],
                    'school_tax_rate': info['school_tax_rate'],
                    'hostel_tax_rate': info['hostel_tax_rate'],
                    'coaching_tax_rate': info['coaching_tax_rate']
                }, conn)
                
                # Check if student was previously custom-fee or has custom components
                existing_student_db = conn.execute("SELECT is_custom_fee, monthly_fee, remaining_fee FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                was_custom = existing_student_db and existing_student_db['is_custom_fee'] == 1
                
                has_custom_components = any([
                    info['tuition_fee'] > 0.0,
                    info['transport_fee'] > 0.0,
                    info['lab_library_fee'] > 0.0,
                    info['academic_discount'] > 0.0,
                    info['room_rent'] > 0.0,
                    info['mess_food_charges'] > 0.0,
                    info['utility_cost'] > 0.0,
                    info['security_deposit'] > 0.0,
                    info['coaching_combo_fee'] > 0.0,
                    info['study_material_charges'] > 0.0,
                    info['exam_test_series_fee'] > 0.0,
                    info['combo_discount'] > 0.0
                ])
                
                # Check if the user entered custom values in the main inputs:
                monthly_fee_input = request.form.get('monthly_fee')
                admission_fee_input = request.form.get('admission_fee')
                readmission_fee_input = request.form.get('readmission_fee')

                has_main_overrides = any([
                    monthly_fee_input and float(monthly_fee_input) > 0.0,
                    admission_fee_input and float(admission_fee_input) > 0.0,
                    readmission_fee_input and float(readmission_fee_input) > 0.0
                ])

                is_custom_fee_val = 0

                if is_custom_fee_val == 1:
                    if not has_custom_components:
                        info['monthly_fee'] = float(request.form.get('monthly_fee') or 0.0)
                    else:
                        info['monthly_fee'] = bd['total_fee']
                else:
                    info['monthly_fee'] = bd['total_fee']
                    # Resolve default admission / readmission fees from templates
                    class_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (info['class'].lower(), info['branch'].lower())).fetchone()
                    a_fee = 0.0
                    r_fee = 0.0
                    if class_row:
                        if info['take_day_hostel']:
                            a_fee = class_row['admission_fee_hostel'] if class_row else 0.0
                            r_fee = class_row['readmission_fee_hostel'] if class_row else 0.0
                        elif info['take_coaching']:
                            a_fee = class_row['admission_fee_coaching'] if class_row else 0.0
                            r_fee = class_row['readmission_fee_coaching'] if class_row else 0.0
                        elif info['take_school']:
                            a_fee = class_row['admission_fee'] if class_row else 0.0
                            r_fee = class_row['readmission_fee_school'] if class_row else 0.0
                    info['admission_fee'] = a_fee
                    info['readmission_fee'] = r_fee
                
                row_exists = dict(conn.execute("SELECT * FROM student_info WHERE user_id = ?", (user_id,)).fetchone() or {})
                changed_info = {}
                if row_exists:
                    for k, v in info.items():
                        old_v = row_exists.get(k)
                        if old_v is not None:
                            if isinstance(v, float):
                                try: old_v = float(old_v)
                                except: pass
                            elif isinstance(v, int):
                                try: old_v = int(old_v)
                                except: pass
                            elif isinstance(v, str) and isinstance(old_v, (int, float)):
                                try: v = type(old_v)(v)
                                except: pass
                        
                        if v == '' and old_v is None:
                            continue
                            
                        if old_v != v:
                            changed_info[k] = v

                    if changed_info or is_custom_fee_val != (row_exists.get('is_custom_fee') or 0):
                        set_clause_items = [f"{k} = :{k}" for k in changed_info.keys()]
                        query_params = {**changed_info, 'user_id': user_id}
                        
                        try:
                            import os
                            with open(os.path.join(app.root_path, "debug_log.txt"), "a") as f:
                                f.write("====== UPDATE DIFF DEBUG ======\n")
                                f.write(f"request.form keys: {list(request.form.keys())}\n")
                                f.write(f"take_coaching in request.form: {'take_coaching' in request.form}\n")
                                f.write(f"take_coaching form value: {request.form.get('take_coaching')}\n")
                                f.write(f"info['take_coaching'] = {info.get('take_coaching')}\n")
                        except Exception as file_e:
                            pass
                        
                        if is_custom_fee_val != (row_exists.get('is_custom_fee') or 0):
                            set_clause_items.append('is_custom_fee = :is_custom_fee')
                            query_params['is_custom_fee'] = is_custom_fee_val
                        
                        if set_clause_items:
                            set_clause = ', '.join(set_clause_items)
                            
                            try:
                                with open("debug_log.txt", "a") as f:
                                    f.write(f"changed_info dict: {changed_info}\n")
                                    f.write(f"set_clause: {set_clause}\n")
                            except Exception:
                                pass
                                                          
                            res = conn.execute(f'''
                                UPDATE student_info SET
                                {set_clause}
                                WHERE user_id = :user_id
                            ''', query_params)
                            
                            try:
                                with open("debug_log.txt", "a") as f:
                                    f.write(f"UPDATE rowcount: {res.rowcount}\n")
                                    row = conn.execute("SELECT take_coaching FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                                    f.write(f"IMMEDIATE DB VALUE: {dict(row) if row else None}\n")
                            except Exception as e:
                                pass
                else:
                    cols = ', '.join(list(info.keys()) + ['is_custom_fee'])
                    vals = ', '.join([':' + k for k in info.keys()] + [':is_custom_fee'])
                    conn.execute(f"INSERT INTO student_info (user_id, {cols}) VALUES (:user_id, {vals})", {**info, 'is_custom_fee': is_custom_fee_val, 'user_id': user_id})

                # Adjust dues for enrollment change
                if 'enrollment_type' in changed_info and old_type != info['enrollment_type']:
                    adjust_dues_for_enrollment_change(conn, user_id, old_type, info['enrollment_type'])
                    try:
                        row = conn.execute("SELECT take_coaching FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                        with open("debug_log.txt", "a") as f:
                            f.write(f"AFTER adjust_dues DB VALUE: {dict(row) if row else None}\n")
                    except Exception: pass
                
                # Sync marks table class name and certificates
                if 'class' in changed_info or not row_exists:
                    conn.execute("UPDATE marks SET class_name = ? WHERE student_id = ?", (info['class'], user_id))
                    conn.execute("UPDATE certificates SET class_name = ? WHERE recipient_id = ? AND recipient_type = 'student'", (info['class'], user_id))
                
                fee_fields = ['enrollment_type', 'tuition_fee', 'transport_fee', 'lab_library_fee', 'academic_discount', 'room_rent', 'mess_food_charges', 'utility_cost', 'security_deposit', 'coaching_combo_fee', 'study_material_charges', 'exam_test_series_fee', 'combo_discount', 'school_tax_rate', 'hostel_tax_rate', 'coaching_tax_rate', 'monthly_fee', 'admission_fee', 'readmission_fee', 'financial_aid_monthly', 'financial_aid_readmission']
                if any(f in changed_info for f in fee_fields) or is_custom_fee_val != (row_exists.get('is_custom_fee') or 0) or not row_exists:
                    try:
                        sync_student_ledger_and_dues(conn, user_id)
                        try:
                            row = conn.execute("SELECT take_coaching FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                            with open("debug_log.txt", "a") as f:
                                f.write(f"AFTER sync_ledger DB VALUE: {dict(row) if row else None}\n")
                        except Exception: pass
                    except Exception as e:
                        try:
                            with open("debug_log.txt", "a") as f:
                                import traceback
                                f.write(f"BILLING ERROR: {e}\n{traceback.format_exc()}\n")
                        except: pass
                
                # Ensure photo is synced
                if 'photo_path' in info:
                    pass

                try:
                    with open("debug_log.txt", "a") as f:
                        f.write("BEFORE sync_classes\n")
                    sync_classes(conn)
                    with open("debug_log.txt", "a") as f:
                        f.write("AFTER sync_classes\n")
                    try:
                        row = conn.execute("SELECT take_coaching FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                        with open("debug_log.txt", "a") as f:
                            f.write(f"AFTER sync_classes DB VALUE: {dict(row) if row else None}\n")
                    except Exception: pass
                except Exception as e:
                    with open("debug_log.txt", "a") as f:
                        f.write(f"SYNC_CLASSES ERROR: {e}\n")
                    print(f" [DB MIGRATE ERROR] sync_classes failed in edit_student: {e}")
                
                # Handle Photo Upload
                photo_file = request.files.get('photo')
                if photo_file and photo_file.filename:
                    ext = photo_file.filename.split('.')[-1].lower()
                    if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                        import os
                        upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'student_photos')
                        os.makedirs(upload_folder, exist_ok=True)
                        filename = f"student_{user_id}_{int(datetime.now(timezone.utc).timestamp())}.{ext}"
                        
                        # Delete old photo if exists
                        old_photo = conn.execute("SELECT photo_path FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                        if old_photo and old_photo['photo_path']:
                            try:
                                import threading
                                threading.Thread(target=delete_old_mapped_file, args=(old_photo['photo_path'],), daemon=True).start()
                                os.remove(os.path.join(upload_folder, old_photo['photo_path']))
                            except:
                                pass
                        
                        local_path = os.path.join(upload_folder, filename)
                        photo_file.save(local_path)
                        import threading
                        threading.Thread(target=upload_file_to_drive_and_map, args=(local_path, filename, photo_file.content_type, os.getenv('GOOGLE_DRIVE_FOLDER_STUDENTS'), None), daemon=True).start()
                        conn.execute("UPDATE student_info SET photo_path = ? WHERE user_id = ?", (filename, user_id))
                
                try:
                    with open("debug_log.txt", "a") as f:
                        f.write("BEFORE sync_classes\\n")
                    # sync_classes(conn)
                    with open("debug_log.txt", "a") as f:
                        f.write("AFTER sync_classes\\n")
                except Exception as e:
                    with open("debug_log.txt", "a") as f:
                        f.write(f"SYNC_CLASSES ERROR: {e}\\n")
                    print(f" [DB MIGRATE ERROR] sync_classes failed in edit_student: {e}")
                conn.commit()
                flash('Student updated successfully!')
                return redirect(url_for('student_list'))
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                    flash(f'Error updating student: {str(e)}')
                else:
                    flash('Username already exists or database error!')
            finally:
                conn.close()

        # GET request: fetch existing data
        student = conn.execute('''
            SELECT u.username, u.email, si.* 
            FROM users u
            LEFT JOIN student_info si ON u.id = si.user_id
            WHERE u.id = ? AND u.role = 'student'
        ''', (user_id,)).fetchone()
        
        if not student:
            conn.close()
            flash('Student not found!')
            return redirect(url_for('student_list'))
            
        student_dict_debug = dict(student) if student else {}
        try:
            import os
            with open(os.path.join(app.root_path, "debug_log.txt"), "a") as f:
                f.write("====== GET REQUEST DEBUG ======\n")
                f.write(f"student keys: {list(student_dict_debug.keys())}\n")
                f.write(f"student values: {student_dict_debug}\n")
        except Exception:
            pass
            
        try:
            with open("debug_log.txt", "a") as f:
                f.write("====== SCHEMA AND DIRECT DB DUMP ======\\n")
                triggers = conn.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='student_info'").fetchall()
                f.write(f"Triggers: {[dict(t) for t in triggers]}\\n")
                row = conn.execute("SELECT user_id, take_coaching, coaching_opted FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
                f.write(f"Direct select: {dict(row) if row else None}\\n")
        except Exception as e:
            pass

        branch_filter = session.get('branch') or (student['branch'] if student else None) or 'bhogram'
        classes = [dict(row) for row in conn.execute("SELECT * FROM classes WHERE LOWER(branch) = LOWER(?)", (branch_filter,)).fetchall()]
        
        # Calculate default components breakdown
        default_fees = calculate_student_fees_breakdown({
            'class': student['class'],
            'branch': student['branch'] or 'bhogram',
            'take_school': student['take_school'] if student['take_school'] is not None else 1,
            'take_coaching': student['take_coaching'] or 0,
            'take_day_hostel': student['take_day_hostel'] or 0,
            'take_car': student['take_car'] or 0,
            'is_custom_fee': 0
        }, conn)
        
        # Calculate default admission / readmission rates
        cls_name = student['class']
        branch = student['branch'] or 'bhogram'
        default_admission = 0.0
        default_readmission = 0.0
        if cls_name:
            cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls_name, branch)).fetchone()
            if cls_row:
                if student['take_day_hostel']:
                    default_admission = cls_row['admission_fee_hostel'] if cls_row else 0.0
                    default_readmission = cls_row['readmission_fee_hostel'] if cls_row else 0.0
                elif student['take_coaching']:
                    default_admission = cls_row['admission_fee_coaching'] if cls_row else 0.0
                    default_readmission = cls_row['readmission_fee_coaching'] if cls_row else 0.0
                elif student['take_school'] if student['take_school'] is not None else 1:
                    default_admission = cls_row['admission_fee'] if cls_row else 0.0
                    default_readmission = cls_row['readmission_fee_school'] if cls_row else 0.0

        student_resolved = resolve_student_default_fees([student], conn)[0]
        conn.close()
        
        return render_template('admin/edit_student.html', 
                               student=student_resolved, 
                               user_id=user_id, 
                               classes=classes, 
                               default_fees=default_fees, 
                               default_admission=default_admission, 
                               default_readmission=default_readmission)
    return redirect(url_for('home'))

@app.route('/admin/edit-teacher/<int:user_id>', methods=['GET', 'POST'])
def edit_teacher(user_id):
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('home'))

    conn = get_db_connection()

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip()
        password  = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone_number', '').strip()
        qual      = request.form.get('qualification', '').strip()
        joining   = request.form.get('joining_date', '').strip()
        address   = request.form.get('address', '').strip()
        aadhaar_number = request.form.get('aadhaar_number', '').strip()
        assigned_classes = request.form.get('assigned_classes', '').strip()
        teacher_type = request.form.get('teacher_type', 'Regular Class').strip()
        
        # Parse bank details and serialize
        bank_name = request.form.get('bank_name', '').strip()
        branch_name = request.form.get('branch_name', '').strip()
        account_no = request.form.get('account_no', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        bank_details = None
        if bank_name or branch_name or account_no or ifsc_code:
            bank_details = json.dumps({
                'bank_name': bank_name,
                'branch_name': branch_name,
                'account_no': account_no,
                'ifsc_code': ifsc_code
            })

        if not username:
            flash('Username is required.')
            conn.close()
            return redirect(url_for('edit_teacher', user_id=user_id))

        try:
            if password:
                conn.execute('UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?',
                             (username, email or None, hash_password(password), user_id))
            else:
                conn.execute('UPDATE users SET username = ?, email = ? WHERE id = ?',
                             (username, email or None, user_id))

            # Upsert teacher_info (handles teachers without a prior record)
            conn.execute('''
                INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address, aadhaar_number, assigned_classes, bank_details, teacher_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name      = excluded.full_name,
                    phone_number   = excluded.phone_number,
                    qualification  = excluded.qualification,
                    joining_date   = excluded.joining_date,
                    address        = excluded.address,
                    aadhaar_number = excluded.aadhaar_number,
                    assigned_classes = excluded.assigned_classes,
                    bank_details   = excluded.bank_details,
                    teacher_type   = excluded.teacher_type
            ''', (user_id, full_name or None, phone or None, qual or None, joining or None, address or None, aadhaar_number or None, assigned_classes or None, bank_details or None, teacher_type))

            sync_teacher_subjects_from_string(conn, user_id, assigned_classes)

            # Handle Photo Upload
            photo_file = request.files.get('photo')
            if photo_file and photo_file.filename:
                ext = photo_file.filename.split('.')[-1].lower()
                if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                    import os
                    upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'teacher_photos')
                    os.makedirs(upload_folder, exist_ok=True)
                    filename = f"teacher_{user_id}_{int(datetime.now(timezone.utc).timestamp())}.{ext}"
                    
                    # Delete old photo if exists
                    old_photo = conn.execute("SELECT photo_path FROM teacher_info WHERE user_id = ?", (user_id,)).fetchone()
                    if old_photo and old_photo['photo_path']:
                        try:
                            delete_old_mapped_file(old_photo['photo_path'])
                            os.remove(os.path.join(upload_folder, old_photo['photo_path']))
                        except:
                            pass
                    
                    local_path = os.path.join(upload_folder, filename)
                    photo_file.save(local_path)
                    upload_file_to_drive_and_map(local_path, filename, photo_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_TEACHERS'), conn=conn)
                    conn.execute("UPDATE teacher_info SET photo_path = ? WHERE user_id = ?", (filename, user_id))

            # Handle CV Upload
            cv_file = request.files.get('cv_file')
            if cv_file and cv_file.filename:
                filename = secure_filename(cv_file.filename)
                if filename:
                    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'cvs')
                    os.makedirs(upload_dir, exist_ok=True)
                    timestamp = int(datetime.now(timezone.utc).timestamp())
                    saved_filename = f"cv_{timestamp}_{filename}"
                    local_path = os.path.join(upload_dir, saved_filename)
                    cv_file.save(local_path)
                    upload_file_to_drive_and_map(local_path, saved_filename, cv_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_CV'), conn=conn)
                    
                    # Delete old CV if exists
                    old_cv = conn.execute("SELECT cv_path FROM teacher_info WHERE user_id = ?", (user_id,)).fetchone()
                    if old_cv and old_cv['cv_path']:
                        try:
                            delete_old_mapped_file(old_cv['cv_path'])
                            os.remove(os.path.join(app.root_path, 'static', old_cv['cv_path']))
                        except:
                            pass
                    
                    conn.execute("UPDATE teacher_info SET cv_path = ? WHERE user_id = ?", (f"uploads/cvs/{saved_filename}", user_id))

            conn.commit()
            flash(f'Teacher "{full_name or username}" updated successfully!')
            return redirect(url_for('teacher_list'))
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                flash(f'Error updating teacher: {str(e)}')
            else:
                flash('Username already exists or database error!')
        finally:
            conn.close()
        return redirect(url_for('edit_teacher', user_id=user_id))

    teacher = conn.execute('''
        SELECT u.id, u.username, u.email, ti.full_name, ti.phone_number,
               ti.qualification, ti.joining_date, ti.address, ti.photo_path,
               ti.aadhaar_number, ti.assigned_classes, ti.bank_details, ti.teacher_type, ti.cv_path
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.id = ? AND u.role = 'teacher'
    ''', (user_id,)).fetchone()
    conn.close()

    if not teacher:
        flash('Teacher not found!')
        return redirect(url_for('teacher_list'))

    logo_url = LOGO_URL
    return render_template('admin/edit_teacher.html', teacher=teacher, role=session['role'], logo_url=logo_url)

@app.route('/admin/add-user', methods=['GET', 'POST'])
def add_user():
    if 'user' in session and session['role'] == 'admin':
        if request.method == 'POST':
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']

            is_strong, error_msg = check_password_strength(password)
            if not is_strong:
                flash(error_msg)
                return render_template('admin/add_user.html')

            role = request.form['role']
            security_key = request.form.get('security_key') or 'admin-created'
            branch = session['branch'] if session.get('branch') else request.form.get('branch') or None

            conn = get_db_connection()
            try:
                # Insert into users
                conn.execute("INSERT INTO users (username, email, password, role, security_key, temp_password, branch) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (username, email, hash_password(password), role, security_key, password, branch))
                user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                if role == 'teacher':
                    full_name = request.form.get('full_name', '')
                    phone_number = request.form.get('phone_number', '')
                    qualification = request.form.get('qualification', '')
                    joining_date = request.form.get('joining_date', '')
                    address = request.form.get('address', '')
                    aadhaar_number = request.form.get('aadhaar_number', '').strip()
                    assigned_classes = request.form.get('assigned_classes', '').strip()
                    teacher_type = request.form.get('teacher_type', 'Regular Class').strip()
                    
                    # Parse bank details and serialize
                    bank_name = request.form.get('bank_name', '').strip()
                    branch_name = request.form.get('branch_name', '').strip()
                    account_no = request.form.get('account_no', '').strip()
                    ifsc_code = request.form.get('ifsc_code', '').strip()
                    bank_details = None
                    if bank_name or branch_name or account_no or ifsc_code:
                        bank_details = json.dumps({
                            'bank_name': bank_name,
                            'branch_name': branch_name,
                            'account_no': account_no,
                            'ifsc_code': ifsc_code
                        })

                    conn.execute('''
                        INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address, aadhaar_number, assigned_classes, bank_details, teacher_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (user_id, full_name, phone_number, qualification, joining_date, address, aadhaar_number, assigned_classes, bank_details, teacher_type))
                    sync_teacher_subjects_from_string(conn, user_id, assigned_classes)
                elif role == 'student':
                    unique_code = generate_unique_student_code(conn)
                    
                    # Parse bank details and serialize
                    bank_name = request.form.get('bank_name', '').strip()
                    branch_name = request.form.get('branch_name', '').strip()
                    account_no = request.form.get('account_no', '').strip()
                    ifsc_code = request.form.get('ifsc_code', '').strip()
                    bank_details = None
                    if bank_name or branch_name or account_no or ifsc_code:
                        bank_details = json.dumps({
                            'bank_name': bank_name,
                            'branch_name': branch_name,
                            'account_no': account_no,
                            'ifsc_code': ifsc_code
                        })

                    info = {
                        'branch': branch,
                        'class': normalize_class_name(request.form.get('class')),
                        'roll_number': request.form.get('roll_number'),
                        'full_name': request.form.get('student_full_name'),
                        'guardian_name': request.form.get('guardian_name'),
                        'dob': request.form.get('dob'),
                        'section': request.form.get('section'),
                        'blood_group': request.form.get('blood_group'),
                        'village': request.form.get('village'),
                        'post_office': request.form.get('post_office'),
                        'police_station': request.form.get('police_station'),
                        'district': request.form.get('district'),
                        'phone_number': request.form.get('student_phone'),
                        'aadhaar_number': request.form.get('aadhaar_number'),
                        'mothers_name': request.form.get('mothers_name'),
                        'date_of_admission': request.form.get('date_of_admission'),
                        'monthly_fee': float(request.form.get('monthly_fee') or 0),
                        'unique_code': unique_code,
                        'bank_details': bank_details
                    }
                    conn.execute('''
                        INSERT INTO student_info (user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number, unique_code, aadhaar_number, mothers_name, date_of_admission, monthly_fee, bank_details)
                        VALUES (:user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number, :unique_code, :aadhaar_number, :mothers_name, :date_of_admission, :monthly_fee, :bank_details)
                    ''', {**info, 'user_id': user_id})

                conn.commit()
                flash(f'User ({role}) added successfully!')
                return redirect(url_for('dashboard'))
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                    flash(f'Error adding user: {str(e)}')
                else:
                    flash('Username already exists!')
            except Exception as e:
                flash(f'Error adding user: {str(e)}')
            finally:
                conn.close()

        return render_template('admin/add_user.html')
    return redirect(url_for('home'))

@app.route('/admin/input-result', methods=['GET', 'POST'])
def input_result():
    return redirect(url_for('bulk_marks'))

def calculate_grade(pct):
    try:
        p = float(pct)
        if p >= 90.0: return 'AA'
        if p >= 80.0: return 'A+'
        if p >= 60.0: return 'A'
        if p >= 45.0: return 'B+'
        if p >= 35.0: return 'B'
        if p >= 25.0: return 'C'
        return 'D'
    except:
        return 'D'

def calculate_overall_grade(percentage):
    return calculate_grade(percentage)

@app.route('/admin/marksheet')
def marksheet():
    if 'user' in session:
        conn = get_db_connection()
        role = session['role']
        
        user = conn.execute("SELECT id, role FROM users WHERE username = ?", (session['user'],)).fetchone()
        student_id = user['id'] if user['role'] == 'student' else request.args.get('student_id')
            
        if student_id:
            # Check permissions for Branch Admin
            if user['role'] != 'student' and session.get('branch'):
                student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                if not student or student['branch'] != session['branch']:
                    conn.close()
                    flash('Permission denied: Student does not belong to your campus.')
                    return redirect(url_for('dashboard'))

            # Gating logic for student
            if user['role'] == 'student':
                student_perm = conn.execute("SELECT allow_marksheet FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
                if not student_perm or not student_perm['allow_marksheet']:
                    conn.close()
                    return render_template('admin/marksheet_locked.html', role=role)

            # Fetch student meta early to know their class/branch
            student_meta = conn.execute('''
                SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.roll_number, si.section, si.branch, si.guardian_name, si.session
                FROM users u
                LEFT JOIN student_info si ON u.id = si.user_id
                WHERE u.id = ?
            ''', (student_id,)).fetchone()

            class_name = student_meta['class'] if student_meta else None
            branch_name = (student_meta['branch'] if student_meta else '') or ''

            # Setup subjects and full marks maps early
            subject_fm_1st_map = {}
            subject_fm_2nd_map = {}
            subject_fm_annual_map = {}
            subject_oral_1st_map = {}
            subject_written_1st_map = {}
            subject_oral_2nd_map = {}
            subject_written_2nd_map = {}
            subject_oral_annual_map = {}
            subject_written_annual_map = {}
            subject_ct_annual_map = {}
            db_classes = []
            class_subjects = []
            if class_name:
                db_classes = get_db_class_names(class_name)
                placeholders = ', '.join('?' for _ in db_classes)
                subjects_rows = conn.execute(f"""
                    SELECT subject_name AS name, term_name, full_marks, oral_limit, written_limit, ct_limit
                    FROM class_subjects 
                    WHERE class_name IN ({placeholders})
                """, db_classes).fetchall()
                for r in subjects_rows:
                    if r['name']:
                        sub_name_norm = r['name'].strip().title()
                        term_norm = r['term_name'].strip()
                        if term_norm in ['1st Term', '1st Unit']:
                            term_norm = '1st Unit'
                        elif term_norm in ['2nd Term', '2nd Unit']:
                            term_norm = '2nd Unit'
                        elif term_norm in ['Annual Exam', 'Final Exam', 'Annual']:
                            term_norm = 'Final Exam'
                            
                        if term_norm == '1st Unit':
                            subject_fm_1st_map[sub_name_norm] = r['full_marks']
                            subject_oral_1st_map[sub_name_norm] = r['oral_limit']
                            subject_written_1st_map[sub_name_norm] = r['written_limit']
                        elif term_norm == '2nd Unit':
                            subject_fm_2nd_map[sub_name_norm] = r['full_marks']
                            subject_oral_2nd_map[sub_name_norm] = r['oral_limit']
                            subject_written_2nd_map[sub_name_norm] = r['written_limit']
                        elif term_norm == 'Final Exam':
                            subject_fm_annual_map[sub_name_norm] = r['full_marks']
                            subject_oral_annual_map[sub_name_norm] = r['oral_limit']
                            subject_written_annual_map[sub_name_norm] = r['written_limit']
                            subject_ct_annual_map[sub_name_norm] = r['ct_limit']

            class_subjects = sorted(list(set(list(subject_fm_1st_map.keys()) + list(subject_fm_2nd_map.keys()) + list(subject_fm_annual_map.keys()))))

            marks_rows = conn.execute('''
                SELECT m.obtained_marks AS marks,
                       m.full_marks AS total_marks,
                       m.oral_marks,
                       m.written_marks,
                       m.ct_marks,
                       COALESCE(m.is_absent, 0) AS is_absent,
                       m.subject_name AS subject,
                       m.term_name AS term,
                       m.uploaded_at AS submitted_at,
                       m.student_id,
                       m.class_name,
                       m.uploaded_by,
                       COALESCE(si.full_name, u.username) as student_name, 
                       si.class, 
                       si.roll_number, 
                       si.branch, 
                       si.guardian_name, 
                       si.dob, 
                       si.section 
                FROM marks m 
                JOIN users u ON m.student_id = u.id 
                LEFT JOIN student_info si ON u.id = si.user_id
                WHERE m.student_id = ?
                ORDER BY m.uploaded_at DESC
            ''', (student_id,)).fetchall()
            
            # Standard monthly tests keywords matching fallback
            def is_monthly_test(term_name):
                if not term_name:
                    return False
                term_clean = term_name.strip()
                if term_clean in ['1st Unit', '2nd Unit', 'Final Exam', '1st Term', '2nd Term', 'Annual Exam', 'Annual']:
                    return False
                return True
                
            class_test_names = []
            for r in marks_rows:
                t = r['term']
                if t and is_monthly_test(t) and t.strip() not in class_test_names:
                    class_test_names.append(t.strip())
            class_test_names.sort(key=get_month_sort_key)
            
            monthly_marks = []
            term_marks = []
            
            def fmt_limit(lim):
                if lim is None: return '-'
                if lim == int(lim): return str(int(lim))
                return f"{lim:.1f}"

            for m in marks_rows:
                term_name = m['term'].strip()
                sub_name_lower = m['subject'].strip().lower()
                is_ct_special = sub_name_lower in ['physical education', 'work education', 'hand writing', 'behaviour', 'attendance']
                
                if is_monthly_test(term_name):
                    if not is_ct_special:
                        monthly_marks.append(m)
                else:
                    if term_name in ['1st Term', '1st Unit']:
                        term_name = '1st Unit'
                    elif term_name in ['2nd Term', '2nd Unit']:
                        term_name = '2nd Unit'
                    elif term_name in ['Annual Exam', 'Final Exam', 'Annual']:
                        term_name = 'Final Exam'
                    
                    if not (term_name in ['1st Unit', '2nd Unit'] and is_ct_special):
                        m_dict = dict(m)
                        m_dict['term'] = term_name
                        
                        # Attach dynamic component limits
                        sub_name = m_dict['subject'].strip().title()
                        
                        if term_name in ['1st Unit', '1st Term']:
                            tot_fm = subject_fm_1st_map.get(sub_name)
                            if tot_fm is None:
                                tot_fm = m_dict['total_marks'] if m_dict['total_marks'] is not None else 50.0
                            m_dict['oral_limit'] = fmt_limit(subject_oral_1st_map.get(sub_name))
                            m_dict['written_limit'] = fmt_limit(subject_written_1st_map.get(sub_name))
                            m_dict['ct_limit'] = '-'
                        elif term_name in ['2nd Unit', '2nd Term']:
                            tot_fm = subject_fm_2nd_map.get(sub_name)
                            if tot_fm is None:
                                tot_fm = m_dict['total_marks'] if m_dict['total_marks'] is not None else 50.0
                            m_dict['oral_limit'] = fmt_limit(subject_oral_2nd_map.get(sub_name))
                            m_dict['written_limit'] = fmt_limit(subject_written_2nd_map.get(sub_name))
                            m_dict['ct_limit'] = '-'
                        elif term_name in ['Final Exam', 'Annual Exam']:
                            tot_fm = subject_fm_annual_map.get(sub_name)
                            if tot_fm is None:
                                tot_fm = m_dict['total_marks'] if m_dict['total_marks'] is not None else 100.0
                            m_dict['oral_limit'] = fmt_limit(subject_oral_annual_map.get(sub_name))
                            m_dict['written_limit'] = fmt_limit(subject_written_annual_map.get(sub_name))
                            m_dict['ct_limit'] = fmt_limit(subject_ct_annual_map.get(sub_name))
                        else:
                            tot_fm = float(m_dict['total_marks'] if m_dict['total_marks'] is not None else 100.0)
                            m_dict['oral_limit'] = '-'
                            m_dict['written_limit'] = '-'
                            m_dict['ct_limit'] = '-'
                            
                        if m_dict['oral_limit'] == '-':
                            m_dict['oral_marks'] = None
                        if m_dict['written_limit'] == '-':
                            m_dict['written_marks'] = None
                        if m_dict['ct_limit'] == '-':
                            m_dict['ct_marks'] = None
                            
                        m_dict['total_marks'] = tot_fm
                        term_marks.append(m_dict)
                    
            # Get distinct term names for term exams
            distinct_terms = []
            for m in term_marks:
                t = m['term']
                if t not in distinct_terms:
                    distinct_terms.append(t)

            # Group monthly marks by subject and terms chronologically
            monthly_terms = []
            for m in reversed(marks_rows):
                term_name = m['term']
                if is_monthly_test(term_name):
                    t_clean = term_name.strip()
                    if t_clean not in monthly_terms:
                        monthly_terms.append(t_clean)
            monthly_terms.sort(key=get_month_sort_key)
            
            def get_short_term_name(name):
                name_upper = name.upper()
                if "MONTHLY TEST" in name_upper:
                    parts = name.split()
                    if len(parts) >= 3:
                        return parts[2][:3].upper()
                if "CLASS TEST" in name_upper:
                    parts = name.split()
                    if len(parts) >= 3:
                        return "CT " + parts[2]
                return name[:6].upper()

            monthly_terms_short = {t: get_short_term_name(t) for t in monthly_terms}

            monthly_subjects = []
            for m in monthly_marks:
                sub = m['subject'].strip().title()
                if sub not in monthly_subjects:
                    monthly_subjects.append(sub)
            monthly_subjects.sort()

            # Query class subject configurations to get the correct full marks configured
            ct_fm_map = {}
            monthly_fms = {}
            if class_name:
                student_db_classes = get_db_class_names(class_name)
                placeholders_ct = ', '.join('?' for _ in student_db_classes)
                ct_config_rows = conn.execute(f"""
                    SELECT term_name, subject_name, full_marks 
                    FROM class_subjects 
                    WHERE class_name IN ({placeholders_ct})
                """, student_db_classes).fetchall()
                for row in ct_config_rows:
                    t_name = row['term_name'].strip().title()
                    sub_title = row['subject_name'].strip().title()
                    ct_fm_map[(t_name, sub_title)] = row['full_marks']
                    
                    if t_name not in monthly_fms or row['full_marks'] > monthly_fms[t_name]:
                        monthly_fms[t_name] = row['full_marks']
            
            for t in monthly_terms:
                t_title = t.strip().title()
                if t_title not in monthly_fms:
                    test_marks = [m for m in monthly_marks if m['term'].strip() == t]
                    if test_marks:
                        monthly_fms[t_title] = max(m['total_marks'] for m in test_marks if m['total_marks'] is not None)
                    else:
                        monthly_fms[t_title] = 20.0
                        
            monthly_fms_formatted = {}
            for k, v in monthly_fms.items():
                monthly_fms_formatted[k] = int(v) if v == int(v) else v

            monthly_grid = []
            for sub in monthly_subjects:
                sub_entry = {
                    'name': sub.upper(),
                    'marks': {}
                }
                for term_name in monthly_terms:
                    match = None
                    for m in monthly_marks:
                        if m['subject'].strip().title() == sub and m['term'].strip() == term_name:
                            match = m
                            break
                            
                    configured_fm = ct_fm_map.get((term_name.strip().title(), sub))
                    if configured_fm is None:
                        if match and match['total_marks'] is not None:
                            configured_fm = match['total_marks']
                        else:
                            configured_fm = 20.0
                            
                    if match:
                        obt = match['marks']
                        if obt is None:
                            sub_entry['marks'][term_name] = {
                                'obt': '-',
                                'tot': int(configured_fm) if configured_fm == int(configured_fm) else configured_fm
                            }
                        else:
                            sub_entry['marks'][term_name] = {
                                'obt': int(obt) if obt == int(obt) else obt,
                                'tot': int(configured_fm) if configured_fm == int(configured_fm) else configured_fm
                            }
                    else:
                        sub_entry['marks'][term_name] = {
                            'obt': '-',
                            'tot': int(configured_fm) if configured_fm == int(configured_fm) else configured_fm
                        }
                
                # Calculate totals for this subject
                sub_tot_obt = 0.0
                sub_tot_pos = 0.0
                has_any_mark = False
                for term_name in monthly_terms:
                    m_data = sub_entry['marks'][term_name]
                    if m_data['obt'] != '-':
                        sub_tot_obt += float(m_data['obt'])
                        sub_tot_pos += float(m_data['tot'])
                        has_any_mark = True
                
                if has_any_mark and sub_tot_pos > 0:
                    sub_pct = (sub_tot_obt / sub_tot_pos) * 100
                    sub_entry['total_obt'] = int(sub_tot_obt) if sub_tot_obt == int(sub_tot_obt) else round(sub_tot_obt, 1)
                    sub_entry['total_pos'] = int(sub_tot_pos) if sub_tot_pos == int(sub_tot_pos) else round(sub_tot_pos, 1)
                    sub_entry['pct'] = round(sub_pct, 1)
                    sub_entry['grade'] = calculate_grade(sub_pct)
                else:
                    sub_entry['total_obt'] = '-'
                    sub_entry['total_pos'] = '-'
                    sub_entry['pct'] = '-'
                    sub_entry['grade'] = '-'
                
                monthly_grid.append(sub_entry)

            monthly_grand_obt = 0.0
            monthly_grand_pos = 0.0
            monthly_has_marks = False
            for sub_entry in monthly_grid:
                if sub_entry['total_obt'] != '-':
                    monthly_grand_obt += float(sub_entry['total_obt'])
                    monthly_grand_pos += float(sub_entry['total_pos'])
                    monthly_has_marks = True

            monthly_overall_pct = 0.0
            if monthly_has_marks and monthly_grand_pos > 0:
                monthly_overall_pct = round((monthly_grand_obt / monthly_grand_pos) * 100, 1)

            monthly_overall_pass = monthly_overall_pct >= 40
            monthly_overall_grade = calculate_grade(monthly_overall_pct)
            
            selected_term = request.args.get('term')
            if selected_term:
                selected_term = selected_term.strip()
                if selected_term in ['1st Term', '1st Unit']:
                    selected_term = '1st Unit'
                elif selected_term in ['2nd Term', '2nd Unit']:
                    selected_term = '2nd Unit'
                elif selected_term in ['Annual Exam', 'Final Exam', 'Annual']:
                    selected_term = 'Final Exam'
                    
            if not selected_term and distinct_terms:
                selected_term = distinct_terms[0]
                
            filtered_term_marks = []
            if selected_term:
                filtered_term_marks = [m for m in term_marks if m['term'] == selected_term]
            else:
                filtered_term_marks = term_marks

            additional_subject_names = ['physical education', 'work education', 'hand writing', 'behaviour', 'attendance']
            filtered_scholastic_marks = [
                m for m in filtered_term_marks 
                if m['subject'].strip().lower() not in additional_subject_names
            ]
            filtered_additional_marks = [
                m for m in filtered_term_marks 
                if m['subject'].strip().lower() in additional_subject_names
            ]

            # Compile Annual Progress Report Card Data
            annual_students = []
            if student_meta:
                # Separate main, art, additional
                additional_names = ['physical education', 'work education', 'hand writing', 'behaviour', 'attendance']
                active_main_subjects = [s_sub for s_sub in class_subjects if s_sub.lower() != 'art' and s_sub.lower() not in additional_names]
                is_art_active = 'Art' in class_subjects
                is_add_active = any(add_s in [x.lower() for x in class_subjects] for add_s in additional_names)
                
                # Fetch all marks of the student for grouping with term normalization
                student_marks_by_sub = {}
                for m in marks_rows:
                    sub = m['subject'].strip().title()
                    term = m['term'].strip()
                    
                    norm_term = term
                    if term in ['1st Term', '1st Unit']:
                        norm_term = '1st Unit'
                    elif term in ['2nd Term', '2nd Unit']:
                        norm_term = '2nd Unit'
                    elif term in ['Annual Exam', 'Final Exam']:
                        norm_term = 'Final Exam'
                        
                    if sub not in student_marks_by_sub:
                        student_marks_by_sub[sub] = {}
                    student_marks_by_sub[sub][norm_term] = m
                
                # Fetch all students in the same class and branch for ranking
                db_classes = get_db_class_names(class_name)
                placeholders = ', '.join('?' for _ in db_classes)
                all_class_students = conn.execute(f'''
                    SELECT u.id, COALESCE(si.full_name, u.username) as name, si.roll_number
                    FROM users u
                    JOIN student_info si ON u.id = si.user_id
                    WHERE si.branch = ? AND si.class IN ({placeholders})
                ''', [branch_name] + db_classes).fetchall()
                
                # Fetch all marks for all class students in a single query
                student_ids = [s_row['id'] for s_row in all_class_students]
                marks_by_student = {}
                if student_ids:
                    placeholders_stud = ', '.join('?' for _ in student_ids)
                    all_marks = conn.execute(f'''
                        SELECT student_id, subject_name, term_name, obtained_marks
                        FROM marks
                        WHERE student_id IN ({placeholders_stud})
                    ''', student_ids).fetchall()
                    
                    for m in all_marks:
                        sid = m['student_id']
                        if sid not in marks_by_student:
                            marks_by_student[sid] = {}
                        sub_n = m['subject_name'].strip().title()
                        term_n = m['term_name'].strip()
                        
                        norm_term = term_n
                        if term_n in ['1st Term', '1st Unit']:
                            norm_term = '1st Unit'
                        elif term_n in ['2nd Term', '2nd Unit']:
                            norm_term = '2nd Unit'
                        elif term_n in ['Annual Exam', 'Final Exam']:
                            norm_term = 'Final Exam'
                            
                        if sub_n not in marks_by_student[sid]:
                            marks_by_student[sid][sub_n] = {}
                        marks_by_student[sid][sub_n][norm_term] = m['obtained_marks']

                # Compute function for totals using in-memory cached data
                def compute_student_annual_total_fast(sid):
                    m_by_sub = marks_by_student.get(sid, {})
                    tot_obt = 0.0
                    for sub_n in active_main_subjects:
                        sub_tot = 0.0
                        for term_n in ['1st Unit', '2nd Unit', 'Final Exam']:
                            if term_n in m_by_sub.get(sub_n, {}):
                                sub_tot += float(m_by_sub[sub_n][term_n] or 0.0)
                        tot_obt += sub_tot
                        
                    if is_art_active:
                        art_tot = 0.0
                        for term_n in ['1st Unit', '2nd Unit', 'Final Exam']:
                            if 'Art' in m_by_sub and term_n in m_by_sub['Art']:
                                art_tot += float(m_by_sub['Art'][term_n] or 0.0)
                        tot_obt += art_tot
                        
                    if is_add_active:
                        add_tot = 0.0
                        for add_sub in ['Physical Education', 'Work Education', 'Hand Writing', 'Behaviour', 'Attendance']:
                            if add_sub in m_by_sub and 'Final Exam' in m_by_sub[add_sub]:
                                add_tot += float(m_by_sub[add_sub]['Final Exam'] or 0.0)
                        tot_obt += add_tot
                        
                    return tot_obt

                # Calculate ranks
                student_totals = []
                for s_row in all_class_students:
                    s_tot = compute_student_annual_total_fast(s_row['id'])
                    student_totals.append((s_row['id'], s_tot))
                
                student_totals.sort(key=lambda x: x[1], reverse=True)
                ranks = {}
                current_rank = 1
                for i, (sid, tot) in enumerate(student_totals):
                    if i > 0 and tot == student_totals[i-1][1]:
                        ranks[sid] = ranks[student_totals[i-1][0]]
                    else:
                        ranks[sid] = current_rank
                    current_rank += 1
                
                # Build student card
                s = {}
                s['name'] = student_meta['name']
                s['class_name'] = student_meta['class']
                s['roll'] = student_meta['roll_number']
                s['section'] = student_meta['section'] or 'A'
                s['branch'] = student_meta['branch'] or 'BHOGRAM'
                s['session'] = student_meta['session'] or '2025'
                
                # Initialize sums for column totals
                u1_o_tot = 0.0
                u1_w_tot = 0.0
                u1_tot_tot = 0.0
                u1_o_pos = 0.0
                u1_w_pos = 0.0
                u1_tot_pos = 0.0
                
                u2_o_tot = 0.0
                u2_w_tot = 0.0
                u2_tot_tot = 0.0
                u2_o_pos = 0.0
                u2_w_pos = 0.0
                u2_tot_pos = 0.0
                
                f_o_tot = 0.0
                f_w_tot = 0.0
                f_ct_tot = 0.0
                f_tot_tot = 0.0
                f_o_pos = 0.0
                f_w_pos = 0.0
                f_ct_pos = 0.0
                f_tot_pos = 0.0
                
                grand_tot_tot = 0.0
                grand_tot_pos = 0.0

                def row_get(row, field, default=None):
                    if row is None:
                        return default
                    try:
                        return row[field]
                    except:
                        return default

                def fmt_val(row, field):
                    val = row_get(row, field)
                    if val is None: return '-'
                    val_str = str(val).strip()
                    if '/' in val_str:
                        val_str = val_str.split('/')[0].strip()
                    if val_str == '': return '-'
                    try:
                        fval = float(val_str)
                        if fval == int(fval): return str(int(fval))
                        return f"{fval:.1f}"
                    except:
                        return val_str

                def get_float(row, field):
                    val = row_get(row, field)
                    if val is None: return 0.0
                    val_str = str(val).strip()
                    if '/' in val_str:
                        val_str = val_str.split('/')[0].strip()
                    try: return float(val_str)
                    except: return 0.0

                subjects_list = []
                for sub in active_main_subjects:
                    sub_entry = {'name': sub.upper()}
                    
                    u1_m = student_marks_by_sub.get(sub, {}).get('1st Unit')
                    u2_m = student_marks_by_sub.get(sub, {}).get('2nd Unit')
                    f_m = student_marks_by_sub.get(sub, {}).get('Final Exam')
                    
                    sub_entry['u1_o'] = fmt_val(u1_m, 'oral_marks')
                    sub_entry['u1_w'] = fmt_val(u1_m, 'written_marks')
                    sub_entry['u1_tot'] = fmt_val(u1_m, 'marks')
                    
                    sub_entry['u2_o'] = fmt_val(u2_m, 'oral_marks')
                    sub_entry['u2_w'] = fmt_val(u2_m, 'written_marks')
                    sub_entry['u2_tot'] = fmt_val(u2_m, 'marks')
                    
                    sub_entry['f_o'] = fmt_val(f_m, 'oral_marks')
                    sub_entry['f_w'] = fmt_val(f_m, 'written_marks')
                    
                    # --- AUTO CT MARK CALCULATION DISABLED (CONNECTED TO MANUAL INPUT) ---
                    auto_ct_val = None

                    f_o_val = get_float(f_m, 'oral_marks')
                    f_w_val = get_float(f_m, 'written_marks')
                    f_ct_val = get_float(f_m, 'ct_marks')

                    sub_entry['f_ct'] = fmt_val(f_m, 'ct_marks')

                    if f_m is None:
                        sub_entry['f_tot'] = '-'
                        f_tot_val = 0.0
                    else:
                        # B6 FIX: fall back to obtained_marks when component fields are all zero/absent
                        if f_o_val == 0.0 and f_w_val == 0.0 and f_ct_val == 0.0:
                            f_tot_val = get_float(f_m, 'marks')
                        else:
                            f_tot_val = f_o_val + f_w_val + f_ct_val
                        sub_entry['f_tot'] = f"{f_tot_val:.1f}" if f_tot_val != int(f_tot_val) else str(int(f_tot_val))

                    u1_tot_val = get_float(u1_m, 'marks')
                    u2_tot_val = get_float(u2_m, 'marks')
                    grand_val = u1_tot_val + u2_tot_val + f_tot_val
                    
                    u1_possible_val = subject_fm_1st_map.get(sub)
                    if u1_possible_val is None:
                        u1_possible_val = get_float(u1_m, 'total_marks') if u1_m is not None else None
                        
                    u2_possible_val = subject_fm_2nd_map.get(sub)
                    if u2_possible_val is None:
                        u2_possible_val = get_float(u2_m, 'total_marks') if u2_m is not None else None
                        
                    f_possible_val = subject_fm_annual_map.get(sub)
                    if f_possible_val is None:
                        f_possible_val = get_float(f_m, 'total_marks') if f_m is not None else None

                    custom_u1_o_val = subject_oral_1st_map.get(sub)
                    custom_u1_w_val = subject_written_1st_map.get(sub)
                    custom_u2_o_val = subject_oral_2nd_map.get(sub)
                    custom_u2_w_val = subject_written_2nd_map.get(sub)
                    custom_f_o_val = subject_oral_annual_map.get(sub)
                    custom_f_w_val = subject_written_annual_map.get(sub)
                    custom_f_ct_val = subject_ct_annual_map.get(sub)

                    sub_entry['u1_o_limit'] = fmt_limit(custom_u1_o_val)
                    sub_entry['u1_w_limit'] = fmt_limit(custom_u1_w_val)
                    sub_entry['u1_tot_limit'] = fmt_limit(u1_possible_val)

                    sub_entry['u2_o_limit'] = fmt_limit(custom_u2_o_val)
                    sub_entry['u2_w_limit'] = fmt_limit(custom_u2_w_val)
                    sub_entry['u2_tot_limit'] = fmt_limit(u2_possible_val)

                    sub_entry['f_o_limit'] = fmt_limit(custom_f_o_val)
                    sub_entry['f_w_limit'] = fmt_limit(custom_f_w_val)
                    sub_entry['f_ct_limit'] = fmt_limit(custom_f_ct_val)
                    sub_entry['f_tot_limit'] = fmt_limit(f_possible_val)
                    
                    u1_pos_calc = u1_possible_val if u1_possible_val is not None else 0.0
                    u2_pos_calc = u2_possible_val if u2_possible_val is not None else 0.0
                    f_pos_calc = f_possible_val if f_possible_val is not None else 0.0
                    sub_entry['possible'] = fmt_limit(u1_pos_calc + u2_pos_calc + f_pos_calc)

                    possible_val = 0.0
                    if u1_m is not None:
                        possible_val += u1_pos_calc
                        u1_o_tot += get_float(u1_m, 'oral_marks')
                        u1_w_tot += get_float(u1_m, 'written_marks')
                        u1_tot_tot += u1_tot_val
                        if custom_u1_o_val is not None: u1_o_pos += custom_u1_o_val
                        if custom_u1_w_val is not None: u1_w_pos += custom_u1_w_val
                        u1_tot_pos += u1_pos_calc
                        
                    if u2_m is not None:
                        possible_val += u2_pos_calc
                        u2_o_tot += get_float(u2_m, 'oral_marks')
                        u2_w_tot += get_float(u2_m, 'written_marks')
                        u2_tot_tot += u2_tot_val
                        if custom_u2_o_val is not None: u2_o_pos += custom_u2_o_val
                        if custom_u2_w_val is not None: u2_w_pos += custom_u2_w_val
                        u2_tot_pos += u2_pos_calc
                        
                    if f_m is not None:
                        possible_val += f_pos_calc
                        f_o_tot += f_o_val
                        f_w_tot += f_w_val
                        f_ct_tot += f_ct_val
                        f_tot_tot += f_tot_val
                        if custom_f_o_val is not None: f_o_pos += custom_f_o_val
                        if custom_f_w_val is not None: f_w_pos += custom_f_w_val
                        if custom_f_ct_val is not None: f_ct_pos += custom_f_ct_val
                        f_tot_pos += f_pos_calc
                    
                    if u1_m is None and u2_m is None and f_m is None:
                        sub_entry['grand'] = '-'
                        sub_entry['grade'] = '-'
                    else:
                        sub_entry['grand'] = int(grand_val) if grand_val == int(grand_val) else round(grand_val, 2)
                        pct = (grand_val / possible_val * 100) if possible_val > 0 else 0.0
                        sub_entry['grade'] = calculate_grade(pct)
                        grand_tot_tot += grand_val
                        grand_tot_pos += possible_val
                        
                    subjects_list.append(sub_entry)
                    
                s['subjects'] = subjects_list
                
                art_u1_limit_val = subject_fm_1st_map.get('Art', 50.0)
                art_u2_limit_val = subject_fm_2nd_map.get('Art', 50.0)
                art_f_limit_val = subject_fm_annual_map.get('Art', 100.0)

                s['art_u1_limit'] = fmt_limit(art_u1_limit_val)
                s['art_u2_limit'] = fmt_limit(art_u2_limit_val)
                s['art_f_limit'] = fmt_limit(art_f_limit_val)
                s['art_possible'] = fmt_limit(art_u1_limit_val + art_u2_limit_val + art_f_limit_val)

                art_u1_row = student_marks_by_sub.get('Art', {}).get('1st Unit')
                art_u2_row = student_marks_by_sub.get('Art', {}).get('2nd Unit')
                art_f_row = student_marks_by_sub.get('Art', {}).get('Final Exam')
                
                s['art_u1'] = fmt_val(art_u1_row, 'marks')
                s['art_u2'] = fmt_val(art_u2_row, 'marks')
                s['art_f'] = fmt_val(art_f_row, 'marks')
                
                art_u1_val = get_float(art_u1_row, 'marks')
                art_u2_val = get_float(art_u2_row, 'marks')
                art_f_val = get_float(art_f_row, 'marks')
                art_grand_val = art_u1_val + art_u2_val + art_f_val
                
                art_possible_val = 0.0
                if art_u1_row is not None:
                    art_possible_val += art_u1_limit_val
                    u1_tot_tot += art_u1_val
                    u1_tot_pos += art_u1_limit_val
                if art_u2_row is not None:
                    art_possible_val += art_u2_limit_val
                    u2_tot_tot += art_u2_val
                    u2_tot_pos += art_u2_limit_val
                if art_f_row is not None:
                    art_possible_val += art_f_limit_val
                    f_tot_tot += art_f_val
                    f_tot_pos += art_f_limit_val
                
                if art_u1_row is None and art_u2_row is None and art_f_row is None:
                    s['art_grand'] = '-'
                    s['art_grade'] = '-'
                else:
                    s['art_grand'] = int(art_grand_val) if art_grand_val == int(art_grand_val) else round(art_grand_val, 2)
                    art_pct = (art_grand_val / art_possible_val * 100) if art_possible_val > 0 else 0.0
                    s['art_grade'] = calculate_grade(art_pct)
                    grand_tot_tot += art_grand_val
                    grand_tot_pos += art_possible_val

                # Format sums for displaying
                def fmt_sum(tot):
                    return int(tot) if tot == int(tot) else round(tot, 1)

                s['u1_o_sum'] = fmt_sum(u1_o_tot) if u1_o_pos > 0 else '-'
                s['u1_w_sum'] = fmt_sum(u1_w_tot) if u1_w_pos > 0 else '-'
                s['u1_tot_sum'] = fmt_sum(u1_tot_tot) if u1_tot_pos > 0 else '-'
                
                s['u2_o_sum'] = fmt_sum(u2_o_tot) if u2_o_pos > 0 else '-'
                s['u2_w_sum'] = fmt_sum(u2_w_tot) if u2_w_pos > 0 else '-'
                s['u2_tot_sum'] = fmt_sum(u2_tot_tot) if u2_tot_pos > 0 else '-'
                
                s['f_o_sum'] = fmt_sum(f_o_tot) if f_o_pos > 0 else '-'
                s['f_w_sum'] = fmt_sum(f_w_tot) if f_w_pos > 0 else '-'
                s['f_ct_sum'] = fmt_sum(f_ct_tot) if f_ct_pos > 0 else '-'
                s['f_tot_sum'] = fmt_sum(f_tot_tot) if f_tot_pos > 0 else '-'
                
                s['grand_tot_sum'] = fmt_sum(grand_tot_tot) if grand_tot_pos > 0 else '-'
                if grand_tot_pos > 0:
                    s['grand_tot_grade'] = calculate_grade((grand_tot_tot / grand_tot_pos) * 100)
                else:
                    s['grand_tot_grade'] = '-'
                    
                ped_row = student_marks_by_sub.get('Physical Education', {}).get('Final Exam')
                wed_row = student_marks_by_sub.get('Work Education', {}).get('Final Exam')
                hw_row = student_marks_by_sub.get('Hand Writing', {}).get('Final Exam')
                behav_row = student_marks_by_sub.get('Behaviour', {}).get('Final Exam')
                attend_row = student_marks_by_sub.get('Attendance', {}).get('Final Exam')
                
                s['add'] = {
                    'ped': fmt_val(ped_row, 'marks'),
                    'wed': fmt_val(wed_row, 'marks'),
                    'hw': fmt_val(hw_row, 'marks'),
                    'behav': fmt_val(behav_row, 'marks'),
                    'attend': fmt_val(attend_row, 'marks')
                }
                
                ped_val = get_float(ped_row, 'marks')
                wed_val = get_float(wed_row, 'marks')
                hw_val = get_float(hw_row, 'marks')
                behav_val = get_float(behav_row, 'marks')
                attend_val = get_float(attend_row, 'marks')
                add_tot_val = ped_val + wed_val + hw_val + behav_val + attend_val
                
                if ped_row is None and wed_row is None and hw_row is None and behav_row is None and attend_row is None:
                    s['add_tot'] = '-'
                else:
                    s['add_tot'] = int(add_tot_val) if add_tot_val == int(add_tot_val) else round(add_tot_val, 2)
                    
                # Compute total obtained and possible dynamically across scholastic and additional
                total_obtained = grand_tot_tot
                total_possible = grand_tot_pos
                
                ped_fm = subject_fm_annual_map.get('Physical Education', 20.0)
                wed_fm = subject_fm_annual_map.get('Work Education', 30.0)
                hw_fm = subject_fm_annual_map.get('Hand Writing', 20.0)
                behav_fm = subject_fm_annual_map.get('Behaviour', 20.0)
                attend_fm = subject_fm_annual_map.get('Attendance', 10.0)

                s['add_fm'] = {
                    'ped': fmt_limit(ped_fm),
                    'wed': fmt_limit(wed_fm),
                    'hw': fmt_limit(hw_fm),
                    'behav': fmt_limit(behav_fm),
                    'attend': fmt_limit(attend_fm),
                    'total': fmt_limit(ped_fm + wed_fm + hw_fm + behav_fm + attend_fm)
                }

                if s['add_tot'] != '-':
                    total_obtained += add_tot_val
                    if ped_row is not None: total_possible += ped_fm
                    if wed_row is not None: total_possible += wed_fm
                    if hw_row is not None: total_possible += hw_fm
                    if behav_row is not None: total_possible += behav_fm
                    if attend_row is not None: total_possible += attend_fm
                    
                s['total_obtained'] = fmt_sum(total_obtained)
                s['max_marks'] = fmt_sum(total_possible)
                
                if s['max_marks'] > 0:
                    s['percentage'] = round((s['total_obtained'] / s['max_marks']) * 100, 2)
                else:
                    s['percentage'] = 0.0
                    
                s['overall_grade'] = calculate_overall_grade(s['percentage'])
                s['rank'] = ranks.get(student_id, '-')
                
                annual_students.append(s)

            conn.close()
            logo_url = LOGO_URL
            return render_template('admin/marksheet.html', 
                                   marks=filtered_scholastic_marks, 
                                   additional_marks=filtered_additional_marks,
                                   monthly_marks=monthly_marks, 
                                   annual_composite=annual_students,
                                   student_info=student_meta,
                                   role=role,
                                   logo_url=logo_url,
                                   distinct_terms=distinct_terms,
                                   selected_term=selected_term,
                                   monthly_grid=monthly_grid,
                                   monthly_terms=monthly_terms,
                                   monthly_terms_short=monthly_terms_short,
                                   monthly_fms=monthly_fms_formatted,
                                   monthly_grand_obt=int(monthly_grand_obt) if monthly_grand_obt == int(monthly_grand_obt) else round(monthly_grand_obt, 1),
                                   monthly_grand_pos=int(monthly_grand_pos) if monthly_grand_pos == int(monthly_grand_pos) else round(monthly_grand_pos, 1),
                                   monthly_overall_pct=monthly_overall_pct,
                                   monthly_overall_grade=monthly_overall_grade,
                                   monthly_overall_pass=monthly_overall_pass)
        
        # Load students list if not specifying a student
        if session.get('branch'):
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
        else:
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
        conn.close()
        return render_template('admin/marksheet.html', marks=None, students=students, role=role)
    return redirect(url_for('home'))

def get_written_marks_limit(conn, class_name, term_name, subject_name):
    sub_title = subject_name.strip().title()
    norm_term = term_name.strip()
    if norm_term in ['1st Term', '1st Unit']:
        norm_term = '1st Unit'
    elif norm_term in ['2nd Term', '2nd Unit']:
        norm_term = '2nd Unit'
    elif norm_term in ['Annual Exam', 'Final Exam', 'Annual']:
        norm_term = 'Final Exam'
        
    db_classes = get_db_class_names(class_name)
    placeholders = ', '.join('?' for _ in db_classes)
    
    row = conn.execute(f"""
        SELECT written_limit FROM class_subjects
        WHERE class_name IN ({placeholders}) AND subject_name = ? AND term_name = ?
    """, (*db_classes, sub_title, norm_term)).fetchone()
    
    if not row:
        row = conn.execute(f"""
            SELECT written_limit FROM class_subjects
            WHERE class_name IN ({placeholders}) AND LOWER(subject_name) = ? AND term_name = ?
        """, (*db_classes, sub_title.lower(), norm_term)).fetchone()
        
    if row and row['written_limit'] is not None:
        return row['written_limit']
        
    default_fm_dict = {'Physical Education': 20.0, 'Work Education': 30.0, 'Hand Writing': 20.0, 'Behaviour': 20.0, 'Attendance': 10.0}
    if sub_title in default_fm_dict:
        return default_fm_dict[sub_title]
        
    if norm_term in ['1st Unit', '2nd Unit']:
        return 40.0
    elif norm_term == 'Final Exam':
        return 70.0
    return 50.0

@app.route('/admin/marksheet/bulk')
@login_required
def bulk_marksheet():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return redirect(url_for('home'))
        
    class_name = request.args.get('class_name')
    term_name = request.args.get('term_name')
    if not class_name or not term_name:
        flash('Class name and term name are required.', 'error')
        return redirect(url_for('dashboard'))
        
    branch = session.get('branch')
    conn = get_db_connection()
    db_classes = get_db_class_names(class_name)
    placeholders = ', '.join('?' for _ in db_classes)
    
    norm_term = term_name
    if term_name in ['1st Term', '1st Unit']:
        norm_term = '1st Unit'
    elif term_name in ['2nd Term', '2nd Unit']:
        norm_term = '2nd Unit'
    elif term_name in ['Annual Exam', 'Final Exam', 'Annual']:
        norm_term = 'Final Exam'
    else:
        norm_term = normalize_monthly_test_name(term_name)

    subjects_rows = conn.execute(f"""
        SELECT subject_name AS name, full_marks, oral_limit, written_limit, ct_limit
        FROM class_subjects 
        WHERE class_name IN ({placeholders}) AND term_name = ?
    """, db_classes + [norm_term]).fetchall()
    
    subject_fm_map = {}
    subject_oral_map = {}
    subject_written_map = {}
    subject_ct_map = {}
    
    for r in subjects_rows:
        if r['name']:
            sub_name_norm = r['name'].strip().title()
            subject_fm_map[sub_name_norm] = r['full_marks']
            subject_oral_map[sub_name_norm] = r['oral_limit']
            subject_written_map[sub_name_norm] = r['written_limit']
            subject_ct_map[sub_name_norm] = r['ct_limit']

    if branch:
        students = conn.execute(f'''
            SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.roll_number, si.section, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE u.role = 'student' AND si.class IN ({placeholders}) AND si.branch = ?
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', (*db_classes, branch)).fetchall()
    else:
        students = conn.execute(f'''
            SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.roll_number, si.section, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE u.role = 'student' AND si.class IN ({placeholders})
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', tuple(db_classes)).fetchall()

    def fmt_limit(lim):
        if lim is None: return '-'
        if lim == int(lim): return int(lim)
        return round(lim, 1)

    student_reports = []
    
    student_ids = [s['id'] for s in students]
    marks_map = {}
    if student_ids:
        placeholders_stud = ', '.join('?' for _ in student_ids)
        marks_rows = conn.execute(f'''
            SELECT m.student_id, m.obtained_marks, m.full_marks, m.oral_marks, m.written_marks, m.ct_marks, m.subject_name
            FROM marks m
            WHERE m.student_id IN ({placeholders_stud}) AND (m.term_name = ? OR m.term_name = ?)
        ''', (*student_ids, term_name, norm_term)).fetchall()
        for m in marks_rows:
            sid = m['student_id']
            if sid not in marks_map:
                marks_map[sid] = []
            marks_map[sid].append(m)

    for student in students:
        sid = student['id']
        s_marks = marks_map.get(sid, [])
        
        compiled_marks = []
        total_obtained = 0.0
        total_possible = 0.0
        
        active_subjects = sorted(list(subject_fm_map.keys()))
        
        for sub_name in active_subjects:
            match = None
            for m in s_marks:
                if m['subject_name'].strip().title() == sub_name:
                    match = m
                    break
            
            tot_fm = subject_fm_map.get(sub_name, 100.0)
            oral_lim = subject_oral_map.get(sub_name)
            written_lim = subject_written_map.get(sub_name)
            ct_lim = subject_ct_map.get(sub_name)

            if match:
                obt = match['obtained_marks']
                obt_val = float(obt) if obt is not None else 0.0
                oral_obt = match['oral_marks'] if oral_lim is not None else None
                written_obt = match['written_marks'] if written_lim is not None else None
                ct_obt = match['ct_marks'] if ct_lim is not None else None
            else:
                obt_val = 0.0
                obt = '-'
                oral_obt = '-'
                written_obt = '-'
                ct_obt = '-'
            
            total_obtained += obt_val
            total_possible += float(tot_fm)
            
            compiled_marks.append({
                'subject_name': sub_name,
                'oral_limit': fmt_limit(oral_lim),
                'oral_marks': oral_obt if oral_obt is not None else '-',
                'written_limit': fmt_limit(written_lim),
                'written_marks': written_obt if written_obt is not None else '-',
                'ct_limit': fmt_limit(ct_lim),
                'ct_marks': ct_obt if ct_obt is not None else '-',
                'full_marks': fmt_limit(tot_fm),
                'obtained_marks': obt if obt is not None else '-'
            })
            
        pct = (total_obtained / total_possible * 100) if total_possible > 0 else 0.0
        grade = calculate_grade(pct)
        
        student_reports.append({
            'id': sid,
            'name': student['name'],
            'roll': student['roll_number'] or '-',
            'section': student['section'] or '-',
            'branch': student['branch'] or '-',
            'marks': compiled_marks,
            'total_obtained': int(total_obtained) if total_obtained == int(total_obtained) else round(total_obtained, 1),
            'total_possible': int(total_possible) if total_possible == int(total_possible) else round(total_possible, 1),
            'percentage': f"{pct:.1f}%",
            'pct_val': pct,
            'grade': grade,
            'rank': '-'
        })

    sorted_reports = sorted(student_reports, key=lambda x: x['total_obtained'] if x['total_obtained'] != '-' else -1, reverse=True)
    for idx, r in enumerate(sorted_reports):
        if r['total_obtained'] == '-':
            r['rank'] = '-'
            continue
        if idx > 0 and r['total_obtained'] == sorted_reports[idx-1]['total_obtained']:
            r['rank'] = sorted_reports[idx-1]['rank']
        else:
            r['rank'] = idx + 1
            
    conn.close()
    
    return render_template(
        'admin/bulk_marksheet.html',
        marksheets=sorted_reports,
        class_name=class_name,
        term_name=term_name,
        logo_url=LOGO_URL
    )

@app.route('/admin/result-sheet')
@login_required
def result_sheet():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return redirect(url_for('home'))
        
    class_name = request.args.get('class_name')
    term_name = request.args.get('term_name')
    if not class_name or not term_name:
        flash('Class name and term name are required.', 'error')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    db_classes = get_db_class_names(class_name)
    placeholders = ', '.join('?' for _ in db_classes)
    
    norm_term = term_name
    if term_name in ['1st Term', '1st Unit']:
        norm_term = '1st Unit'
    elif term_name in ['2nd Term', '2nd Unit']:
        norm_term = '2nd Unit'
    elif term_name in ['Annual Exam', 'Final Exam', 'Annual']:
        norm_term = 'Final Exam'
    else:
        norm_term = normalize_monthly_test_name(term_name)

    subjects_rows = conn.execute(f"""
        SELECT subject_name AS name, full_marks
        FROM class_subjects 
        WHERE class_name IN ({placeholders}) AND term_name = ?
    """, db_classes + [norm_term]).fetchall()
    
    subject_fm_map = {}
    for r in subjects_rows:
        if r['name']:
            sub_name_norm = r['name'].strip().title()
            subject_fm_map[sub_name_norm] = r['full_marks']

    branch = session.get('branch')  # B1 FIX: was undefined, caused NameError
    if branch:
        students = conn.execute(f'''
            SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.roll_number, si.section, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE u.role = 'student' AND si.class IN ({placeholders}) AND si.branch = ?
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', (*db_classes, branch)).fetchall()
    else:
        students = conn.execute(f'''
            SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.roll_number, si.section, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE u.role = 'student' AND si.class IN ({placeholders})
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', tuple(db_classes)).fetchall()

    student_ids = [s['id'] for s in students]
    marks_map = {}
    if student_ids:
        placeholders_stud = ', '.join('?' for _ in student_ids)
        marks_rows = conn.execute(f'''
            SELECT m.student_id, m.obtained_marks, m.full_marks, m.subject_name
            FROM marks m
            WHERE m.student_id IN ({placeholders_stud}) AND (m.term_name = ? OR m.term_name = ?)
        ''', (*student_ids, term_name, norm_term)).fetchall()
        for m in marks_rows:
            sid = m['student_id']
            if sid not in marks_map:
                marks_map[sid] = []
            marks_map[sid].append(m)

    active_subjects = sorted(list(subject_fm_map.keys()))

    students_results = []
    for student in students:
        sid = student['id']
        s_marks = marks_map.get(sid, [])
        
        subject_marks = {}
        total_obtained = 0.0
        total_possible = 0.0
        
        for sub_name in active_subjects:
            match = None
            for m in s_marks:
                if m['subject_name'].strip().title() == sub_name:
                    match = m
                    break
            
            tot_fm = subject_fm_map.get(sub_name, 100.0)
                
            if match and match['obtained_marks'] is not None:
                obt = match['obtained_marks']
                obt_val = float(obt)
                subject_marks[sub_name] = int(obt) if obt == int(obt) else obt
            else:
                obt_val = 0.0
                subject_marks[sub_name] = '-'
                
            total_obtained += obt_val
            total_possible += float(tot_fm)
            
        pct = (total_obtained / total_possible * 100) if total_possible > 0 else 0.0
        grade = calculate_grade(pct)
        
        students_results.append({
            'roll': student['roll_number'] or '-',
            'name': student['name'],
            'section': student['section'] or '-',
            'branch': student['branch'] or '-',
            'subject_marks': subject_marks,
            'total_obtained': int(total_obtained) if total_obtained == int(total_obtained) else round(total_obtained, 1),
            'total_possible': int(total_possible) if total_possible == int(total_possible) else round(total_possible, 1),
            'percentage': f"{pct:.1f}%",
            'grade': grade,
            'rank': '-'
        })

    sorted_results = sorted(students_results, key=lambda x: x['total_obtained'] if x['total_obtained'] != '-' else -1, reverse=True)
    for idx, r in enumerate(sorted_results):
        if r['total_obtained'] == '-':
            r['rank'] = '-'
            continue
        if idx > 0 and r['total_obtained'] == sorted_results[idx-1]['total_obtained']:
            r['rank'] = sorted_results[idx-1]['rank']
        else:
            r['rank'] = idx + 1
            
    conn.close()
    
    return render_template(
        'admin/result_sheet.html',
        students_results=sorted_results,
        subjects=active_subjects,
        class_name=class_name,
        term_name=term_name,
        logo_url=LOGO_URL
    )

@app.route('/admin/question-papers', methods=['GET', 'POST'])
@login_required
def question_papers():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        if user['role'] != 'admin':
            flash('Only administrators can upload question papers.', 'error')
            conn.close()
            return redirect(url_for('question_papers'))
            
        class_name = request.form.get('class_name')
        term_name = request.form.get('term_name')
        subject_name = request.form.get('subject_name')
        
        if not class_name or not term_name or not subject_name:
            flash('Class, Term, and Subject are required.', 'error')
            conn.close()
            return redirect(url_for('question_papers'))
            
        uploaded_files = request.files.getlist('question_files')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            flash('Please select at least one DOCX file to upload.', 'error')
            conn.close()
            return redirect(url_for('question_papers'))
            
        uploaded_count = 0
        for file in uploaded_files:
            if file and file.filename != '':
                if not file.filename.lower().endswith('.docx'):
                    flash(f"File '{file.filename}' skipped: Only .docx files are allowed.", 'error')
                    continue
                    
                import time
                filename = secure_filename(f"{int(time.time())}_{file.filename}")
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'question_papers')
                os.makedirs(upload_folder, exist_ok=True)
                local_path = os.path.join(upload_folder, filename)
                file.save(local_path)
                
                drive_file_id = upload_file_to_drive_and_map(
                    local_path, 
                    filename, 
                    file.content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                    folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_QUESTION_PAPERS'), 
                    conn=conn
                )
                
                conn.execute('''
                    INSERT INTO question_papers (class_name, term_name, subject_name, filename, filepath, uploaded_by, drive_file_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (class_name, term_name, subject_name, file.filename, filename, user['id'], drive_file_id))
                uploaded_count += 1
                
        if uploaded_count > 0:
            conn.commit()
            flash(f"Successfully uploaded {uploaded_count} question paper(s).", 'success')
        conn.close()
        return redirect(url_for('question_papers'))
        
    if user['role'] == 'teacher':
        allowed = get_teacher_allowed_subjects(conn, user['username'])
        allowed_pairs = set()
        for x in allowed:
            c = normalize_class_name(x.get('class'))
            s = normalize_subject_name(x.get('name'))
            if c and s:
                allowed_pairs.add((c, s))
        
        all_papers = conn.execute('''
            SELECT qp.id, qp.class_name, qp.term_name, qp.subject_name, qp.filename, qp.filepath, qp.uploaded_at, qp.uploaded_by,
                   COALESCE(si.full_name, u.username) as uploader_name, qp.drive_file_id
            FROM question_papers qp
            LEFT JOIN users u ON qp.uploaded_by = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            ORDER BY qp.uploaded_at DESC
        ''').fetchall()
        
        papers_rows = []
        for r in all_papers:
            c_norm = normalize_class_name(r['class_name'])
            s_norm = normalize_subject_name(r['subject_name'])
            if (c_norm, s_norm) in allowed_pairs:
                papers_rows.append(r)
    else:
        papers_rows = conn.execute('''
            SELECT qp.id, qp.class_name, qp.term_name, qp.subject_name, qp.filename, qp.filepath, qp.uploaded_at, qp.uploaded_by,
                   COALESCE(si.full_name, u.username) as uploader_name, qp.drive_file_id
            FROM question_papers qp
            LEFT JOIN users u ON qp.uploaded_by = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            ORDER BY qp.uploaded_at DESC
        ''').fetchall()
    
    papers = []
    for r in papers_rows:
        limit = get_written_marks_limit(conn, r['class_name'], r['term_name'], r['subject_name'])
        limit_str = int(limit) if limit == int(limit) else round(limit, 1)
        
        p_dict = dict(r)
        p_dict['written_limit'] = limit_str
        papers.append(p_dict)
        
    classes_rows = conn.execute("SELECT DISTINCT class FROM student_info WHERE class IS NOT NULL AND class != ''").fetchall()
    classes = [c['class'] for c in classes_rows]
    if user['role'] == 'teacher':
        allowed = get_teacher_allowed_subjects(conn, user['username'])
        allowed_classes = {normalize_class_name(x['class']) for x in allowed if x.get('class')}
        classes = [c for c in classes if normalize_class_name(c) in allowed_classes]
        if not classes:
            std_order = ["Nursery", "U/N", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
            classes = [c for c in std_order if normalize_class_name(c) in allowed_classes]
    else:
        std_order = ["Nursery", "U/N", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
        classes = sorted(classes, key=lambda x: std_order.index(x) if x in std_order else 99)
        if not classes:
            classes = std_order
        
    class_tests_rows = conn.execute("SELECT DISTINCT term_name FROM class_subjects").fetchall()
    terms = ["1st Unit", "2nd Unit", "Final Exam"] + [r['term_name'] for r in class_tests_rows if r['term_name']]
    terms = sorted(list(set(terms)))
    
    subjects_rows = conn.execute("SELECT DISTINCT name FROM subjects WHERE name IS NOT NULL AND name != ''").fetchall()
    subjects = sorted(list(set([r['name'].strip().title() for r in subjects_rows])))
    if not subjects:
        subjects = ["English", "Bengali", "Arabic", "Mathematics", "Science", "G.K.", "E.V.S", "Hindi", "Art", "Physical Education", "Work Education", "Hand Handwriting", "Behaviour", "Attendance"]
        
    if user['role'] == 'teacher':
        allowed = get_teacher_allowed_subjects(conn, user['username'])
        allowed_subjects = {normalize_subject_name(x['name']) for x in allowed if x.get('name')}
        subjects = [s for s in subjects if normalize_subject_name(s) in allowed_subjects]
    
    conn.close()
    
    return render_template(
        'admin/question_papers.html',
        papers=papers,
        classes=classes,
        terms=terms,
        subjects=subjects,
        role=user['role'],
        user_id=user['id']
    )

@app.route('/admin/question-papers/delete/<int:paper_id>', methods=['POST'])
@login_required
def delete_question_paper(paper_id):
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Only administrators can delete question papers.', 'error')
        return redirect(url_for('question_papers'))
        
    conn = get_db_connection()
    paper = conn.execute("SELECT filepath, uploaded_by, drive_file_id FROM question_papers WHERE id = ?", (paper_id,)).fetchone()
    if paper:
        if user['role'] != 'admin' and paper['uploaded_by'] != user['id']:
            flash('You can only delete question papers you uploaded.', 'error')
            conn.close()
            return redirect(url_for('question_papers'))
            
        filepath = os.path.join(app.root_path, 'static', 'uploads', 'question_papers', paper['filepath'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                app.logger.error(f"Error removing file {filepath}: {e}")
                
        # Also delete from Google Drive if mapped
        drive_file_ids = set()
        if paper['drive_file_id']:
            drive_file_ids.add(paper['drive_file_id'])
            
        # Clean up drive_mappings too for backward compatibility
        conn.execute("DELETE FROM drive_mappings WHERE filename = ?", (paper['filepath'],))
        conn.execute("DELETE FROM question_papers WHERE id = ?", (paper_id,))
        conn.commit()
        
        for drive_file_id in drive_file_ids:
            delete_from_google_drive(drive_file_id)
            
        flash('Question paper successfully deleted.', 'success')
    else:
        flash('Question paper not found.', 'error')
        
    conn.close()
    return redirect(url_for('question_papers'))


@app.route('/admin/bulk-marks', methods=['GET', 'POST'])
def bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        role = session['role']

        if request.method == 'POST' and role == 'admin' and request.form.get('action_type'):
            action_type = request.form.get('action_type')
            class_name = request.form.get('class_name')
            branch = request.form.get('branch', 'bhogram')
            term_name = request.form.get('term_name')
            
            if action_type == 'add_subject':
                new_subject = request.form.get('new_subject', '').strip().title()
                if new_subject:
                    written_enabled = request.form.get('written_enabled')
                    written_max = request.form.get('written_max')
                    oral_enabled = request.form.get('oral_enabled')
                    oral_max = request.form.get('oral_max')
                    ct_enabled = request.form.get('ct_enabled')
                    ct_max = request.form.get('ct_max')
                    
                    try:
                        written_limit = float(written_max) if (written_enabled and written_max) else None
                    except ValueError:
                        written_limit = None
                    try:
                        oral_limit = float(oral_max) if (oral_enabled and oral_max) else None
                    except ValueError:
                        oral_limit = None
                    try:
                        ct_limit = float(ct_max) if (ct_enabled and ct_max) else None
                    except ValueError:
                        ct_limit = None
                        
                    full_marks = (written_limit or 0.0) + (oral_limit or 0.0) + (ct_limit or 0.0)
                    if written_limit is None and oral_limit is None and ct_limit is None:
                        written_limit = 100.0
                        full_marks = 100.0
                        
                    db_classes = get_db_class_names(class_name)
                    for c_name in db_classes:
                        conn.execute("""
                            INSERT OR REPLACE INTO class_subjects (class_name, subject_name, term_name, full_marks, oral_limit, written_limit, ct_limit)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (c_name, new_subject, term_name, full_marks, oral_limit, written_limit, ct_limit))
                    conn.commit()
                    flash(f'Subject {new_subject} added successfully.', 'success')
                
            elif action_type == 'delete_subject':
                subj_to_delete = request.form.get('subject_name')
                if subj_to_delete:
                    db_classes = get_db_class_names(class_name)
                    for c_name in db_classes:
                        conn.execute("DELETE FROM class_subjects WHERE class_name = ? AND subject_name = ? AND term_name = ?", (c_name, subj_to_delete, term_name))
                    conn.commit()
                    flash(f'Subject {subj_to_delete} removed from {term_name}.', 'success')
                    
            elif action_type == 'update_fm':
                subj_name = request.form.get('subject_name')
                w_limit = request.form.get('written_limit')
                o_limit = request.form.get('oral_limit')
                c_limit = request.form.get('ct_limit')
                
                try:
                    w_val = float(w_limit) if (w_limit and w_limit.strip() != '') else None
                except ValueError:
                    w_val = None
                try:
                    o_val = float(o_limit) if (o_limit and o_limit.strip() != '') else None
                except ValueError:
                    o_val = None
                try:
                    c_val = float(c_limit) if (c_limit and c_limit.strip() != '') else None
                except ValueError:
                    c_val = None
                    
                full_val = (w_val or 0.0) + (o_val or 0.0) + (c_val or 0.0)
                if w_val is None and o_val is None and c_val is None:
                    try:
                        full_val = float(request.form.get('full_marks') or 100.0)
                    except ValueError:
                        full_val = 100.0
                        
                db_classes = get_db_class_names(class_name)
                for c_name in db_classes:
                    conn.execute("""
                        INSERT OR REPLACE INTO class_subjects (class_name, subject_name, term_name, full_marks, oral_limit, written_limit, ct_limit)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (c_name, subj_name, term_name, full_val, o_val, w_val, c_val))
                conn.commit()
                flash(f'Subject {subj_name} configurations updated.', 'success')
            
            elif action_type == 'update_fm_inline':
                subj_name = request.form.get('subject_name')
                field = request.form.get('field') # 'full', 'oral', 'written', 'ct'
                value = request.form.get('value')
                
                if subj_name and field in ['full', 'oral', 'written', 'ct']:
                    col_map = {
                        'full': 'full_marks',
                        'oral': 'oral_limit',
                        'written': 'written_limit',
                        'ct': 'ct_limit'
                    }
                    col_name = col_map.get(field)
                    try:
                        val = float(value) if (value and value.strip() != '') else None
                    except ValueError:
                        val = None
                        
                    db_classes = get_db_class_names(class_name)
                    for c_name in db_classes:
                        conn.execute(f"UPDATE class_subjects SET {col_name} = ? WHERE class_name = ? AND subject_name = ? AND term_name = ?", (val, c_name, subj_name, term_name))
                        conn.execute("""
                            UPDATE class_subjects 
                            SET full_marks = CASE 
                                WHEN oral_limit IS NULL AND written_limit IS NULL AND ct_limit IS NULL THEN full_marks
                                ELSE COALESCE(oral_limit, 0) + COALESCE(written_limit, 0) + COALESCE(ct_limit, 0)
                            END
                            WHERE class_name = ? AND subject_name = ? AND term_name = ?
                        """, (c_name, subj_name, term_name))
                    conn.commit()
                    conn.close()
                    return jsonify({'status': 'success'})
            
            conn.close()
            return redirect(url_for('bulk_marks', branch=branch, **{'class': class_name}, term=term_name))

        # Query class tests from marks table
        existing_marks_terms = conn.execute("SELECT DISTINCT term_name FROM marks").fetchall()
        class_test_names = []
        for r in existing_marks_terms:
            t = r['term_name']
            if t:
                t_lower = t.lower()
                is_monthly = 'monthly' in t_lower or 'class test' in t_lower or 'test' in t_lower
                if is_monthly and t not in class_test_names:
                    class_test_names.append(t)
        
        # Sort monthly test names chronologically
        class_test_names.sort(key=get_month_sort_key)
        
        # Determine the user's role and fetch allowed subjects if teacher
        role = session['role']
        username = session['user']
        allowed_subjects = []

        students = []
        if session.get('branch'):
            selected_branch = session['branch']
        else:
            selected_branch = request.args.get('branch')
        selected_class = request.args.get('class')
        selected_subject = request.args.get('subject') # Optional pre-fill for admin or selected subject
        selected_term = request.args.get('term', '1st Unit')
        
        assigned_class = request.args.get('assigned_class')
        if role == 'teacher' and assigned_class:
            parts = assigned_class.split('|')
            if len(parts) == 3:
                selected_branch, selected_class, selected_subject = parts
                
        if selected_class:
            selected_class = normalize_class_name(selected_class)
        
        # Normalize the term name internally to prevent duplicates / naming mismatches
        selected_term = selected_term.strip()
        if selected_term in ['1st Term', '1st Unit']:
            selected_term = '1st Unit'
        elif selected_term in ['2nd Term', '2nd Unit']:
            selected_term = '2nd Unit'
        elif selected_term in ['Annual Exam', 'Final Exam', 'Annual']:
            selected_term = 'Final Exam'
        else:
            selected_term = normalize_monthly_test_name(selected_term)
            
        is_class_test = selected_term in class_test_names

        # Fetch allowed subjects if teacher
        if role == 'teacher':
             allowed_subjects = get_teacher_allowed_subjects(conn, username)

        subject_full_marks = {}
        configured_class_test_subjects = []
        class_test_default_fm = 20.0
        
        full_marks_val = request.args.get('full_marks', '100')
        if is_class_test:
            full_marks_val = '20'

        # Validate final selections for teacher to ensure they cannot view unauthorized classrooms
        if role == 'teacher':
            if selected_branch and selected_class and selected_subject:
                is_valid = False
                for sub in allowed_subjects:
                    sub_class_norms = [c.lower() for c in get_db_class_names(sub['class'])]
                    if sub['branch'] == selected_branch and selected_class.lower() in sub_class_norms and sub['name'].strip().lower() == selected_subject.strip().lower():
                        is_valid = True
                        break
                if not is_valid:
                    selected_branch = None
                    selected_class = None
                    selected_subject = None
                    assigned_class = None
                
        subject_names = []
        marks_dict = {}
        subject_oral_limit = {}
        subject_written_limit = {}
        subject_ct_limit = {}
        subjects_rows = []
        global_subjects = []
        
        if selected_branch and selected_class:
            db_classes = get_db_class_names(selected_class)
            placeholders = ', '.join('?' for _ in db_classes)

            global_subjects = conn.execute("SELECT id, name FROM subjects ORDER BY name").fetchall()

            # Fetch class-subject settings for this class and term
            subjects_rows = conn.execute(f"""
                SELECT DISTINCT subject_name AS name, full_marks, oral_limit, written_limit, ct_limit
                FROM class_subjects 
                WHERE class_name IN ({placeholders}) AND term_name = ?
                ORDER BY name
            """, db_classes + [selected_term]).fetchall()
            
            for r in subjects_rows:
                if r['name']:
                    name_norm = r['name'].strip().title()
                    is_ct_subj = name_norm.lower() in ['behaviour', 'work education', 'physical education', 'attendance', 'hand writing']
                    if is_ct_subj and selected_term != 'Final Exam':
                        continue
                        
                    subject_names.append(name_norm)
                    subject_full_marks[name_norm] = r['full_marks']
                    subject_oral_limit[name_norm] = r['oral_limit']
                    subject_written_limit[name_norm] = r['written_limit']
                    subject_ct_limit[name_norm] = r['ct_limit']
                    
            if role == 'teacher':
                allowed_filtered = []
                for x in allowed_subjects:
                    if x['class'].lower() in [c.lower() for c in db_classes]:
                        name_norm = x['name'].strip().title()
                        is_ct_subj = name_norm.lower() in ['behaviour', 'work education', 'physical education', 'attendance', 'hand writing']
                        if is_ct_subj and selected_term != 'Final Exam':
                            continue
                        if name_norm not in allowed_filtered:
                            allowed_filtered.append(name_norm)
                subject_names = [s for s in subject_names if s in allowed_filtered]
                
            subject_names = sorted(list(set(subject_names)))
            
            students = conn.execute(f'''
                SELECT u.id, u.username, si.full_name, si.roll_number, si.whatsapp_no 
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE si.branch = ? AND si.class IN ({placeholders})
                ORDER BY CAST(si.roll_number AS INTEGER)
            ''', [selected_branch] + db_classes).fetchall()
            
            # Fetch existing marks for these students and term
            marks_rows = conn.execute(f'''
                SELECT student_id, subject_name, obtained_marks, full_marks, oral_marks, written_marks, ct_marks, is_absent
                FROM marks 
                WHERE class_name IN ({placeholders}) AND term_name = ?
            ''', db_classes + [selected_term]).fetchall()
            
            for row in marks_rows:
                sid = row['student_id']
                if sid not in marks_dict:
                    marks_dict[sid] = {}
                sub_norm = row['subject_name'].strip().title() if row['subject_name'] else ''
                marks_dict[sid][sub_norm] = {
                    'obt': row['obtained_marks'],
                    'full': row['full_marks'],
                    'oral': row['oral_marks'],
                    'written': row['written_marks'],
                    'ct': row['ct_marks'],
                    'is_absent': row['is_absent'] or 0  # A2: absent flag
                }
            
        # Check if currently selected exam term is locked
        is_locked = False
        if selected_branch and selected_class and selected_term:
            is_locked_row = conn.execute("SELECT is_locked FROM exam_locks WHERE branch = ? AND class_name = ? AND term_name = ?", (selected_branch, selected_class, selected_term)).fetchone()
            is_locked = True if (is_locked_row and is_locked_row['is_locked'] == 1) else False

        all_terms = get_all_academic_terms(conn)
        active_classes = get_active_classes(conn)
        conn.close()
        
        return render_template('admin/bulk_marks.html', 
                               students=students, 
                               branches=BRANCHES, 
                               classes=active_classes,
                               selected_branch=selected_branch,
                               selected_class=selected_class,
                               selected_subject=selected_subject,
                               assigned_class=assigned_class,
                               allowed_subjects=allowed_subjects,
                               role=role,
                               subjects=subject_names,
                               marks_dict=marks_dict,
                               selected_term=selected_term,
                               full_marks=full_marks_val,
                               class_tests=class_test_names,
                               is_class_test=is_class_test,
                               all_terms=all_terms,
                               subject_full_marks=subject_full_marks,
                               subject_oral_limit=subject_oral_limit,
                               subject_written_limit=subject_written_limit,
                               subject_ct_limit=subject_ct_limit,
                               configured_class_test_subjects=configured_class_test_subjects,
                               is_locked=is_locked,
                               db_subjects=subjects_rows,
                               global_subjects=global_subjects)
    return redirect(url_for('home'))

@app.route('/admin/marks-setup', methods=['GET', 'POST'])
def marks_setup():
    class_name = request.args.get('class_name') or request.form.get('class_name')
    term_name = request.args.get('term_name') or request.form.get('term_name') or request.args.get('term') or request.form.get('term')
    
    params = {}
    if class_name:
        params['class'] = class_name
    if term_name:
        params['term'] = term_name
        
    return redirect(url_for('bulk_marks', **params))

@app.route('/admin/marks-entry', methods=['GET', 'POST'])
def marks_entry():
    class_name = request.args.get('class_name') or request.form.get('class_name')
    term_name = request.args.get('term_name') or request.form.get('term_name') or request.args.get('term') or request.form.get('term')
    
    params = {}
    if class_name:
        params['class'] = class_name
    if term_name:
        params['term'] = term_name
        
    return redirect(url_for('bulk_marks', **params))

@app.route('/admin/api/marks/bulk-save', methods=['POST'])
def save_marks_api():
    if 'user' not in session or session['role'] not in ['admin', 'teacher']:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    data = request.get_json()
    class_name = data.get('class_name')
    term_name = data.get('term_name')
    marks_data = data.get('marks') # [{'student_id': 1, 'subject_name': 'Math', 'obtained_marks': 45, 'full_marks': 50}, ...]

    if not class_name or not term_name or marks_data is None:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    # Normalize the term name internally to prevent duplicates / naming mismatches
    term_name = term_name.strip()
    if term_name in ['1st Term', '1st Unit']:
        term_name = '1st Unit'
    elif term_name in ['2nd Term', '2nd Unit']:
        term_name = '2nd Unit'
    elif term_name in ['Annual Exam', 'Final Exam', 'Annual']:
        term_name = 'Final Exam'
    else:
        term_name = normalize_monthly_test_name(term_name)

    # Get branch
    branch = data.get('branch')
    if not branch:
        if session.get('branch'):
            branch = session['branch']
        else:
            branch = 'bhogram'

    conn = get_db_connection()
    is_locked_row = conn.execute("SELECT is_locked FROM exam_locks WHERE branch = ? AND class_name = ? AND term_name = ?", (branch, class_name, term_name)).fetchone()
    if is_locked_row and is_locked_row['is_locked'] == 1:
        conn.close()
        return jsonify({'status': 'error', 'message': f"The exam '{term_name}' for class '{class_name}' is locked and cannot be edited."}), 403

    user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()

    try:
        for mark in marks_data:
            student_id = mark.get('student_id')
            subject_name = mark.get('subject_name')
            obt = mark.get('obtained_marks')
            full = mark.get('full_marks')

            if obt is None or obt == '' or full is None or full == '':
                continue # Skip partial entries

            try:
                obt = float(obt)
                full = float(full)
            except ValueError:
                continue # Skip invalid

            # B5 FIX: also accept and store oral/written/ct component marks
            oral_marks = mark.get('oral_marks')
            written_marks = mark.get('written_marks')
            ct_marks = mark.get('ct_marks')

            # Insert or update
            conn.execute('''
                INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, oral_marks, written_marks, ct_marks, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                    obtained_marks = excluded.obtained_marks,
                    full_marks = excluded.full_marks,
                    oral_marks = excluded.oral_marks,
                    written_marks = excluded.written_marks,
                    ct_marks = excluded.ct_marks,
                    uploaded_by = excluded.uploaded_by,
                    uploaded_at = CURRENT_TIMESTAMP
            ''', (student_id, class_name, term_name, subject_name, obt, full, oral_marks, written_marks, ct_marks, user['id']))

        conn.commit()
        send_activity_notification("API Mark Entry", f"Successfully saved {len(marks_data)} mark entries for Class {class_name}, Term {term_name} via API.")
        return jsonify({'status': 'success', 'message': 'Marks saved successfully.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/save-bulk-marks', methods=['POST'])
def save_bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        sync_and_normalize_monthly_tests(conn)
        
        selected_class = normalize_class_name(request.form.get('class'))
        selected_branch = session['branch'] if session.get('branch') else request.form.get('branch')
        selected_term = request.form.get('term', '1st Unit')
        
        # Normalize the term name internally to prevent duplicates / naming mismatches
        selected_term = selected_term.strip()
        if selected_term in ['1st Term', '1st Unit']:
            selected_term = '1st Unit'
        elif selected_term in ['2nd Term', '2nd Unit']:
            selected_term = '2nd Unit'
        elif selected_term in ['Annual Exam', 'Final Exam', 'Annual']:
            selected_term = 'Final Exam'
        else:
            selected_term = normalize_monthly_test_name(selected_term)
            
        full_marks_val = request.form.get('full_marks') or request.form.get('total_marks') or '100'
        
        # Check if the exam term is locked
        is_locked_row = conn.execute("SELECT is_locked FROM exam_locks WHERE branch = ? AND class_name = ? AND term_name = ?", (selected_branch, selected_class, selected_term)).fetchone()
        if is_locked_row and is_locked_row['is_locked'] == 1:
            flash(f"Error: The exam term '{selected_term}' for class '{selected_class}' is locked and cannot be edited.", 'error')
            conn.close()
            return redirect(url_for('bulk_marks', **{'branch': selected_branch, 'class': selected_class, 'term': selected_term}))
            
        try:
            full_marks = float(full_marks_val)
        except ValueError:
            flash('Invalid full marks value.', 'error')
            conn.close()
            return redirect(url_for('bulk_marks'))

        user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        subject_full_marks = {}
        subject_oral_limit = {}
        subject_written_limit = {}
        subject_ct_limit = {}

        # Populate subject_full_marks with values from database subjects table
        db_classes = get_db_class_names(selected_class)
        placeholders = ', '.join('?' for _ in db_classes)
        subjects_rows = conn.execute(f"""
            SELECT DISTINCT subject_name AS name, full_marks, oral_limit, written_limit, ct_limit
            FROM class_subjects 
            WHERE class_name IN ({placeholders}) AND term_name = ?
        """, db_classes + [selected_term]).fetchall()
        for r in subjects_rows:
            if r['name']:
                name_norm = r['name'].strip().title()
                # Exclude class-teacher subjects if not Final Exam
                is_ct_subj = name_norm.lower() in ['behaviour', 'work education', 'physical education', 'attendance', 'hand writing']
                if is_ct_subj and selected_term != 'Final Exam':
                    continue
                subject_full_marks[name_norm] = r['full_marks'] if r['full_marks'] is not None else 100.0
                subject_oral_limit[name_norm] = r['oral_limit']
                subject_written_limit[name_norm] = r['written_limit']
                subject_ct_limit[name_norm] = r['ct_limit']
        
        # Security check for teacher using parsed qualifications and assigned subjects
        allowed_subjects_list = []
        if session['role'] == 'teacher':
            allowed = get_teacher_allowed_subjects(conn, session['user'])
            allowed_subjects_list = [
                x['name'].strip().title() for x in allowed
                if x['branch'].lower() == selected_branch.lower() and x['class'].lower() == selected_class.lower()
            ]

        saved_count = 0
        
        def handle_error_redirect(error_msg):
            flash(error_msg, 'error')
            conn.close()
            redirect_args = {
                'branch': selected_branch,
                'class': selected_class,
                'term': selected_term,
                'full_marks': full_marks_val
            }
            if session['role'] == 'teacher':
                assigned_class = request.form.get('assigned_class')
                if assigned_class: redirect_args['assigned_class'] = assigned_class
            else:
                selected_subject = request.form.get('subject')
                if selected_subject: redirect_args['subject'] = selected_subject
            return redirect(url_for('bulk_marks', **redirect_args))

        # A3: Collect absent flags from form: absent_{student_id}_{subject}
        absent_entries = set()
        for key in request.form.keys():
            if key.startswith('absent_'):
                rest = key[len('absent_'):]
                parts = rest.split('_')
                if len(parts) >= 2:
                    sid = parts[0]
                    sub = '_'.join(parts[1:]).replace('_', ' ').strip().title()
                    absent_entries.add((sid, sub))

        # Collect all student_id and subject combinations from form keys
        entries = set()
        for key in request.form.keys():
            if key.startswith('marks_'):
                parts = key.split('_')
                if len(parts) >= 3:
                    student_id = parts[1]
                    subject_name = '_'.join(parts[2:]).replace('_', ' ').strip().title()
                    entries.add((student_id, subject_name))
            elif key.startswith('oral_marks_'):
                parts = key.split('_')
                if len(parts) >= 3:
                    student_id = parts[2]
                    subject_name = '_'.join(parts[3:]).replace('_', ' ').strip().title()
                    entries.add((student_id, subject_name))
            elif key.startswith('written_marks_'):
                parts = key.split('_')
                if len(parts) >= 3:
                    student_id = parts[2]
                    subject_name = '_'.join(parts[3:]).replace('_', ' ').strip().title()
                    entries.add((student_id, subject_name))
            elif key.startswith('ct_marks_'):
                parts = key.split('_')
                if len(parts) >= 3:
                    student_id = parts[2]
                    subject_name = '_'.join(parts[3:]).replace('_', ' ').strip().title()
                    entries.add((student_id, subject_name))
        # Also ensure absent entries get processed even if no mark inputs were submitted
        for (sid, sub) in absent_entries:
            entries.add((sid, sub))

        # Security check: verify that the student actually belongs to this branch and get student name mapping
        student_info_rows = conn.execute('''
            SELECT si.user_id, si.full_name, u.username 
            FROM student_info si 
            JOIN users u ON si.user_id = u.id 
            WHERE si.branch = ?
        ''', (selected_branch,)).fetchall()
        allowed_students = {str(row['user_id']) for row in student_info_rows}
        student_names = {str(row['user_id']): (row['full_name'] or row['username']) for row in student_info_rows}

        try:
            for student_id, subject_name in sorted(list(entries)):
                # If teacher, only let them save their assigned subjects
                if session['role'] == 'teacher' and subject_name not in allowed_subjects_list:
                    continue
                    
                # Block saving marks for unconfigured subjects
                if subject_name not in subject_full_marks:
                    continue
                    
                # Security check: verify that the student actually belongs to this branch
                if student_id not in allowed_students:
                    continue

                # A3: Handle absent flag — save as absent with zero marks
                is_absent = 1 if (student_id, subject_name) in absent_entries else 0
                if is_absent:
                    subject_fm = subject_full_marks.get(subject_name, 100.0)
                    conn.execute('''
                        INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, oral_marks, written_marks, ct_marks, is_absent, uploaded_by)
                        VALUES (?, ?, ?, ?, 0, ?, NULL, NULL, NULL, 1, ?)
                        ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                            obtained_marks = 0,
                            full_marks = excluded.full_marks,
                            oral_marks = NULL,
                            written_marks = NULL,
                            ct_marks = NULL,
                            is_absent = 1,
                            uploaded_by = excluded.uploaded_by,
                            uploaded_at = CURRENT_TIMESTAMP
                    ''', (student_id, selected_class, selected_term, subject_name, subject_fm, user['id']))
                    saved_count += 1
                    continue  # skip normal mark processing

                # Read component values from the request with robust space/underscore handling
                def get_form_val(prefix, student_id, subject_name):
                    val = request.form.get(f"{prefix}_{student_id}_{subject_name}")
                    if val is not None:
                        return val
                    sub_under = subject_name.replace(' ', '_')
                    return request.form.get(f"{prefix}_{student_id}_{sub_under}")

                oral_val = get_form_val('oral_marks', student_id, subject_name)
                written_val = get_form_val('written_marks', student_id, subject_name)
                ct_val = get_form_val('ct_marks', student_id, subject_name)
                obt_val = get_form_val('marks', student_id, subject_name)

                # Get limits
                oral_limit = subject_oral_limit.get(subject_name)
                written_limit = subject_written_limit.get(subject_name)
                ct_limit = subject_ct_limit.get(subject_name)
                subject_fm = subject_full_marks.get(subject_name, 100.0)

                # Check if all active components are empty (so we skip saving / delete existing)
                if oral_limit is not None or written_limit is not None or ct_limit is not None:
                    all_empty = True
                    if oral_limit is not None and oral_val is not None and str(oral_val).strip() != '':
                        all_empty = False
                    if written_limit is not None and written_val is not None and str(written_val).strip() != '':
                        all_empty = False
                    if ct_limit is not None and ct_val is not None and str(ct_val).strip() != '':
                        all_empty = False
                    if all_empty:
                        conn.execute("DELETE FROM marks WHERE student_id = ? AND class_name = ? AND term_name = ? AND subject_name = ?",
                                     (student_id, selected_class, selected_term, subject_name))
                        continue
                else:
                    if obt_val is None or str(obt_val).strip() == '':
                        conn.execute("DELETE FROM marks WHERE student_id = ? AND class_name = ? AND term_name = ? AND subject_name = ?",
                                     (student_id, selected_class, selected_term, subject_name))
                        continue

                def parse_input_val(val):
                    if val is None or str(val).strip() == '' or str(val).upper().strip() == 'AB':
                        return None
                    try:
                        return float(val)
                    except ValueError:
                        return None

                oral_marks = parse_input_val(oral_val)
                written_marks = parse_input_val(written_val)
                ct_marks = parse_input_val(ct_val)
                
                std_name = student_names.get(student_id, f"ID {student_id}")

                # If at least one component limit is active:
                if oral_limit is not None or written_limit is not None or ct_limit is not None:
                    # Validate each active component limit
                    if oral_limit is not None and oral_marks is not None and oral_marks > oral_limit:
                        return handle_error_redirect(f"Validation Error: Oral marks ({oral_marks}) exceed limit ({oral_limit:.1f}) for student '{std_name}' in subject '{subject_name}'.")
                    if written_limit is not None and written_marks is not None and written_marks > written_limit:
                        return handle_error_redirect(f"Validation Error: Written marks ({written_marks}) exceed limit ({written_limit:.1f}) for student '{std_name}' in subject '{subject_name}'.")
                    if ct_limit is not None and ct_marks is not None and ct_marks > ct_limit:
                        return handle_error_redirect(f"Validation Error: Class Test marks ({ct_marks}) exceed limit ({ct_limit:.1f}) for student '{std_name}' in subject '{subject_name}'.")
                    
                    # Sum the active components
                    obtained_marks = (oral_marks if (oral_limit is not None and oral_marks is not None) else 0.0) + \
                                     (written_marks if (written_limit is not None and written_marks is not None) else 0.0) + \
                                     (ct_marks if (ct_limit is not None and ct_marks is not None) else 0.0)
                else:
                    # No component limit is active: validate single raw obtained marks against subject full marks
                    obtained_marks = parse_input_val(obt_val)
                    if obtained_marks is not None and obtained_marks > subject_fm:
                        return handle_error_redirect(f"Validation Error: Obtained marks ({obtained_marks}) exceed Full Marks ({subject_fm}) for student '{std_name}' in subject '{subject_name}'.")

                conn.execute('''
                    INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, oral_marks, written_marks, ct_marks, is_absent, uploaded_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                        obtained_marks = excluded.obtained_marks,
                        full_marks = excluded.full_marks,
                        oral_marks = excluded.oral_marks,
                        written_marks = excluded.written_marks,
                        ct_marks = excluded.ct_marks,
                        is_absent = 0,
                        uploaded_by = excluded.uploaded_by,
                        uploaded_at = CURRENT_TIMESTAMP
                ''', (student_id, selected_class, selected_term, subject_name, obtained_marks, subject_fm, oral_marks, written_marks, ct_marks, user['id']))
                saved_count += 1
            
            conn.commit()
            if saved_count > 0:
                send_activity_notification("Mark Entry", f"Successfully saved {saved_count} mark entries for Class {selected_class}, Term {selected_term} in branch '{selected_branch}'.")
            flash(f'Successfully saved {saved_count} mark entries!')
        except Exception as e:
            conn.rollback()
            flash(f'Database error: {str(e)}', 'error')
        finally:
            conn.close()
            
        # Build redirect parameters to preserve active state
        redirect_args = {
            'branch': selected_branch,
            'class': selected_class,
            'term': selected_term,
            'full_marks': full_marks_val
        }
        if session['role'] == 'teacher':
            assigned_class = request.form.get('assigned_class')
            if assigned_class:
                redirect_args['assigned_class'] = assigned_class
        else:
            selected_subject = request.form.get('subject')
            if selected_subject:
                redirect_args['subject'] = selected_subject

        return redirect(url_for('bulk_marks', **redirect_args))
    return redirect(url_for('home'))

@app.route('/upload', methods=['POST'])
def upload_file():
    user = get_session_user()
    if not user:
        flash('Please login to upload files.')
        return redirect(url_for('login', user_type='student', next=request.path))

    file = request.files.get('file')
    branch = request.form.get('branch')
    category = request.form.get('category')

    if not file or file.filename == '':
        flash('Please select a file to upload.')
        return redirect(url_for('dashboard'))

    if branch not in BRANCHES or category not in CATEGORIES:
        flash('Please select a valid branch and upload type.')
        return redirect(url_for('dashboard'))

    filename = secure_filename(file.filename)
    if not filename:
        flash('Invalid filename.')
        return redirect(url_for('dashboard'))

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    saved_name = f"{timestamp}_{filename}"

    if user['role'] == 'admin':
        target_folder = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
        os.makedirs(target_folder, exist_ok=True)
        local_path = os.path.join(target_folder, saved_name)
        file.save(local_path)
        
        drive_file_id = upload_file_to_drive_and_map(local_path, saved_name, file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_GALLERY'))
        
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO pending_media (user_id, branch, category, filename, status, drive_file_id) VALUES (?, ?, ?, ?, 'Approved', ?)",
            (user['id'], branch, category, saved_name, drive_file_id)
        )
        conn.commit()
        conn.close()
        
        if drive_file_id:
            flash(f'{branch.title()} {category} uploaded directly to Google Drive successfully.')
        else:
            flash(f'{branch.title()} {category} uploaded successfully (local storage).')
    else:
        temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        os.makedirs(temp_folder, exist_ok=True)
        file.save(os.path.join(temp_folder, saved_name))
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO pending_media (user_id, branch, category, filename, status) VALUES (?, ?, ?, ?, 'Pending')",
            (user['id'], branch, category, saved_name)
        )
        conn.commit()
        conn.close()
        flash('Upload submitted for admin approval.')

    send_activity_notification("Gallery Upload", f"File '{filename}' (saved as '{saved_name}') uploaded for branch '{branch}', category '{category}' (status: {'Approved' if user['role'] == 'admin' else 'Pending'}).")

    return redirect(url_for('dashboard'))


@app.route('/admin/force-sync-all', methods=['GET'])
def force_sync_all():
    if 'user' not in session or session['role'] != 'admin':
        return "Unauthorized", 403
    conn = get_db_connection()
    students = conn.execute("SELECT user_id, branch, class FROM student_info").fetchall()
    
    # Get global max
    max_month = conn.execute("SELECT MAX(month_end_billing_count) FROM student_info").fetchone()[0] or 0
    max_year = conn.execute("SELECT MAX(year_end_billing_count) FROM student_info").fetchone()[0] or 0
    
    for student in students:
        s_id = student['user_id']
        s_dict = dict(conn.execute("SELECT * FROM student_info WHERE user_id = ?", (s_id,)).fetchone())
        
        # update their monthly_fee to actual base fee - financial aid
        bd = calculate_student_fees_breakdown(s_dict, conn)
        new_monthly = bd['total_fee']
        conn.execute("UPDATE student_info SET monthly_fee = ?, is_custom_fee = 0 WHERE user_id = ?", (new_monthly, s_id))
        
        # Sync ledger to recalculate expected remaining fee based on new monthly fee
        sync_student_ledger_and_dues(conn, s_id, max_month_end=max_month, max_year_end=max_year)
    
    conn.commit()
    conn.close()
    return "Successfully recalculated and synced all student fees to remove 1000 custom overrides."

@app.route('/admin/get-fees', methods=['GET', 'POST'])
def get_fees():
    if 'user' in session:
        conn = get_db_connection()
        role = session['role']
        username = session['user']

        if role in ['admin', 'teacher']:
            if request.method == 'POST':
                student_id = request.form['student_id']
                amount = request.form['amount']
                month = request.form['month']
                year = request.form['year']
                
                # Check permissions for Branch Admin
                if session.get('branch'):
                    student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                    if not student or student['branch'] != session['branch']:
                        conn.close()
                        flash('Permission denied: Student does not belong to your campus.')
                        return redirect(url_for('get_fees'))

                school_rev, hostel_rev, coaching_rev, tax_amt, readmission_rev, e_type = allocate_payment_components(conn, student_id, amount)

                conn.execute('''
                    INSERT INTO fees (student_id, amount, month, year, status, paid_at, school_revenue, hostel_revenue, coaching_revenue, tax_amount, readmission_revenue, enrollment_type)
                    VALUES (?, ?, ?, ?, 'Paid', CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
                ''', (student_id, amount, month, year, school_rev, hostel_rev, coaching_rev, tax_amt, readmission_rev, e_type))
                
                record_ledger_payment(conn, student_id, amount)
                
                conn.commit()
                send_activity_notification("Fee Collection", f"Collected fee of ₹{amount} for student ID {student_id} (Month: {month}, Year: {year}).")
                flash('Fee collected successfully!')
                conn.close()
                return redirect(url_for('get_fees'))

            if session.get('branch'):
                students_raw = conn.execute('''
                    SELECT u.id, u.username, si.*
                    FROM users u 
                    LEFT JOIN student_info si ON u.id = si.user_id 
                    WHERE u.role = 'student' AND si.branch = ?
                ''', (session['branch'],)).fetchall()
                recent_fees = conn.execute('''
                    SELECT f.*, u.username as student_name 
                    FROM fees f 
                    JOIN users u ON f.student_id = u.id 
                    JOIN student_info si ON u.id = si.user_id
                    WHERE si.branch = ?
                    ORDER BY f.paid_at DESC
                ''', (session['branch'],)).fetchall()
            else:
                students_raw = conn.execute('''
                    SELECT u.id, u.username, si.*
                    FROM users u 
                    LEFT JOIN student_info si ON u.id = si.user_id 
                    WHERE u.role = 'student'
                ''').fetchall()
                recent_fees = conn.execute('''
                    SELECT f.*, u.username as student_name 
                    FROM fees f 
                    JOIN users u ON f.student_id = u.id 
                    ORDER BY f.paid_at DESC
                ''').fetchall()
            students = resolve_student_default_fees(students_raw, conn)
            conn.close()
            return render_template('admin/get_fees.html', students=students, recent_fees=recent_fees, role=role)
        
        elif role == 'student':
            my_fees = conn.execute('''
                SELECT f.*, u.username as student_name 
                FROM fees f 
                JOIN users u ON f.student_id = u.id 
                WHERE u.username = ?
                ORDER BY f.paid_at DESC
            ''', (username,)).fetchall()
            
            student_info = conn.execute('''
                SELECT si.*
                FROM student_info si
                JOIN users u ON si.user_id = u.id
                WHERE u.username = ?
            ''', (username,)).fetchone()
            
            if student_info:
                student_info_dict = resolve_student_default_fees([student_info], conn)[0]
                if student_info_dict.get('monthly_fee') is None:
                    student_info_dict['monthly_fee'] = 0.0
                if student_info_dict.get('hostel_fee') is None:
                    student_info_dict['hostel_fee'] = 0.0
                if student_info_dict.get('remaining_fee') is None:
                    student_info_dict['remaining_fee'] = 0.0
            else:
                student_info_dict = {'monthly_fee': 0.0, 'hostel_fee': 0.0, 'branch': '', 'remaining_fee': 0.0}
            
            conn.close()
            return render_template(
                'admin/get_fees.html',
                recent_fees=my_fees,
                role=role,
                student_info=student_info_dict,
                razorpay_key_id=RAZORPAY_KEY_ID,
                username=username,
                email='',
                logo_url=LOGO_URL
            )
            
    return redirect(url_for('home'))

@app.route('/admin/api/student-ledger/<int:student_id>')
@login_required
def api_student_ledger(student_id):
    if session.get('role') not in ['admin', 'teacher']:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    if session.get('branch'):
        student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
        if not student or student['branch'] != session['branch']:
            conn.close()
            return jsonify({'error': 'Unauthorized branch'}), 403
            
    ledger = conn.execute("SELECT id, fee_type, amount, month, year, status, created_at, paid_at FROM student_ledger WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()
    ledger_data = [dict(r) for r in ledger]
    conn.close()
    return jsonify({'ledger': ledger_data})

@app.route('/admin/edit-ledger-entry/<int:entry_id>', methods=['POST'])
@login_required
def edit_ledger_entry(entry_id):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        
    fee_type = request.form.get('fee_type', '').strip()
    try:
        new_amount = float(request.form.get('amount', 0))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid amount'}), 400
        
    conn = get_db_connection()
    entry = conn.execute("SELECT * FROM student_ledger WHERE id = ?", (entry_id,)).fetchone()
    
    if not entry:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Entry not found'}), 404
        
    if entry['status'] == 'Paid':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Cannot edit paid entries'}), 400

    old_amount = float(entry['amount'])
    student_id = entry['student_id']
    
    # Only adjust prev_dues if it's a manual entry type (not a core system generated type)
    core_types = ['Monthly Tuition Fee', 'Monthly Coaching Fee', 'Monthly Hostel Fee', 'Monthly Transport Fee', 'Re-admission Fee']
    
    if entry['fee_type'] not in core_types:
        diff = new_amount - old_amount
        if diff != 0:
            student = conn.execute("SELECT prev_dues FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
            if student:
                new_prev = float(student['prev_dues'] or 0.0) + diff
                conn.execute("UPDATE student_info SET prev_dues = ? WHERE user_id = ?", (new_prev, student_id))
    
    conn.execute("UPDATE student_ledger SET fee_type = ?, amount = ? WHERE id = ?", (fee_type, new_amount, entry_id))
    
    # Sync to ensure total dues is updated
    sync_student_ledger_and_dues(conn, student_id)
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Ledger entry updated'})

@app.route('/admin/delete-ledger-entry/<int:entry_id>', methods=['POST'])
@login_required
def delete_ledger_entry(entry_id):
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
        
    conn = get_db_connection()
    entry = conn.execute("SELECT * FROM student_ledger WHERE id = ?", (entry_id,)).fetchone()
    
    if not entry:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Entry not found'}), 404
        
    if entry['status'] == 'Paid':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Cannot delete paid entries'}), 400

    student_id = entry['student_id']
    amount = float(entry['amount'])
    
    core_types = ['Monthly Tuition Fee', 'Monthly Coaching Fee', 'Monthly Hostel Fee', 'Monthly Transport Fee', 'Re-admission Fee']
    
    if entry['fee_type'] not in core_types:
        student = conn.execute("SELECT prev_dues FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
        if student:
            new_prev = float(student['prev_dues'] or 0.0) - amount
            conn.execute("UPDATE student_info SET prev_dues = ? WHERE user_id = ?", (new_prev, student_id))
            
    conn.execute("DELETE FROM student_ledger WHERE id = ?", (entry_id,))
    
    sync_student_ledger_and_dues(conn, student_id)
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Ledger entry deleted'})


@app.route('/admin/delete-fee/<int:fee_id>', methods=['POST'])
def delete_fee(fee_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        fee = conn.execute('''
            SELECT f.*, si.branch 
            FROM fees f
            JOIN users u ON f.student_id = u.id
            JOIN student_info si ON u.id = si.user_id
            WHERE f.id = ?
        ''', (fee_id,)).fetchone()
        
        if not fee:
            conn.close()
            flash('Fee record not found.')
            return redirect(url_for('get_fees'))
            
        # Check branch permission if branch admin
        if session.get('branch'):
            if fee['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: Student belongs to another campus.')
                return redirect(url_for('get_fees'))
                
        conn.execute("DELETE FROM fees WHERE id = ?", (fee_id,))
        conn.execute('''
            UPDATE student_info
            SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
            WHERE user_id = ?
        ''', (float(fee['amount']), fee['student_id']))
        
        conn.commit()
        conn.close()
        flash('Fee record deleted successfully!')
    else:
        flash('Access denied.')
    return redirect(url_for('get_fees'))

@app.route('/create_order', methods=['POST'])
@login_required
def create_order():
    if session.get('role') != 'student':
        return {'error': 'Only students can make online fee payments.'}, 403

    client = get_razorpay_client()
    if not client:
        return {'error': 'Online payment is not configured. Please contact admin.'}, 503

    data = request.get_json(silent=True) or {}
    try:
        amount_rupees = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return {'error': 'Please enter a valid amount.'}, 400

    month = str(data.get('month') or datetime.now().strftime('%B')).strip()
    if amount_rupees <= 0:
        return {'error': 'Please enter a valid amount.'}, 400

    user = get_session_user()
    amount_paise = int(round(amount_rupees * 100))
    receipt = f"fee_{user['id']}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    try:
        order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': receipt,
            'payment_capture': 1,
            'notes': {
                'student_id': str(user['id']),
                'month': month
            }
        })
    except Exception as exc:
        print(f"Razorpay order creation failed: {exc}")
        return {'error': 'Could not initialize online payment. Please try again later.'}, 502

    session['pending_fee_payment'] = {
        'student_id': user['id'],
        'amount': amount_rupees,
        'month': month,
        'order_id': order['id']
    }

    return {
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order.get('currency', 'INR')
    }

@app.route('/verify_payment', methods=['POST'])
@login_required
def verify_payment():
    if session.get('role') != 'student':
        return {'status': 'error', 'message': 'Only students can verify fee payments.'}, 403

    client = get_razorpay_client()
    if not client:
        return {'status': 'error', 'message': 'Online payment is not configured.'}, 503

    data = request.get_json(silent=True) or {}
    pending = session.get('pending_fee_payment') or {}
    required = ['razorpay_payment_id', 'razorpay_order_id', 'razorpay_signature']
    if any(not data.get(key) for key in required):
        return {'status': 'error', 'message': 'Missing payment verification details.'}, 400
    if data['razorpay_order_id'] != pending.get('order_id'):
        return {'status': 'error', 'message': 'Payment order does not match this session.'}, 400

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })
    except Exception:
        return {'status': 'error', 'message': 'Payment verification failed.'}, 400

    student_id = pending.get('student_id')
    amount = pending.get('amount')
    month = pending.get('month') or datetime.now().strftime('%B')
    year = datetime.now().strftime('%Y')

    conn = get_db_connection()
    school_rev, hostel_rev, coaching_rev, tax_amt, readmission_rev, e_type = allocate_payment_components(conn, student_id, amount)
    conn.execute('''
        INSERT INTO fees (student_id, amount, month, year, status, paid_at, school_revenue, hostel_revenue, coaching_revenue, tax_amount, readmission_revenue, enrollment_type)
        VALUES (?, ?, ?, ?, 'Paid', CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
    ''', (student_id, amount, month, year, school_rev, hostel_rev, coaching_rev, tax_amt, readmission_rev, e_type))
    
    record_ledger_payment(conn, student_id, amount)
    
    conn.commit()
    conn.close()
    session.pop('pending_fee_payment', None)

    return {'status': 'success'}

@app.route('/admin/set-fees', methods=['GET', 'POST'])
def set_fees():
    if 'user' not in session or session['role'] not in ['admin', 'teacher']:
        return redirect(url_for('login'))
        
    branch = session.get('branch')
    if not branch:
        branch = 'bhogram'
        
    if request.args.get('branch') and session['role'] == 'admin':
        branch = request.args.get('branch')
        
    conn = get_db_connection()
    db_classes = [dict(row) for row in conn.execute("SELECT * FROM classes WHERE LOWER(branch) = LOWER(?) ORDER BY id", (branch,)).fetchall()]
    
    # Make sure classes are unique names
    seen = set()
    classes = []
    for c in db_classes:
        if c['name'] not in seen:
            seen.add(c['name'])
            classes.append(c['name'])
    
    custom_fees = conn.execute("SELECT * FROM custom_class_fees WHERE branch = ? ORDER BY created_at DESC", (branch,)).fetchall()
    
    students_raw = conn.execute('''
        SELECT u.id, u.username, si.*
        FROM users u 
        LEFT JOIN student_info si ON u.id = si.user_id 
        WHERE u.role = 'student' AND LOWER(si.branch) = LOWER(?)
    ''', (branch,)).fetchall()
    
    conn.close()
    
    return render_template('admin/set_fees.html', 
                           role=session['role'], 
                           branch_filter=branch,
                           classes=classes,
                           db_classes=db_classes,
                           custom_fees=custom_fees,
                           students=students_raw)

@app.route('/admin/bulk-custom-fee', methods=['POST'])
def bulk_custom_fee():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    branch = request.form.get('branch', 'bhogram')
    class_name = request.form.get('class_name')
    fee_type = request.form.get('fee_type')
    amount = request.form.get('due_amount')
    
    filter_school = request.form.get('filter_take_school') == '1'
    filter_coaching = request.form.get('filter_take_coaching') == '1'
    filter_day_hostel = request.form.get('filter_take_day_hostel') == '1'
    filter_car = request.form.get('filter_take_car') == '1'
    
    if not class_name or not fee_type or not amount:
        flash("All fields are required.")
        return redirect(url_for('set_fees'))
        
    try:
        amount = float(amount)
        conn = get_db_connection()
        
        # 1. Add to custom_class_fees table
        conn.execute("INSERT INTO custom_class_fees (branch, class_name, fee_type, amount) VALUES (?, ?, ?, ?)",
                     (branch, class_name, fee_type, amount))
                     
        # 2. Get all students in this class, applying filters if selected
        query = '''
            SELECT u.id, si.prev_dues 
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE u.role='student' AND si.class=? AND si.branch=?
        '''
        params = [class_name, branch]
        
        if filter_school:
            query += " AND si.take_school = 1"
        if filter_coaching:
            query += " AND si.take_coaching = 1"
        if filter_day_hostel:
            query += " AND si.take_day_hostel = 1"
        if filter_car:
            query += " AND si.take_car = 1"
            
        students = conn.execute(query, params).fetchall()
        
        for student in students:
            # 3. Add to ledger
            conn.execute('''
                INSERT INTO student_ledger (student_id, fee_type, amount, status, month, year, branch)
                VALUES (?, ?, ?, 'Unpaid/Pending', ?, ?, ?)
            ''', (student['id'], fee_type, amount, datetime.now().strftime('%B'), datetime.now().year, branch))
            
            # 4. Update student dues directly without running the destructive sync
            conn.execute('''
                UPDATE student_info 
                SET prev_dues = COALESCE(prev_dues, 0.0) + ?,
                    remaining_fee = COALESCE(remaining_fee, 0.0) + ?
                WHERE user_id = ?
            ''', (amount, amount, student['id']))

        conn.commit()
        conn.close()
        flash(f"Successfully added '{fee_type}' of ₹{amount} to all students in {class_name}.")
    except Exception as e:
        flash(f"An error occurred: {str(e)}")
        
    return redirect(url_for('set_fees'))

@app.route('/admin/set-salary', methods=['GET', 'POST'])
def set_salary():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        if request.method == 'POST':
            recipient_type = request.form.get('recipient_type', 'teacher')
            recipient_id = request.form.get('recipient_id')
            amount = request.form['amount']
            remaining_salary = request.form.get('remaining_salary', 0.0)
            
            # Check permissions if branch admin
            if session.get('branch'):
                if recipient_type == 'teacher':
                    member = conn.execute("SELECT branch FROM users WHERE id = ?", (recipient_id,)).fetchone()
                else:
                    member = conn.execute("SELECT branch FROM staff WHERE id = ?", (recipient_id,)).fetchone()
                if member and member['branch'] != session['branch']:
                    conn.close()
                    flash("Permission denied: Recipient belongs to another campus.")
                    return redirect(url_for('set_salary'))
            
            if recipient_type == 'teacher':
                conn.execute('''
                    UPDATE teacher_info 
                    SET salary = ?, remaining_salary = ? 
                    WHERE user_id = ?
                ''', (amount, remaining_salary, recipient_id))
            elif recipient_type == 'staff':
                conn.execute('''
                    UPDATE staff 
                    SET salary = ?, remaining_salary = ? 
                    WHERE id = ?
                ''', (amount, remaining_salary, recipient_id))
                
            conn.commit()
            conn.close()
            flash(f'Successfully updated salary to ₹{amount} and remaining salary to ₹{remaining_salary}')
            return redirect(url_for('set_salary'))
            
        if session.get('branch'):
            teachers = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.salary, ti.remaining_salary 
                FROM users u 
                JOIN teacher_info ti ON u.id = ti.user_id 
                WHERE u.role = 'teacher' AND u.branch = ?
                ORDER BY COALESCE(ti.full_name, u.username)
            ''', (session['branch'],)).fetchall()
            
            staff_list = conn.execute('''
                SELECT id, full_name, staff_type, salary, remaining_salary, branch
                FROM staff
                WHERE branch = ?
                ORDER BY full_name
            ''', (session['branch'],)).fetchall()
        else:
            teachers = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.salary, ti.remaining_salary 
                FROM users u 
                JOIN teacher_info ti ON u.id = ti.user_id 
                WHERE u.role = 'teacher'
                ORDER BY COALESCE(ti.full_name, u.username)
            ''').fetchall()
            
            staff_list = conn.execute('''
                SELECT id, full_name, staff_type, salary, remaining_salary, branch
                FROM staff
                ORDER BY full_name
            ''').fetchall()
            
        conn.close()
        logo_url = LOGO_URL
        return render_template('admin/set_salary.html', teachers=teachers, staff_list=staff_list, role=session['role'], logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/give-salary', methods=['GET', 'POST'])
def give_salary():
    if 'user' in session and session['role'] == 'admin':
        role = session['role']
        conn = get_db_connection()
        
        if request.method == 'POST':
            recipient_type = request.form.get('recipient_type', 'teacher')
            recipient_id = request.form['recipient_id']
            amount = request.form['amount']
            month = request.form['month']
            year = request.form['year']
            description = request.form.get('description', '')
            
            # Fetch recipient branch
            if recipient_type == 'teacher':
                member = conn.execute("SELECT branch FROM users WHERE id = ?", (recipient_id,)).fetchone()
            else:
                member = conn.execute("SELECT branch FROM staff WHERE id = ?", (recipient_id,)).fetchone()
            branch = member['branch'] if member else (session['branch'] if session.get('branch') else 'bhogram')
            
            # Check permissions for Branch Admin
            if session.get('branch') and branch != session['branch']:
                conn.close()
                flash('Permission denied: Recipient does not belong to your campus.')
                return redirect(url_for('give_salary'))

            # Handle proof upload
            proof_file = request.files.get('proof')
            proof_path = None
            if proof_file and proof_file.filename != '':
                filename = secure_filename(proof_file.filename)
                if filename:
                    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
                    saved_name = f"{timestamp}_{filename}"
                    proofs_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'proofs')
                    os.makedirs(proofs_folder, exist_ok=True)
                    local_path = os.path.join(proofs_folder, saved_name)
                    proof_file.save(local_path)
                    upload_file_to_drive_and_map(local_path, saved_name, proof_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_PROOFS'), conn=conn)
                    proof_path = saved_name

            # Log as a Salary category expense
            desc_with_month = f"{description} (Salary for {month} {year})".strip()
            conn.execute('''
                INSERT INTO expenses (amount, category, description, branch, proof_path, recipient_type, recipient_id)
                VALUES (?, 'Salary', ?, ?, ?, ?, ?)
            ''', (amount, desc_with_month, branch, proof_path, recipient_type, recipient_id))

            # Deduct from recipient's remaining salary
            if recipient_type == 'teacher':
                conn.execute('''
                    UPDATE teacher_info
                    SET remaining_salary = CASE 
                        WHEN COALESCE(remaining_salary, 0.0) - ? < 0 THEN 0.0 
                        ELSE COALESCE(remaining_salary, 0.0) - ? 
                    END
                    WHERE user_id = ?
                ''', (float(amount), float(amount), recipient_id))
            elif recipient_type == 'staff':
                conn.execute('''
                    UPDATE staff
                    SET remaining_salary = CASE 
                        WHEN COALESCE(remaining_salary, 0.0) - ? < 0 THEN 0.0 
                        ELSE COALESCE(remaining_salary, 0.0) - ? 
                    END
                    WHERE id = ?
                ''', (float(amount), float(amount), recipient_id))

            conn.commit()
            send_activity_notification("Salary Disbursed", f"Disbursed salary of ₹{amount} to {recipient_type} ID {recipient_id} (Month: {month}, Year: {year}).")
            flash('Salary disbursed successfully!')
            conn.close()
            return redirect(url_for('give_salary'))

        # GET request: fetch list of teachers, staff and recent salary payments
        if session.get('branch'):
            teachers = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.salary, ti.remaining_salary, u.branch
                FROM users u
                JOIN teacher_info ti ON u.id = ti.user_id
                WHERE u.role = 'teacher' AND u.branch = ?
                ORDER BY COALESCE(ti.full_name, u.username)
            ''', (session['branch'],)).fetchall()
            
            staff_list = conn.execute('''
                SELECT id, full_name, staff_type, salary, remaining_salary, branch
                FROM staff
                WHERE branch = ?
                ORDER BY full_name
            ''', (session['branch'],)).fetchall()
            
            recent_salaries = conn.execute('''
                SELECT e.*, 
                       CASE WHEN e.recipient_type = 'teacher' THEN COALESCE(ti.full_name, u.username)
                            ELSE s.full_name 
                       END as recipient_name
                FROM expenses e
                LEFT JOIN users u ON e.recipient_id = u.id AND e.recipient_type = 'teacher'
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                LEFT JOIN staff s ON e.recipient_id = s.id AND e.recipient_type = 'staff'
                WHERE e.category = 'Salary' AND e.branch = ?
                ORDER BY e.date DESC
            ''', (session['branch'],)).fetchall()
        else:
            teachers = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.salary, ti.remaining_salary, u.branch
                FROM users u
                JOIN teacher_info ti ON u.id = ti.user_id
                WHERE u.role = 'teacher'
                ORDER BY COALESCE(ti.full_name, u.username)
            ''').fetchall()
            
            staff_list = conn.execute('''
                SELECT id, full_name, staff_type, salary, remaining_salary, branch
                FROM staff
                ORDER BY full_name
            ''').fetchall()
            
            recent_salaries = conn.execute('''
                SELECT e.*, 
                       CASE WHEN e.recipient_type = 'teacher' THEN COALESCE(ti.full_name, u.username)
                            ELSE s.full_name 
                       END as recipient_name
                FROM expenses e
                LEFT JOIN users u ON e.recipient_id = u.id AND e.recipient_type = 'teacher'
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                LEFT JOIN staff s ON e.recipient_id = s.id AND e.recipient_type = 'staff'
                WHERE e.category = 'Salary'
                ORDER BY e.date DESC
            ''').fetchall()

        conn.close()
        logo_url = LOGO_URL
        return render_template('admin/give_salary.html', teachers=teachers, staff_list=staff_list, recent_salaries=recent_salaries, role=role, logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/reminder-fees')
def reminder_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        from datetime import datetime
        month = datetime.now().strftime('%B')
        year = datetime.now().strftime('%Y')
        
        if session.get('branch'):
            pending_students = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.phone_number, si.whatsapp_no, si.class, si.guardian_name,
                       si.monthly_fee, si.hostel_fee, si.remaining_fee
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND LOWER(si.branch) = LOWER(?)
                AND u.id NOT IN (SELECT student_id FROM fees WHERE month = ? AND year = ?)
            ''', (session['branch'], month, year)).fetchall()
        else:
            pending_students = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.phone_number, si.whatsapp_no, si.class, si.guardian_name,
                       si.monthly_fee, si.hostel_fee, si.remaining_fee
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' 
                AND u.id NOT IN (SELECT student_id FROM fees WHERE month = ? AND year = ?)
            ''', (month, year)).fetchall()
        conn.close()
        return render_template('admin/reminder_fees.html', students=pending_students, month=month)
    return redirect(url_for('home'))

@app.route('/admin/spend', methods=['GET', 'POST'])
def spend():
    if 'user' in session and session['role'] == 'admin':
        role = session['role']
        conn = get_db_connection()
        
        if request.method == 'POST':
            amount = request.form['amount']
            category = request.form['category']
            description = request.form['description']
            branch = session['branch'] if session.get('branch') else request.form.get('branch')
            
            # Handle proof upload
            proof_file = request.files.get('proof')
            proof_path = None
            if proof_file and proof_file.filename != '':
                filename = secure_filename(proof_file.filename)
                if filename:
                    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
                    saved_name = f"{timestamp}_{filename}"
                    proofs_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'proofs')
                    os.makedirs(proofs_folder, exist_ok=True)
                    local_path = os.path.join(proofs_folder, saved_name)
                    proof_file.save(local_path)
                    upload_file_to_drive_and_map(local_path, saved_name, proof_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_PROOFS'), conn=conn)
                    proof_path = saved_name
            
            conn.execute('''
                INSERT INTO expenses (amount, category, description, branch, proof_path, recipient_type, recipient_id)
                VALUES (?, ?, ?, ?, ?, NULL, NULL)
            ''', (amount, category, description, branch, proof_path))
            
            conn.commit()
            send_activity_notification("Spend/Expense Recorded", f"Recorded expense of ₹{amount} under category '{category}' for branch '{branch}'. Description: {description}")
            flash('Expense recorded!')
            conn.close()
            return redirect(url_for('spend'))

        if session.get('branch'):
            expenses = conn.execute("SELECT * FROM expenses WHERE branch = ? ORDER BY date DESC", (session['branch'],)).fetchall()
        else:
            expenses = conn.execute("SELECT * FROM expenses ORDER BY date DESC").fetchall()
            
        all_teachers_lookup = {t['id']: t['full_name'] or t['username'] for t in conn.execute("SELECT u.id, u.username, ti.full_name FROM users u JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher'").fetchall()}
        all_staff_lookup = {s['id']: s['full_name'] for s in conn.execute("SELECT id, full_name FROM staff").fetchall()}
        
        expenses_with_recipients = []
        for e in expenses:
            e_dict = dict(e)
            e_dict['recipient_name'] = None
            if e_dict.get('recipient_type') == 'teacher':
                e_dict['recipient_name'] = all_teachers_lookup.get(e_dict.get('recipient_id'), 'Unknown Teacher')
            elif e_dict.get('recipient_type') == 'staff':
                e_dict['recipient_name'] = all_staff_lookup.get(e_dict.get('recipient_id'), 'Unknown Staff')
            expenses_with_recipients.append(e_dict)
            
        conn.close()
        logo_url = LOGO_URL
        return render_template('admin/spend.html', expenses=expenses_with_recipients, role=role, logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/delete-expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        expense = conn.execute("SELECT amount, category, branch, proof_path, recipient_type, recipient_id FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not expense:
            conn.close()
            flash('Expense not found.')
            return redirect(url_for('spend'))
            
        # Check branch permission if branch admin
        if session.get('branch'):
            if expense['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: Expense belongs to another campus.')
                return redirect(url_for('spend'))
                
        if expense['proof_path']:
            delete_old_mapped_file(expense['proof_path'])
            
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        
        if expense['category'] == 'Salary' and expense['recipient_id']:
            if expense['recipient_type'] == 'teacher':
                conn.execute('''
                    UPDATE teacher_info
                    SET remaining_salary = COALESCE(remaining_salary, 0.0) + ?
                    WHERE user_id = ?
                ''', (float(expense['amount']), expense['recipient_id']))
            elif expense['recipient_type'] == 'staff':
                conn.execute('''
                    UPDATE staff
                    SET remaining_salary = COALESCE(remaining_salary, 0.0) + ?
                    WHERE id = ?
                ''', (float(expense['amount']), expense['recipient_id']))
            
        conn.commit()
        send_activity_notification("Delete Spend/Expense", f"Deleted expense record ID {expense_id} (amount: ₹{expense['amount']}, category: '{expense['category']}', branch: '{expense['branch']}').")
        conn.close()
        flash('Expense deleted successfully!')
    else:
        flash('Access denied.')
        
    referrer = request.referrer
    if referrer and 'give-salary' in referrer:
        return redirect(url_for('give_salary'))
    return redirect(url_for('spend'))

@app.route('/admin/audit-report')
def audit_report():
    if 'user' in session and session['role'] == 'admin':
        role = session['role']
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        # Parse query params
        take_school = request.args.get('take_school')
        take_coaching = request.args.get('take_coaching')
        take_day_hostel = request.args.get('take_day_hostel')
        take_car = request.args.get('take_car')
        time_range = request.args.get('time_range', '').strip().lower()
        if time_range not in ('day', 'week', 'month', 'year', 'all'):
            time_range = 'all'
            
        # Build SQL where clauses
        student_where = []
        student_params = []
        
        fees_where = []
        fees_params = []
        
        if session.get('branch'):
            student_where.append("si.branch = ? COLLATE NOCASE")
            student_params.append(session['branch'])
            fees_where.append("si.branch = ? COLLATE NOCASE")
            fees_params.append(session['branch'])
            
        benefit_conditions = []
        if take_school:
            benefit_conditions.append("si.take_school = 1")
        if take_coaching:
            benefit_conditions.append("si.take_coaching = 1")
        if take_day_hostel:
            benefit_conditions.append("si.take_day_hostel = 1")
        if take_car:
            benefit_conditions.append("si.take_car = 1")
            
        if benefit_conditions:
            benefit_clause = "(" + " OR ".join(benefit_conditions) + ")"
            student_where.append(benefit_clause)
            fees_where.append(benefit_clause)
            
        # Time range clauses
        date_clause = None
        
        filter_year = request.args.get('filter_year', '').strip()
        filter_month = request.args.get('filter_month', '').strip()

        if filter_year and filter_month:
            date_clause = f"strftime('%Y-%m', {{col}}) = '{filter_year}-{filter_month}'"
        elif filter_year:
            date_clause = f"strftime('%Y', {{col}}) = '{filter_year}'"
        elif filter_month:
            date_clause = f"strftime('%m', {{col}}) = '{filter_month}'"
        else:
            if time_range == 'day':
                date_clause = "DATE({col}) = DATE('now', 'localtime')"
            elif time_range == 'week':
                date_clause = "strftime('%Y-%W', {col}) = strftime('%Y-%W', 'now', 'localtime')"
            elif time_range == 'month':
                date_clause = "strftime('%Y-%m', {col}) = strftime('%Y-%m', 'now', 'localtime')"
            elif time_range == 'year':
                date_clause = "strftime('%Y', {col}) = strftime('%Y', 'now', 'localtime')"
            
        if date_clause:
            fees_where.append(date_clause.format(col="f.paid_at"))

        # Fetch available years for filter
        years_query = conn.execute('''
            SELECT DISTINCT strftime('%Y', paid_at) as year FROM fees WHERE paid_at IS NOT NULL
            UNION
            SELECT DISTINCT strftime('%Y', date) as year FROM expenses WHERE date IS NOT NULL
            ORDER BY year DESC
        ''').fetchall()
        available_years = [y['year'] for y in years_query if y['year']]
        if not available_years:
            import datetime
            available_years = [str(datetime.datetime.now().year)]

            
        student_clause = " AND ".join(student_where) if student_where else "1=1"
        fees_clause = " AND ".join(fees_where) if fees_where else "1=1"
        
        # Aggregations
        fees_totals = conn.execute(f'''
            SELECT 
                SUM(f.amount) as total,
                SUM(CASE WHEN COALESCE(f.school_revenue, 0) = 0 AND COALESCE(f.hostel_revenue, 0) = 0 AND COALESCE(f.coaching_revenue, 0) = 0 AND COALESCE(f.readmission_revenue, 0) = 0 THEN f.amount ELSE COALESCE(f.school_revenue, 0) END) as school_rev,
                SUM(COALESCE(f.hostel_revenue, 0)) as hostel_rev,
                SUM(COALESCE(f.coaching_revenue, 0)) as coaching_rev,
                SUM(COALESCE(f.readmission_revenue, 0)) as readmission_rev,
                SUM(COALESCE(f.tax_amount, 0)) as tax_amt
            FROM fees f
            JOIN student_info si ON f.student_id = si.user_id
            WHERE {fees_clause}
        ''', fees_params).fetchone()
        
        total_fees = fees_totals['total'] or 0.0
        school_revenue = fees_totals['school_rev'] or 0.0
        hostel_revenue = fees_totals['hostel_rev'] or 0.0
        coaching_revenue = fees_totals['coaching_rev'] or 0.0
        readmission_revenue = fees_totals['readmission_rev'] or 0.0
        tax_revenue = fees_totals['tax_amt'] or 0.0
        
        # Expenses (non-student specific)
        expenses_where = []
        expenses_params = []
        if session.get('branch'):
            expenses_where.append("branch = ? COLLATE NOCASE")
            expenses_params.append(session['branch'])
            
        if date_clause:
            expenses_where.append(date_clause.format(col="date"))
            
        expenses_clause = " AND ".join(expenses_where) if expenses_where else "1=1"
        
        total_expenses = conn.execute(f'''
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE {expenses_clause}
        ''', expenses_params).fetchone()['total'] or 0.0
        
        if date_clause:
            ledger_clause = date_clause.format(col="sl.created_at")
            total_remaining_fees = conn.execute(f'''
                SELECT SUM(sl.amount) as total 
                FROM student_ledger sl
                JOIN student_info si ON sl.student_id = si.user_id
                WHERE {student_clause} AND sl.status = 'Unpaid/Pending' AND {ledger_clause}
            ''', student_params).fetchone()['total'] or 0.0
            
            remaining_fees_details = conn.execute(f'''
                SELECT u.username, si.full_name, si.class, si.roll_number, SUM(sl.amount) as remaining_fee
                FROM student_info si
                JOIN users u ON si.user_id = u.id
                JOIN student_ledger sl ON si.user_id = sl.student_id
                WHERE {student_clause} AND sl.status = 'Unpaid/Pending' AND {ledger_clause}
                GROUP BY u.username, si.full_name, si.class, si.roll_number
                HAVING SUM(sl.amount) != 0
                ORDER BY si.class, CAST(si.roll_number AS INTEGER)
            ''', student_params).fetchall()
        else:
            total_remaining_fees = conn.execute(f'''
                SELECT SUM(si.remaining_fee) as total 
                FROM student_info si
                WHERE {student_clause}
            ''', student_params).fetchone()['total'] or 0.0
            
            remaining_fees_details = conn.execute(f'''
                SELECT u.username, si.full_name, si.class, si.roll_number, si.remaining_fee
                FROM student_info si
                JOIN users u ON si.user_id = u.id
                WHERE {student_clause} AND si.remaining_fee != 0
                ORDER BY si.class, CAST(si.roll_number AS INTEGER)
            ''', student_params).fetchall()
        
        readmission_where = [student_clause, "sl.fee_type = 'Re-admission Fee'"]
        if date_clause:
            readmission_where.append(date_clause.format(col="sl.created_at"))
            
        readmission_totals = conn.execute(f'''
            SELECT 
                SUM(CASE WHEN sl.status = 'Unpaid/Pending' THEN sl.amount ELSE 0.0 END) as pending_amt
            FROM student_ledger sl
            JOIN student_info si ON sl.student_id = si.user_id
            WHERE {" AND ".join(readmission_where)}
        ''', student_params).fetchone()
        
        readmission_pending = readmission_totals['pending_amt'] or 0.0
        
        balance = total_fees - total_expenses  # B2 FIX: remaining_fees are unpaid dues, not cash in hand
        
        conn.close()
        
        return render_template(
            'admin/audit_report.html', 
            fees=total_fees, 
            expenses=total_expenses, 
            balance=balance, 
            remaining_fees=total_remaining_fees, 
            remaining_fees_details=remaining_fees_details, 
            school_revenue=school_revenue,
            hostel_revenue=hostel_revenue,
            coaching_revenue=coaching_revenue,
            tax_revenue=tax_revenue,
            readmission_revenue=readmission_revenue,
            readmission_pending=readmission_pending,
            month_wise_report=month_wise_report,
            role=session['role'], 
            logo_url=LOGO_URL,
            take_school=take_school,
            take_coaching=take_coaching,
            take_day_hostel=take_day_hostel,
            take_car=take_car,
            time_range=time_range,
            filter_year=filter_year,
            filter_month=filter_month,
            available_years=available_years
        )
    return redirect(url_for('home'))

@app.route('/admin/print-audit')
def print_audit():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        # Parse query params
        take_school = request.args.get('take_school')
        take_coaching = request.args.get('take_coaching')
        take_day_hostel = request.args.get('take_day_hostel')
        take_car = request.args.get('take_car')
        time_range = request.args.get('time_range', '').strip().lower()
        if time_range not in ('day', 'week', 'month', 'year', 'all'):
            time_range = 'all'
            
        # Build SQL where clauses
        student_where = []
        student_params = []
        
        fees_where = []
        fees_params = []
        
        if session.get('branch'):
            student_where.append("si.branch = ? COLLATE NOCASE")
            student_params.append(session['branch'])
            fees_where.append("si.branch = ? COLLATE NOCASE")
            fees_params.append(session['branch'])
            
        benefit_conditions = []
        if take_school:
            benefit_conditions.append("si.take_school = 1")
        if take_coaching:
            benefit_conditions.append("si.take_coaching = 1")
        if take_day_hostel:
            benefit_conditions.append("si.take_day_hostel = 1")
        if take_car:
            benefit_conditions.append("si.take_car = 1")
            
        if benefit_conditions:
            benefit_clause = "(" + " OR ".join(benefit_conditions) + ")"
            student_where.append(benefit_clause)
            fees_where.append(benefit_clause)
            
        # Time range clauses
        date_clause = None
        
        filter_year = request.args.get('filter_year', '').strip()
        filter_month = request.args.get('filter_month', '').strip()

        if filter_year and filter_month:
            date_clause = f"strftime('%Y-%m', {{col}}) = '{filter_year}-{filter_month}'"
        elif filter_year:
            date_clause = f"strftime('%Y', {{col}}) = '{filter_year}'"
        elif filter_month:
            date_clause = f"strftime('%m', {{col}}) = '{filter_month}'"
        else:
            if time_range == 'day':
                date_clause = "DATE({col}) = DATE('now', 'localtime')"
            elif time_range == 'week':
                date_clause = "strftime('%Y-%W', {col}) = strftime('%Y-%W', 'now', 'localtime')"
            elif time_range == 'month':
                date_clause = "strftime('%Y-%m', {col}) = strftime('%Y-%m', 'now', 'localtime')"
            elif time_range == 'year':
                date_clause = "strftime('%Y', {col}) = strftime('%Y', 'now', 'localtime')"
            
        if date_clause:
            fees_where.append(date_clause.format(col="f.paid_at"))
            
        student_clause = " AND ".join(student_where) if student_where else "1=1"
        fees_clause = " AND ".join(fees_where) if fees_where else "1=1"
        
        # Aggregations
        fees_totals = conn.execute(f'''
            SELECT 
                SUM(f.amount) as total,
                SUM(CASE WHEN COALESCE(f.school_revenue, 0) = 0 AND COALESCE(f.hostel_revenue, 0) = 0 AND COALESCE(f.coaching_revenue, 0) = 0 AND COALESCE(f.readmission_revenue, 0) = 0 THEN f.amount ELSE COALESCE(f.school_revenue, 0) END) as school_rev,
                SUM(COALESCE(f.hostel_revenue, 0)) as hostel_rev,
                SUM(COALESCE(f.coaching_revenue, 0)) as coaching_rev,
                SUM(COALESCE(f.readmission_revenue, 0)) as readmission_rev,
                SUM(COALESCE(f.tax_amount, 0)) as tax_amt
            FROM fees f
            JOIN student_info si ON f.student_id = si.user_id
            WHERE {fees_clause}
        ''', fees_params).fetchone()
        
        total_fees = fees_totals['total'] or 0.0
        school_revenue = fees_totals['school_rev'] or 0.0
        hostel_revenue = fees_totals['hostel_rev'] or 0.0
        coaching_revenue = fees_totals['coaching_rev'] or 0.0
        readmission_revenue = fees_totals['readmission_rev'] or 0.0
        tax_revenue = fees_totals['tax_amt'] or 0.0
        
        # Expenses (non-student specific)
        expenses_where = []
        expenses_params = []
        if session.get('branch'):
            expenses_where.append("branch = ? COLLATE NOCASE")
            expenses_params.append(session['branch'])
            
        if date_clause:
            expenses_where.append(date_clause.format(col="date"))
            
        expenses_clause = " AND ".join(expenses_where) if expenses_where else "1=1"
        
        total_expenses = conn.execute(f'''
            SELECT SUM(amount) as total 
            FROM expenses 
            WHERE {expenses_clause}
        ''', expenses_params).fetchone()['total'] or 0.0
        
        if date_clause:
            ledger_clause = date_clause.format(col="sl.created_at")
            total_remaining_fees = conn.execute(f'''
                SELECT SUM(sl.amount) as total 
                FROM student_ledger sl
                JOIN student_info si ON sl.student_id = si.user_id
                WHERE {student_clause} AND sl.status = 'Unpaid/Pending' AND {ledger_clause}
            ''', student_params).fetchone()['total'] or 0.0
            
            remaining_fees_details = conn.execute(f'''
                SELECT u.username, si.full_name, si.class, si.roll_number, SUM(sl.amount) as remaining_fee
                FROM student_info si
                JOIN users u ON si.user_id = u.id
                JOIN student_ledger sl ON si.user_id = sl.student_id
                WHERE {student_clause} AND sl.status = 'Unpaid/Pending' AND {ledger_clause}
                GROUP BY u.username, si.full_name, si.class, si.roll_number
                HAVING SUM(sl.amount) != 0
                ORDER BY si.class, CAST(si.roll_number AS INTEGER)
            ''', student_params).fetchall()
        else:
            total_remaining_fees = conn.execute(f'''
                SELECT SUM(si.remaining_fee) as total 
                FROM student_info si
                WHERE {student_clause}
            ''', student_params).fetchone()['total'] or 0.0
            
            remaining_fees_details = conn.execute(f'''
                SELECT u.username, si.full_name, si.class, si.roll_number, si.remaining_fee
                FROM student_info si
                JOIN users u ON si.user_id = u.id
                WHERE {student_clause} AND si.remaining_fee != 0
                ORDER BY si.class, CAST(si.roll_number AS INTEGER)
            ''', student_params).fetchall()
        
        fees_details = conn.execute(f'''
            SELECT f.student_id, f.amount, f.month, f.year, f.paid_at, si.full_name as student_name, si.class, si.roll_number,
                   f.school_revenue, f.hostel_revenue, f.coaching_revenue, f.tax_amount, f.enrollment_type,
                   si.tuition_fee, si.transport_fee, si.lab_library_fee, si.academic_discount,
                   si.room_rent, si.mess_food_charges, si.utility_cost, si.security_deposit,
                   si.coaching_combo_fee, si.study_material_charges, si.exam_test_series_fee, si.combo_discount
            FROM fees f
            JOIN student_info si ON f.student_id = si.user_id
            WHERE {fees_clause}
            ORDER BY f.paid_at DESC
        ''', fees_params).fetchall()

        fees_list = []
        for fee in fees_details:
            f_dict = dict(fee)
            if not f_dict.get('school_revenue') and not f_dict.get('hostel_revenue') and not f_dict.get('coaching_revenue') and not f_dict.get('readmission_revenue'):
                school_rev, hostel_rev, coaching_rev, tax_amt, readmission_rev, e_type = allocate_payment_components(conn, fee['student_id'], fee['amount'])
                f_dict['school_revenue'] = school_rev
                f_dict['hostel_revenue'] = hostel_rev
                f_dict['coaching_revenue'] = coaching_rev
                f_dict['tax_amount'] = tax_amt
                f_dict['readmission_revenue'] = readmission_rev
                f_dict['enrollment_type'] = e_type
            fees_list.append(f_dict)
            
        expenses_details = conn.execute(f'''
            SELECT amount, category, description, date, recipient_type, recipient_id
            FROM expenses
            WHERE {expenses_clause}
            ORDER BY date DESC
        ''', expenses_params).fetchall()
        
        balance = total_fees - total_expenses  # B2 FIX: remaining_fees are unpaid dues, not cash in hand

        readmission_where = [student_clause, "sl.fee_type = 'Re-admission Fee'"]
        if date_clause:
            readmission_where.append(date_clause.format(col="sl.created_at"))
            
        readmission_totals = conn.execute(f'''
            SELECT 
                SUM(CASE WHEN sl.status = 'Unpaid/Pending' THEN sl.amount ELSE 0.0 END) as pending_amt
            FROM student_ledger sl
            JOIN student_info si ON sl.student_id = si.user_id
            WHERE {" AND ".join(readmission_where)}
        ''', student_params).fetchone()
        
        readmission_pending = readmission_totals['pending_amt'] or 0.0

        all_teachers = conn.execute("SELECT u.id, ti.full_name, u.username FROM users u LEFT JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher'").fetchall()
        teacher_map = {t['id']: (t['full_name'] or t['username']) for t in all_teachers}
        
        all_staff = conn.execute("SELECT id, full_name FROM staff").fetchall()
        staff_map = {s['id']: s['full_name'] for s in all_staff}
        
        expenses_with_names = []
        for e in expenses_details:
            e_dict = dict(e)
            if e_dict.get('recipient_type') == 'teacher':
                e_dict['recipient_name'] = teacher_map.get(e_dict.get('recipient_id'))
            elif e_dict.get('recipient_type') == 'staff':
                e_dict['recipient_name'] = staff_map.get(e_dict.get('recipient_id'))
            else:
                e_dict['recipient_name'] = None
            expenses_with_names.append(e_dict)

        conn.close()
        
        return render_template(
            'admin/print_audit.html', 
            fees=total_fees, 
            expenses=total_expenses, 
            balance=balance, 
            remaining_fees=total_remaining_fees,
            fees_details=fees_list, 
            expenses_details=expenses_with_names, 
            remaining_fees_details=remaining_fees_details,
            school_revenue=school_revenue,
            hostel_revenue=hostel_revenue,
            coaching_revenue=coaching_revenue,
            tax_revenue=tax_revenue,
            readmission_revenue=readmission_revenue,
            readmission_pending=readmission_pending,
            role=session['role'], 
            logo_url=LOGO_URL,
            current_date=datetime.datetime.now().strftime('%d %B %Y, %I:%M %p'),
            take_school=take_school,
            take_coaching=take_coaching,
            take_day_hostel=take_day_hostel,
            take_car=take_car,
            time_range=time_range,
            filter_year=filter_year,
            filter_month=filter_month
        )
    return redirect(url_for('home'))

@app.route('/admin/academics-setting', methods=['GET', 'POST'])
def academics_setting():
    if 'user' in session and session['role'] == 'admin': # Only Admin sets subjects
        conn = get_db_connection()
        # No synchronization on GET load to avoid performance penalties.
        # sync_and_normalize_monthly_tests and sync_teacher_subjects_from_string are handled on writes/edits.
        
        if request.method == 'POST' and 'update_general_settings' in request.form:
            new_coaching_time = request.form.get('coaching_class_time', '').strip()
            new_log_email = request.form.get('log_destination_email', '').strip()
            
            if not new_coaching_time or not new_log_email:
                flash('All general settings fields are required.', 'error')
            else:
                old_log_email = get_school_setting('log_destination_email', 'missionalhidayet@gmail.com')
                
                # If log email has changed, notify the previous email
                if old_log_email != new_log_email:
                    subject = "AHM Log Destination Email Changed"
                    body = f"""Hello,

This is to notify you that the AHM system activity log destination email address has been changed.

Previous Destination: {old_log_email}
New Destination: {new_log_email}

Future activity logs will be sent to the new email address.

Best regards,
Al-Hidayet Mission"""
                    # Send notification to previous email address
                    threading.Thread(target=_send_email_raw, args=(subject, body, old_log_email), daemon=True).start()
                    print(f" [EMAIL SENT] Change notification queued to previous email: {old_log_email}")
                
                set_school_setting('coaching_class_time', new_coaching_time)
                set_school_setting('log_destination_email', new_log_email)
                flash('General school settings updated successfully.', 'success')
                
                # Log this activity
                send_activity_notification("Settings Updated", f"Coaching Time: {new_coaching_time}, Log Email: {new_log_email}")
                
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'assign_class_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            class_name = request.form['class_name']
            
            existing = conn.execute("SELECT id FROM class_teachers WHERE class_name = ?", (class_name,)).fetchone()
            if existing:
                flash(f'A class teacher is already assigned to Class {class_name}. Please delete it first.', 'error')
            else:
                conn.execute("INSERT INTO class_teachers (teacher_id, class_name) VALUES (?, ?)", (teacher_id, class_name))
                conn.commit()
                flash('Class teacher assigned successfully!')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        if request.method == 'POST' and 'delete_class_teacher' in request.form:
            ct_id = request.form['ct_id']
            conn.execute("DELETE FROM class_teachers WHERE id = ?", (ct_id,))
            conn.commit()
            conn.close()
            flash('Class teacher assignment deleted successfully.')
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'create_subject' in request.form:
            name = request.form['name']
            # Support comma-separated subject registration
            subject_names = [s.strip() for s in name.split(',') if s.strip()]
            for sub_name in subject_names:
                existing = conn.execute("SELECT id FROM subjects WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (sub_name,)).fetchone()
                if not existing:
                    try:
                        conn.execute("INSERT INTO subjects (name) VALUES (?)", (sub_name,))
                    except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                        if "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                            raise e
            conn.commit()
            flash('Global subject(s) added successfully!')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        if request.method == 'POST' and 'assign_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            subject_name = request.form['subject_name']
            classes = request.form.getlist('classes')
            if not classes:
                flash('Please select at least one class.')
            else:
                subject = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,)).fetchone()
                if subject:
                    assigned_count = 0
                    for class_name in classes:
                        try:
                            conn.execute("INSERT INTO teacher_subjects (teacher_id, class_name, subject_id) VALUES (?, ?, ?)", (teacher_id, class_name, subject['id']))
                            add_teacher_assigned_classes_string(conn, teacher_id, class_name, subject_name)
                            assigned_count += 1
                        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                            if isinstance(e, sqlite3.OperationalError) and "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                                raise e
                            pass
                    conn.commit()
                    if assigned_count > 0:
                        flash(f'Teacher assigned to {assigned_count} class(es) for {subject_name}!')
                    else:
                        flash('No new assignments made. Make sure the assignment does not already exist.')
                else:
                    flash('Subject not found.')
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'delete_subject' in request.form:
            subject_id = request.form['subject_id']
            try:
                subject_row = conn.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
                if subject_row:
                    subject_name = subject_row['name']
                    # Find all teachers assigned to this subject to update their assigned_classes text
                    teachers = conn.execute("SELECT DISTINCT teacher_id FROM teacher_subjects WHERE subject_id = ?", (subject_id,)).fetchall()
                    # Cascade deletions to prevent foreign key or orphan row issues
                    conn.execute("DELETE FROM teacher_subjects WHERE subject_id = ?", (subject_id,))
                    conn.execute("DELETE FROM teacher_assignments WHERE subject_id = ?", (subject_id,))
                    conn.execute("DELETE FROM class_subjects WHERE LOWER(subject_name) = LOWER(?)", (subject_name.lower(),))
                    conn.execute("DELETE FROM marks WHERE LOWER(subject_name) = LOWER(?)", (subject_name.lower(),))
                    conn.execute("DELETE FROM class_routine WHERE LOWER(subject) = LOWER(?)", (subject_name.lower(),))
                    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
                    
                    # Rebuild assigned_classes string for each affected teacher from DB
                    for t in teachers:
                        sync_teacher_assigned_classes_string_from_db(conn, t['teacher_id'])
                        
                    conn.commit()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                        conn.close()
                        return jsonify({'status': 'success', 'message': 'Subject and all its assignments/routines deleted successfully.'})
                        
                    flash('Subject deleted successfully.')
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                        conn.close()
                        return jsonify({'status': 'error', 'message': 'Subject not found.'})
                    flash('Subject not found.')
            except Exception as e:
                conn.rollback()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    conn.close()
                    return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'})
                flash(f'Server error: {str(e)}')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        if request.method == 'POST' and 'delete_assignment' in request.form:
            assignment_id = request.form['assignment_id']
            try:
                # Find details of this assignment to update their assigned_classes text
                info = conn.execute('''
                    SELECT ts.teacher_id, s.name as subject_name, ts.class_name
                    FROM teacher_subjects ts
                    JOIN subjects s ON ts.subject_id = s.id
                    WHERE ts.id = ?
                ''', (assignment_id,)).fetchone()
                
                conn.execute("DELETE FROM teacher_subjects WHERE id = ?", (assignment_id,))
                
                if info:
                    sync_teacher_assigned_classes_string_from_db(conn, info['teacher_id'])
                    
                conn.commit()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    conn.close()
                    return jsonify({'status': 'success', 'message': 'Teacher assignment deleted successfully.'})
                    
                flash('Teacher assignment deleted successfully.')
            except Exception as e:
                conn.rollback()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    conn.close()
                    return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'})
                flash(f'Server error: {str(e)}')
            conn.close()
            return redirect(url_for('academics_setting'))

        # Class test config post handlers disabled (moved to Bulk Marks)
        pass

        if request.method == 'POST' and 'create_exam_schedule' in request.form:
            class_name = request.form.get('class_name', '').strip()
            if class_name and class_name.startswith('Class '):
                class_name = class_name[6:].strip()
            term_name = request.form.get('term_name', '').strip()
            branch = (session.get('branch') or 'bhogram').strip()
            
            dates = request.form.getlist('schedule_date[]')
            times = request.form.getlist('schedule_time[]')
            subjects = request.form.getlist('schedule_subject[]')
            
            schedule_list = []
            for d, t, s in zip(dates, times, subjects):
                if d or t or s:  # skip empty rows
                    schedule_list.append({"date": d, "time": t, "subject": s})
            
            schedule_text = json.dumps(schedule_list) if schedule_list else '[]'
            
            try:
                conn.execute('''
                    INSERT INTO exam_schedules (class_name, term_name, branch, schedule_text)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(class_name, term_name, branch) DO UPDATE SET schedule_text = excluded.schedule_text, schedule_image = NULL
                ''', (class_name, term_name, branch, schedule_text))
                conn.commit()
                flash(f'Exam schedule configured for Class {class_name} ({term_name}).')
            except Exception as e:
                conn.rollback()
                flash(f'Server error: {str(e)}')
            
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'delete_exam_schedule' in request.form:
            schedule_id = request.form.get('schedule_id')
            try:
                conn.execute("DELETE FROM exam_schedules WHERE id = ?", (schedule_id,))
                conn.commit()
                flash('Exam schedule deleted successfully.')
            except Exception as e:
                conn.rollback()
                flash(f'Server error: {str(e)}')
            conn.close()
            return redirect(url_for('academics_setting'))

        subjects = conn.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        distinct_subjects = subjects
        teachers = conn.execute('''
            SELECT u.id, u.username, ti.full_name
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        assignments = conn.execute('''
            SELECT ts.id, COALESCE(NULLIF(ti.full_name, ''), u.username) as teacher_name, s.name as subject_name, ts.class_name as class 
            FROM teacher_subjects ts
            JOIN users u ON ts.teacher_id = u.id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            JOIN subjects s ON ts.subject_id = s.id
        ''').fetchall()
        branch_filter = session.get('branch')
        classes = conn.execute("SELECT * FROM classes WHERE ? IS NULL OR LOWER(branch) = LOWER(?) ORDER BY id", (branch_filter, branch_filter)).fetchall()
        
        # Get distinct class names programmatically to avoid any duplicates due to spacing or case differences
        class_names = get_all_classes(conn, branch=branch_filter)
        distinct_classes = [{'name': name} for name in class_names]
                
        registration_documents = conn.execute("SELECT * FROM registration_documents ORDER BY id").fetchall()
        
        exam_locks_raw = conn.execute("SELECT * FROM exam_locks").fetchall()
        exam_locks = [dict(row) for row in exam_locks_raw]
        class_tests_rows = conn.execute("SELECT DISTINCT term_name FROM marks WHERE LOWER(term_name) NOT IN ('1st unit', '1st term', '2nd unit', '2nd term', 'final exam', 'annual exam')").fetchall()
        all_terms = ['1st Unit', '2nd Unit', 'Final Exam'] + sorted(list({r['term_name'] for r in class_tests_rows if r['term_name']}), key=get_month_sort_key)
        
        log_email = get_school_setting('log_destination_email', 'missionalhidayet@gmail.com')
        
        class_teachers = conn.execute('''
            SELECT ct.id, ct.class_name, COALESCE(ti.full_name, u.username) as teacher_name
            FROM class_teachers ct
            JOIN users u ON ct.teacher_id = u.id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            ORDER BY ct.class_name
        ''').fetchall()
        
        exam_schedules_list = conn.execute("SELECT * FROM exam_schedules ORDER BY class_name, term_name").fetchall()
        
        conn.close()
        return render_template('admin/academics_setting.html', subjects=subjects, distinct_subjects=distinct_subjects, teachers=teachers, assignments=assignments, class_test_configs=[], classes=classes, distinct_classes=distinct_classes, class_teachers=class_teachers, registration_documents=registration_documents, role=session['role'], exam_locks=exam_locks, all_terms=all_terms, log_destination_email=log_email, exam_schedules=exam_schedules_list)
    elif 'user' in session and session['role'] == 'teacher': # Teachers just view
         conn = get_db_connection()
         branch_filter = session.get('branch')
         classes = conn.execute("SELECT * FROM classes WHERE ? IS NULL OR LOWER(branch) = LOWER(?) ORDER BY id", (branch_filter, branch_filter)).fetchall()
         
         # Get distinct class names programmatically to avoid any duplicates due to spacing or case differences
         class_names = get_all_classes(conn, branch=branch_filter)
         distinct_classes = [{'name': name} for name in class_names]
                 
         registration_documents = conn.execute("SELECT * FROM registration_documents ORDER BY id").fetchall()
         exam_locks_raw = conn.execute("SELECT * FROM exam_locks").fetchall()
         exam_locks = [dict(row) for row in exam_locks_raw]
         exam_schedules_list = conn.execute("SELECT * FROM exam_schedules ORDER BY class_name, term_name").fetchall()
         conn.close()
         return render_template('admin/academics_setting.html', class_test_configs=[], classes=classes, distinct_classes=distinct_classes, registration_documents=registration_documents, role=session['role'], exam_locks=exam_locks, exam_schedules=exam_schedules_list) # Needs simplified view

@app.route('/admin/toggle-exam-lock', methods=['POST'])
def toggle_exam_lock():
    if 'user' in session and session['role'] == 'admin':
        branch = session.get('branch') or request.form.get('branch', 'bhogram').strip()
        class_name = request.form.get('class_name', '').strip()
        
        # Support both multiple term selection and single term fallback
        term_names = request.form.getlist('term_names')
        if not term_names:
            single_term = request.form.get('term_name')
            term_names = [single_term] if single_term else []
            
        is_locked = int(request.form.get('is_locked', '0'))
        
        # Remove any empty values
        term_names = [t.strip() for t in term_names if t and t.strip()]
        
        if not class_name or not term_names:
            flash('Invalid class or term selection.')
            return redirect(url_for('academics_setting'))
            
        conn = get_db_connection()
        for t_name in term_names:
            conn.execute('''
                INSERT INTO exam_locks (branch, class_name, term_name, is_locked)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(branch, class_name, term_name) DO UPDATE SET is_locked = excluded.is_locked
            ''', (branch, class_name, t_name, is_locked))
        conn.commit()
        conn.close()
        
        status_str = "locked" if is_locked == 1 else "unlocked"
        if len(term_names) == 1:
            flash(f"Exam '{term_names[0]}' for class '{class_name}' has been {status_str} successfully.")
        else:
            flash(f"{len(term_names)} exams for class '{class_name}' have been {status_str} successfully.")
    return redirect(url_for('academics_setting'))

@app.route('/admin/update-class-fees', methods=['POST'])
def update_class_fees():
    if 'user' in session and session['role'] == 'admin':
        class_id = request.form.get('class_id')
        try:
            def parse_fee(val):
                if val is None or str(val).strip() == '':
                    return None
                try:
                    return float(val)
                except ValueError:
                    return None

            admission_fee = parse_fee(request.form.get('admission_fee'))
            admission_fee_coaching = parse_fee(request.form.get('admission_fee_coaching'))
            admission_fee_hostel = parse_fee(request.form.get('admission_fee_hostel'))
            readmission_fee_school = parse_fee(request.form.get('readmission_fee_school'))
            readmission_fee_coaching = parse_fee(request.form.get('readmission_fee_coaching'))
            readmission_fee_hostel = parse_fee(request.form.get('readmission_fee_hostel'))
            monthly_fee = parse_fee(request.form.get('monthly_fee'))
            monthly_fee_coaching = parse_fee(request.form.get('monthly_fee_coaching'))
            hostel_fee = parse_fee(request.form.get('hostel_fee'))
            
            conn = get_db_connection()
            class_info = conn.execute("SELECT name, branch FROM classes WHERE id = ?", (class_id,)).fetchone()

            conn.execute("""
                UPDATE classes 
                SET admission_fee = ?, admission_fee_coaching = ?, admission_fee_hostel = ?,
                    readmission_fee_school = ?, readmission_fee_coaching = ?, readmission_fee_hostel = ?,
                    monthly_fee = ?, monthly_fee_coaching = ?, hostel_fee = ?
                WHERE id = ?
            """, (admission_fee, admission_fee_coaching, admission_fee_hostel,
                  readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                  monthly_fee, monthly_fee_coaching, hostel_fee, class_id))
            
            if class_info:
                class_name = class_info['name']
                branch = class_info['branch']
                
                db_classes = get_db_class_names(class_name)
                placeholders = ', '.join(['?'] * len(db_classes))
                students = conn.execute(f"SELECT user_id, take_coaching, take_day_hostel FROM student_info WHERE class IN ({placeholders}) AND branch = ?", db_classes + [branch]).fetchall()
                for student in students:
                    s_adm = admission_fee
                    s_readm = readmission_fee_school
                    s_mon = monthly_fee
                    s_hostel = None
                    
                    if student['take_day_hostel']:
                        s_adm = admission_fee_hostel
                        s_readm = readmission_fee_hostel
                        s_hostel = hostel_fee
                    elif student['take_coaching']:
                        s_adm = admission_fee_coaching
                        s_readm = readmission_fee_coaching
                        s_mon = monthly_fee_coaching
                        
                    conn.execute("""
                        UPDATE student_info
                        SET admission_fee = ?, readmission_fee = ?, monthly_fee = ?, hostel_fee = ?
                        WHERE user_id = ?
                    """, (s_adm, s_readm, s_mon, s_hostel, student['user_id']))

            conn.commit()
            conn.close()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'success', 'message': 'Class fees updated successfully!'})
            flash('Class fees updated successfully!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'error', 'message': str(e)})
            flash(f'Failed to update fees: {e}')
@app.route('/admin/fee-matrix', methods=['GET', 'POST'])
@app.route('/admin/fee_matrix', methods=['GET', 'POST'])
def fee_matrix():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        
        branch_filter = session.get('branch') or request.args.get('branch', 'bhogram').strip().lower()
        
        if request.method == 'POST':
            # 1. Create a class
            if 'create_class' in request.form:
                class_name = request.form['class_name'].strip()
                branch = session['branch'] if session.get('branch') else request.form.get('branch', 'bhogram')
                if not class_name or not branch:
                    flash('Please enter a valid class name and branch.')
                else:
                    existing = conn.execute("SELECT id FROM classes WHERE name = ? AND branch = ?", (class_name, branch)).fetchone()
                    if existing:
                        flash(f'Class {class_name} already exists for branch {branch.title()}!')
                    else:
                        try:
                            admission_fee = float(request.form.get('admission_fee', 0.0) or 0.0)
                            admission_fee_coaching = float(request.form.get('admission_fee_coaching', 0.0) or 0.0)
                            admission_fee_hostel = float(request.form.get('admission_fee_hostel', 0.0) or 0.0)
                            readmission_fee_school = float(request.form.get('readmission_fee_school', 0.0) or 0.0)
                            readmission_fee_coaching = float(request.form.get('readmission_fee_coaching', 0.0) or 0.0)
                            readmission_fee_hostel = float(request.form.get('readmission_fee_hostel', 0.0) or 0.0)
                            monthly_fee = float(request.form.get('monthly_fee', 0.0) or 0.0)
                            monthly_fee_coaching = float(request.form.get('monthly_fee_coaching', 0.0) or 0.0)
                            hostel_fee = float(request.form.get('hostel_fee', 0.0) or 0.0)
                        except ValueError:
                            admission_fee = 0.0
                            admission_fee_coaching = 0.0
                            admission_fee_hostel = 0.0
                            readmission_fee_school = 0.0
                            readmission_fee_coaching = 0.0
                            readmission_fee_hostel = 0.0
                            monthly_fee = 0.0
                            monthly_fee_coaching = 0.0
                            hostel_fee = 0.0
                        
                        conn.execute("""
                            INSERT INTO classes (
                                name, branch, admission_fee, admission_fee_coaching, admission_fee_hostel,
                                readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                                monthly_fee, monthly_fee_coaching, hostel_fee
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (class_name, branch, admission_fee, admission_fee_coaching, admission_fee_hostel,
                              readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                              monthly_fee, monthly_fee_coaching, hostel_fee))

                        # Seed default fee_structures for this new class
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, school_tax_rate) VALUES (?, ?, 'Day School Only', ?, 0.0)", (class_name, branch, monthly_fee))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, room_rent, hostel_tax_rate) VALUES (?, ?, 'Day Hostel Only', ?, 0.05)", (class_name, branch, hostel_fee))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, coaching_combo_fee, combo_discount, school_tax_rate, coaching_tax_rate) VALUES (?, ?, 'School + Coaching', ?, ?, 0.0, 0.0, 0.0)", (class_name, branch, monthly_fee, monthly_fee_coaching))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, room_rent, school_tax_rate, hostel_tax_rate) VALUES (?, ?, 'Hostel Only (or School + Hostel)', ?, ?, 0.0, 0.05)", (class_name, branch, monthly_fee, hostel_fee))

                        seed_default_subjects(conn)
                        conn.commit()
                        flash(f'Class {class_name} added successfully for {branch.title()} with fees!')
                conn.close()
                return redirect(url_for('fee_matrix'))

            # 2. Delete a class
            elif 'delete_class' in request.form:
                class_id = request.form['class_id']
                try:
                    class_row = conn.execute("SELECT name, branch FROM classes WHERE id = ?", (class_id,)).fetchone()
                    if class_row:
                        class_name = class_row['name']
                        db_classes = get_db_class_names(class_name)
                        placeholders = ', '.join('?' for _ in db_classes)
                        teachers = conn.execute(f'''
                            SELECT DISTINCT teacher_id
                            FROM teacher_subjects
                            WHERE LOWER(class_name) IN ({placeholders})
                        ''', tuple(c.lower() for c in db_classes)).fetchall()
                        
                        conn.execute(f"DELETE FROM teacher_subjects WHERE LOWER(class_name) IN ({placeholders})", tuple(c.lower() for c in db_classes))
                        conn.execute(f"DELETE FROM teacher_assignments WHERE LOWER(class_name) IN ({placeholders})", tuple(c.lower() for c in db_classes))
                        conn.execute(f"DELETE FROM marks WHERE LOWER(class_name) IN ({placeholders})", tuple(c.lower() for c in db_classes))
                        conn.execute(f"DELETE FROM class_subjects WHERE LOWER(class_name) IN ({placeholders})", tuple(c.lower() for c in db_classes))
                        conn.execute(f"DELETE FROM class_routine WHERE LOWER(class_name) IN ({placeholders})", tuple(c.lower() for c in db_classes))
                        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
                        
                        for t in teachers:
                            sync_teacher_assigned_classes_string_from_db(conn, t['teacher_id'])
                            
                        conn.commit()
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                            conn.close()
                            return jsonify({'status': 'success', 'message': f'Class {class_name} deleted successfully.'})
                        flash(f'Class {class_name} deleted successfully.')
                    else:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                            conn.close()
                            return jsonify({'status': 'error', 'message': 'Class not found.'})
                        flash('Class not found.')
                except Exception as e:
                    conn.rollback()
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                        conn.close()
                        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'})
                    flash(f'Server error: {str(e)}')
                conn.close()
                return redirect(url_for('fee_matrix'))

            # 3. Update class-wise or student-wise settings
            elif 'update_type' in request.form:
                update_type = request.form.get('update_type')
                branch = session['branch'] if session.get('branch') else request.form.get('branch', 'bhogram')
                
                if update_type == 'class':
                    class_name = request.form.get('class')
                    db_classes = get_db_class_names(class_name)
                    placeholders = ', '.join('?' for _ in db_classes)
                    
                    admission_fee = float(request.form.get('admission_fee') or 0.0)
                    admission_fee_coaching = float(request.form.get('admission_fee_coaching') or 0.0)
                    admission_fee_hostel = float(request.form.get('admission_fee_hostel') or 0.0)
                    readmission_fee_school = float(request.form.get('readmission_fee_school') or 0.0)
                    readmission_fee_coaching = float(request.form.get('readmission_fee_coaching') or 0.0)
                    readmission_fee_hostel = float(request.form.get('readmission_fee_hostel') or 0.0)
                    monthly_fee = float(request.form.get('monthly_fee') or 0.0)
                    monthly_fee_coaching = float(request.form.get('monthly_fee_coaching') or 0.0)
                    hostel_fee = float(request.form.get('hostel_fee') or 0.0)
                    
                    for db_cls in db_classes:
                        row_exist = conn.execute("SELECT id FROM classes WHERE name = ? AND branch = ?", (db_cls, branch)).fetchone()
                        if row_exist:
                            conn.execute('''
                                UPDATE classes 
                                SET admission_fee = ?, admission_fee_coaching = ?, admission_fee_hostel = ?,
                                    readmission_fee_school = ?, readmission_fee_coaching = ?, readmission_fee_hostel = ?,
                                    monthly_fee = ?, monthly_fee_coaching = ?, hostel_fee = ?
                                WHERE id = ?
                            ''', (admission_fee, admission_fee_coaching, admission_fee_hostel,
                                  readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                                  monthly_fee, monthly_fee_coaching, hostel_fee, row_exist['id']))
                        else:
                            conn.execute('''
                                INSERT INTO classes (
                                    name, branch, admission_fee, admission_fee_coaching, admission_fee_hostel,
                                    readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                                    monthly_fee, monthly_fee_coaching, hostel_fee
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (db_cls, branch, admission_fee, admission_fee_coaching, admission_fee_hostel,
                                  readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel,
                                  monthly_fee, monthly_fee_coaching, hostel_fee))

                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, school_tax_rate) VALUES (?, ?, 'Day School Only', ?, 0.0)", (db_cls, branch, monthly_fee))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, room_rent, hostel_tax_rate) VALUES (?, ?, 'Day Hostel Only', ?, 0.05)", (db_cls, branch, hostel_fee))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, coaching_combo_fee, combo_discount, school_tax_rate, coaching_tax_rate) VALUES (?, ?, 'School + Coaching', ?, ?, 0.0, 0.0, 0.0)", (db_cls, branch, monthly_fee, monthly_fee_coaching))
                        conn.execute("INSERT OR REPLACE INTO fee_structures (class_name, branch, enrollment_type, tuition_fee, room_rent, school_tax_rate, hostel_tax_rate) VALUES (?, ?, 'Hostel Only (or School + Hostel)', ?, ?, 0.0, 0.05)", (db_cls, branch, monthly_fee, hostel_fee))
                    
                    students_in_class = conn.execute(f'''
                        SELECT user_id, take_school, take_coaching, take_day_hostel, take_car
                        FROM student_info
                        WHERE branch = ? AND class IN ({placeholders}) AND (is_custom_fee = 0 OR is_custom_fee IS NULL)
                    ''', (branch, *db_classes)).fetchall()
                    
                    for student in students_in_class:
                        old_data = conn.execute("SELECT remaining_fee, monthly_fee, readmission_fee, enrollment_type FROM student_info WHERE user_id = ?", (student['user_id'],)).fetchone()
                        old_remaining_fee = float(old_data['remaining_fee']) if old_data and old_data['remaining_fee'] is not None else 0.0
                        old_monthly_fee = float(old_data['monthly_fee']) if old_data and old_data['monthly_fee'] is not None else 0.0
                        old_readmission_fee = float(old_data['readmission_fee']) if old_data and old_data['readmission_fee'] is not None else 0.0
                        
                        take_school = student['take_school']
                        take_coaching = student['take_coaching']
                        take_day_hostel = student['take_day_hostel']
                        take_car = student['take_car']
                        
                        e_type = old_data['enrollment_type'] if (old_data and old_data['enrollment_type']) else 'Day School Only'
                        
                        bd = calculate_student_fees_breakdown({
                            'class': class_name,
                            'branch': branch,
                            'enrollment_type': e_type,
                            'take_car': take_car
                        }, conn)
                        m_fee = bd['total_fee']
                        
                        a_fee = 0.0
                        r_fee = 0.0
                        
                        if take_day_hostel:
                            a_fee = admission_fee_hostel
                            r_fee = readmission_fee_hostel
                        elif take_coaching:
                            a_fee = admission_fee_coaching
                            r_fee = readmission_fee_coaching
                        elif take_school:
                            a_fee = admission_fee
                            r_fee = readmission_fee_school
                            
                        new_remaining_fee = old_remaining_fee + (m_fee - old_monthly_fee) + (r_fee - old_readmission_fee)
                        # ALLOW NEGATIVE DUES
                            
                        conn.execute('''
                            UPDATE student_info
                            SET monthly_fee = ?, admission_fee = ?, readmission_fee = ?, remaining_fee = ?
                            WHERE user_id = ?
                        ''', (m_fee, a_fee, r_fee, new_remaining_fee, student['user_id']))
                        
                        sync_student_ledger_and_dues(conn, student['user_id'], submitted_remaining_fee=new_remaining_fee, is_manual_dues_change=True)
                    
                    conn.commit()
                    flash(f'Successfully updated class fees and student fee balances for Class {class_name}')
                    
                elif update_type == 'student':
                    student_id = request.form.get('student_id')
                    if session.get('branch'):
                        student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                        if not student or student['branch'] != session['branch']:
                            conn.close()
                            flash('Permission denied: Student does not belong to your campus.')
                            return redirect(url_for('fee_matrix'))
                    
                    take_school = 1 if request.form.get('take_school') else 0
                    take_coaching = 1 if request.form.get('take_coaching') else 0
                    take_day_hostel = 1 if request.form.get('take_day_hostel') else 0
                    take_car = 1 if request.form.get('take_car') else 0
                    coaching_opted = take_coaching
                    car_opted = take_car
                    mode_of_admission = 'Day Hostel' if take_day_hostel else ('School with Coaching' if take_coaching else 'School')
                    
                    amount_str = request.form.get('amount')
                    admission_fee_str = request.form.get('admission_fee')
                    readmission_fee_str = request.form.get('readmission_fee')
                    
                    old_student = conn.execute("SELECT prev_dues, remaining_fee, monthly_fee, readmission_fee FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                    
                    # If amount is not provided, it's not a custom fee override
                    is_custom_fee_val = 1 if (amount_str and amount_str.strip() != '') else 0
                    
                    amount = float(amount_str) if is_custom_fee_val else (float(old_student['monthly_fee']) if old_student and old_student['monthly_fee'] is not None else 0.0)
                    admission_fee = float(admission_fee_str) if admission_fee_str and admission_fee_str.strip() != '' else 0.0
                    readmission_fee = float(readmission_fee_str) if readmission_fee_str and readmission_fee_str.strip() != '' else (float(old_student['readmission_fee']) if old_student and old_student['readmission_fee'] is not None else 0.0)
                    
                    submitted_total_due_str = request.form.get('total_due')
                    if submitted_total_due_str is None:
                        submitted_total_due_str = request.form.get('prev_dues')
                        
                    submitted_total_due = float(submitted_total_due_str or 0.0)
                    if submitted_total_due < 0.0:
                        submitted_total_due = 0.0
                        
                    # prev_dues = total_due - remaining_fee + old_prev_dues
                    old_remaining = float(old_student['remaining_fee'] or 0.0)
                    old_prev_dues = float(old_student['prev_dues'] or 0.0)
                    new_prev_dues = submitted_total_due - old_remaining + old_prev_dues

                    conn.execute('''
                        UPDATE student_info
                        SET take_school = ?, take_coaching = ?, take_day_hostel = ?, take_car = ?,
                            coaching_opted = ?, car_opted = ?, mode_of_admission = ?,
                            monthly_fee = ?, admission_fee = ?, readmission_fee = ?,
                            prev_dues = ?, is_custom_fee = ?
                        WHERE user_id = ?
                    ''', (take_school, take_coaching, take_day_hostel, take_car,
                          coaching_opted, car_opted, mode_of_admission,
                          amount, admission_fee, readmission_fee, new_prev_dues, is_custom_fee_val, student_id))
                    
                    sync_student_ledger_and_dues(conn, student_id)
                    conn.commit()
                    flash(f'Successfully updated fees and benefits for student ID {student_id}')
                
                elif update_type == 'class_due':
                    class_name = request.form.get('class_name')
                    amount_str = request.form.get('due_amount', '0.0')
                    fee_type = request.form.get('fee_type', 'Manual Fee Adjustment').strip()
                    if not fee_type:
                        fee_type = 'Manual Fee Adjustment'
                        
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        amount = 0.0
                        
                    if amount > 0:
                        branch_filter = session.get('branch')
                        if branch_filter:
                            students = conn.execute("SELECT user_id, prev_dues, branch FROM student_info WHERE class = ? AND branch = ?", (class_name, branch_filter)).fetchall()
                        else:
                            students = conn.execute("SELECT user_id, prev_dues, branch FROM student_info WHERE class = ?", (class_name,)).fetchall()
                            
                        from datetime import datetime
                        month = datetime.now().strftime('%B')
                        year = datetime.now().strftime('%Y')
                        
                        for s in students:
                            new_due = float(s['prev_dues'] or 0.0) + amount
                            conn.execute("UPDATE student_info SET prev_dues = ? WHERE user_id = ?", (new_due, s['user_id']))
                            
                            # Insert into student_ledger so it shows up specifically by name
                            conn.execute('''
                                INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                                VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                            ''', (s['user_id'], fee_type, amount, month, year, s['branch']))
                            
                            # Log the charge
                            conn.execute('''
                                INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                                VALUES (?, 'Charge', ?, ?, ?, ?, ?)
                            ''', (s['user_id'], fee_type, amount, month, year, s['branch']))
                            
                            sync_student_ledger_and_dues(conn, s['user_id'])
                        
                        conn.commit()
                        flash(f'Successfully added ₹{amount} ({fee_type}) to all students in Class {class_name}')
                    else:
                        flash('Amount must be greater than 0.')
                
                elif update_type == 'student_due':
                    student_id = request.form.get('student_id')
                    amount_str = request.form.get('due_amount', '0.0')
                    fee_type = request.form.get('fee_type', 'Manual Fee Adjustment').strip()
                    if not fee_type:
                        fee_type = 'Manual Fee Adjustment'
                        
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        amount = 0.0
                        
                    if amount != 0:
                        s = conn.execute("SELECT user_id, prev_dues, branch, full_name FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                        if s:
                            if session.get('branch') and s['branch'] != session['branch']:
                                flash("Permission denied.")
                            else:
                                from datetime import datetime
                                month = datetime.now().strftime('%B')
                                year = datetime.now().strftime('%Y')
                                
                                new_due = float(s['prev_dues'] or 0.0) + amount
                                conn.execute("UPDATE student_info SET prev_dues = ? WHERE user_id = ?", (new_due, student_id))
                                
                                conn.execute('''
                                    INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                                    VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                                ''', (s['user_id'], fee_type, amount, month, year, s['branch']))
                                
                                conn.execute('''
                                    INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                                    VALUES (?, 'Charge', ?, ?, ?, ?, ?)
                                ''', (s['user_id'], fee_type, amount, month, year, s['branch']))
                                
                                sync_student_ledger_and_dues(conn, s['user_id'])
                                conn.commit()
                                flash(f"Successfully added ₹{amount} ({fee_type}) to {s['full_name']}")
                    else:
                        flash('Amount must not be 0.')

                conn.close()
                if request.form.get('redirect_to') == 'set_fees':
                    return redirect(url_for('set_fees'))
                return redirect(url_for('fee_matrix'))

            # 4. Bulk update of fee matrix
            else:
                try:
                    classes_list = conn.execute("SELECT id, class_name FROM fee_matrix WHERE branch = 'bhogram'").fetchall()
                    for cls in classes_list:
                        cls_id = cls['id']
                        sm = float(request.form.get(f'sm_{cls_id}', 0.0) or 0.0)
                        sa = float(request.form.get(f'sa_{cls_id}', 0.0) or 0.0)
                        sr = float(request.form.get(f'sr_{cls_id}', 0.0) or 0.0)
                        cm = float(request.form.get(f'cm_{cls_id}', 0.0) or 0.0)
                        ca = float(request.form.get(f'ca_{cls_id}', 0.0) or 0.0)
                        cr = float(request.form.get(f'cr_{cls_id}', 0.0) or 0.0)
                        hm = float(request.form.get(f'hm_{cls_id}', 0.0) or 0.0)
                        ha = float(request.form.get(f'ha_{cls_id}', 0.0) or 0.0)
                        hr = float(request.form.get(f'hr_{cls_id}', 0.0) or 0.0)
                        
                        conn.execute('''
                            UPDATE fee_matrix 
                            SET school_monthly = ?, school_admission = ?, school_readmission = ?,
                                coaching_monthly = ?, coaching_admission = ?, coaching_readmission = ?,
                                hostel_monthly = ?, hostel_admission = ?, hostel_readmission = ?
                            WHERE id = ?
                        ''', (sm, sa, sr, cm, ca, cr, hm, ha, hr, cls_id))
                    
                    flat_rate = float(request.form.get('flat_rate', 400.0) or 400.0)
                    conn.execute("INSERT INTO transport_settings (flat_rate) VALUES (?)", (flat_rate,))
                    conn.commit()
                    flash('Fee Configuration Matrix updated successfully!')
                except Exception as e:
                    conn.rollback()
                    flash(f'Failed to update fee matrix: {e}')
                conn.close()
                return redirect(url_for('fee_matrix'))

        # GET Request
        db_classes = [dict(row) for row in conn.execute("SELECT * FROM fee_matrix WHERE branch = 'bhogram'").fetchall()]
        trans_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
        flat_rate = trans_row['flat_rate'] if trans_row else 400.0
        
        if session.get('branch'):
            students_raw = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, 
                       si.monthly_fee, si.hostel_fee, si.branch,
                       si.take_school, si.take_coaching, si.take_day_hostel, si.take_car,
                       si.admission_fee, si.readmission_fee, si.remaining_fee, si.prev_dues, si.is_custom_fee
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.branch = ?
            ''', (session['branch'],)).fetchall()
            
            custom_fee_students_raw = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, 
                       si.monthly_fee, si.readmission_fee, si.remaining_fee, si.prev_dues, si.branch
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.branch = ? AND si.is_custom_fee = 1
            ''', (session['branch'],)).fetchall()
        else:
            students_raw = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, 
                       si.monthly_fee, si.hostel_fee, si.branch,
                       si.take_school, si.take_coaching, si.take_day_hostel, si.take_car,
                       si.admission_fee, si.readmission_fee, si.remaining_fee, si.prev_dues, si.is_custom_fee
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student'
            ''').fetchall()
            
            custom_fee_students_raw = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, 
                       si.monthly_fee, si.readmission_fee, si.remaining_fee, si.prev_dues, si.branch
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.is_custom_fee = 1
            ''').fetchall()
            
        db_classes_all = [dict(row) for row in conn.execute("SELECT * FROM classes WHERE LOWER(branch) = LOWER(?)", (branch_filter,)).fetchall()]
        
        # Post-process students to dynamically resolve default templates when not custom-fee
        students = resolve_student_default_fees(students_raw, conn)
            
        custom_fee_students = [dict(row) for row in custom_fee_students_raw]
        classes_names = get_all_classes(conn, branch=branch_filter)
        
        conn.close()
        return render_template('admin/fee_matrix.html', 
                               db_classes=db_classes, 
                               flat_rate=flat_rate, 
                               branch_filter=branch_filter, 
                               role=session['role'], 
                               branches=BRANCHES,
                               students=students,
                               custom_fee_students=custom_fee_students,
                               db_classes_all=db_classes_all,
                               classes=classes_names)
    return redirect(url_for('home'))


@app.route('/admin/update-matrix-row', methods=['POST'])
def update_matrix_row():
    if 'user' in session and session['role'] == 'admin':
        try:
            row_id = request.form.get('row_id')
            sm = float(request.form.get('school_monthly', 0.0) or 0.0)
            sa = float(request.form.get('school_admission', 0.0) or 0.0)
            sr = float(request.form.get('school_readmission', 0.0) or 0.0)
            cm = float(request.form.get('coaching_monthly', 0.0) or 0.0)
            ca = float(request.form.get('coaching_admission', 0.0) or 0.0)
            cr = float(request.form.get('coaching_readmission', 0.0) or 0.0)
            hm = float(request.form.get('hostel_monthly', 0.0) or 0.0)
            ha = float(request.form.get('hostel_admission', 0.0) or 0.0)
            hr = float(request.form.get('hostel_readmission', 0.0) or 0.0)
            
            conn = get_db_connection()
            conn.execute('''
                UPDATE fee_matrix 
                SET school_monthly = ?, school_admission = ?, school_readmission = ?,
                    coaching_monthly = ?, coaching_admission = ?, coaching_readmission = ?,
                    hostel_monthly = ?, hostel_admission = ?, hostel_readmission = ?
                WHERE id = ?
            ''', (sm, sa, sr, cm, ca, cr, hm, ha, hr, row_id))
            conn.commit()
            conn.close()
            return jsonify({'status': 'success', 'message': 'Class fee row updated successfully.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

@app.route('/admin/update-transport-allowance', methods=['POST'])
def update_transport_allowance():
    if 'user' in session and session['role'] == 'admin':
        try:
            flat_rate = float(request.form.get('flat_rate', 400.0) or 400.0)
            conn = get_db_connection()
            conn.execute("INSERT INTO transport_settings (flat_rate) VALUES (?)", (flat_rate,))
            conn.commit()
            conn.close()
            return jsonify({'status': 'success', 'message': 'Transport flat rate updated successfully.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

@app.route('/admin/reset-student-fee/<student_id>', methods=['GET', 'POST'])
def reset_student_fee(student_id):
    if 'user' in session and session['role'] == 'admin':
        try:
            conn = get_db_connection()
            # Fetch the student details to check campus and calculate standard rates
            student = conn.execute('''
                SELECT user_id, class, branch, take_school, take_coaching, take_day_hostel, take_car, enrollment_type, remaining_fee, monthly_fee, readmission_fee 
                FROM student_info 
                WHERE user_id = ?
            ''', (student_id,)).fetchone()
            
            if not student:
                conn.close()
                flash('Student not found.')
                return redirect(url_for('fee_matrix'))
                
            if session.get('branch'):
                if student['branch'] != session['branch']:
                    conn.close()
                    flash('Permission denied: Student does not belong to your campus.')
                    return redirect(url_for('fee_matrix'))
            
            # Reset overrides to 0.0 (or default) and is_custom_fee to 0
            conn.execute('''
                UPDATE student_info
                SET is_custom_fee = 0,
                    tuition_fee = 0.0,
                    transport_fee = 0.0,
                    lab_library_fee = 0.0,
                    academic_discount = 0.0,
                    room_rent = 0.0,
                    mess_food_charges = 0.0,
                    utility_cost = 0.0,
                    security_deposit = 0.0,
                    coaching_combo_fee = 0.0,
                    study_material_charges = 0.0,
                    exam_test_series_fee = 0.0,
                    combo_discount = 0.0,
                    school_tax_rate = 0.0,
                    hostel_tax_rate = 0.05,
                    coaching_tax_rate = 0.0
                WHERE user_id = ?
            ''', (student_id,))
            
            # Calculate standard class fees using templates since overrides are now 0.0 and is_custom_fee is 0
            bd = calculate_student_fees_breakdown({
                'class': student['class'],
                'branch': student['branch'],
                'enrollment_type': student['enrollment_type'],
                'take_car': student['take_car'],
                'take_school': student['take_school'],
                'take_coaching': student['take_coaching'],
                'take_day_hostel': student['take_day_hostel'],
                'is_custom_fee': 0
            }, conn)
            m_fee = bd['total_fee']
            
            # Fetch default admission/readmission rates from classes table
            class_row = conn.execute("SELECT * FROM classes WHERE name = ? AND branch = ?", (student['class'], student['branch'])).fetchone()
            a_fee = 0.0
            r_fee = 0.0
            if student['take_day_hostel']:
                a_fee = class_row['admission_fee_hostel'] if class_row else 0.0
                r_fee = class_row['readmission_fee_hostel'] if class_row else 0.0
            elif student['take_coaching']:
                a_fee = class_row['admission_fee_coaching'] if class_row else 0.0
                r_fee = class_row['readmission_fee_coaching'] if class_row else 0.0
            elif student['take_school']:
                a_fee = class_row['admission_fee'] if class_row else 0.0
                r_fee = class_row['readmission_fee_school'] if class_row else 0.0
                
            # Update monthly_fee, admission_fee, readmission_fee to standard rates in student_info
            conn.execute('''
                UPDATE student_info
                SET monthly_fee = ?, admission_fee = ?, readmission_fee = ?
                WHERE user_id = ?
            ''', (m_fee, a_fee, r_fee, student_id))
            
            # Sync ledger and dues to prevent historical shifting
            old_monthly_fee = float(student['monthly_fee']) if student['monthly_fee'] is not None else 0.0
            old_readmission_fee = float(student['readmission_fee']) if student['readmission_fee'] is not None else 0.0
            old_remaining_fee = float(student['remaining_fee']) if student['remaining_fee'] is not None else 0.0
            
            new_remaining_fee = old_remaining_fee + (m_fee - old_monthly_fee) + (r_fee - old_readmission_fee)
                
            sync_student_ledger_and_dues(conn, student_id, submitted_remaining_fee=new_remaining_fee, force_align_prev_dues=True)
            
            conn.commit()
            conn.close()
            flash('Student fee reset to regular rates successfully.')
        except Exception as e:
            flash(f'Error resetting student fee: {e}')
        return redirect(url_for('fee_matrix'))
    return redirect(url_for('home'))

@app.route('/admin/re-trigger-monthly-fees', methods=['POST'])
def re_trigger_monthly_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        try:
            students = conn.execute("SELECT id FROM users WHERE role = 'student'").fetchall()
            student_ids = [student['id'] for student in students]
            
            max_month_end = conn.execute("SELECT MAX(month_end_billing_count) FROM student_info").fetchone()[0] or 0
            max_year_end = conn.execute("SELECT MAX(year_end_billing_count) FROM student_info").fetchone()[0] or 0
            transport_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
            flat_transport_fee = float(transport_row['flat_rate']) if transport_row else 400.0
            
            count = 0
            failed = 0
            for student_id in student_ids:
                try:
                    sync_student_ledger_and_dues(
                        conn, 
                        student_id,
                        max_month_end=max_month_end,
                        max_year_end=max_year_end,
                        flat_transport_fee=flat_transport_fee
                    )
                    conn.commit()
                    count += 1
                except Exception as e:
                    conn.rollback()
                    print(f" [RE-TRIGGER ERROR] Failed for student {student_id}: {e}")
                    failed += 1
            
            if failed > 0:
                flash(f'Synced monthly dues for {count} student(s). Failed for {failed} student(s).')
            else:
                flash(f'Successfully re-triggered and synced monthly dues for {count} student(s).')
                
            send_activity_notification("Re-trigger Current Month Dues", f"Manually re-triggered outstanding monthly dues synchronization for {count} students.")
        except Exception as e:
            flash(f'Failed to re-trigger monthly fees: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/re-trigger-yearly-fees', methods=['POST'])
def re_trigger_yearly_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        try:
            students = conn.execute("SELECT id FROM users WHERE role = 'student'").fetchall()
            student_ids = [student['id'] for student in students]
            
            max_month_end = conn.execute("SELECT MAX(month_end_billing_count) FROM student_info").fetchone()[0] or 0
            max_year_end = conn.execute("SELECT MAX(year_end_billing_count) FROM student_info").fetchone()[0] or 0
            transport_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
            flat_transport_fee = float(transport_row['flat_rate']) if transport_row else 400.0
            
            count = 0
            failed = 0
            for student_id in student_ids:
                try:
                    sync_student_ledger_and_dues(
                        conn, 
                        student_id,
                        max_month_end=max_month_end,
                        max_year_end=max_year_end,
                        flat_transport_fee=flat_transport_fee
                    )
                    conn.commit()
                    count += 1
                except Exception as e:
                    conn.rollback()
                    print(f" [RE-TRIGGER ERROR] Failed for student {student_id}: {e}")
                    failed += 1
            
            if failed > 0:
                flash(f'Synced yearly dues for {count} student(s). Failed for {failed} student(s).')
            else:
                flash(f'Successfully re-triggered and synced yearly dues for {count} student(s).')
                
            send_activity_notification("Re-trigger Current Year Dues", f"Manually re-triggered outstanding yearly dues synchronization for {count} students.")
        except Exception as e:
            flash(f'Failed to re-trigger yearly fees: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/post-monthly-fees', methods=['POST'])
def post_monthly_fees():
    if 'user' in session and session['role'] == 'admin':
        from datetime import datetime
        month = datetime.now().strftime('%B')
        year = datetime.now().strftime('%Y')
        
        conn = get_db_connection()
        try:
            count = run_monthly_billing(conn, month, year)
            conn.commit()
            flash(f'Successfully posted monthly fees for {count} active student(s).')
            send_activity_notification("Month End Billing", f"Triggered monthly billing for {month} {year}. Billed {count} students.")
        except Exception as e:
            conn.rollback()
            flash(f'Failed to run Month End billing: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/update-total-due', methods=['POST'])
def update_total_due():
    if 'user' not in session or session['role'] != 'admin':
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
        
    data = request.json
    student_id = data.get('student_id')
    new_total_due = data.get('new_total_due')
    
    if student_id is None or new_total_due is None:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400
        
    try:
        new_total_due = float(new_total_due)
        conn = get_db_connection()
        
        student = conn.execute("SELECT * FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
        if not student:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Student not found'}), 404
            
        student_dict = dict(student)
        max_month_end = conn.execute("SELECT MAX(month_end_billing_count) FROM student_info").fetchone()[0] or 0
        max_year_end = conn.execute("SELECT MAX(year_end_billing_count) FROM student_info").fetchone()[0] or 0
        
        curr_month_count = student_dict.get('month_end_billing_count') or 0
        curr_year_count = student_dict.get('year_end_billing_count') or 0
        
        billing_month_count = max_month_end if curr_month_count < max_month_end else curr_month_count
        billing_year_count = max_year_end if curr_year_count < max_year_end else curr_year_count
        
        bd = calculate_student_fees_breakdown(student_dict, conn=conn)
        monthly_fee_val = float(bd['total_fee'] or 0.0)
        
        take_coaching = int(student_dict.get('take_coaching') or 0)
        take_day_hostel = int(student_dict.get('take_day_hostel') or 0)
        
        expected_readm = float(student_dict.get('readmission_fee') or 0.0)
        if not student_dict.get('is_custom_fee'):
            matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
            if matrix:
                if take_day_hostel:
                    expected_readm = float(matrix['hostel_readmission'] or 0.0)
                elif take_coaching:
                    expected_readm = float(matrix['coaching_readmission'] or 0.0)
                else:
                    expected_readm = float(matrix['school_readmission'] or 0.0)
            else:
                cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
                if cls_row:
                    if take_day_hostel:
                        expected_readm = float(cls_row['readmission_fee_hostel'] or 0.0)
                    elif take_coaching:
                        expected_readm = float(cls_row['readmission_fee_coaching'] or 0.0)
                    else:
                        expected_readm = float(cls_row['readmission_fee_school'] or 0.0)
                        
        readmission_fee_val = float(student_dict.get('readmission_fee') or 0.0) if student_dict.get('is_custom_fee') == 1 else expected_readm
        
        total_paid = conn.execute("SELECT SUM(amount) FROM fees WHERE student_id = ? AND status = 'Paid'", (student_id,)).fetchone()[0] or 0.0
        
        new_prev_dues = new_total_due - (monthly_fee_val * billing_month_count) - (readmission_fee_val * billing_year_count) + total_paid
        
        conn.execute("UPDATE student_info SET prev_dues = ? WHERE user_id = ?", (new_prev_dues, student_id))
        
        sync_student_ledger_and_dues(conn, student_id)
        conn.commit()
        
        updated_student = conn.execute("SELECT remaining_fee FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
        final_remaining_fee = updated_student['remaining_fee']
        
        conn.close()
        send_activity_notification("Total Due Adjusted", f"Total due for student ID {student_id} manually adjusted to {new_total_due}.")
        return jsonify({'status': 'success', 'new_remaining_fee': final_remaining_fee, 'new_prev_dues': new_prev_dues})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/undo-monthly-fees', methods=['POST'])
def undo_monthly_fees():
    if 'user' in session and session['role'] == 'admin':
        from datetime import datetime
        month = datetime.now().strftime('%B')
        year = datetime.now().strftime('%Y')
        
        conn = get_db_connection()
        try:
            count = undo_monthly_billing(conn, month, year)
            conn.commit()
            flash(f'Successfully reverted monthly billing entries for {count} records.')
            send_activity_notification("Undo Month End Billing", f"Reverted monthly billing runs for {month} {year}. Restored dues balance for {count} records.")
        except Exception as e:
            conn.rollback()
            flash(f'Failed to undo billing: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/post-year-end-fees', methods=['POST'])
def post_year_end_fees():
    if 'user' in session and session['role'] == 'admin':
        from datetime import datetime
        year = datetime.now().strftime('%Y')
        
        conn = get_db_connection()
        try:
            count = run_year_end_billing(conn, year)
            conn.commit()
            flash(f'Successfully posted Year End Re-admission fees for {count} active student(s).')
            send_activity_notification("Year End Billing", f"Triggered Year End readmission billing for {year}. Billed {count} students.")
        except Exception as e:
            conn.rollback()
            flash(f'Failed to run Year End billing: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/undo-year-end-fees', methods=['POST'])
def undo_year_end_fees():
    if 'user' in session and session['role'] == 'admin':
        from datetime import datetime
        year = datetime.now().strftime('%Y')
        
        conn = get_db_connection()
        try:
            count = undo_year_end_billing(conn, year)
            conn.commit()
            flash(f'Successfully reverted Year End billing entries for {count} records.')
            send_activity_notification("Undo Year End Billing", f"Reverted Year End billing runs for {year}. Restored dues balance for {count} records.")
        except Exception as e:
            conn.rollback()
            flash(f'Failed to undo Year End billing: {e}')
        finally:
            conn.close()
    else:
        flash('Access denied.')
    return redirect(url_for('audit_report'))

@app.route('/admin/update-subject-marks', methods=['POST'])
def update_subject_marks():
    if 'user' in session and session['role'] == 'admin':
        subject_id = request.form.get('subject_id')
        try:
            fm_1st = float(request.form.get('full_marks_1st', 50.0) or 50.0)
            fm_2nd = float(request.form.get('full_marks_2nd', 50.0) or 50.0)
            fm_annual = float(request.form.get('full_marks_annual', 100.0) or 100.0)

            def parse_float_opt(val):
                if val is not None and val.strip() != '':
                    try:
                        return float(val)
                    except ValueError:
                        return None
                return None

            oral_1st = parse_float_opt(request.form.get('oral_marks_1st'))
            oral_2nd = parse_float_opt(request.form.get('oral_marks_2nd'))
            oral_annual = parse_float_opt(request.form.get('oral_marks_annual'))

            written_1st = (fm_1st - oral_1st) if oral_1st is not None else None
            written_2nd = (fm_2nd - oral_2nd) if oral_2nd is not None else None
            ct_annual = (fm_annual * 0.1) if oral_annual is not None else None
            written_annual = (fm_annual - oral_annual - ct_annual) if oral_annual is not None else None

            conn = get_db_connection()
            conn.execute("""
                UPDATE subjects 
                SET full_marks = ?, full_marks_1st = ?, full_marks_2nd = ?, full_marks_annual = ?,
                    oral_marks_1st = ?, written_marks_1st = ?,
                    oral_marks_2nd = ?, written_marks_2nd = ?,
                    oral_marks_annual = ?, written_marks_annual = ?,
                    ct_marks_annual = ?
                WHERE id = ?
            """, (
                fm_annual, fm_1st, fm_2nd, fm_annual,
                oral_1st, written_1st,
                oral_2nd, written_2nd,
                oral_annual, written_annual,
                ct_annual, subject_id
            ))
            conn.commit()
            conn.close()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'success', 'message': 'Subject full marks updated successfully!'})
            flash('Subject full marks updated successfully!')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'error', 'message': str(e)})
            flash(f'Failed to update full marks: {e}')
    return redirect(url_for('academics_setting'))


@app.route('/admin/upload-document', methods=['POST'])
def upload_document():
    if 'user' in session and session['role'] == 'admin':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        file = request.files.get('document_file')
        
        if not title or not file:
            flash('Title and file are required.')
            return redirect(url_for('academics_setting'))
            
        if file:
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'documents')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join('static', 'uploads', 'documents', filename).replace('\\', '/')
            local_path = os.path.join(app.root_path, 'static', 'uploads', 'documents', filename)
            file.save(local_path)
            upload_file_to_drive_and_map(local_path, filename, file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_DOCUMENTS'))
            
            conn = get_db_connection()
            conn.execute("INSERT INTO registration_documents (title, description, file_path) VALUES (?, ?, ?)", (title, description, file_path))
            conn.commit()
            conn.close()
            flash('Document uploaded successfully!')
    return redirect(url_for('academics_setting'))

@app.route('/admin/delete-document', methods=['POST'])
def delete_document():
    if 'user' in session and session['role'] == 'admin':
        doc_id = request.form.get('doc_id')
        conn = get_db_connection()
        doc = conn.execute("SELECT * FROM registration_documents WHERE id = ?", (doc_id,)).fetchone()
        if doc:
            try:
                filename = os.path.basename(doc['file_path'])
                drive_file_id = None
                row = conn.execute("SELECT drive_file_id FROM drive_mappings WHERE filename = ?", (filename,)).fetchone()
                if row and row['drive_file_id']:
                    drive_file_id = row['drive_file_id']
                
                # Delete mapping and registration document first to release DB lock early
                conn.execute("DELETE FROM drive_mappings WHERE filename = ?", (filename,))
                conn.execute("DELETE FROM registration_documents WHERE id = ?", (doc_id,))
                conn.commit()
                conn.close()
                
                # Perform Drive and disk deletion after committing
                if drive_file_id:
                    delete_from_google_drive(drive_file_id)
                
                file_abs_path = os.path.join(app.root_path, doc['file_path'])
                if os.path.exists(file_abs_path):
                    os.remove(file_abs_path)
            except Exception as e:
                print(f"Error deleting file from disk/drive: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'success', 'message': 'Document deleted successfully!'})
            flash('Document deleted successfully!')
        else:
            conn.close()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'status': 'error', 'message': 'Document not found.'})
            flash('Document not found.')
    return redirect(url_for('academics_setting'))

@app.route('/admin/student-promotion', methods=['GET', 'POST'])
def student_promotion():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        
        # Determine branch filter
        if session.get('branch'):
            branch_filter = session['branch']
        else:
            branch_filter = request.args.get('branch', 'bhogram').strip().lower()
            if branch_filter not in ['surangapur', 'bhogram']:
                branch_filter = 'bhogram'
                
        class_filter = normalize_class_name(request.args.get('class_filter', '').strip())

        classes = get_all_classes(conn, branch=branch_filter)

        if request.method == 'POST':
            student_ids = request.form.getlist('student_ids')
            new_class = normalize_class_name(request.form.get('new_class', '').strip())
            new_section = request.form.get('new_section', '').strip()
            
            if not student_ids:
                flash('Error: No students selected for promotion.')
                conn.close()
                return redirect(url_for('student_promotion', branch=branch_filter, class_filter=class_filter))
                
            if not new_class:
                flash('Error: Please specify the target new class.')
                conn.close()
                return redirect(url_for('student_promotion', branch=branch_filter, class_filter=class_filter))
                
            success_count = 0
            for student_id in student_ids:
                # Fetch student info to get branch and opt-in settings
                student = conn.execute('''
                    SELECT branch, take_school, take_coaching, take_day_hostel, take_car, mode_of_admission, is_custom_fee, monthly_fee
                    FROM student_info
                    WHERE user_id = ?
                ''', (student_id,)).fetchone()
                
                if not student:
                    continue
                    
                # Security check for Branch Admin
                if session.get('branch') and student['branch'] != session['branch']:
                    continue
                
                if student['is_custom_fee']:
                    target_monthly_fee = student['monthly_fee']
                else:
                    take_school = student['take_school'] or 0
                    take_coaching = student['take_coaching'] or 0
                    take_day_hostel = student['take_day_hostel'] or 0
                    take_car = student['take_car'] or 0
                    mode_of_admission = student['mode_of_admission'] or ('Day Hostel' if take_day_hostel else ('School with Coaching' if take_coaching else 'School'))
                    
                    target_monthly_fee = calculate_default_monthly_fee(
                        class_name=new_class,
                        mode_of_admission=mode_of_admission,
                        coaching_opted=bool(take_coaching),
                        car_opted=bool(take_car),
                        branch=branch_filter,
                        conn=conn
                    )
                
                # Update class, optional section, and monthly fee
                if new_section:
                    conn.execute("UPDATE student_info SET class = ?, section = ?, monthly_fee = ? WHERE user_id = ?", 
                                 (new_class, new_section, target_monthly_fee, student_id))
                else:
                    conn.execute("UPDATE student_info SET class = ?, section = NULL, monthly_fee = ? WHERE user_id = ?", 
                                 (new_class, target_monthly_fee, student_id))
                                 
                # Update historical marks table class_name to prevent mismatch/stale data
                conn.execute("UPDATE marks SET class_name = ? WHERE student_id = ?", (new_class, student_id))
                # Also update certificates
                conn.execute("UPDATE certificates SET class_name = ? WHERE recipient_id = ? AND recipient_type = 'student'", (new_class, student_id))
                
                try:
                    bill_readmission_fee(conn, student_id, new_class, student['branch'], student['take_coaching'], student['take_day_hostel'])
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to auto-bill readmission fee: {e}")
                
                try:
                    sync_student_ledger_and_dues(conn, student_id)
                except Exception as e:
                    print(f" [BILLING ERROR] Failed to sync student dues in promotion: {e}")
                
                success_count += 1
                
            try:
                sync_classes(conn)
            except Exception as e:
                print(f" [DB MIGRATE ERROR] sync_classes failed in student_promotion: {e}")
            conn.commit()
            if success_count > 0:
                flash(f'Successfully promoted {success_count} student(s) to Class {new_class}!')
            else:
                flash('No students were promoted.')
            conn.close()
            return redirect(url_for('student_promotion', branch=branch_filter, class_filter=class_filter))

        # Query students matching filters
        if class_filter:
            db_classes = get_db_class_names(class_filter)
            placeholders = ', '.join(['?'] * len(db_classes))
            if branch_filter:
                students = conn.execute(f'''
                    SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, si.section, si.unique_code 
                    FROM users u 
                    JOIN student_info si ON u.id = si.user_id 
                    WHERE u.role = 'student' AND LOWER(si.branch) = LOWER(?) AND si.class IN ({placeholders})
                    ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
                ''', [branch_filter] + db_classes).fetchall()
            else:
                students = conn.execute(f'''
                    SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name, si.section, si.unique_code 
                    FROM users u 
                    JOIN student_info si ON u.id = si.user_id 
                    WHERE u.role = 'student' AND si.class IN ({placeholders})
                    ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
                ''', db_classes).fetchall()
        else:
            students = []

        conn.close()
        return render_template(
            'admin/student_promotion.html', 
            students=students, 
            classes=classes, 
            class_filter=class_filter, 
            branch_filter=branch_filter,
            role=session['role'], 
            logo_url=LOGO_URL
        )
    return redirect(url_for('home'))

@app.route('/admin/admit-card')
@login_required
def admit_card():
    user = get_session_user()
    if not user:
        return redirect(url_for('login', user_type='student'))
        
    conn = get_db_connection()
    all_terms = get_all_academic_terms(conn)
    student = None
    term_name = request.args.get('term', '1st Unit')
    
    if user['role'] in ['admin', 'teacher']:
        student_id = request.args.get('student_id')
        if student_id:
            student = conn.execute('''
                SELECT u.username, si.full_name, si.class, si.roll_number, si.branch, si.guardian_name 
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE u.id = ?
            ''', (student_id,)).fetchone()
            
            # Check permissions for Branch Admin
            if session.get('branch') and student and student['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: Student does not belong to your campus.')
                return redirect(url_for('dashboard'))
        else:
            if session.get('branch'):
                students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
            else:
                students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
            conn.close()
            return render_template('admin/select_student.html', students=students, action='admit-card', role=user['role'], all_terms=all_terms)
    else:
        # Check student permission
        student = conn.execute('''
            SELECT u.username, si.full_name, si.class, si.roll_number, si.branch, si.allow_admit, si.guardian_name 
            FROM users u 
            LEFT JOIN student_info si ON u.id = si.user_id 
            WHERE u.id = ?
        ''', (user['id'],)).fetchone()

    # Get the latest schedule from DB
    schedule_image = None
    schedule_list = []
    if student:
        branch = student['branch'] or 'bhogram'
        class_name = student['class']
        sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (class_name, term_name, branch)).fetchone()
        if not sched_row and class_name and 'nursery' in class_name.lower():
            sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) LIKE '%nursery%' AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (term_name, branch)).fetchone()
        if sched_row:
            schedule_image = sched_row['schedule_image']
            schedule_text = sched_row['schedule_text']
            if schedule_text:
                try:
                    schedule_list = json.loads(schedule_text)
                except Exception:
                    pass

    # Check student permission after fetching schedule, if role is student
    if user['role'] == 'student':
        if not student or not student['allow_admit']:
            conn.close()
            return render_template(
                'admin/admit_locked.html',
                role=user['role'],
                student=student,
                term_name=term_name,
                schedule_image=schedule_image,
                schedule_list=schedule_list,
                logo_url=LOGO_URL,
                all_terms=all_terms
            )

    import datetime
    current_year = datetime.datetime.now().year

    conn.close()
    return render_template(
        'admin/admit_card.html',
        student=student,
        role=user['role'],
        term_name=term_name,
        schedule_image=schedule_image,
        schedule_list=schedule_list,
        logo_url=LOGO_URL,
        current_year=current_year,
        all_terms=all_terms
    )

@app.route('/admin/admit-card/bulk', methods=['POST'])
@login_required
def bulk_admit_card():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return redirect(url_for('home'))
        
    class_name = request.form.get('class_name')
    term_name = request.form.get('term_name')
    cards_per_page = int(request.form.get('cards_per_page', 2))
    
    branch = 'bhogram'
    if session.get('branch'):
        branch = session['branch']
        
    conn = get_db_connection()
    
    # Check if a schedule image is uploaded or manual schedule is sent
    schedule_mode = request.form.get('schedule_mode', 'image')
    if schedule_mode == 'manual':
        schedule_text_json = request.form.get('schedule_text_json', '[]')
        conn.execute('''
            INSERT INTO exam_schedules (class_name, term_name, branch, schedule_image, schedule_text)
            VALUES (?, ?, ?, NULL, ?)
            ON CONFLICT(class_name, term_name, branch) DO UPDATE SET schedule_image = NULL, schedule_text = excluded.schedule_text
        ''', (class_name, term_name, branch, schedule_text_json))
        conn.commit()
    else:
        if 'schedule_image' in request.files:
            file = request.files['schedule_image']
            if file and file.filename != '':
                import time
                filename = secure_filename(f"{int(time.time())}_{file.filename}")
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'exam_schedules')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                
                conn.execute('''
                    INSERT INTO exam_schedules (class_name, term_name, branch, schedule_image, schedule_text)
                    VALUES (?, ?, ?, ?, NULL)
                    ON CONFLICT(class_name, term_name, branch) DO UPDATE SET schedule_image = excluded.schedule_image, schedule_text = NULL
                ''', (class_name, term_name, branch, filename))
                conn.commit()

    # Get the latest schedule from DB
    sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (class_name, term_name, branch)).fetchone()
    if not sched_row and class_name and 'nursery' in class_name.lower():
        sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = 'nursery' AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (term_name, branch)).fetchone()
    schedule_image = sched_row['schedule_image'] if sched_row else None
    schedule_text = sched_row['schedule_text'] if sched_row else None
    
    schedule_list = []
    if schedule_text:
        try:
            schedule_list = json.loads(schedule_text)
        except Exception:
            pass
            
    db_classes = get_db_class_names(class_name)
    placeholders = ', '.join(['?'] * len(db_classes))
    students = conn.execute(f'''
        SELECT u.id, u.username, si.full_name, si.roll_number, si.branch 
        FROM users u 
        JOIN student_info si ON u.id = si.user_id 
        WHERE u.role = 'student' AND si.class IN ({placeholders}) AND si.branch = ?
        ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
    ''', db_classes + [branch]).fetchall()
    
    conn.close()
    
    return render_template(
        'admin/bulk_admit_card.html',
        students=students,
        class_name=class_name,
        term_name=term_name,
        cards_per_page=cards_per_page,
        schedule_image=schedule_image,
        schedule_list=schedule_list,
        logo_url=LOGO_URL
    )

@app.route('/admin/exam-routine/bulk', methods=['POST'])
@login_required
def bulk_exam_routine():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return redirect(url_for('home'))
        
    class_name = request.form.get('class_name')
    term_name = request.form.get('term_name')
    cards_per_page = int(request.form.get('cards_per_page', 2))
    
    branch = 'bhogram'
    if session.get('branch'):
        branch = session['branch']
        
    conn = get_db_connection()
    
    sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (class_name, term_name, branch)).fetchone()
    if not sched_row and class_name and 'nursery' in class_name.lower():
        sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = 'nursery' AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (term_name, branch)).fetchone()
    schedule_image = sched_row['schedule_image'] if sched_row else None
    schedule_text = sched_row['schedule_text'] if sched_row else None
    
    schedule_list = []
    if schedule_text:
        try:
            schedule_list = json.loads(schedule_text)
        except Exception:
            pass
            
    conn.close()
    
    import datetime
    current_year = datetime.datetime.now().year
    
    return render_template(
        'admin/bulk_routine.html',
        class_name=class_name,
        term_name=term_name,
        cards_per_page=cards_per_page,
        schedule_image=schedule_image,
        schedule_list=schedule_list,
        logo_url=LOGO_URL,
        current_year=current_year
    )

@app.route('/exam-routine/print/<class_name>')
@login_required
def print_exam_routine(class_name):
    user = get_session_user()
    term_name = request.args.get('term', '1st Unit')
    branch = session.get('branch', 'bhogram')
    if user['role'] == 'student':
        conn = get_db_connection()
        student = conn.execute("SELECT class, branch FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
        conn.close()
        if student:
            class_name = student['class']
            branch = student['branch'] or 'bhogram'
            
    conn = get_db_connection()
    sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (class_name, term_name, branch)).fetchone()
    if not sched_row and class_name and 'nursery' in class_name.lower():
        sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = 'nursery' AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (term_name, branch)).fetchone()
    conn.close()
    
    schedule_image = sched_row['schedule_image'] if sched_row else None
    schedule_text = sched_row['schedule_text'] if sched_row else None
    schedule_list = []
    if schedule_text:
        try:
            schedule_list = json.loads(schedule_text)
        except Exception:
            pass
            
    import datetime
    current_year = datetime.datetime.now().year
    
    return render_template(
        'admin/bulk_routine.html',
        class_name=class_name,
        term_name=term_name,
        cards_per_page=1,
        schedule_image=schedule_image,
        schedule_list=schedule_list,
        logo_url=LOGO_URL,
        current_year=current_year,
        single_print=True
    )

@app.route('/api/exam-schedule/all')
def api_exam_schedule_all():
    term_name = request.args.get('term', '1st Unit')
    branch = request.args.get('branch', 'bhogram')
    conn = get_db_connection()
    schedules = conn.execute("SELECT class_name, schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?)) ORDER BY class_name", (term_name, branch)).fetchall()
    conn.close()
    
    result = []
    for s in schedules:
        result.append({
            'class_name': s['class_name'],
            'schedule_image': s['schedule_image'],
            'schedule_text': s['schedule_text']
        })
        
    return jsonify({
        'status': 'success',
        'schedules': result
    })

@app.route('/api/exam-schedule/<class_name>')
def api_exam_schedule(class_name):
    term_name = request.args.get('term', '1st Unit')
    branch = request.args.get('branch', 'bhogram')
    conn = get_db_connection()
    sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (class_name, term_name, branch)).fetchone()
    if not sched_row and class_name and 'nursery' in class_name.lower():
        sched_row = conn.execute("SELECT schedule_image, schedule_text FROM exam_schedules WHERE LOWER(TRIM(class_name)) = 'nursery' AND LOWER(TRIM(term_name)) = LOWER(TRIM(?)) AND LOWER(TRIM(branch)) = LOWER(TRIM(?))", (term_name, branch)).fetchone()
    conn.close()
    
    if sched_row:
        return jsonify({
            'status': 'success',
            'schedule_image': sched_row['schedule_image'],
            'schedule_text': sched_row['schedule_text']
        })
    return jsonify({'status': 'error', 'message': 'No schedule found'})


@app.route('/admin/id-card')
def id_card():
    if 'user' in session:
        conn = get_db_connection()
        all_terms = get_all_academic_terms(conn)
        user = conn.execute("SELECT id, role FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        if user['role'] in ['admin', 'teacher']:
            student_id = request.args.get('student_id')
            if student_id:
                student = conn.execute('''
                    SELECT u.id, u.username, si.full_name, si.class, si.roll_number, si.branch, u.email,
                           si.guardian_name, si.dob, si.section, si.blood_group,
                           si.village, si.post_office, si.police_station, si.district, si.phone_number, si.photo_path
                    FROM users u 
                    JOIN student_info si ON u.id = si.user_id 
                    WHERE u.id = ?
                ''', (student_id,)).fetchone()
                
                # Check permissions for Branch Admin
                if session.get('branch') and student and student['branch'] != session['branch']:
                    conn.close()
                    flash('Permission denied: Student does not belong to your campus.')
                    return redirect(url_for('dashboard'))
 
                conn.close()
                return render_template('admin/id_card.html', student=student, role=user['role'])
            else:
                if session.get('branch'):
                    students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
                else:
                    students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
                conn.close()
                return render_template('admin/select_student.html', students=students, action='id-card', role=user['role'], all_terms=all_terms)
        else:
            student = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.class, si.roll_number, si.branch, u.email,
                       si.guardian_name, si.dob, si.section, si.blood_group,
                       si.village, si.post_office, si.police_station, si.district, si.phone_number, si.photo_path
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.id = ?
            ''', (user['id'],)).fetchone()
            conn.close()
            return render_template('admin/id_card.html', student=student, role=user['role'])
    return redirect(url_for('home'))

# ================= CERTIFICATES MANAGEMENT =================

@app.route('/admin/manage-certificates')
def manage_certificates():
    if 'user' not in session or session.get('role') != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    branch = session.get('branch')
    if branch:
        certs = conn.execute("SELECT * FROM certificates WHERE branch = ? ORDER BY created_at DESC", (branch,)).fetchall()
    else:
        certs = conn.execute("SELECT * FROM certificates ORDER BY created_at DESC").fetchall()
    conn.close()
    
    return render_template('admin/manage_certificates.html', certs=certs, role=session.get('role'))


@app.route('/admin/create-certificate', methods=['GET', 'POST'])
def create_certificate():
    if 'user' not in session or session.get('role') != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    branch = session.get('branch')
    
    if request.method == 'POST':
        recipient_type = request.form.get('recipient_type')
        recipient_id = request.form.get('recipient_id')
        recipient_name = request.form.get('recipient_name')
        father_name = request.form.get('father_name')
        class_name = request.form.get('class_name')
        section = request.form.get('section')
        roll_number = request.form.get('roll_number')
        title = request.form.get('title')
        subtitle = request.form.get('subtitle')
        reason_text = request.form.get('reason_text')
        position_text = request.form.get('position_text')
        event_name = request.form.get('event_name')
        congrats_text = request.form.get('congrats_text')
        date_text = request.form.get('date_text')
        signature_text = request.form.get('signature_text')
        theme_style = request.form.get('theme_style', 'classic')
        
        # Auto-fetch names if id is provided
        if recipient_id and recipient_id.strip():
            recipient_id = int(recipient_id)
            if recipient_type == 'student':
                student = conn.execute("SELECT si.full_name, si.guardian_name, si.class, si.section, si.roll_number FROM student_info si WHERE si.user_id = ?", (recipient_id,)).fetchone()
                if student:
                    if not recipient_name or not recipient_name.strip():
                        recipient_name = student['full_name']
                    if not father_name or not father_name.strip():
                        father_name = student['guardian_name']
                    if not class_name or not class_name.strip():
                        class_name = student['class']
                    if not section or not section.strip():
                        section = student['section']
                    if not roll_number or not roll_number.strip():
                        roll_number = student['roll_number']
            elif recipient_type == 'teacher':
                teacher = conn.execute("SELECT ti.full_name FROM teacher_info ti WHERE ti.user_id = ?", (recipient_id,)).fetchone()
                if teacher and (not recipient_name or not recipient_name.strip()):
                    recipient_name = teacher['full_name']
        else:
            recipient_id = None

        conn.execute('''
            INSERT INTO certificates (recipient_type, recipient_id, recipient_name, father_name, class_name, section, roll_number,
                                      title, subtitle, reason_text, position_text, event_name, congrats_text, date_text, signature_text, branch, theme_style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (recipient_type, recipient_id, recipient_name, father_name, class_name, section, roll_number,
              title, subtitle, reason_text, position_text, event_name, congrats_text, date_text, signature_text, branch or 'bhogram', theme_style))
        conn.commit()
        conn.close()
        
        flash('Certificate created successfully.')
        return redirect(url_for('manage_certificates'))
        
    # GET method
    # Fetch students
    if branch:
        students = conn.execute("SELECT u.id, si.full_name, si.class, si.roll_number, si.section FROM users u JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ? ORDER BY si.class, si.roll_number", (branch,)).fetchall()
        teachers = conn.execute("SELECT u.id, ti.full_name FROM users u JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher' ORDER BY ti.full_name").fetchall()
    else:
        students = conn.execute("SELECT u.id, si.full_name, si.class, si.roll_number, si.section FROM users u JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' ORDER BY si.class, si.roll_number").fetchall()
        teachers = conn.execute("SELECT u.id, ti.full_name FROM users u JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher' ORDER BY ti.full_name").fetchall()
        
    conn.close()
    return render_template('admin/create_certificate.html', students=students, teachers=teachers, role=session.get('role'))


@app.route('/admin/edit-certificate/<int:cert_id>', methods=['GET', 'POST'])
def edit_certificate(cert_id):
    if 'user' not in session or session.get('role') != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    branch = session.get('branch')
    
    cert = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    if not cert:
        conn.close()
        flash('Certificate not found.')
        return redirect(url_for('manage_certificates'))
        
    if branch and cert['branch'] != branch:
        conn.close()
        flash('Unauthorized access to branch data.')
        return redirect(url_for('manage_certificates'))
        
    if request.method == 'POST':
        recipient_type = request.form.get('recipient_type')
        recipient_id = request.form.get('recipient_id')
        recipient_name = request.form.get('recipient_name')
        father_name = request.form.get('father_name')
        class_name = request.form.get('class_name')
        section = request.form.get('section')
        roll_number = request.form.get('roll_number')
        title = request.form.get('title')
        subtitle = request.form.get('subtitle')
        reason_text = request.form.get('reason_text')
        position_text = request.form.get('position_text')
        event_name = request.form.get('event_name')
        congrats_text = request.form.get('congrats_text')
        date_text = request.form.get('date_text')
        signature_text = request.form.get('signature_text')
        theme_style = request.form.get('theme_style', 'classic')
        
        if recipient_id and recipient_id.strip():
            recipient_id = int(recipient_id)
            if recipient_type == 'student':
                student = conn.execute("SELECT si.full_name, si.guardian_name, si.class, si.section, si.roll_number FROM student_info si WHERE si.user_id = ?", (recipient_id,)).fetchone()
                if student:
                    if not recipient_name or not recipient_name.strip():
                        recipient_name = student['full_name']
                    if not father_name or not father_name.strip():
                        father_name = student['guardian_name']
                    if not class_name or not class_name.strip():
                        class_name = student['class']
                    if not section or not section.strip():
                        section = student['section']
                    if not roll_number or not roll_number.strip():
                        roll_number = student['roll_number']
            elif recipient_type == 'teacher':
                teacher = conn.execute("SELECT ti.full_name FROM teacher_info ti WHERE ti.user_id = ?", (recipient_id,)).fetchone()
                if teacher and (not recipient_name or not recipient_name.strip()):
                    recipient_name = teacher['full_name']
        else:
            recipient_id = None
            
        conn.execute('''
            UPDATE certificates SET recipient_type=?, recipient_id=?, recipient_name=?, father_name=?, class_name=?, section=?, roll_number=?,
                                   title=?, subtitle=?, reason_text=?, position_text=?, event_name=?, congrats_text=?, date_text=?, signature_text=?, theme_style=?
            WHERE id = ?
        ''', (recipient_type, recipient_id, recipient_name, father_name, class_name, section, roll_number,
              title, subtitle, reason_text, position_text, event_name, congrats_text, date_text, signature_text, theme_style, cert_id))
        conn.commit()
        conn.close()
        
        flash('Certificate updated successfully.')
        return redirect(url_for('manage_certificates'))
        
    # GET method
    if branch:
        students = conn.execute("SELECT u.id, si.full_name, si.class, si.roll_number, si.section FROM users u JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ? ORDER BY si.class, si.roll_number", (branch,)).fetchall()
        teachers = conn.execute("SELECT u.id, ti.full_name FROM users u JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher' ORDER BY ti.full_name").fetchall()
    else:
        students = conn.execute("SELECT u.id, si.full_name, si.class, si.roll_number, si.section FROM users u JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' ORDER BY si.class, si.roll_number").fetchall()
        teachers = conn.execute("SELECT u.id, ti.full_name FROM users u JOIN teacher_info ti ON u.id = ti.user_id WHERE u.role = 'teacher' ORDER BY ti.full_name").fetchall()
        
    conn.close()
    return render_template('admin/edit_certificate.html', cert=cert, students=students, teachers=teachers, role=session.get('role'))


@app.route('/admin/delete-certificate/<int:cert_id>', methods=['POST'])
def delete_certificate(cert_id):
    if 'user' not in session or session.get('role') != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    branch = session.get('branch')
    
    if branch:
        cert = conn.execute("SELECT id FROM certificates WHERE id = ? AND branch = ?", (cert_id, branch)).fetchone()
        if not cert:
            conn.close()
            flash('Certificate not found or unauthorized.')
            return redirect(url_for('manage_certificates'))
            
    conn.execute("DELETE FROM certificates WHERE id = ?", (cert_id,))
    conn.commit()
    conn.close()
    
    flash('Certificate deleted successfully.')
    return redirect(url_for('manage_certificates'))


@app.route('/admin/print-certificate/<int:cert_id>')
def print_certificate(cert_id):
    if 'user' not in session:
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    cert = conn.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,)).fetchone()
    
    # Check authorization (Admins can view all, Teachers can view their own, Students can view their own)
    role = session.get('role')
    user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
    
    if not cert:
        conn.close()
        flash('Certificate not found.')
        return redirect(url_for('dashboard'))
        
    if role == 'student' and (cert['recipient_type'] != 'student' or cert['recipient_id'] != user['id']):
        conn.close()
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    if role == 'teacher' and (cert['recipient_type'] != 'teacher' or cert['recipient_id'] != user['id']):
        conn.close()
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    if role == 'admin' and session.get('branch') and cert['branch'] != session.get('branch'):
        conn.close()
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    conn.close()
    return render_template('admin/print_certificate.html', cert=cert, logo_url=LOGO_URL)


@app.route('/student/my-certificates')
def student_certificates():
    if 'user' not in session or session.get('role') != 'student':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
    certs = conn.execute("SELECT * FROM certificates WHERE recipient_type = 'student' AND recipient_id = ? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    
    return render_template('student/my_certificates.html', certs=certs, role=session.get('role'))


@app.route('/teacher/my-certificates')
def teacher_certificates():
    if 'user' not in session or session.get('role') != 'teacher':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
    certs = conn.execute("SELECT * FROM certificates WHERE recipient_type = 'teacher' AND recipient_id = ? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    
    return render_template('teacher/my_certificates.html', certs=certs, role=session.get('role'))

@app.route('/teacher/complaints', methods=['GET', 'POST'])
def teacher_complaints():
    if 'user' not in session or session.get('role') != 'teacher':
        flash('Unauthorized access.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
    teacher_id = user['id']
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        class_name = request.form.get('class_name')
        complaint_text = request.form.get('complaint_text', '').strip()
        
        if not student_id or not class_name or not complaint_text:
            flash('All fields are required.', 'error')
        else:
            conn.execute('''
                INSERT INTO complaints (teacher_id, student_id, class_name, complaint_text)
                VALUES (?, ?, ?, ?)
            ''', (teacher_id, student_id, class_name, complaint_text))
            conn.commit()
            flash('Complaint submitted successfully!', 'success')
            conn.close()
            return redirect(url_for('teacher_complaints'))
            
    complaints = conn.execute('''
        SELECT c.*, COALESCE(si.full_name, u.username) as student_name 
        FROM complaints c
        JOIN users u ON c.student_id = u.id
        LEFT JOIN student_info si ON u.id = si.user_id
        WHERE c.teacher_id = ?
        ORDER BY c.created_at DESC
    ''', (teacher_id,)).fetchall()
    
    students_rows = conn.execute('''
        SELECT u.id, COALESCE(si.full_name, u.username) as name, si.class, si.branch
        FROM users u
        JOIN student_info si ON u.id = si.user_id
        WHERE u.role = 'student'
        ORDER BY si.class, name
    ''').fetchall()
    
    students_by_class = {}
    for row in students_rows:
        cls = row['class']
        if not cls:
            continue
        if cls not in students_by_class:
            students_by_class[cls] = []
        students_by_class[cls].append({
            'id': row['id'],
            'name': f"{row['name']} ({row['branch'].title() if row['branch'] else ''})"
        })
        
    conn.close()
    return render_template('teacher/complaints.html', 
                           complaints=complaints, 
                           students_by_class=students_by_class, 
                           role=session.get('role'))

@app.route('/admin/bulk-upload')
def bulk_upload():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        return render_template('admin/bulk_upload.html', role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/process-upload', methods=['POST'])
def process_upload(smart_type=None, smart_stream=None):
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        upload_type = smart_type or request.form.get('upload_type')
        if not smart_stream and ('file' not in request.files or request.files['file'].filename == ''):
            flash('No valid file selected')
            return redirect(url_for('bulk_upload'))
            
        def flexible_get(row_dict, aliases):
            for key, val in row_dict.items():
                if key in aliases and val:
                    return val
            return ''

        if smart_stream or (request.files.get('file') and request.files['file'].filename.endswith('.csv')):
            if smart_stream:
                stream = smart_stream
            else:
                stream = io.StringIO(request.files['file'].stream.read().decode("utf-8-sig", errors='ignore'), newline=None)
                
            csv_input = csv.DictReader(stream)
            conn = get_db_connection()
            c = conn.cursor()
            
            try:
                success_count = 0
                errors = []
                row_num = 1
                
                if upload_type == 'students':
                    aliases_name = ['NAME', 'FULL NAME', 'STUDENT NAME', 'U NAME']
                    aliases_phone = ['CONTACT NUM(O P)', 'CONTACT NUM(OP)', 'CONTACT NUMBER', 'PHONE', 'MOBILE', 'PHONE NUMBER', 'CONTACT']
                    aliases_guardian = ['FATHERS NAME', 'FATHER NAME', 'GUARDIANS NAME', 'GUARDIAN']
                    aliases_mother = ['MOTHERS NAME', 'MOTHER NAME', 'MOTHER']
                    aliases_dob = ['D O B', 'DOB', 'DATE OF BIRTH']
                    aliases_class = ['CLASS', 'GRADE', 'STANDARD']
                    aliases_village = ['VILLAGE', 'VILL', 'CITY']
                    aliases_po = ['POST OFFICE', 'P.O', 'PO']
                    aliases_ps = ['POLICE STATION', 'P.S', 'PS']
                    aliases_district = ['DISTRICT', 'DIST']
                    
                    for raw_row in csv_input:
                        row_num += 1
                        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
                        name = flexible_get(row, aliases_name)
                        if not name: 
                            errors.append(f"Row {row_num}: Missing Student Name. Skipped.")
                            continue
                        
                        phone = flexible_get(row, aliases_phone)
                        guardian_name = flexible_get(row, aliases_guardian)
                        dob = flexible_get(row, aliases_dob)
                        
                        # Find if THIS EXACT student already exists (to prevent duplicating on re-upload)
                        existing_user = None
                        existing_student_info = c.execute('''
                            SELECT user_id FROM student_info 
                            WHERE LOWER(full_name) = ? AND dob = ? AND LOWER(guardian_name) = ?
                        ''', (name.lower(), dob, guardian_name.lower())).fetchone()
                        
                        if existing_student_info:
                            existing_user = {'id': existing_student_info['user_id']}
                        
                        if not existing_user:
                            # New student, generate unique username
                            base_username = phone if phone and str(phone).strip() else name.replace(' ', '').lower() + str(random.randint(100, 999))
                            username = base_username
                            
                            # Ensure username is unique (handles siblings with same phone)
                            counter = 1
                            while True:
                                if not c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                                    break
                                # Collision! Append first name or a counter
                                first_name = name.split()[0].lower().replace('.', '')
                                if counter == 1:
                                    username = f"{base_username}_{first_name}"
                                else:
                                    username = f"{base_username}_{first_name}{counter}"
                                counter += 1
                            # Generate formatted password: Firstname@Year
                            first_name_formatted = name.split()[0].title().replace('.', '')
                            year = dob[-4:] if dob and len(dob) >= 4 and dob[-4:].isdigit() else "123"
                            password = f"{first_name_formatted}@{year}"
                            
                            c.execute("INSERT INTO users (username, password, role, security_key) VALUES (?, ?, ?, ?)",
                                      (username, hash_password(password), 'student', 'default-key'))
                            user_id = c.lastrowid
                        else:
                            user_id = existing_user['id']
                            # Generate and update formatted password for existing users too
                            first_name_formatted = name.split()[0].title().replace('.', '')
                            year = dob[-4:] if dob and len(dob) >= 4 and dob[-4:].isdigit() else "123"
                            password = f"{first_name_formatted}@{year}"
                            c.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(password), user_id))
                        
                        form_branch = request.form.get('target_branch')
                        raw_branch = flexible_get(row, ['BRANCH', 'CAMPUS'])
                        branch = form_branch.strip().lower() if form_branch else (raw_branch.strip().lower() if raw_branch else (session.get('branch') or 'bhogram'))
                        if branch not in BRANCHES:
                            branch = session.get('branch') or 'bhogram'
                        unique_code = generate_unique_student_code(c)
                        c.execute('''
                            INSERT OR REPLACE INTO student_info 
                            (user_id, branch, class, roll_number, full_name, date_of_admission, dob, guardian_name, mothers_name, phone_number, village, post_office, police_station, district, unique_code)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (user_id, branch, flexible_get(row, aliases_class), flexible_get(row, ['ROLL', 'ROLL NO', 'ROLL NUMBER']), name,
                              flexible_get(row, ['DATE OF AD', 'DATE OF ADMISSION', 'ADMISSION DATE']), dob, 
                              guardian_name, flexible_get(row, aliases_mother),
                              phone, flexible_get(row, aliases_village),
                              flexible_get(row, aliases_po), flexible_get(row, aliases_ps),
                              flexible_get(row, aliases_district), unique_code))
                        success_count += 1
                        
                    flash(f'Successfully added {success_count} students.')
                    for err in errors[:5]: flash(err)
                    if len(errors) > 5: flash(f"...and {len(errors) - 5} more errors.")
                
                elif upload_type == 'update_students':
                    aliases_name = ['NAME', 'FULL NAME', 'STUDENT NAME', 'U NAME']
                    aliases_roll = ['ROLL', 'ROLL NO', 'ROLL NUMBER', 'ROLL_NO', 'ROLL_NUMBER', 'R/NO']
                    aliases_guardian = ['GUARDIANS NAME', 'FATHERS NAME', 'FATHER NAME', 'GUARDIAN']

                    for raw_row in csv_input:
                        row_num += 1
                        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
                        name = flexible_get(row, aliases_name)
                        if not name:
                            errors.append(f"Row {row_num}: Missing Student Name. Skipped.")
                            continue
                        roll = flexible_get(row, aliases_roll)
                        guardian = flexible_get(row, aliases_guardian)
                        
                        if name:
                            # Match student by full name (ignoring spaces and case)
                            student_info = c.execute("SELECT user_id FROM student_info WHERE LOWER(REPLACE(full_name, ' ', '')) = ?", (name.lower().replace(' ', ''),)).fetchone()
                            
                            if student_info:
                                c.execute('''
                                    UPDATE student_info
                                    SET roll_number = ?, guardian_name = ?
                                    WHERE user_id = ?
                                ''', (roll, guardian, student_info['user_id']))
                                success_count += 1
                            else:
                                errors.append(f"Row {row_num}: Could not find existing student named '{name}'.")
                                
                    flash(f'Successfully updated {success_count} students.')
                    for err in errors[:5]: flash(err)
                    if len(errors) > 5: flash(f"...and {len(errors) - 5} more errors.")
                
                elif upload_type == 'teachers':
                    aliases_user = ['USERNAME', 'U NAME', 'LOGIN ID']
                    aliases_pass = ['PASSWORD', 'PASS']
                    aliases_name = ['NAME', 'FULL NAME', 'TEACHER NAME', 'TEACHER']
                    aliases_phone = ['PHONE NUMBER', 'PHONE', 'MOBILE', 'CONTACT']
                    aliases_qual = ['QUALIFICATION', 'DEGREE']
                    aliases_join = ['JOINING DATE', 'JOIN DATE', 'DATE OF JOINING']
                    aliases_address = ['ADDRESS', 'ADDR']

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
                        
                        c.execute("INSERT OR IGNORE INTO users (username, password, role, security_key, temp_password) VALUES (?, ?, ?, ?, ?)",
                                  (username, hash_password(password), 'teacher', 'default-key', password))
                        user_id_row = c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                        if not user_id_row: continue
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
                        
                    flash(f'Successfully processed {success_count} teacher records.')
                    for err in errors[5]: flash(err)
                    if len(errors) > 5: flash(f"...and {len(errors) - 5} more errors.")
                    
                elif upload_type == 'marks':
                    aliases_name = ['STUDENT_NAME', 'STUDENT NAME', 'NAME', 'FULL NAME', 'U NAME']
                    aliases_subject = ['SUBJECT', 'SUB']
                    aliases_marks = ['MARKS', 'MARK', 'SCORE', 'OBTAINED', 'GRADE']
                    aliases_total = ['TOTAL_MARKS', 'TOTAL MARKS', 'TOTAL', 'OUT OF', 'FULL MARKS']
                    aliases_term = ['TERM', 'EXAM', 'EXAM_TYPE', 'SEMESTER']

                    teacher = c.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
                    teacher_id = teacher['id'] if teacher else None

                    for raw_row in csv_input:
                        row_num += 1
                        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
                        name = flexible_get(row, aliases_name)
                        if not name:
                            errors.append(f"Row {row_num}: Missing Student Name. Skipped.")
                            continue
                            
                        subject = flexible_get(row, aliases_subject) or "General"
                        marks = flexible_get(row, aliases_marks)
                        total_marks = flexible_get(row, aliases_total) or "100"
                        term = flexible_get(row, aliases_term) or "Term 1"
                        
                        student_info = c.execute("SELECT user_id, class FROM student_info WHERE LOWER(REPLACE(full_name, ' ', '')) = ?", (name.lower().replace(' ', ''),)).fetchone()
                        
                        if student_info:
                            norm_term = term.strip()
                            if norm_term in ['1st Term', '1st Unit']:
                                norm_term = '1st Unit'
                            elif norm_term in ['2nd Term', '2nd Unit']:
                                norm_term = '2nd Unit'
                            elif norm_term in ['Annual Exam', 'Final Exam', 'Annual']:
                                norm_term = 'Final Exam'
                                
                            c.execute('''
                                INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                                    obtained_marks = excluded.obtained_marks,
                                    full_marks = excluded.full_marks,
                                    class_name = excluded.class_name,
                                    uploaded_by = excluded.uploaded_by,
                                    uploaded_at = CURRENT_TIMESTAMP
                            ''', (student_info['user_id'], student_info['class'] or 'One', norm_term, subject, marks, total_marks, teacher_id or 1))
                            success_count += 1
                        else:
                            errors.append(f"Row {row_num}: Could not find existing student named '{name}'.")
                            
                    sync_and_normalize_monthly_tests(conn)
                    flash(f'Successfully imported {success_count} mark records.')
                    for err in errors[:5]: flash(err)
                    if len(errors) > 5: flash(f"...and {len(errors) - 5} more errors.")
                    
                elif upload_type == 'routine':
                    for raw_row in csv_input:
                        row_num += 1
                        row = {str(k).strip().upper(): str(v).strip() for k, v in raw_row.items() if k}
                        
                        class_name = flexible_get(row, ['CLASS_NAME', 'CLASS'])
                        if not class_name:
                            errors.append(f"Row {row_num}: Missing Class Name. Skipped.")
                            continue
                            
                        c.execute('''
                            INSERT INTO class_routine 
                            (branch, class_name, day, start_time, end_time, subject, teacher_name)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (flexible_get(row, ['BRANCH']), class_name, flexible_get(row, ['DAY']),
                              flexible_get(row, ['START_TIME', 'START TIME']), flexible_get(row, ['END_TIME', 'END TIME']),
                              flexible_get(row, ['SUBJECT']), flexible_get(row, ['TEACHER_NAME', 'TEACHER NAME', 'TEACHER'])))
                        success_count += 1
                        
                    flash(f'Successfully imported {success_count} class routine entries.')
                    for err in errors[:5]: flash(err)
                    if len(errors) > 5: flash(f"...and {len(errors) - 5} more errors.")
                else:
                    flash('Error: Could not determine data type from headers. Please ensure your CSV includes standard headers like CLASS, DOB, ROLL, or SUBJECT.')
                    
                try:
                    sync_classes(conn)
                except Exception as e:
                    print(f" [DB MIGRATE ERROR] sync_classes failed in process_upload: {e}")
                conn.commit()
            except Exception as e:
                flash(f'CRITICAL ERROR during upload: {str(e)}')
                flash('Please check your CSV file formatting. Ensure there are no corrupt rows or strange characters.')
            finally:
                conn.close()
        else:
            flash('Please upload a valid CSV file.')
            
        return redirect(url_for('bulk_upload'))
    return redirect(url_for('home'))

@app.route('/admin/smart-upload', methods=['POST'])
def smart_upload():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for('bulk_upload'))
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('bulk_upload'))
            
        if file and file.filename.endswith('.csv'):
            content = file.stream.read().decode("utf-8-sig", errors='ignore')
            stream = io.StringIO(content, newline=None)
            csv_input = list(csv.DictReader(stream))
            
            if not csv_input:
                flash('CSV file is empty.')
                return redirect(url_for('bulk_upload'))
                
            first_row = {str(k).strip().upper(): str(v).strip() for k, v in csv_input[0].items() if k}
            headers = list(first_row.keys())
            
            upload_type = 'students' # default
            smart_stream = io.StringIO(content)
            gemini_success = False
            
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                gemini_success = True
                try:
                    conn = get_db_connection()
                    existing_students = [r['full_name'] for r in conn.execute("SELECT full_name FROM student_info").fetchall()]
                    conn.close()
                    
                    client = genai.Client(api_key=gemini_api_key)
                    prompt = f"""
                    You are a smart data processing assistant for a school system.
                    I am providing you with an entire uploaded CSV file parsed as a JSON array.

                    1. Determine the upload type:
                       - 'students' (contains full new student details like DOB, Class, Village, etc.)
                       - 'update_students' (contains basic info like names, roll numbers, guardians to update existing students.)
                       - 'teachers' (contains teacher qualifications, joining dates)
                       - 'routine' (contains class schedule)
                       - 'marks' (contains student marks, grades, scores, subject, term)

                    2. Clean, normalize, and fix the data. 
                       - Fix any upper/lowercase inconsistencies.
                       - CRITICAL: If this is 'update_students' or 'marks', match the student name from the CSV to the closest name in this list of existing students: {existing_students}. If there is a typo or case difference, replace the CSV name with the exact existing student name from the list. If you can't find a close match, leave it as is.
                       - If 'marks', make sure each row clearly has 'STUDENT_NAME', 'SUBJECT', 'MARKS', 'TOTAL_MARKS' (default to 100 if missing), and 'TERM' (default to 'Term 1' if missing). If the raw data is wide (e.g. subjects as columns), unpivot it into this structure.
                    
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
                    
                    response_text = response.text.strip()
                    if response_text.startswith('```json'):
                        response_text = response_text[7:-3]
                    elif response_text.startswith('```'):
                        response_text = response_text[3:-3]
                        
                    ai_result = json.loads(response_text)
                    upload_type = ai_result.get('upload_type', 'students')
                    cleaned_csv = ai_result.get('cleaned_csv', csv_input)
                    
                    if cleaned_csv:
                        # Convert cleaned dicts back to a stream
                        smart_stream = io.StringIO()
                        writer = csv.DictWriter(smart_stream, fieldnames=cleaned_csv[0].keys())
                        writer.writeheader()
                        writer.writerows(cleaned_csv)
                        smart_stream.seek(0)
                        
                except Exception as e:
                    # Log the API error and force fallback to heuristic
                    print(f"Gemini API Error: {e}")
                    gemini_success = False

            # AI/Heuristic detection fallback
            if not gemini_success:
                if any(h in headers for h in ['MARKS', 'SCORE', 'OBTAINED', 'GRADE']) and any(h in headers for h in ['NAME', 'STUDENT NAME', 'FULL NAME']):
                    upload_type = 'marks'
                elif any(h in headers for h in ['DAY', 'START TIME', 'START_TIME', 'TIME', 'SCHEDULE', 'END TIME', 'END_TIME', 'TEACHER_NAME']):
                    upload_type = 'routine'
                elif any(h in headers for h in ['QUALIFICATION', 'JOINING DATE', 'JOIN DATE', 'DEGREE', 'TEACHER', 'SUBJECT', 'SALARY']):
                    upload_type = 'teachers'
                elif any(h in headers for h in ['ROLL', 'ROLL NO', 'ROLL NUMBER', 'ROLL_NO']) and not any(h in headers for h in ['D O B', 'DOB', 'DATE OF BIRTH', 'CLASS']):
                    upload_type = 'update_students'
                elif any(h in headers for h in ['CLASS', 'DOB', 'D O B', 'DATE OF BIRTH']):
                    upload_type = 'students'
                else:
                    upload_type = 'students' # absolute default
                    
                # For fallback, we just use the original CSV
                csv_input = list(csv.DictReader(io.StringIO(content)))
                if csv_input:
                    smart_stream = io.StringIO()
                    writer = csv.DictWriter(smart_stream, fieldnames=csv_input[0].keys())
                    writer.writeheader()
                    writer.writerows(csv_input)
                    smart_stream.seek(0)
            
            flash(f'Smart AI detected upload type: {upload_type.replace("_", " ").title()}')
            # Now call process_upload function directly
            return process_upload(smart_type=upload_type, smart_stream=smart_stream)
            
        else:
            flash('Please upload a valid CSV file.')
            
        return redirect(url_for('bulk_upload'))
    return redirect(url_for('home'))

@app.route('/admin/teachers')
def teacher_list():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        teachers = conn.execute('''
            SELECT u.id, u.username, u.email, u.temp_password, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date,
                   ti.aadhaar_number, ti.assigned_classes, ti.bank_details, ti.teacher_type, ti.cv_path
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
            ORDER BY COALESCE(ti.full_name, u.username)
        ''').fetchall()
        conn.close()
        logo_url = LOGO_URL
        return render_template('admin/teacher_list.html', teachers=teachers, role=session['role'], logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/staff', methods=['GET', 'POST'])
def manage_staff():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            staff_type = request.form.get('staff_type', '').strip()
            salary = request.form.get('salary', '0').strip()
            phone_number = request.form.get('phone_number', '').strip()
            branch = session['branch'] if session.get('branch') else request.form.get('branch')
            
            if not full_name or not staff_type:
                flash('Full Name and Staff Type are required!')
            else:
                try:
                    salary_val = float(salary or 0)
                except ValueError:
                    salary_val = 0.0
                conn.execute('''
                    INSERT INTO staff (full_name, staff_type, salary, phone_number, branch)
                    VALUES (?, ?, ?, ?, ?)
                ''', (full_name, staff_type, salary_val, phone_number, branch))
                conn.commit()
                flash('Staff member added successfully!')
            conn.close()
            return redirect(url_for('manage_staff'))
            
        # GET request
        branch_filter = session.get('branch')
        if branch_filter:
            staff_list = conn.execute("SELECT * FROM staff WHERE branch = ? ORDER BY full_name", (branch_filter,)).fetchall()
        else:
            staff_list = conn.execute("SELECT * FROM staff ORDER BY full_name").fetchall()
        conn.close()
        
        logo_url = LOGO_URL
        return render_template('admin/manage_staff.html', staff_list=staff_list, branches=BRANCHES, role=session['role'], logo_url=logo_url)
    return redirect(url_for('home'))

@app.route('/admin/delete-staff/<int:staff_id>', methods=['POST'])
def delete_staff(staff_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        staff_member = conn.execute("SELECT branch FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if not staff_member:
            conn.close()
            flash('Staff member not found.')
            return redirect(url_for('manage_staff'))
            
        # Check branch permission if branch admin
        if session.get('branch') and staff_member['branch'] != session['branch']:
            conn.close()
            flash('Permission denied: Staff member belongs to another campus.')
            return redirect(url_for('manage_staff'))
            
        conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
        conn.commit()
        conn.close()
        flash('Staff member deleted successfully!')
    return redirect(url_for('manage_staff'))


# ================= STUDENT INFO EDIT REQUESTS =================

@app.route('/student/edit-info', methods=['GET', 'POST'])
@login_required
def student_edit_info():
    user = get_session_user()
    if user['role'] != 'student':
        flash('Access denied: Only students can edit profile info.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        guardian_name = request.form.get('guardian_name', '').strip()
        mothers_name = request.form.get('mothers_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        dob = request.form.get('dob', '').strip()
        section = request.form.get('section', '').strip()
        blood_group = request.form.get('blood_group', '').strip()
        aadhaar_number = request.form.get('aadhaar_number', '').strip()
        village = request.form.get('village', '').strip()
        post_office = request.form.get('post_office', '').strip()
        police_station = request.form.get('police_station', '').strip()
        district = request.form.get('district', '').strip()
        
        # Parse bank details and serialize
        bank_name = request.form.get('bank_name', '').strip()
        branch_name = request.form.get('branch_name', '').strip()
        account_no = request.form.get('account_no', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        bank_details = None
        if bank_name or branch_name or account_no or ifsc_code:
            bank_details = json.dumps({
                'bank_name': bank_name,
                'branch_name': branch_name,
                'account_no': account_no,
                'ifsc_code': ifsc_code
            })

        if not full_name or not guardian_name or not mothers_name or not phone_number or not dob:
            flash('Error: Please fill in all required fields.')
            conn.close()
            return redirect(url_for('student_edit_info'))
            
        edit_data = {
            'full_name': full_name,
            'guardian_name': guardian_name,
            'mothers_name': mothers_name,
            'phone_number': phone_number,
            'dob': dob,
            'section': section,
            'blood_group': blood_group,
            'aadhaar_number': aadhaar_number,
            'village': village,
            'post_office': post_office,
            'police_station': police_station,
            'district': district,
            'bank_details': bank_details,
            'sl_no': request.form.get('sl_no', '').strip(),
            'session': request.form.get('session', '').strip(),
            'mode_of_admission': 'Day Hostel' if request.form.get('take_day_hostel') else ('School with Coaching' if request.form.get('take_coaching') else 'School'),
            'father_qualification': request.form.get('father_qualification', '').strip(),
            'father_occupation': request.form.get('father_occupation', '').strip(),
            'father_monthly_income': request.form.get('father_monthly_income', '').strip(),
            'mother_qualification': request.form.get('mother_qualification', '').strip(),
            'mother_occupation': request.form.get('mother_occupation', '').strip(),
            'mother_monthly_income': request.form.get('mother_monthly_income', '').strip(),
            'nationality': request.form.get('nationality', 'Indian').strip(),
            'religion': request.form.get('religion', '').strip(),
            'gender': request.form.get('gender', '').strip(),
            'caste': request.form.get('caste', '').strip(),
            'whatsapp_no': request.form.get('whatsapp_no', '').strip(),
            'previous_class': request.form.get('previous_class', '').strip(),
            'prev_marks_percentage': request.form.get('prev_marks_percentage', '').strip(),
            'identification_mark': request.form.get('identification_mark', '').strip(),
            'attached_documents': ', '.join(request.form.getlist('attached_documents')),
            'coaching_opted': 1 if request.form.get('take_coaching') else 0,
            'car_opted': 1 if request.form.get('take_car') else 0,
            'take_school': 1 if request.form.get('take_school') else 0,
            'take_coaching': 1 if request.form.get('take_coaching') else 0,
            'take_day_hostel': 1 if request.form.get('take_day_hostel') else 0,
            'take_car': 1 if request.form.get('take_car') else 0
        }
        
        student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
        branch = student['branch'] if student else None
        
        existing = conn.execute("SELECT id FROM applications WHERE user_id = ? AND type = 'student_info_edit' AND status = 'Pending'", (user['id'],)).fetchone()
        
        if existing:
            conn.execute("UPDATE applications SET data = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(edit_data), existing['id']))
        else:
            conn.execute('''
                INSERT INTO applications (user_id, type, data, branch, status)
                VALUES (?, 'student_info_edit', ?, ?, 'Pending')
            ''', (user['id'], json.dumps(edit_data), branch))
            
        conn.commit()
        conn.close()
        flash('Profile edit request submitted successfully! Awaiting Admin approval.')
        return redirect(url_for('student_edit_info'))
        
    student_info = conn.execute('''
        SELECT si.*, u.email 
        FROM student_info si 
        JOIN users u ON si.user_id = u.id 
        WHERE u.id = ?
    ''', (user['id'],)).fetchone()
    
    if not student_info:
        student_info = {
            'photo_path': '',
            'class': '',
            'roll_number': '',
            'unique_code': '',
            'date_of_admission': '',
            'full_name': user['username'],
            'dob': '',
            'section': '',
            'gender': 'Male',
            'caste': 'General',
            'religion': '',
            'nationality': 'Indian',
            'whatsapp_no': '',
            'identification_mark': '',
            'previous_class': '',
            'prev_marks_percentage': '',
            'sl_no': '',
            'session': '2026',
            'mode_of_admission': 'School',
            'coaching_opted': 0,
            'car_opted': 0,
            'guardian_name': '',
            'mothers_name': '',
            'father_qualification': '',
            'father_occupation': '',
            'father_monthly_income': '',
            'mother_qualification': '',
            'mother_occupation': '',
            'mother_monthly_income': '',
            'village': '',
            'post_office': '',
            'police_station': '',
            'district': '',
            'bank_details': '',
            'attached_documents': ''
        }
    
    pending_edit = conn.execute('''
        SELECT * FROM applications 
        WHERE user_id = ? AND type = 'student_info_edit' AND status = 'Pending'
    ''', (user['id'],)).fetchone()
    
    pending_data = {}
    if pending_edit:
        try:
            pending_data = json.loads(pending_edit['data'])
        except Exception:
            pass
            
    conn.close()
    return render_template('student/edit_info.html', student_info=student_info, pending_edit=pending_edit, pending_data=pending_data, role=user['role'])


# ================= TEACHER INFO EDIT REQUESTS =================

@app.route('/teacher/edit-info', methods=['GET', 'POST'])
@login_required
def teacher_edit_info():
    user = get_session_user()
    if user['role'] != 'teacher':
        flash('Access denied: Only teachers can edit profile info.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        qualification = request.form.get('qualification', '').strip()
        address = request.form.get('address', '').strip()
        aadhaar_number = request.form.get('aadhaar_number', '').strip()
        
        # Handle Photo Upload
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            ext = photo_file.filename.split('.')[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'teacher_photos')
                os.makedirs(upload_folder, exist_ok=True)
                filename = f"teacher_{user['id']}_{int(datetime.now(timezone.utc).timestamp())}.{ext}"
                
                # Ensure teacher_info record exists
                exists = conn.execute("SELECT 1 FROM teacher_info WHERE user_id = ?", (user['id'],)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO teacher_info (user_id, full_name) VALUES (?, ?)", (user['id'], full_name or user['username']))
                
                # Delete old photo if exists
                old_photo = conn.execute("SELECT photo_path FROM teacher_info WHERE user_id = ?", (user['id'],)).fetchone()
                if old_photo and old_photo['photo_path']:
                    try:
                        delete_old_mapped_file(old_photo['photo_path'])
                        os.remove(os.path.join(upload_folder, old_photo['photo_path']))
                    except:
                        pass
                
                local_path = os.path.join(upload_folder, filename)
                photo_file.save(local_path)
                upload_file_to_drive_and_map(local_path, filename, photo_file.content_type, folder_id=os.getenv('GOOGLE_DRIVE_FOLDER_TEACHERS'), conn=conn)
                conn.execute("UPDATE teacher_info SET photo_path = ? WHERE user_id = ?", (filename, user['id']))

        # Parse bank details and serialize
        bank_name = request.form.get('bank_name', '').strip()
        branch_name = request.form.get('branch_name', '').strip()
        account_no = request.form.get('account_no', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        bank_details = None
        if bank_name or branch_name or account_no or ifsc_code:
            bank_details = json.dumps({
                'bank_name': bank_name,
                'branch_name': branch_name,
                'account_no': account_no,
                'ifsc_code': ifsc_code
            })

        if not full_name or not phone_number or not qualification or not address:
            flash('Error: Please fill in all required fields.')
            conn.close()
            return redirect(url_for('teacher_edit_info'))
            
        edit_data = {
            'full_name': full_name,
            'phone_number': phone_number,
            'qualification': qualification,
            'address': address,
            'aadhaar_number': aadhaar_number,
            'bank_details': bank_details
        }
        
        branch = user['branch']
        
        existing = conn.execute("SELECT id FROM applications WHERE user_id = ? AND type = 'teacher_info_edit' AND status = 'Pending'", (user['id'],)).fetchone()
        
        if existing:
            conn.execute("UPDATE applications SET data = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?", (json.dumps(edit_data), existing['id']))
        else:
            conn.execute('''
                INSERT INTO applications (user_id, type, data, branch, status)
                VALUES (?, 'teacher_info_edit', ?, ?, 'Pending')
            ''', (user['id'], json.dumps(edit_data), branch))
            
        conn.commit()
        conn.close()
        flash('Profile edit request submitted successfully! Awaiting Admin approval.')
        return redirect(url_for('teacher_edit_info'))
        
    teacher_info = conn.execute('''
        SELECT ti.*, u.email 
        FROM teacher_info ti 
        JOIN users u ON ti.user_id = u.id 
        WHERE u.id = ?
    ''', (user['id'],)).fetchone()
    
    if not teacher_info:
        teacher_info = {
            'photo_path': '',
            'joining_date': '',
            'assigned_classes': '',
            'full_name': user['username'],
            'phone_number': '',
            'qualification': '',
            'aadhaar_number': '',
            'address': '',
            'bank_details': ''
        }
    
    pending_edit = conn.execute('''
        SELECT * FROM applications 
        WHERE user_id = ? AND type = 'teacher_info_edit' AND status = 'Pending'
    ''', (user['id'],)).fetchone()
    
    pending_data = {}
    if pending_edit:
        try:
            pending_data = json.loads(pending_edit['data'])
        except Exception:
            pass
            
    conn.close()
    return render_template('teacher/edit_info.html', teacher_info=teacher_info, pending_edit=pending_edit, pending_data=pending_data, role=user['role'])


# ================= CLASS ROUTINE SCHEDULER =================

@app.route('/routine', methods=['GET', 'POST'])
@login_required
def view_routine():
    user = get_session_user()
    conn = get_db_connection()
    
    CLASSES = get_all_classes(conn)
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    if request.method == 'POST' and user['role'] == 'admin':
        if 'add_slot' in request.form:
            branch = 'bhogram'
            if session.get('branch'):
                branch = session['branch']
            class_name = request.form.get('class_name')
            days = request.form.getlist('day')
            if not days:
                single_day = request.form.get('day')
                days = [single_day] if single_day else []
            start_time = request.form.get('start_time').strip()
            end_time = request.form.get('end_time').strip()
            subject = request.form.get('subject')
            teacher_name = request.form.get('teacher_name')
            
            for d in days:
                if d:
                    conn.execute('''
                        INSERT INTO class_routine (branch, class_name, day, start_time, end_time, subject, teacher_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (branch, class_name, d, start_time, end_time, subject, teacher_name))
            conn.commit()
            flash('Routine slot(s) added successfully!')
            
        elif 'edit_slot' in request.form:
            slot_id = request.form.get('slot_id')
            class_name = request.form.get('class_name')
            day = request.form.get('day')
            start_time = request.form.get('start_time').strip()
            end_time = request.form.get('end_time').strip()
            subject = request.form.get('subject')
            teacher_name = request.form.get('teacher_name')
            
            conn.execute('''
                UPDATE class_routine 
                SET class_name = ?, day = ?, start_time = ?, end_time = ?, subject = ?, teacher_name = ?
                WHERE id = ?
            ''', (class_name, day, start_time, end_time, subject, teacher_name, slot_id))
            conn.commit()
            flash('Routine slot updated successfully!')
            
        elif 'delete_slot' in request.form:
            slot_id = request.form.get('slot_id')
            conn.execute("DELETE FROM class_routine WHERE id = ?", (slot_id,))
            conn.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                conn.close()
                return jsonify({'status': 'success', 'message': 'Routine slot deleted successfully.'})
            flash('Routine slot deleted!')
            
        conn.close()
        return redirect(url_for('view_routine'))
        
    if user['role'] == 'teacher':
        teacher_row = conn.execute('''
            SELECT COALESCE(ti.full_name, u.username) as name
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.id = ?
        ''', (user['id'],)).fetchone()
        t_name = teacher_row['name'] if teacher_row else ''
        routines = conn.execute("SELECT * FROM class_routine WHERE LOWER(teacher_name) = LOWER(?)", (t_name,)).fetchall()
    else:
        routines = conn.execute("SELECT * FROM class_routine").fetchall()
    day_order = {d: i for i, d in enumerate(DAYS)}
    
    def parse_time_to_minutes(time_str):
        if not time_str:
            return 9999
        time_str = str(time_str).strip().lower()
        is_pm = 'pm' in time_str
        is_am = 'am' in time_str
        time_clean = time_str.replace('am', '').replace('pm', '').strip()
        parts = time_clean.split(':') if ':' in time_clean else (time_clean.split('.') if '.' in time_clean else [time_clean])
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            if is_am or is_pm:
                if hours == 12:
                    if is_am:
                        hours = 0
                elif is_pm:
                    hours += 12
            return hours * 60 + minutes
        except Exception:
            return 9999

    sorted_routines = sorted(
        [dict(r) for r in routines],
        key=lambda x: (x['branch'], get_class_sort_key(x['class_name']), day_order.get(x['day'], 99), parse_time_to_minutes(x['start_time']))
    )
    
    routine_data = {}
    for r in sorted_routines:
        b = r['branch'].strip().lower()
        c = r['class_name']
        d = r['day']
        if b not in routine_data: routine_data[b] = {}
        if c not in routine_data[b]: routine_data[b][c] = {}
        if d not in routine_data[b][c]: routine_data[b][c][d] = []
        routine_data[b][c][d].append(r)
        
    db_classes = conn.execute('''
        SELECT DISTINCT class FROM student_info WHERE class IS NOT NULL AND class != ''
        UNION
        SELECT DISTINCT class_name as class FROM class_subjects WHERE class_name IS NOT NULL AND class_name != ''
    ''').fetchall()
    classes_list = sorted([c[0] for c in db_classes], key=get_class_sort_key)
    
    distinct_subjects = [r['name'] for r in conn.execute("SELECT name FROM subjects").fetchall()]
    
    db_subjects_all = conn.execute("SELECT DISTINCT subject_name as name, class_name as class FROM class_subjects").fetchall()
    class_subjects_map = {}
    for r in db_subjects_all:
        c = r['class']
        n = r['name']
        if c not in class_subjects_map:
            class_subjects_map[c] = []
        if n not in class_subjects_map[c]:
            class_subjects_map[c].append(n)

    teachers_list = conn.execute('''
        SELECT COALESCE(ti.full_name, u.username) as name
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.role = 'teacher'
    ''').fetchall()
    teachers = [t['name'] for t in teachers_list]
    
    all_terms = get_all_academic_terms(conn)
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('routine.html', 
                           classes=classes_list, 
                           days=DAYS, 
                           distinct_subjects=distinct_subjects, 
                           class_subjects_map=class_subjects_map,
                           teachers=teachers, 
                           routine_data=routine_data, 
                           role=user['role'], 
                           logo_url=logo_url,
                           all_terms=all_terms)


# ================= GUARDIAN MEETINGS =================

@app.route('/admin/guardian-meetings', methods=['GET', 'POST'])
@login_required
def admin_guardian_meetings():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    predefined_names = ['General Guardian Meeting', 'Special Guardian Meeting', 'Academic Review Meeting', 'Parent-Teacher Meet']
    branches = BRANCHES
    
    if request.method == 'POST' and user['role'] == 'admin':
        meeting_name = request.form.get('meeting_name')
        meeting_month = request.form.get('meeting_month')
        meeting_date = request.form.get('meeting_date')
        branch = request.form.get('branch', '').strip().lower()
        if session.get('branch'):
            branch = session['branch']
            
        if not meeting_name or not meeting_month or not meeting_date or not branch:
            flash('Error: All fields are required.')
            conn.close()
            return redirect(url_for('admin_guardian_meetings'))
            
        conn.execute('''
            INSERT INTO guardian_meetings (meeting_name, meeting_date, meeting_month, branch)
            VALUES (?, ?, ?, ?)
        ''', (meeting_name, meeting_date, meeting_month, branch))
        conn.commit()
        flash('Guardian meeting initialized successfully!')
        conn.close()
        return redirect(url_for('admin_guardian_meetings'))
        
    if session.get('branch'):
        branch_filter = session['branch']
    else:
        branch_filter = request.args.get('branch_filter', '').strip().lower()
        if branch_filter not in BRANCHES:
            branch_filter = 'bhogram'
            
    if branch_filter:
        meetings_rows = conn.execute("SELECT * FROM guardian_meetings WHERE branch = ? ORDER BY meeting_date DESC", (branch_filter,)).fetchall()
    else:
        meetings_rows = conn.execute("SELECT * FROM guardian_meetings ORDER BY meeting_date DESC").fetchall()
        
    meetings = []
    for row in meetings_rows:
        mid = row['id']
        teacher_cnt = conn.execute("SELECT COUNT(*) FROM meeting_attendance WHERE meeting_id = ? AND attendee_type = 'teacher' AND status = 'Present'", (mid,)).fetchone()[0]
        guardian_cnt = conn.execute("SELECT COUNT(*) FROM meeting_attendance WHERE meeting_id = ? AND attendee_type = 'guardian' AND status = 'Present'", (mid,)).fetchone()[0]
        other_cnt = conn.execute("SELECT COUNT(*) FROM meeting_attendance WHERE meeting_id = ? AND attendee_type = 'other' AND status = 'Present'", (mid,)).fetchone()[0]
        
        meeting_dict = dict(row)
        meeting_dict['stats'] = {
            'teacher': teacher_cnt,
            'guardian': guardian_cnt,
            'other': other_cnt
        }
        meetings.append(meeting_dict)
        
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('admin/guardian_meetings.html', 
                           predefined_names=predefined_names, 
                           branches=[b.title() for b in branches], 
                           meetings=meetings, 
                           role=user['role'], 
                           user_branch=session.get('branch'), 
                           branch_filter=branch_filter, 
                           logo_url=logo_url)

@app.route('/admin/guardian-meetings/<int:meeting_id>/attendance', methods=['GET', 'POST'])
@login_required
def guardian_meeting_attendance(meeting_id):
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    meeting = conn.execute("SELECT * FROM guardian_meetings WHERE id = ?", (meeting_id,)).fetchone()
    
    if not meeting:
        conn.close()
        flash('Meeting not found.')
        return redirect(url_for('admin_guardian_meetings'))
        
    if session.get('branch') and meeting['branch'] != session['branch']:
        conn.close()
        flash('Access denied: Meeting belongs to another campus branch.')
        return redirect(url_for('admin_guardian_meetings'))
        
    if request.method == 'POST':
        attendee_type = request.form.get('attendee_type')
        if attendee_type in ['teacher', 'guardian']:
            for key in request.form.keys():
                if key.startswith('status_'):
                    uid = int(key.split('_')[1])
                    status = request.form.get(key)
                    remarks = request.form.get(f'remarks_{uid}', '').strip()
                    
                    conn.execute('''
                        INSERT OR REPLACE INTO meeting_attendance (meeting_id, attendee_type, user_id, status, remarks)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (meeting_id, attendee_type, uid, status, remarks))
            conn.commit()
            flash(f'{attendee_type.title()} attendance saved!')
            
        elif attendee_type == 'other':
            other_name = request.form.get('other_name', '').strip()
            other_designation = request.form.get('other_designation', '').strip()
            status = request.form.get('status', 'Present')
            remarks = request.form.get('remarks', '').strip()
            
            if other_name:
                conn.execute('''
                    INSERT INTO meeting_attendance (meeting_id, attendee_type, other_name, other_designation, status, remarks)
                    VALUES (?, 'other', ?, ?, ?, ?)
                ''', (meeting_id, other_name, other_designation, status, remarks))
                conn.commit()
                flash('Guest attendee registered!')
                
        elif attendee_type == 'delete_other':
            other_id = request.form.get('other_id')
            conn.execute("DELETE FROM meeting_attendance WHERE id = ? AND meeting_id = ?", (other_id, meeting_id))
            conn.commit()
            flash('Guest attendee removed!')
            
        conn.close()
        active_tab = request.form.get('attendee_type', 'teachers')
        if active_tab == 'delete_other': active_tab = 'others'
        if active_tab == 'other': active_tab = 'others'
        if active_tab == 'guardian': active_tab = 'guardians'
        if active_tab == 'teacher': active_tab = 'teachers'
        
        class_name = request.form.get('class_name', '')
        return redirect(url_for('guardian_meeting_attendance', meeting_id=meeting_id, tab=active_tab, class_name=class_name))
        
    teachers_rows = conn.execute('''
        SELECT u.id as user_id, u.username, ti.full_name, ti.phone_number, ma.status, ma.remarks
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        LEFT JOIN meeting_attendance ma ON u.id = ma.user_id AND ma.meeting_id = ? AND ma.attendee_type = 'teacher'
        WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
        ORDER BY COALESCE(ti.full_name, u.username)
    ''', (meeting_id, meeting['branch'])).fetchall()
    
    db_classes = conn.execute('''
        SELECT DISTINCT class FROM student_info WHERE branch = ? AND class IS NOT NULL AND class != ''
    ''', (meeting['branch'],)).fetchall()
    
    classes_list = sorted([c['class'] for c in db_classes], key=get_class_sort_key)
    selected_class = request.args.get('class_name', classes_list[0] if classes_list else '')
    
    guardians_roster = []
    if selected_class:
        db_classes = get_db_class_names(selected_class)
        placeholders = ', '.join(['?'] * len(db_classes))
        guardians_roster = conn.execute(f'''
            SELECT u.id as user_id, si.full_name as student_name, si.guardian_name, si.class, si.roll_number, ma.status, ma.remarks
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            LEFT JOIN meeting_attendance ma ON u.id = ma.user_id AND ma.meeting_id = ? AND ma.attendee_type = 'guardian'
            WHERE u.role = 'student' AND si.branch = ? AND si.class IN ({placeholders})
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', [meeting_id, meeting['branch']] + db_classes).fetchall()
        
    others_roster = conn.execute('''
        SELECT * FROM meeting_attendance
        WHERE meeting_id = ? AND attendee_type = 'other'
        ORDER BY id DESC
    ''', (meeting_id,)).fetchall()
    
    active_tab = request.args.get('tab', 'teachers')
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('admin/guardian_meeting_attendance.html',
                           meeting=meeting,
                           teachers_roster=teachers_rows,
                           guardians_roster=guardians_roster,
                           others_roster=others_roster,
                           classes=classes_list,
                           selected_class=selected_class,
                           active_tab=active_tab,
                           role=user['role'],
                           logo_url=logo_url)


# ================= ATTENDANCE ROUTES =================

@app.route('/admin/attendance', methods=['GET', 'POST'])
@login_required
def admin_attendance():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    CLASSES = get_active_classes(conn)
    
    if session.get('branch'):
        branch_filter = session['branch']
    else:
        branch_filter = request.args.get('branch', 'bhogram').strip().lower()
        if branch_filter not in BRANCHES:
            branch_filter = 'bhogram'
            
    role_filter = request.args.get('role_filter', 'student').strip().lower()
    class_filter = request.args.get('class_filter', '').strip()
    date_filter = request.args.get('date_filter', datetime.today().strftime('%Y-%m-%d')).strip()
    attendance_type = request.args.get('attendance_type', 'regular').strip().lower()
    if attendance_type not in ['regular', 'coaching', 'guest']:
        attendance_type = 'regular'
    
    if request.method == 'POST':
        role_type = request.form.get('role_type')
        date_val = request.form.get('date')
        user_ids = request.form.getlist('user_ids')
        post_attendance_type = request.form.get('attendance_type', 'regular').strip().lower()
        if post_attendance_type not in ['regular', 'coaching', 'guest']:
            post_attendance_type = 'regular'
        
        if not user_ids:
            flash('No records to save.')
            conn.close()
            return redirect(url_for('admin_attendance', branch=branch_filter, role_filter=role_filter, class_filter=class_filter, date_filter=date_val, attendance_type=post_attendance_type))
            
        for uid in user_ids:
            status = request.form.get(f'status_{uid}', 'Present')
            remarks = request.form.get(f'remarks_{uid}', '').strip()
            
            conn.execute('''
                INSERT OR REPLACE INTO attendance (user_id, role, date, status, remarks, attendance_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uid, role_type, date_val, status, remarks, post_attendance_type))
            
        conn.commit()
        conn.close()
        flash('Attendance saved successfully!')
        return redirect(url_for('admin_attendance', branch=branch_filter, role_filter=role_type, class_filter=class_filter, date_filter=date_val, attendance_type=post_attendance_type))
        
    users_list = []
    if role_filter == 'student':
        if class_filter:
            db_classes = get_db_class_names(class_filter)
            placeholders = ', '.join(['?'] * len(db_classes))
            users_list = conn.execute(f'''
                SELECT u.id, u.username, si.full_name, si.class, si.roll_number, si.phone_number, att.status as att_status, att.remarks as att_remarks
                FROM users u
                JOIN student_info si ON u.id = si.user_id
                LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ? AND att.attendance_type = ?
                WHERE u.role = 'student' AND si.branch = ? AND si.class IN ({placeholders})
                ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
            ''', [date_filter, attendance_type, branch_filter] + db_classes).fetchall()
    elif role_filter == 'teacher':
        if attendance_type == 'coaching':
            users_list = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.phone_number, 'Teacher' as class, '' as roll_number, att.status as att_status, att.remarks as att_remarks, ti.teacher_type
                FROM users u
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ? AND att.attendance_type = ?
                WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
                  AND ti.teacher_type IN ('Coaching Class', 'Both')
                ORDER BY COALESCE(ti.full_name, u.username)
            ''', (date_filter, attendance_type, branch_filter)).fetchall()
        elif attendance_type == 'guest':
            users_list = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.phone_number, 'Teacher' as class, '' as roll_number, att.status as att_status, att.remarks as att_remarks, ti.teacher_type
                FROM users u
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ? AND att.attendance_type = ?
                WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
                  AND ti.teacher_type = 'Guest Teacher'
                ORDER BY COALESCE(ti.full_name, u.username)
            ''', (date_filter, attendance_type, branch_filter)).fetchall()
        else: # regular
            users_list = conn.execute('''
                SELECT u.id, u.username, ti.full_name, ti.phone_number, 'Teacher' as class, '' as roll_number, att.status as att_status, att.remarks as att_remarks, ti.teacher_type
                FROM users u
                LEFT JOIN teacher_info ti ON u.id = ti.user_id
                LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ? AND att.attendance_type = ?
                WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
                  AND (ti.teacher_type IS NULL OR ti.teacher_type = '' OR ti.teacher_type IN ('Regular Class', 'Both'))
                ORDER BY COALESCE(ti.full_name, u.username)
            ''', (date_filter, attendance_type, branch_filter)).fetchall()
        
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('admin/attendance.html',
                           users_list=users_list,
                           role=user['role'],
                           classes=CLASSES,
                           branches=['Bhogram'],
                           branch_filter=branch_filter,
                           role_filter=role_filter,
                           class_filter=class_filter,
                           date_filter=date_filter,
                           attendance_type=attendance_type,
                           logo_url=logo_url)


def sync_leave_dates_to_attendance(conn, user_id, role, start_date_str, end_date_str, leave_type):
    from datetime import datetime, timedelta
    try:
        start = datetime.strptime(start_date_str, '%Y-%m-%d')
        end = datetime.strptime(end_date_str, '%Y-%m-%d')
        delta = end - start
        for i in range(delta.days + 1):
            day = (start + timedelta(days=i)).strftime('%Y-%m-%d')
            conn.execute('''
                INSERT OR REPLACE INTO attendance (user_id, role, date, status, remarks, attendance_type)
                VALUES (?, ?, ?, 'On Leave', ?, 'regular')
            ''', (user_id, role, day, f'Approved Leave ({leave_type})'))
    except Exception as e:
        print(f"Error syncing leave dates to attendance: {e}")


# ================= LEAVE MANAGEMENT =================

@app.route('/admin/leaves', methods=['GET'])
@login_required
def admin_leaves():
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
        
    if session.get('branch'):
        pending_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as applicant_name, u.username, COALESCE(si.class, 'Teacher') as class_name
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status = 'Pending' AND (si.branch = ? OR ti.address LIKE '%' || ? || '%' OR u.branch = ?)
            ORDER BY l.submitted_at DESC
        ''', (session['branch'], session['branch'], session['branch'])).fetchall()
        
        resolved_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as applicant_name, u.username, COALESCE(si.class, 'Teacher') as class_name
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status != 'Pending' AND (si.branch = ? OR ti.address LIKE '%' || ? || '%' OR u.branch = ?)
            ORDER BY l.submitted_at DESC LIMIT 50
        ''', (session['branch'], session['branch'], session['branch'])).fetchall()
        
        students_dropdown = conn.execute('''
            SELECT u.id, si.full_name, si.roll_number, si.class, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            WHERE LOWER(si.branch) = LOWER(?)
        ''', (session['branch'],)).fetchall()
        
        teachers_list = conn.execute('''
            SELECT u.id, u.username, ti.full_name,
                   COALESCE((
                       SELECT SUM(CAST(julianday(l.end_date) - julianday(l.start_date) + 1 AS INTEGER))
                       FROM leaves l
                       WHERE l.user_id = u.id AND l.status = 'Approved' AND l.leave_type = 'Casual Leave'
                   ), 0) as leaves_taken
            FROM users u
            JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher' AND (u.branch = ? OR ti.address LIKE '%' || ? || '%')
        ''', (session['branch'], session['branch'])).fetchall()
    else:
        pending_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as applicant_name, u.username, COALESCE(si.class, 'Teacher') as class_name
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status = 'Pending'
            ORDER BY l.submitted_at DESC
        ''').fetchall()
        
        resolved_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as applicant_name, u.username, COALESCE(si.class, 'Teacher') as class_name
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status != 'Pending'
            ORDER BY l.submitted_at DESC LIMIT 50
        ''').fetchall()
        
        students_dropdown = conn.execute('''
            SELECT u.id, si.full_name, si.roll_number, si.class, si.branch
            FROM users u
            JOIN student_info si ON u.id = si.user_id
        ''').fetchall()
        
        teachers_list = conn.execute('''
            SELECT u.id, u.username, ti.full_name,
                   COALESCE((
                       SELECT SUM(CAST(julianday(l.end_date) - julianday(l.start_date) + 1 AS INTEGER))
                       FROM leaves l
                       WHERE l.user_id = u.id AND l.status = 'Approved' AND l.leave_type = 'Casual Leave'
                   ), 0) as leaves_taken
            FROM users u
            JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('admin/leaves.html',
                           pending_leaves=pending_leaves,
                           past_leaves=resolved_leaves,
                           resolved_leaves=resolved_leaves,
                           students_dropdown=students_dropdown,
                           teachers_list=teachers_list,
                           role=user['role'],
                           logo_url=logo_url)


@app.route('/admin/leaves/action/<int:leave_id>/<action>', methods=['POST'])
@login_required
def admin_leave_action(leave_id, action):
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    status = 'Approved' if action == 'approve' else 'Rejected'
    conn = get_db_connection()
    conn.execute("UPDATE leaves SET status = ? WHERE id = ?", (status, leave_id))
    
    if status == 'Approved':
        # Retrieve leave details to update attendance
        leave = conn.execute("SELECT * FROM leaves WHERE id = ?", (leave_id,)).fetchone()
        if leave:
            sync_leave_dates_to_attendance(conn, leave['user_id'], leave['role'], leave['start_date'], leave['end_date'], leave['leave_type'])
                
    conn.commit()
    conn.close()
    flash(f'Leave application {status.lower()} successfully.')
    return redirect(url_for('admin_leaves'))


@app.route('/admin/leaves/record-direct', methods=['POST'])
@login_required
def record_direct_leave():
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    user_id = request.form.get('user_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    leave_type = request.form.get('leave_type', 'Casual Leave')
    reason = request.form.get('reason', '').strip()
    
    if not user_id or not start_date or not end_date:
        flash('Missing required fields for direct leave.')
        return redirect(url_for('admin_leaves'))
        
    conn = get_db_connection()
    # Find recipient role
    target_user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target_user:
        flash('Recipient user not found.')
        conn.close()
        return redirect(url_for('admin_leaves'))
        
    role = target_user['role']
    
    # Insert approved leave
    conn.execute('''
        INSERT INTO leaves (user_id, role, leave_type, start_date, end_date, reason, status)
        VALUES (?, ?, ?, ?, ?, ?, 'Approved')
    ''', (user_id, role, leave_type, start_date, end_date, reason))
    
    # Mark attendance as 'On Leave' for the dates using shared helper
    sync_leave_dates_to_attendance(conn, user_id, role, start_date, end_date, leave_type)
        
    conn.commit()
    conn.close()
    flash('Direct leave recorded and attendance updated successfully.')
    return redirect(url_for('admin_leaves'))

@app.route('/student/attendance-leaves', methods=['GET', 'POST'])
@login_required
def student_attendance_leaves():
    user = get_session_user()
    if user['role'] != 'student':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        leave_type = request.form.get('leave_type')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        reason = request.form.get('reason', '').strip()
        
        if not start_date or not end_date:
            flash('Error: Date range is required.')
            conn.close()
            return redirect(url_for('student_attendance_leaves'))
            
        conn.execute('''
            INSERT INTO leaves (user_id, role, leave_type, start_date, end_date, reason, status)
            VALUES (?, 'student', ?, ?, ?, ?, 'Pending')
        ''', (user['id'], leave_type, start_date, end_date, reason))
        conn.commit()
        conn.close()
        
        flash('Leave application submitted successfully! Awaiting Admin approval.')
        return redirect(url_for('student_attendance_leaves'))
        
    leave_history = conn.execute('''
        SELECT * FROM leaves WHERE user_id = ? ORDER BY submitted_at DESC
    ''', (user['id'],)).fetchall()
    
    attendance_log = conn.execute('''
        SELECT * FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 30
    ''', (user['id'],)).fetchall()
    
    total_att = len(attendance_log)
    present_att = len([r for r in attendance_log if r['status'] == 'Present'])
    percentage = int((present_att / total_att) * 100) if total_att > 0 else 100
    
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('student/leaves.html',
                           leave_history=leave_history,
                           attendance_log=attendance_log,
                           att_percentage=percentage,
                           role=user['role'],
                           username=user['username'],
                           logo_url=logo_url)

@app.route('/teacher/attendance-leaves', methods=['GET', 'POST'])
@login_required
def teacher_attendance_leaves():
    user = get_session_user()
    if user['role'] != 'teacher':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        leave_type = request.form.get('leave_type')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        reason = request.form.get('reason', '').strip()
        
        if not start_date or not end_date:
            flash('Error: Date range is required.')
            conn.close()
            return redirect(url_for('teacher_attendance_leaves'))
            
        conn.execute('''
            INSERT INTO leaves (user_id, role, leave_type, start_date, end_date, reason, status)
            VALUES (?, 'teacher', ?, ?, ?, ?, 'Pending')
        ''', (user['id'], leave_type, start_date, end_date, reason))
        conn.commit()
        conn.close()
        
        flash('Leave application submitted successfully! Awaiting Admin approval.')
        return redirect(url_for('teacher_attendance_leaves'))
        
    leave_history = conn.execute('''
        SELECT * FROM leaves WHERE user_id = ? ORDER BY submitted_at DESC
    ''', (user['id'],)).fetchall()
    
    attendance_log = conn.execute('''
        SELECT * FROM attendance WHERE user_id = ? ORDER BY date DESC LIMIT 30
    ''', (user['id'],)).fetchall()
    
    cl_quota = 12
    cl_taken = conn.execute('''
        SELECT COALESCE(SUM(CAST(julianday(end_date) - julianday(start_date) + 1 AS INTEGER)), 0)
        FROM leaves
        WHERE user_id = ? AND status = 'Approved' AND leave_type = 'Casual Leave'
    ''', (user['id'],)).fetchone()[0]
    cl_balance = cl_quota - cl_taken
    
    conn.close()
    logo_url = LOGO_URL
    
    return render_template('teacher/leaves.html',
                           leave_history=leave_history,
                           attendance_log=attendance_log,
                           cl_quota=cl_quota,
                           cl_balance=cl_balance,
                           role=user['role'],
                           username=user['username'],
                           logo_url=logo_url)


@app.route('/admin/manage-admins', methods=['GET', 'POST'])
def manage_admins():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            branch = request.form.get('branch', '').strip() or None
            
            if not username or not password:
                flash('Username and password are required.')
            else:
                is_strong, error_msg = check_password_strength(password)
                if not is_strong:
                    flash(error_msg)
                else:
                    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                    if existing:
                        flash('Username already exists.')
                    else:
                        hashed = hash_password(password)
                        security_key = secrets.token_hex(16)
                        conn.execute('''
                            INSERT INTO users (username, email, password, role, security_key, branch)
                            VALUES (?, ?, ?, 'admin', ?, ?)
                        ''', (username, email, hashed, security_key, branch))
                        conn.commit()
                        flash('Admin account created successfully.')
                    
        elif action == 'edit':
            user_id = request.form.get('user_id')
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            branch = request.form.get('branch', '').strip() or None
            
            if not username or not user_id:
                flash('Admin ID and Username are required.')
            elif password and not check_password_strength(password)[0]:
                flash(check_password_strength(password)[1])
            else:
                existing = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id)).fetchone()
                if existing:
                    flash('Username already exists.')
                else:
                    conn.execute('''
                        UPDATE users 
                        SET username = ?, email = ?, branch = ?
                        WHERE id = ? AND role = 'admin'
                    ''', (username, email, branch, user_id))
                    
                    if password:
                        hashed = hash_password(password)
                        conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_id))
                        
                    conn.commit()
                    flash('Admin account updated successfully.')
                    
        elif action == 'delete':
            user_id = request.form.get('user_id')
            current_admin = get_session_user()
            if current_admin and int(user_id) == current_admin['id']:
                flash('You cannot delete your own admin account.')
            else:
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admin_count <= 1:
                    flash('You cannot delete the last remaining admin account.')
                else:
                    conn.execute("DELETE FROM users WHERE id = ? AND role = 'admin'", (user_id,))
                    conn.commit()
                    flash('Admin account deleted successfully.')
                    
        return redirect(url_for('manage_admins'))
        
    admins = conn.execute("SELECT id, username, email, branch FROM users WHERE role = 'admin' ORDER BY username ASC").fetchall()
    conn.close()
    
    logo_url = LOGO_URL
    return render_template('admin/manage_admins.html', admins=admins, branches=BRANCHES, role=session['role'], logo_url=logo_url)


@app.route('/debug-db')
def debug_db():
    conn = get_db_connection()
    sql_create = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='attendance'").fetchone()[0]
    conn.close()
    return jsonify({'sql_create': sql_create})

@app.route('/admin/attendance/upload-csv', methods=['POST'])
@login_required
def admin_attendance_upload_csv():
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
    
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('No file selected.')
        return redirect(url_for('admin_attendance'))
        
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        flash('Only CSV files are allowed.')
        return redirect(url_for('admin_attendance'))
        
    role_type = request.form.get('role_type', 'student')
    attendance_type = request.form.get('attendance_type', 'regular')
    
    try:
        import io
        import csv
        stream = io.StringIO(file.stream.read().decode("utf-8-sig", errors='ignore'), newline=None)
        csv_input = csv.DictReader(stream)
        conn = get_db_connection()
        
        success_count = 0
        errors = []
        row_num = 1
        
        for raw_row in csv_input:
            row_num += 1
            row = {str(k).strip().lower(): str(v).strip() for k, v in raw_row.items() if k}
            
            username = row.get('username')
            date_val = row.get('date')
            status = row.get('status', 'Present')
            remarks = row.get('remarks', '')
            
            if not username or not date_val:
                errors.append(f"Row {row_num}: Missing username or date. Skipped.")
                continue
                
            user_row = conn.execute("SELECT id FROM users WHERE username = ? AND role = ?", (username, role_type)).fetchone()
            if not user_row:
                errors.append(f"Row {row_num}: User '{username}' with role '{role_type}' not found. Skipped.")
                continue
                
            uid = user_row['id']
            conn.execute('''
                INSERT OR REPLACE INTO attendance (user_id, role, date, status, remarks, attendance_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uid, role_type, date_val, status, remarks, attendance_type))
            success_count += 1
            
        conn.commit()
        conn.close()
        
        if errors:
            flash(f"Uploaded {success_count} records. Errors: " + "; ".join(errors[:5]))
        else:
            flash(f"Successfully uploaded {success_count} attendance records!")
            
    except Exception as e:
        flash(f"Error processing CSV: {str(e)}")
        
    return redirect(url_for('admin_attendance'))

@app.route('/admin/attendance-charts')
@login_required
def admin_attendance_charts():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    students = conn.execute('''
        SELECT u.id, si.full_name, si.class, si.roll_number, u.username
        FROM users u
        JOIN student_info si ON u.id = si.user_id
        ORDER BY si.class, CAST(si.roll_number AS INTEGER), si.roll_number
    ''').fetchall()
    
    teachers = conn.execute('''
        SELECT u.id, ti.full_name, u.username, ti.teacher_type
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.role = 'teacher'
        ORDER BY COALESCE(ti.full_name, u.username)
    ''').fetchall()
    
    conn.close()
    logo_url = LOGO_URL
    return render_template('admin/attendance_charts.html',
                           students=students,
                           teachers=teachers,
                           role=user['role'],
                           logo_url=logo_url)

@app.route('/api/attendance-stats')
@login_required
def api_attendance_stats_overall():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db_connection()
    stats = conn.execute('''
        SELECT status, COUNT(*) as cnt
        FROM attendance
        GROUP BY status
    ''').fetchall()
    stats_dict = {row['status']: row['cnt'] for row in stats}
    
    trend = conn.execute('''
        SELECT date, 
               SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present,
               COUNT(*) as total
        FROM attendance
        GROUP BY date
        ORDER BY date DESC
        LIMIT 30
    ''').fetchall()
    trend_data = [{'date': row['date'], 'rate': round((row['present'] / row['total'] * 100), 1) if row['total'] > 0 else 0} for row in reversed(trend)]
    
    class_stats = conn.execute('''
        SELECT si.class,
               SUM(CASE WHEN att.status = 'Present' THEN 1 ELSE 0 END) as present,
               COUNT(*) as total
        FROM attendance att
        JOIN student_info si ON att.user_id = si.user_id
        GROUP BY si.class
    ''').fetchall()
    class_data = [{'class': row['class'], 'rate': round((row['present'] / row['total'] * 100), 1) if row['total'] > 0 else 0} for row in class_stats]
    
    conn.close()
    return jsonify({
        'overall': stats_dict,
        'trend': trend_data,
        'classes': class_data
    })

@app.route('/api/attendance-stats/<int:user_id>')
@login_required
def api_attendance_stats_user(user_id):
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db_connection()
    user_row = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
        
    if user_row['role'] == 'student':
        name_row = conn.execute("SELECT full_name FROM student_info WHERE user_id = ?", (user_id,)).fetchone()
        name = name_row['full_name'] if name_row else user_row['username']
    else:
        name_row = conn.execute("SELECT full_name FROM teacher_info WHERE user_id = ?", (user_id,)).fetchone()
        name = name_row['full_name'] if name_row else user_row['username']
        
    logs = conn.execute('''
        SELECT date, status, remarks, attendance_type
        FROM attendance
        WHERE user_id = ?
        ORDER BY date ASC
    ''', (user_id,)).fetchall()
    
    counts = {'Present': 0, 'Absent': 0, 'Late': 0, 'Half Day': 0, 'On Leave': 0}
    timeline = []
    for log in logs:
        status = log['status']
        if status in counts:
            counts[status] += 1
        elif status == 'Leave' or status == 'On Leave':
            counts['On Leave'] += 1
            
        timeline.append({
            'date': log['date'],
            'status': status,
            'remarks': log['remarks'],
            'type': log['attendance_type']
        })
        
    total = sum(counts.values())
    present_total = counts['Present'] + counts['Late'] + counts['Half Day']
    rate = round((present_total / total * 100), 1) if total > 0 else 100.0
    
    conn.close()
    return jsonify({
        'name': name,
        'role': user_row['role'],
        'rate': rate,
        'counts': counts,
        'timeline': timeline
    })

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/admin/delete-complaint/<int:complaint_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_complaint(complaint_id):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
        conn.commit()
        conn.close()
        flash('Complaint deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting complaint: {str(e)}', 'danger')
    return redirect(url_for('dashboard'))

def sync_all_existing_teacher_assignments():
    debug_lines = []
    try:
        conn = get_db_connection()
        db_subjects = conn.execute("SELECT id, name FROM subjects").fetchall()
        debug_lines.append(f"DB Subjects count: {len(db_subjects)}")
        for sub in db_subjects:
            debug_lines.append(f"  DB Sub: id={sub['id']}, name='{sub['name']}', s_norm='{normalize_subject_name(sub['name'])}'")
            
        teachers = conn.execute("SELECT user_id, full_name, assigned_classes FROM teacher_info").fetchall()
        debug_lines.append(f"Teachers count: {len(teachers)}")
        for t in teachers:
            teacher_id = t['user_id']
            full_name = t['full_name']
            assigned_classes = t['assigned_classes']
            debug_lines.append(f"\n--- Teacher: {full_name} (id={teacher_id}), assigned_classes='{assigned_classes}' ---")
            
            # Sync assignments
            if assigned_classes:
                sync_teacher_subjects_from_string(conn, teacher_id, assigned_classes)
                
            # Log what is now in teacher_subjects for this teacher
            ts_rows = conn.execute('''
                SELECT ts.id, s.name as subject_name, ts.class_name as subject_class
                FROM teacher_subjects ts
                JOIN subjects s ON ts.subject_id = s.id
                WHERE ts.teacher_id = ?
            ''', (teacher_id,)).fetchall()
            
            debug_lines.append(f"  Synced assignments in DB ({len(ts_rows)}):")
            for r in ts_rows:
                debug_lines.append(f"    - Class {r['subject_class']}: {r['subject_name']}")
                
        # Specific diagnostic for Ajinur Khatun
        ajinur_user = conn.execute("SELECT username, id FROM users WHERE LOWER(username) = 'ajinur76' OR LOWER(username) = 'ajinur'").fetchone()
        if ajinur_user:
            debug_lines.append("\n================ AJINUR KHATUN DIAGNOSTIC ================")
            allowed = get_teacher_allowed_subjects(conn, ajinur_user['username'])
            debug_lines.append(f"Allowed subjects count: {len(allowed)}")
            for idx, x in enumerate(allowed):
                debug_lines.append(f"  Allowed {idx+1}: Class {x['class']} - Subject {x['name']} (branch={x['branch']})")
                
            ti = conn.execute("SELECT qualification, full_name, assigned_classes FROM teacher_info WHERE user_id = ?", (ajinur_user['id'],)).fetchone()
            if ti:
                debug_lines.append(f"Qualification: '{ti['qualification']}'")
                debug_lines.append(f"Full Name: '{ti['full_name']}'")
                
                cr = conn.execute("SELECT * FROM class_routine WHERE LOWER(teacher_name) = LOWER(?)", (ti['full_name'],)).fetchall()
                debug_lines.append(f"Class routine matches count: {len(cr)}")
                for r in cr:
                    debug_lines.append(f"  Routine row: branch={r['branch']}, class={r['class_name']}, subject={r['subject']}, teacher={r['teacher_name']}")
        conn.commit()
        conn.close()
    except Exception as e:
        debug_lines.append(f"ERROR: {str(e)}")
        
    try:
        with open(os.path.join(BASE_DIR, 'debug_sync.txt'), 'w', encoding='utf-8') as f:
            f.write("\n".join(debug_lines))
    except Exception as e:
        print(f"Failed to write debug_sync.txt: {e}")

# sync_all_existing_teacher_assignments() # Moved to bottom

def migrate_billing_system():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Create fee_matrix table
        c.execute('''
            CREATE TABLE IF NOT EXISTS fee_matrix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT 'bhogram',
                school_monthly REAL DEFAULT 0.0,
                school_admission REAL DEFAULT 0.0,
                school_readmission REAL DEFAULT 0.0,
                coaching_monthly REAL DEFAULT 0.0,
                coaching_admission REAL DEFAULT 0.0,
                coaching_readmission REAL DEFAULT 0.0,
                hostel_monthly REAL DEFAULT 0.0,
                hostel_admission REAL DEFAULT 0.0,
                hostel_readmission REAL DEFAULT 0.0,
                UNIQUE(class_name, branch)
            )
        ''')
        
        # Populate fee_matrix with default classes if empty
        exist = c.execute("SELECT id FROM fee_matrix").fetchone()
        if not exist:
            classes_names = ['Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI']
            for branch in ['bhogram']:
                for cls in classes_names:
                    cls_row = c.execute("SELECT monthly_fee, admission_fee, monthly_fee_coaching, admission_fee_coaching, admission_fee_hostel, readmission_fee_school, readmission_fee_coaching, readmission_fee_hostel, hostel_fee FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (cls, branch)).fetchone()
                    if cls_row:
                        c.execute('''
                            INSERT OR IGNORE INTO fee_matrix (
                                class_name, branch, school_monthly, school_admission, school_readmission,
                                coaching_monthly, coaching_admission, coaching_readmission,
                                hostel_monthly, hostel_admission, hostel_readmission
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (cls, branch, 
                              float(cls_row['monthly_fee'] or 0.0), 
                              float(cls_row['admission_fee'] or 0.0), 
                              float(cls_row['readmission_fee_school'] or 0.0),
                              float(cls_row['monthly_fee_coaching'] or 0.0), 
                              float(cls_row['admission_fee_coaching'] or 0.0), 
                              float(cls_row['readmission_fee_coaching'] or 0.0),
                              float(cls_row['hostel_fee'] or 0.0), 
                              float(cls_row['admission_fee_hostel'] or 0.0), 
                              float(cls_row['readmission_fee_hostel'] or 0.0)))
                    else:
                        c.execute('''
                            INSERT OR IGNORE INTO fee_matrix (
                                class_name, branch, school_monthly, school_admission, school_readmission,
                                coaching_monthly, coaching_admission, coaching_readmission,
                                hostel_monthly, hostel_admission, hostel_readmission
                            ) VALUES (?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                        ''', (cls, branch))

        # Clean up any extra classes and non-bhogram branches from fee_matrix
        c.execute("DELETE FROM fee_matrix WHERE class_name NOT IN ('Nursery', 'Upper Nursery', 'I', 'II', 'III', 'IV', 'V', 'VI')")
        c.execute("DELETE FROM fee_matrix WHERE branch != 'bhogram'")

        # Create transport_settings table
        c.execute('''
            CREATE TABLE IF NOT EXISTS transport_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flat_rate REAL DEFAULT 400.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Seed transport_settings if empty
        exist_trans = c.execute("SELECT id FROM transport_settings").fetchone()
        if not exist_trans:
            c.execute("INSERT INTO transport_settings (flat_rate) VALUES (400.0)")
            
        # Create student_ledger table
        c.execute('''
            CREATE TABLE IF NOT EXISTS student_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                fee_type TEXT NOT NULL,
                amount REAL NOT NULL,
                month TEXT NOT NULL,
                year TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Unpaid/Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                branch TEXT,
                FOREIGN KEY (student_id) REFERENCES users (id)
            )
        ''')
        
        # Create financial_logs table
        c.execute('''
            CREATE TABLE IF NOT EXISTS financial_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                log_type TEXT NOT NULL,
                fee_type TEXT NOT NULL,
                amount REAL NOT NULL,
                month TEXT NOT NULL,
                year TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                branch TEXT,
                FOREIGN KEY (student_id) REFERENCES users (id)
            )
        ''')
        
        # Add readmission_revenue column to fees table
        try:
            c.execute("ALTER TABLE fees ADD COLUMN readmission_revenue REAL DEFAULT 0.0")
            print(" [DB MIGRATE] Added readmission_revenue column to fees table.")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()
        conn.close()
        print(" [DB MIGRATE] Billing System tables migrated successfully.")
    except Exception as e:
        print(f" [DB MIGRATE ERROR] Billing System tables migration failed: {e}")

def bill_admission_fee(conn, user_id, class_name, branch, take_coaching, take_day_hostel, custom_admission_fee=None):
    from datetime import datetime
    month = datetime.now().strftime('%B')
    year = datetime.now().strftime('%Y')
    
    amount = 0.0
    if custom_admission_fee is not None and float(custom_admission_fee) > 0.0:
        amount = float(custom_admission_fee)
    else:
        matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
        if matrix:
            if take_day_hostel:
                amount = float(matrix['hostel_admission'] or 0.0)
            elif take_coaching:
                amount = float(matrix['coaching_admission'] or 0.0)
            else:
                amount = float(matrix['school_admission'] or 0.0)
        else:
            cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
            if cls_row:
                if take_day_hostel:
                    amount = float(cls_row['admission_fee_hostel'] or 0.0)
                elif take_coaching:
                    amount = float(cls_row['admission_fee_coaching'] or 0.0)
                else:
                    amount = float(cls_row['admission_fee'] or 0.0)
                    
    if amount > 0.0:
        conn.execute('''
            INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
            VALUES (?, 'Admission Fee', ?, ?, ?, 'Unpaid/Pending', ?)
        ''', (user_id, amount, month, year, branch))
        
        conn.execute('''
            INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
            VALUES (?, 'Charge', 'Admission Fee', ?, ?, ?, ?)
        ''', (user_id, amount, month, year, branch))
        
        conn.execute('''
            UPDATE student_info
            SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
            WHERE user_id = ?
        ''', (amount, user_id))

def bill_readmission_fee(conn, user_id, class_name, branch, take_coaching, take_day_hostel, custom_readmission_fee=None):
    from datetime import datetime
    month = datetime.now().strftime('%B')
    year = datetime.now().strftime('%Y')
    
    amount = 0.0
    if custom_readmission_fee is not None and float(custom_readmission_fee) > 0.0:
        amount = float(custom_readmission_fee)
    else:
        matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
        if matrix:
            if take_day_hostel:
                amount = float(matrix['hostel_readmission'] or 0.0)
            elif take_coaching:
                amount = float(matrix['coaching_readmission'] or 0.0)
            else:
                amount = float(matrix['school_readmission'] or 0.0)
        else:
            cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
            if cls_row:
                if take_day_hostel:
                    amount = float(cls_row['readmission_fee_hostel'] or 0.0)
                elif take_coaching:
                    amount = float(cls_row['readmission_fee_coaching'] or 0.0)
                else:
                    amount = float(cls_row['readmission_fee_school'] or 0.0)
                    
    if amount > 0.0:
        conn.execute('''
            INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
            VALUES (?, 'Re-admission Fee', ?, ?, ?, 'Unpaid/Pending', ?)
        ''', (user_id, amount, month, year, branch))
        
        conn.execute('''
            INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
            VALUES (?, 'Charge', 'Re-admission Fee', ?, ?, ?, ?)
        ''', (user_id, amount, month, year, branch))
        
        conn.execute('''
            UPDATE student_info
            SET remaining_fee = COALESCE(remaining_fee, 0.0) + ?
            WHERE user_id = ?
        ''', (amount, user_id))

def run_monthly_billing(conn, month=None, year=None):
    from datetime import datetime
    if not month:
        month = datetime.now().strftime('%B')
    if not year:
        year = datetime.now().strftime('%Y')
        
    students = conn.execute('''
        SELECT u.id, si.*
        FROM users u
        JOIN student_info si ON u.id = si.user_id
        WHERE u.role = 'student'
    ''').fetchall()
    
    transport_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
    flat_transport_fee = float(transport_row['flat_rate']) if transport_row else 400.0
    
    billed_count = 0
    for student in students:
        student_id = student['id']
        class_name = student['class']
        branch = student['branch'] or 'bhogram'
        take_school = student['take_school'] or 0
        take_coaching = student['take_coaching'] or 0
        take_day_hostel = student['take_day_hostel'] or 0
        take_car = student['take_car'] or 0
        
        already_billed = conn.execute('''
            SELECT id FROM student_ledger 
            WHERE student_id = ? AND month = ? AND year = ? AND fee_type LIKE 'Monthly%'
        ''', (student_id, month, year)).fetchone()
        if already_billed:
            continue
            
        student_dict = dict(student)
        bd = calculate_student_fees_breakdown(student_dict, conn=conn)
        
        school_fee = bd['tuition_fee'] if take_school else 0.0
        coaching_fee = bd['coaching_combo_fee'] if take_coaching else 0.0
        hostel_fee = bd['room_rent'] if take_day_hostel else 0.0
        car_fee = flat_transport_fee if take_car else 0.0
        
        line_items = []
        if school_fee > 0.0:
            line_items.append(('Monthly Tuition Fee', school_fee))
        if coaching_fee > 0.0:
            line_items.append(('Monthly Coaching Fee', coaching_fee))
        if hostel_fee > 0.0:
            line_items.append(('Monthly Hostel Fee', hostel_fee))
        if car_fee > 0.0:
            line_items.append(('Monthly Transport Fee', car_fee))
            
        total_due = school_fee + coaching_fee + hostel_fee + car_fee
        if total_due <= 0.0:
            continue
            
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
            SET month_end_billing_count = COALESCE(month_end_billing_count, 0) + 1
            WHERE user_id = ?
        ''', (student_id,))
        sync_student_ledger_and_dues(conn, student_id)
        billed_count += 1
        
    return billed_count

def undo_monthly_billing(conn, month=None, year=None):
    from datetime import datetime
    if not month:
        month = datetime.now().strftime('%B')
    if not year:
        year = datetime.now().strftime('%Y')
        
    entries = conn.execute('''
        SELECT id, student_id, amount 
        FROM student_ledger 
        WHERE month = ? AND year = ? AND fee_type LIKE 'Monthly%' AND status = 'Unpaid/Pending'
    ''', (month, year)).fetchall()
    
    deleted_count = 0
    for entry in entries:
        entry_id = entry['id']
        student_id = entry['student_id']
        amount = float(entry['amount'])
        
        conn.execute("DELETE FROM student_ledger WHERE id = ?", (entry_id,))
        conn.execute("DELETE FROM financial_logs WHERE student_id = ? AND log_type = 'Charge' AND month = ? AND year = ? AND amount = ?", (student_id, month, year, amount))
        
        conn.execute('''
            UPDATE student_info
            SET month_end_billing_count = CASE 
                    WHEN COALESCE(month_end_billing_count, 0) - 1 < 0 THEN 0
                    ELSE COALESCE(month_end_billing_count, 0) - 1
                END,
                remaining_fee = CASE 
                    WHEN COALESCE(remaining_fee, 0.0) - ? < 0 THEN 0.0
                    ELSE COALESCE(remaining_fee, 0.0) - ?
                END
            WHERE user_id = ?
        ''', (amount, amount, student_id))
        deleted_count += 1
        
    return deleted_count

def record_ledger_payment(conn, student_id, amount_paid):
    from datetime import datetime
    month = datetime.now().strftime('%B')
    year = datetime.now().strftime('%Y')
    
    unpaid_entries = conn.execute('''
        SELECT id, amount, fee_type, branch 
        FROM student_ledger 
        WHERE student_id = ? AND status = 'Unpaid/Pending'
        ORDER BY id ASC
    ''', (student_id,)).fetchall()
    
    remaining_payment = float(amount_paid)
    for entry in unpaid_entries:
        entry_id = entry['id']
        entry_amount = float(entry['amount'])
        
        if remaining_payment >= entry_amount:
            conn.execute('''
                UPDATE student_ledger 
                SET status = 'Paid', paid_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (entry_id,))
            
            conn.execute('''
                INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                VALUES (?, 'Payment', ?, ?, ?, ?, ?)
            ''', (student_id, entry['fee_type'] + ' Payment', entry_amount, month, year, entry['branch']))
            
            remaining_payment -= entry_amount
        else:
            if remaining_payment > 0:
                conn.execute('''
                    UPDATE student_ledger 
                    SET amount = ?, status = 'Paid', paid_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (remaining_payment, entry_id))
                
                conn.execute('''
                    INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                    VALUES (?, 'Payment', ?, ?, ?, ?, ?)
                ''', (student_id, entry['fee_type'] + ' Payment', remaining_payment, month, year, entry['branch']))
                
                remainder = entry_amount - remaining_payment
                conn.execute('''
                    INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                    VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                ''', (student_id, entry['fee_type'], remainder, month, year, entry['branch']))
                
                remaining_payment = 0
            break
            
    conn.execute('''
        UPDATE student_info
        SET remaining_fee = CASE 
            WHEN COALESCE(remaining_fee, 0.0) - ? < 0 THEN 0.0 
            ELSE COALESCE(remaining_fee, 0.0) - ? 
        END
        WHERE user_id = ?
    ''', (float(amount_paid), float(amount_paid), student_id))

def run_year_end_billing(conn, year=None):
    from datetime import datetime
    if not year:
        year = datetime.now().strftime('%Y')
    month = datetime.now().strftime('%B')
        
    students = conn.execute('''
        SELECT u.id, si.class, si.branch, si.take_school, si.take_coaching, si.take_day_hostel, si.is_custom_fee, si.readmission_fee
        FROM users u
        JOIN student_info si ON u.id = si.user_id
        WHERE u.role = 'student'
    ''').fetchall()
    
    billed_count = 0
    for student in students:
        student_id = student['id']
        class_name = student['class']
        branch = student['branch'] or 'bhogram'
        take_school = int(student['take_school'] if student['take_school'] is not None else 1)
        take_coaching = int(student['take_coaching'] or 0)
        take_day_hostel = int(student['take_day_hostel'] or 0)
        
        # Check duplicate billing for Re-admission fee in this year
        already_billed = conn.execute('''
            SELECT id FROM student_ledger 
            WHERE student_id = ? AND year = ? AND fee_type = 'Re-admission Fee'
        ''', (student_id, year)).fetchone()
        if already_billed:
            continue
            
        custom_readm = student['readmission_fee'] if student['is_custom_fee'] else None
        
        amount = 0.0
        if custom_readm is not None and float(custom_readm) > 0.0:
            amount = float(custom_readm)
        else:
            matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
            if matrix:
                if take_day_hostel:
                    amount = float(matrix['hostel_readmission'] or 0.0)
                elif take_coaching:
                    amount = float(matrix['coaching_readmission'] or 0.0)
                else:
                    amount = float(matrix['school_readmission'] or 0.0)
            else:
                cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (class_name.lower(), branch.lower())).fetchone()
                if cls_row:
                    if take_day_hostel:
                        amount = float(cls_row['readmission_fee_hostel'] or 0.0)
                    elif take_coaching:
                        amount = float(cls_row['readmission_fee_coaching'] or 0.0)
                    else:
                        amount = float(cls_row['readmission_fee_school'] or 0.0)
                        
        if amount <= 0.0:
            continue
            
        conn.execute('''
            INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
            VALUES (?, 'Re-admission Fee', ?, ?, ?, 'Unpaid/Pending', ?)
        ''', (student_id, amount, month, year, branch))
        
        conn.execute('''
            INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
            VALUES (?, 'Charge', 'Re-admission Fee', ?, ?, ?, ?)
        ''', (student_id, amount, month, year, branch))
        
        conn.execute('''
            UPDATE student_info
            SET year_end_billing_count = COALESCE(year_end_billing_count, 0) + 1
            WHERE user_id = ?
        ''', (student_id,))
        sync_student_ledger_and_dues(conn, student_id)
        billed_count += 1
        
    return billed_count

def undo_year_end_billing(conn, year=None):
    from datetime import datetime
    if not year:
        year = datetime.now().strftime('%Y')
        
    entries = conn.execute('''
        SELECT id, student_id, amount 
        FROM student_ledger 
        WHERE year = ? AND fee_type = 'Re-admission Fee' AND status = 'Unpaid/Pending'
    ''', (year,)).fetchall()
    
    deleted_count = 0
    for entry in entries:
        entry_id = entry['id']
        student_id = entry['student_id']
        amount = float(entry['amount'])
        
        conn.execute("DELETE FROM student_ledger WHERE id = ?", (entry_id,))
        conn.execute("DELETE FROM financial_logs WHERE student_id = ? AND log_type = 'Charge' AND fee_type = 'Re-admission Fee' AND year = ? AND amount = ?", (student_id, year, amount))
        
        conn.execute('''
            UPDATE student_info
            SET year_end_billing_count = CASE 
                    WHEN COALESCE(year_end_billing_count, 0) - 1 < 0 THEN 0
                    ELSE COALESCE(year_end_billing_count, 0) - 1
                END,
                remaining_fee = CASE 
                    WHEN COALESCE(remaining_fee, 0.0) - ? < 0 THEN 0.0
                    ELSE COALESCE(remaining_fee, 0.0) - ?
                END
            WHERE user_id = ?
        ''', (amount, amount, student_id))
        deleted_count += 1
        
    return deleted_count

def sync_student_ledger_and_dues(conn, student_id, submitted_remaining_fee=None, *args, **kwargs):
    is_manual_dues_change = kwargs.get('is_manual_dues_change', False)
    if not is_manual_dues_change and args:
        is_manual_dues_change = args[0]
        
    from datetime import datetime
    month = datetime.now().strftime('%B')
    year = datetime.now().strftime('%Y')
    
    student = conn.execute("SELECT * FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
    if not student:
        return
        
    student_dict = dict(student)
    if student_id == 1 or str(student_id) == '1':
        print(f"[DEBUG SYNC 1] student_id={student_id} submitted_remaining_fee={submitted_remaining_fee} args={args} kwargs={kwargs}")
        print(f"[DEBUG SYNC 2] student_dict={student_dict}")
    
    # 1. Recalculate what their current month/year billed fees SHOULD be
    take_school = int(student_dict.get('take_school') if student_dict.get('take_school') is not None else 1)
    take_coaching = int(student_dict.get('take_coaching') or 0)
    take_day_hostel = int(student_dict.get('take_day_hostel') or 0)
    take_car = int(student_dict.get('take_car') or 0)
    
    # Get monthly fee breakdown
    bd = calculate_student_fees_breakdown(student_dict, conn=conn)
    
    # Monthly expected items
    expected_monthly = {}
    if take_school and bd['tuition_fee'] > 0.0:
        expected_monthly['Monthly Tuition Fee'] = bd['tuition_fee']
    if take_coaching and bd['coaching_combo_fee'] > 0.0:
        expected_monthly['Monthly Coaching Fee'] = bd['coaching_combo_fee']
    if take_day_hostel and bd['room_rent'] > 0.0:
        expected_monthly['Monthly Hostel Fee'] = bd['room_rent']
    if take_car:
        flat_transport_fee = kwargs.get('flat_transport_fee')
        if flat_transport_fee is None:
            transport_row = conn.execute("SELECT flat_rate FROM transport_settings ORDER BY id DESC LIMIT 1").fetchone()
            flat_transport_fee = float(transport_row['flat_rate']) if transport_row else 400.0
        expected_monthly['Monthly Transport Fee'] = flat_transport_fee
        
    # Get global max billing counts
    max_month_end = kwargs.get('max_month_end')
    if max_month_end is None:
        max_month_end = conn.execute("SELECT MAX(month_end_billing_count) FROM student_info").fetchone()[0] or 0
        
    max_year_end = kwargs.get('max_year_end')
    if max_year_end is None:
        max_year_end = conn.execute("SELECT MAX(year_end_billing_count) FROM student_info").fetchone()[0] or 0
    
    curr_month_count = student_dict.get('month_end_billing_count') or 0
    curr_year_count = student_dict.get('year_end_billing_count') or 0
    
    has_monthly_run = False
    if curr_month_count < max_month_end:
        has_monthly_run = True
        conn.execute("UPDATE student_info SET month_end_billing_count = ? WHERE user_id = ?", (max_month_end, student_id))
    elif curr_month_count > 0:
        has_monthly_run = True
        
    has_year_end_run = False
    if curr_year_count < max_year_end:
        has_year_end_run = True
        conn.execute("UPDATE student_info SET year_end_billing_count = ? WHERE user_id = ?", (max_year_end, student_id))
    elif curr_year_count > 0:
        has_year_end_run = True
    
    if has_monthly_run:
        # Sync the current month's ledger entries
        existing_entries = conn.execute('''
            SELECT id, fee_type, amount, status 
            FROM student_ledger 
            WHERE student_id = ? AND month = ? AND year = ? AND fee_type LIKE 'Monthly%'
        ''', (student_id, month, year)).fetchall()
        
        existing_types = {e['fee_type']: e for e in existing_entries}
        
        for f_type, expected_amt in expected_monthly.items():
            if f_type in existing_types:
                entry = existing_types[f_type]
                if entry['status'] == 'Unpaid/Pending':
                    if float(entry['amount']) != expected_amt:
                        conn.execute("UPDATE student_ledger SET amount = ? WHERE id = ?", (expected_amt, entry['id']))
                        conn.execute("UPDATE financial_logs SET amount = ? WHERE student_id = ? AND log_type = 'Charge' AND fee_type = ? AND month = ? AND year = ?", (expected_amt, student_id, f_type, month, year))
            else:
                if expected_amt > 0.0:
                    conn.execute('''
                        INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                        VALUES (?, ?, ?, ?, ?, 'Unpaid/Pending', ?)
                    ''', (student_id, f_type, expected_amt, month, year, student_dict['branch']))
                    conn.execute('''
                        INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                        VALUES (?, 'Charge', ?, ?, ?, ?, ?)
                    ''', (student_id, f_type, expected_amt, month, year, student_dict['branch']))
                    
        for f_type in existing_types:
            if f_type not in expected_monthly:
                entry = existing_types[f_type]
                if entry['status'] == 'Unpaid/Pending':
                    conn.execute("DELETE FROM student_ledger WHERE id = ?", (entry['id'],))
                    conn.execute("DELETE FROM financial_logs WHERE student_id = ? AND log_type = 'Charge' AND fee_type = ? AND month = ? AND year = ?", (student_id, f_type, month, year))

    # 2. Check Re-admission Fee (Year End)
    expected_readm = 0.0
    matrix = conn.execute("SELECT * FROM fee_matrix WHERE LOWER(class_name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
    if matrix:
        if take_day_hostel:
            expected_readm = float(matrix['hostel_readmission'] or 0.0)
        elif take_coaching:
            expected_readm = float(matrix['coaching_readmission'] or 0.0)
        else:
            expected_readm = float(matrix['school_readmission'] or 0.0)
    else:
        cls_row = conn.execute("SELECT * FROM classes WHERE LOWER(name) = LOWER(?) AND LOWER(branch) = LOWER(?)", (student_dict['class'].lower(), student_dict['branch'].lower())).fetchone()
        if cls_row:
            if take_day_hostel:
                expected_readm = float(cls_row['readmission_fee_hostel'] or 0.0)
            elif take_coaching:
                expected_readm = float(cls_row['readmission_fee_coaching'] or 0.0)
            else:
                expected_readm = float(cls_row['readmission_fee_school'] or 0.0)

    # Apply Financial Aid Readmission Reduction
    fin_aid_readm = float(student_dict.get('financial_aid_readmission') or 0.0)
    expected_readm = max(0.0, expected_readm - fin_aid_readm)

    if has_year_end_run:
        existing_readm = conn.execute('''
            SELECT id, amount, status 
            FROM student_ledger 
            WHERE student_id = ? AND year = ? AND fee_type = 'Re-admission Fee'
        ''', (student_id, year)).fetchone()
        
        if existing_readm:
            if existing_readm['status'] == 'Unpaid/Pending':
                if float(existing_readm['amount']) != expected_readm:
                    if expected_readm > 0.0:
                        conn.execute("UPDATE student_ledger SET amount = ? WHERE id = ?", (expected_readm, existing_readm['id']))
                        conn.execute("UPDATE financial_logs SET amount = ? WHERE student_id = ? AND log_type = 'Charge' AND fee_type = 'Re-admission Fee' AND year = ?", (expected_readm, student_id, year))
                    else:
                        conn.execute("DELETE FROM student_ledger WHERE id = ?", (existing_readm['id'],))
                        conn.execute("DELETE FROM financial_logs WHERE student_id = ? AND log_type = 'Charge' AND fee_type = 'Re-admission Fee' AND year = ?", (student_id, year))
        else:
            if expected_readm > 0.0:
                conn.execute('''
                    INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                    VALUES (?, 'Re-admission Fee', ?, ?, ?, 'Unpaid/Pending', ?)
                ''', (student_id, expected_readm, month, year, student_dict['branch']))
                conn.execute('''
                    INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                    VALUES (?, 'Charge', 'Re-admission Fee', ?, ?, ?, ?)
                ''', (student_id, expected_readm, month, year, student_dict['branch']))

    # 3. Calculate expected dues based on formula:
    # total = prev_dues + monthly * total_monthly_trigger + re_admission * total_yearly_trigger - total_paid
    monthly_fee_val = float(bd['total_fee'] or 0.0)
    readmission_fee_val = expected_readm
        
    billing_month_count = max_month_end if curr_month_count < max_month_end else curr_month_count
    billing_year_count = max_year_end if curr_year_count < max_year_end else curr_year_count
    
    total_paid = conn.execute("SELECT SUM(amount) FROM fees WHERE student_id = ? AND status = 'Paid'", (student_id,)).fetchone()[0] or 0.0
    prev_dues = float(student_dict.get('prev_dues') or 0.0)
    
    expected_remaining_fee = prev_dues + (monthly_fee_val * billing_month_count) + (readmission_fee_val * billing_year_count) - total_paid
    # ALLOW NEGATIVE DUES
        


    if student_id == 1 or str(student_id) == '1':
        print(f"[DEBUG SYNC 3] expected_remaining_fee={expected_remaining_fee} prev_dues={prev_dues} billing_month_count={billing_month_count} billing_year_count={billing_year_count} total_paid={total_paid} monthly_fee_val={monthly_fee_val} readmission_fee_val={readmission_fee_val}")

    # Recalculate sum of Unpaid/Pending ledger entries
    unpaid_sum = conn.execute("SELECT SUM(amount) FROM student_ledger WHERE student_id = ? AND status = 'Unpaid/Pending'", (student_id,)).fetchone()[0] or 0.0
    
    diff = expected_remaining_fee - unpaid_sum
    if abs(diff) > 0.01:
        if diff > 0:
            conn.execute('''
                INSERT INTO student_ledger (student_id, fee_type, amount, month, year, status, branch)
                VALUES (?, 'Balance Adjustment', ?, ?, ?, 'Unpaid/Pending', ?)
            ''', (student_id, diff, month, year, student_dict['branch']))
            conn.execute('''
                INSERT INTO financial_logs (student_id, log_type, fee_type, amount, month, year, branch)
                VALUES (?, 'Charge', 'Balance Adjustment', ?, ?, ?, ?)
            ''', (student_id, diff, month, year, student_dict['branch']))
        else:
            unpaid_entries_desc = conn.execute('''
                SELECT id, amount 
                FROM student_ledger 
                WHERE student_id = ? AND status = 'Unpaid/Pending'
                ORDER BY id DESC
            ''', (student_id,)).fetchall()
            to_deduct = abs(diff)
            for entry in unpaid_entries_desc:
                if to_deduct <= 0:
                    break
                entry_amt = float(entry['amount'])
                if to_deduct >= entry_amt:
                    conn.execute("DELETE FROM student_ledger WHERE id = ?", (entry['id'],))
                    to_deduct -= entry_amt
                else:
                    conn.execute("UPDATE student_ledger SET amount = ? WHERE id = ?", (entry_amt - to_deduct, entry['id']))
                    to_deduct = 0.0
        # Re-sum after adjustment (applies to both positive and negative directions)
        unpaid_sum = conn.execute("SELECT SUM(amount) FROM student_ledger WHERE student_id = ? AND status = 'Unpaid/Pending'", (student_id,)).fetchone()[0] or 0.0

    conn.execute("UPDATE student_info SET remaining_fee = ? WHERE user_id = ?", (unpaid_sum, student_id))

def migrate_existing_readmission_fees_in_fees_table(conn):
    try:
        conn.execute("ALTER TABLE fees ADD COLUMN readmission_revenue REAL DEFAULT 0.0")
        conn.commit()
    except Exception:
        pass

    paid_readmissions = conn.execute('''
        SELECT student_id, amount, month, year, paid_at
        FROM student_ledger
        WHERE fee_type = 'Re-admission Fee' AND status = 'Paid'
    ''').fetchall()
    
    for row in paid_readmissions:
        student_id = row['student_id']
        amount = float(row['amount'])
        month = row['month']
        year = row['year']
        
        # Match by student, month, year
        fee_record = conn.execute('''
            SELECT id, amount, school_revenue, hostel_revenue, coaching_revenue, tax_amount, readmission_revenue
            FROM fees
            WHERE student_id = ? AND month = ? AND year = ? AND status = 'Paid'
            LIMIT 1
        ''', (student_id, month, year)).fetchone()
        
        if not fee_record:
            fee_record = conn.execute('''
                SELECT id, amount, school_revenue, hostel_revenue, coaching_revenue, tax_amount, readmission_revenue
                FROM fees
                WHERE student_id = ? AND status = 'Paid'
                ORDER BY abs(strftime('%s', paid_at) - strftime('%s', ?)) ASC
                LIMIT 1
            ''', (student_id, row['paid_at'] or datetime.now().isoformat())).fetchone()
            
        if fee_record:
            fee_id = fee_record['id']
            curr_readmission = float(fee_record['readmission_revenue'] or 0.0)
            if curr_readmission < amount:
                diff = amount - curr_readmission
                school_rev = float(fee_record['school_revenue'] or 0.0)
                hostel_rev = float(fee_record['hostel_revenue'] or 0.0)
                coaching_rev = float(fee_record['coaching_revenue'] or 0.0)
                tax_amt = float(fee_record['tax_amount'] or 0.0)
                
                remaining_to_deduct = diff
                deduct_school = min(remaining_to_deduct, school_rev)
                school_rev -= deduct_school
                remaining_to_deduct -= deduct_school
                
                deduct_hostel = min(remaining_to_deduct, hostel_rev)
                hostel_rev -= deduct_hostel
                remaining_to_deduct -= deduct_hostel
                
                deduct_coaching = min(remaining_to_deduct, coaching_rev)
                coaching_rev -= deduct_coaching
                remaining_to_deduct -= deduct_coaching
                
                deduct_tax = min(remaining_to_deduct, tax_amt)
                tax_amt -= deduct_tax
                
                conn.execute('''
                    UPDATE fees
                    SET school_revenue = ?, hostel_revenue = ?, coaching_revenue = ?, tax_amount = ?, readmission_revenue = ?
                    WHERE id = ?
                ''', (school_rev, hostel_rev, coaching_rev, tax_amt, amount, fee_id))
    conn.commit()

def run_startup_migrations():
    print("Running database migrations and startup tasks...")
    try:
        consolidate_databases()
        update_bhogram_class_fees()
        migrate_class_teachers_and_complaints_schema()
        sync_all_existing_teacher_assignments()
        migrate_billing_system()
        # Retrospective readmission fees migration
        conn = get_db_connection()
        migrate_existing_readmission_fees_in_fees_table(conn)
        conn.close()
        print("Startup tasks complete.")
    except Exception as e:
        print(f"Error during startup tasks: {e}")

@app.route('/admin/fix-dues-corruption')
def fix_dues_corruption():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # 1. Set all prev_dues to remaining_fee (assume remaining fees as previous dues)
    conn.execute("UPDATE student_info SET prev_dues = COALESCE(remaining_fee, 0.0)")
    
    # 2. Delete all artificially injected Balance Adjustments
    conn.execute("DELETE FROM student_ledger WHERE fee_type = 'Balance Adjustment'")
    
    # 3. Recalculate everything naturally
    students = conn.execute("SELECT user_id FROM student_info").fetchall()
    for s in students:
        try:
            sync_student_ledger_and_dues(conn, s['user_id'])
        except Exception as e:
            print(f"Failed to sync {s['user_id']}: {e}")
            
    conn.commit()
    conn.close()
    
    flash("Successfully healed all corrupted student balances!")
    return redirect(url_for('audit_report'))

@app.route('/debug/find-func')
def debug_find_func():
    with open(__file__, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    out = []
    for i, line in enumerate(lines):
        if '/student/edit-info' in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 20)
            out.append(f"Lines {start+1}-{end}:\\n" + "".join(lines[start:end]))
    return "\\n\\n".join(out) if out else "Not found"

@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        run_startup_migrations()
    port = int(os.getenv('PORT', 5001))
    print(f"Starting server on port {port} (debug=True)...")
    app.run(host='0.0.0.0', port=port, debug=True)
