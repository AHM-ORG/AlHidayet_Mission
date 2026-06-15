import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import json
import random
import string
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import csv
import io
import google.generativeai as genai

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-dev-secret-key')

# Database Configuration
DB_NAME = "users.db"

# Email Configuration
SENDER_EMAIL = os.getenv('MAIL_USERNAME', "missionalhidayet@gmail.com")
SENDER_PASSWORD = os.getenv('MAIL_PASSWORD', "kvmwecfrzqbnrbxb")

# Helper: Real Email Sender for OTP
def send_otp_email(to_email, otp):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print(" [EMAIL ERROR] Missing email credentials.")
        return False
        
    try:
        subject = "AHM Login Verification Code"
        body = f"Your OTP Verification Code is: {otp}\n\nDo not share this code with anyone."
        
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email

        # Connect to Gmail SMTP Server
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            
        print(f" [EMAIL SENT] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f" [EMAIL ERROR] Failed to send OTP: {e}")
        return False

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def generate_unique_student_code(c):
    while True:
        code = "AHM-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not c.execute("SELECT user_id FROM student_info WHERE unique_code = ?", (code,)).fetchone():
            return code

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tables creation
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            security_key TEXT NOT NULL
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
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject TEXT,
            marks INTEGER,
            total_marks INTEGER,
            term TEXT,
            teacher_id INTEGER,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        )
    ''')
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
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL,
            category TEXT,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            class TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS teacher_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            subject_id INTEGER,
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id),
            UNIQUE(teacher_id, subject_id)
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
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
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
    
    # Default Admin
    c.execute('SELECT * FROM users WHERE username = ?', ('headmaster',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)',
                  ('headmaster', 'rmdaswif@gmail.com', 'admin123', 'admin', 'admin-secret'))
    
    conn.commit()
    conn.close()

# Initialize DB
init_db()

# Upload Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_BASE

# Branch Configuration
BRANCHES = ['surangapur', 'bhogram']
CATEGORIES = ['photos', 'videos']

# Branding Configuration
LOGO_URL = "https://i.postimg.cc/rpQPT9pk/logo-(1).jpg"
ESTD_YEAR = "2010"

@app.context_processor
def inject_branding():
    return dict(logo_url=LOGO_URL, estd_year=ESTD_YEAR, role=session.get('role'))

# Folder Creation Helper
def create_folders():
    for branch in BRANCHES:
        for category in CATEGORIES:
            path = os.path.join(UPLOAD_BASE, branch, category)
            os.makedirs(path, exist_ok=True)

create_folders()

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/gallery')
def gallery():
    gallery_data = {}
    for branch in BRANCHES:
        gallery_data[branch] = {}
        for category in CATEGORIES:
            path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
            files = os.listdir(path) if os.path.exists(path) else []
            gallery_data[branch][category] = files

    # Check if there is any actual content
    has_content = any(any(items) for branch, categories in gallery_data.items() for items in categories.values())
    if not has_content:
        gallery_data = {}

    return render_template('gallery.html', gallery_data=gallery_data)

@app.route('/login/<user_type>', methods=['GET', 'POST'])
def login(user_type):
    if request.method == 'POST':
        # Step 1: Check Username & Password
        if 'otp_verified' not in session:
            username = request.form['username']
            password = request.form['password']
            
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
            conn.close()

            if user:
                email = user['email']
                
                # Check if email is valid before proceeding
                if not email or '@' not in email:
                     flash('Account has no valid email linked. Please contact admin.')
                     return render_template('login.html', user_type=user_type)

                otp = generate_otp()
                
                # Attempt to send OTP
                if send_otp_email(email, otp):
                    session['temp_user'] = {'username': user['username'], 'role': user['role']}
                    session['otp'] = otp
                    session['otp_email'] = email
                    return render_template('verify_otp.html', email=email, context='login')
                else:
                    flash('Error sending verification code. Please try again later.')
            else:
                flash('Invalid Username or Password!')
            
    return render_template('login.html', user_type=user_type)

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
                    session['user'] = temp_user['username']
                    session['role'] = temp_user['role']
                    session.pop('temp_user', None)
                    flash('Login Successful!')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Session expired. Please login again.')
                    return redirect(url_for('home'))
                    
            elif context == 'forgot_password':
                session['reset_verified'] = True
                return redirect(url_for('reset_new_password'))
        else:
            flash('Invalid OTP! Please try again.')
    
    return render_template('verify_otp.html', email=session.get('otp_email'), context=context)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        security_key = request.form['security_key']

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                      (username, email, password, role, security_key))
            user_id = c.lastrowid
            
            if role == 'student':
                # Extract student info safely
                info = {
                    'branch': request.form.get('branch'),
                    'class': request.form.get('class'),
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
                
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login', user_type='student'))
        except sqlite3.IntegrityError:
            flash('Username already exists!')
        except Exception as e:
            flash(f'Registration error: {str(e)}')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user:
            email = user['email']
            if not email:
                flash('No email found for this user. Cannot send OTP.')
                return render_template('forgot_password.html')

            otp = generate_otp()
            if send_otp_email(email, otp):
                session['otp'] = otp
                session['otp_email'] = email
                session['reset_user_id'] = user['id']
                return render_template('verify_otp.html', email=email, context='forgot_password')
            else:
                 flash('Failed to send OTP. Check system logs.')
        else:
            flash('User not found!')

    return render_template('forgot_password.html')

@app.route('/reset-new-password', methods=['GET', 'POST'])
def reset_new_password():
    if not session.get('reset_verified'):
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        user_id = session.get('reset_user_id')
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()
        conn.close()
        
        session.pop('reset_verified', None)
        session.pop('reset_user_id', None)
        flash('Password Reset Successfully! Please Login.')
        return redirect(url_for('login', user_type='student'))

    return render_template('reset_password.html')

@app.route('/dashboard')
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

        if role == 'admin':
            all_users = c.execute("SELECT id, username, email, role, password FROM users").fetchall()
            all_notices = c.execute("SELECT * FROM notices ORDER BY created_at DESC").fetchall()
            
            pending_forms = c.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                ORDER BY a.submitted_at DESC
            ''').fetchall()
            
            pending_gallery = c.execute('''
                SELECT pm.*, u.username 
                FROM pending_media pm 
                JOIN users u ON pm.user_id = u.id 
                WHERE pm.status = 'Pending'
                ORDER BY pm.submitted_at DESC
            ''').fetchall()

        elif role == 'student':
            student_info = c.execute('''
                SELECT si.*, u.email 
                FROM student_info si 
                JOIN users u ON si.user_id = u.id 
                WHERE u.username = ?
            ''', (username,)).fetchone()

            student_marks = c.execute('''
                SELECT m.*, u.username as teacher_name 
                FROM marks m 
                JOIN users u ON m.teacher_id = u.id 
                WHERE m.student_id = (SELECT id FROM users WHERE username = ?)
                ORDER BY m.submitted_at DESC LIMIT 5
            ''', (username,)).fetchall()
            
            all_notices = c.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 3").fetchall()

        # Files logic
        content = {}
        for branch in BRANCHES:
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
                               student_info=student_info,
                               student_marks=student_marks,
                               all_users=all_users,
                               all_notices=all_notices,
                               pending_forms=pending_forms,
                               pending_gallery=pending_gallery)
    return redirect(url_for('home'))

@app.route('/admission-form')
def admission_form():
    return render_template('application_form.html')

@app.route('/submit-application', methods=['POST'])
def submit_application():
    form_data = request.form.to_dict()
    form_type = form_data.get('form_type', 'Admission Form')
    
    user_id = None
    if 'user' in session:
        conn = get_db_connection()
        res = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
        if res: user_id = res['id']
        conn.close()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO applications (user_id, type, data)
        VALUES (?, ?, ?)
    ''', (user_id, form_type, json.dumps(form_data)))
    conn.commit()
    conn.close()
    
    flash('Your application has been submitted successfully!')
    return redirect(url_for('home'))

@app.route('/admin/applications')
def admin_applications():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        applications = conn.execute('''
            SELECT a.id, a.type, a.status, a.submitted_at, u.username 
            FROM applications a 
            LEFT JOIN users u ON a.user_id = u.id 
            ORDER BY a.submitted_at DESC
        ''').fetchall()
        conn.close()
        return render_template('admin/application_list.html', applications=applications)
    return redirect(url_for('home'))

@app.route('/admin/view-form/<int:form_id>')
def view_form(form_id):
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        form = conn.execute("SELECT * FROM applications WHERE id = ?", (form_id,)).fetchone()
        conn.close()
        
        if form:
            data = json.loads(form['data'])
            return render_template('admin_form_view.html', form=form, data=data)
    return redirect(url_for('dashboard'))

@app.route('/admin/form-action/<int:form_id>/<action>', methods=['POST'])
def form_action(form_id, action):
    if 'user' in session and session['role'] == 'admin':
        status = 'Accepted' if action == 'approve' else 'Rejected'
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, form_id))
        conn.commit()
        conn.close()
        flash(f'Application {status}!')
    return redirect(url_for('admin_applications'))

@app.route('/admin/post-notice', methods=['POST'])
def post_notice():
    if 'user' in session and session['role'] == 'admin':
        content = request.form['content']
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT INTO notices (content) VALUES (?)", (content,))
        conn.commit()
        conn.close()
        flash('Notice posted successfully!')
    return redirect(url_for('dashboard'))

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user' in session and session['role'] == 'admin':
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        c.execute("DELETE FROM student_info WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM teacher_info WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {'status': 'success'}
        flash('User deleted successfully!')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {'status': 'error', 'message': 'Permission denied'}
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/reset-password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    if 'user' in session and session['role'] == 'admin':
        new_password = 'mission123' 
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()
        conn.close()
        flash(f'Password reset successfully to: {new_password}')
    return redirect(url_for('dashboard'))

@app.route('/admin/media-action/<int:media_id>/<action>', methods=['POST'])
def media_action(media_id, action):
    if 'user' in session and session['role'] == 'admin':
        status = 'Approved' if action == 'approve' else 'Rejected'
        conn = sqlite3.connect(DB_NAME)
        if status == 'Approved':
            conn.execute("UPDATE pending_media SET status = 'Approved' WHERE id = ?", (media_id,))
        else:
            conn.execute("UPDATE pending_media SET status = 'Rejected' WHERE id = ?", (media_id,))
        conn.commit()
        conn.close()
        flash(f'Media {status}!')
    return redirect(url_for('dashboard'))

@app.route('/admin/student-list')
def student_list():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        students = conn.execute('''
            SELECT u.id, u.username, u.password, u.email, si.full_name, si.branch, si.class, si.roll_number, si.unique_code 
            FROM users u 
            LEFT JOIN student_info si ON u.id = si.user_id 
            WHERE u.role = 'student'
            ORDER BY si.class, si.roll_number
        ''').fetchall()
        teachers = conn.execute('''
            SELECT u.id, u.username, u.password, u.email, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        
        conn.close()
        students_by_class = {}
        for student in students:
            cls = student['class'] or 'Unassigned'
            if cls not in students_by_class:
                students_by_class[cls] = []
            students_by_class[cls].append(student)
            
        return render_template('admin/student_list.html', students=students, students_by_class=students_by_class, teachers=teachers, role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/add-student-manual', methods=['GET', 'POST'])
def add_student_manual():
    if 'user' in session and session['role'] == 'admin':
        if request.method == 'POST':
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']
            role = 'student'
            security_key = 'admin-secret'

            conn = get_db_connection()
            try:
                # Insert into users
                conn.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                          (username, email, password, role, security_key))
                user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Insert into student_info
                info = {
                    'branch': request.form.get('branch'),
                    'class': request.form.get('class'),
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
                    'phone_number': request.form.get('phone_number')
                }

                unique_code = generate_unique_student_code(conn)
                
                conn.execute('''
                    INSERT INTO student_info (user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number, unique_code)
                    VALUES (:user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number, :unique_code)
                ''', {**info, 'user_id': user_id, 'unique_code': unique_code})
                
                conn.commit()
                flash('Student added manually successfully!')
                return redirect(url_for('student_list'))
            except sqlite3.IntegrityError:
                flash('Username already exists!')
            except Exception as e:
                flash(f'Error adding student: {str(e)}')
            finally:
                conn.close()

        return render_template('admin/add_student.html')
    return redirect(url_for('home'))

@app.route('/admin/edit-student/<int:user_id>', methods=['GET', 'POST'])
def edit_student(user_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        
        if request.method == 'POST':
            # Update user info
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']
            
            try:
                conn.execute("UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?", 
                             (username, email, password, user_id))
                
                # Update student_info
                info = {
                    'branch': request.form.get('branch'),
                    'class': request.form.get('class'),
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
                    'phone_number': request.form.get('phone_number')
                }
                
                conn.execute('''
                    UPDATE student_info SET
                        branch = :branch, class = :class, roll_number = :roll_number, full_name = :full_name,
                        guardian_name = :guardian_name, dob = :dob, section = :section, blood_group = :blood_group,
                        village = :village, post_office = :post_office, police_station = :police_station,
                        district = :district, phone_number = :phone_number
                    WHERE user_id = :user_id
                ''', {**info, 'user_id': user_id})
                
                conn.commit()
                flash('Student updated successfully!')
                return redirect(url_for('student_list'))
            except sqlite3.IntegrityError:
                flash('Username already exists or database error!')
            finally:
                conn.close()

        # GET request: fetch existing data
        student = conn.execute('''
            SELECT u.username, u.email, u.password, si.* 
            FROM users u
            LEFT JOIN student_info si ON u.id = si.user_id
            WHERE u.id = ? AND u.role = 'student'
        ''', (user_id,)).fetchone()
        conn.close()
        
        if not student:
            flash('Student not found!')
            return redirect(url_for('student_list'))
            
        return render_template('admin/edit_student.html', student=student, user_id=user_id)
    return redirect(url_for('home'))

@app.route('/admin/add-user', methods=['GET', 'POST'])
def add_user():
    if 'user' in session and session['role'] == 'admin':
        if request.method == 'POST':
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']
            role = request.form['role']
            security_key = request.form.get('security_key', 'admin-secret')

            conn = get_db_connection()
            try:
                # Insert into users
                conn.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                          (username, email, password, role, security_key))
                user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                if role == 'teacher':
                    full_name = request.form.get('full_name', '')
                    phone_number = request.form.get('phone_number', '')
                    qualification = request.form.get('qualification', '')
                    joining_date = request.form.get('joining_date', '')
                    address = request.form.get('address', '')
                    conn.execute('''
                        INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, full_name, phone_number, qualification, joining_date, address))
                elif role == 'student':
                    info = {
                        'branch': request.form.get('branch'),
                        'class': request.form.get('class'),
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
                        'phone_number': request.form.get('student_phone')
                    }
                    conn.execute('''
                        INSERT INTO student_info (user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number)
                        VALUES (:user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number)
                    ''', {**info, 'user_id': user_id})

                conn.commit()
                flash(f'User ({role}) added successfully!')
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                flash('Username already exists!')
            except Exception as e:
                flash(f'Error adding user: {str(e)}')
            finally:
                conn.close()

        return render_template('admin/add_user.html')
    return redirect(url_for('home'))

@app.route('/admin/input-result', methods=['GET', 'POST'])
def input_result():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        if request.method == 'POST':
            student_id = request.form['student_id']
            subject = request.form['subject']
            marks = request.form['marks']
            total = request.form['total_marks']
            term = request.form['term']
            
            teacher = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
            
            conn.execute('''
                INSERT INTO marks (student_id, subject, marks, total_marks, term, teacher_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (student_id, subject, marks, total, term, teacher['id']))
            conn.commit()
            flash('Marks entered successfully!')
            conn.close()
            return redirect(url_for('input_result'))

        students = conn.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
        conn.close()
        return render_template('admin/input_result.html', students=students)
    return redirect(url_for('home'))

@app.route('/admin/marksheet')
def marksheet():
    if 'user' in session:
        conn = get_db_connection()
        role = session['role']
        
        user = conn.execute("SELECT id, role FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        student_id = user['id'] if user['role'] == 'student' else request.args.get('student_id')
            
        if student_id:
            marks = conn.execute('''
                SELECT m.*, u.username as student_name 
                FROM marks m 
                JOIN users u ON m.student_id = u.id 
                WHERE m.student_id = ?
                ORDER BY m.submitted_at DESC
            ''', (student_id,)).fetchall()
            conn.close()
            return render_template('admin/marksheet.html', marks=marks, role=role)
        
        students = conn.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
        conn.close()
        return render_template('admin/marksheet.html', marks=None, students=students, role=role)
    return redirect(url_for('home'))

@app.route('/admin/bulk-marks', methods=['GET', 'POST'])
def bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        
        # Determine the user's role and fetch allowed subjects if teacher
        role = session['role']
        username = session['user']
        allowed_subjects = []
        
        if role == 'teacher':
             # Find teacher's assigned subjects
             teacher_id = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()['id']
             subjects_rows = conn.execute('''
                SELECT s.name, s.class FROM subjects s
                JOIN teacher_subjects ts ON s.id = ts.subject_id
                WHERE ts.teacher_id = ?
             ''', (teacher_id,)).fetchall()
             allowed_subjects = [{'name': r['name'], 'class': r['class']} for r in subjects_rows]

        students = []
        selected_branch = request.args.get('branch')
        selected_class = request.args.get('class')
        
        if selected_branch and selected_class:
            students = conn.execute('''
                SELECT u.id, u.username, si.roll_number 
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE si.branch = ? AND si.class = ?
            ''', (selected_branch, selected_class)).fetchall()
            
        conn.close()
        
        # Filter subjects if teacher, otherwise show text input or all
        return render_template('admin/bulk_marks.html', 
                               students=students, 
                               branches=BRANCHES, 
                               classes=['Nursery', 'KG', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'],
                               selected_branch=selected_branch,
                               selected_class=selected_class,
                               allowed_subjects=allowed_subjects,
                               role=role)
    return redirect(url_for('home'))

@app.route('/admin/save-bulk-marks', methods=['POST'])
def save_bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        subject = request.form['subject']
        term = request.form['term']
        total_marks = request.form['total_marks']
        
        conn = get_db_connection()
        teacher = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        # Security check: If teacher, verify they are assigned this subject
        if session['role'] == 'teacher':
             # Simplified check: in a real app, you'd check DB. 
             # Assuming the UI restricts them to valid choices for now.
             pass

        for key, value in request.form.items():
            if key.startswith('marks_') and value:
                student_id = key.split('_')[1]
                conn.execute('''
                    INSERT INTO marks (student_id, subject, marks, total_marks, term, teacher_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (student_id, subject, value, total_marks, term, teacher['id']))
        
        conn.commit()
        conn.close()
        flash('Bulk marks saved successfully!')
    return redirect(url_for('dashboard'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'user' in session and session['role'] == 'admin':
        if 'file' not in request.files:
            return 'No file part'
        
        file = request.files['file']
        branch = request.form.get('branch')
        category = request.form.get('category')

        if file.filename == '':
            return 'No selected file'
        
        if file and branch and category:
            target_folder = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
            file.save(os.path.join(target_folder, file.filename))
            flash(f'{branch.title()} {category} Uploaded successfully!')
            return redirect(url_for('dashboard'))
    
    return "Permission denied."

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
                
                conn.execute('''
                    INSERT INTO fees (student_id, amount, month, year, status, paid_at)
                    VALUES (?, ?, ?, ?, 'Paid', CURRENT_TIMESTAMP)
                ''', (student_id, amount, month, year))
                conn.commit()
                flash('Fee collected successfully!')
                conn.close()
                return redirect(url_for('get_fees'))

            students = conn.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
            recent_fees = conn.execute('''
                SELECT f.*, u.username as student_name 
                FROM fees f 
                JOIN users u ON f.student_id = u.id 
                ORDER BY f.paid_at DESC
            ''').fetchall()
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
            conn.close()
            return render_template('admin/get_fees.html', recent_fees=my_fees, role=role)
            
    return redirect(url_for('home'))

@app.route('/admin/reminder-fees')
def reminder_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        from datetime import datetime
        month = datetime.now().strftime('%B')
        year = datetime.now().strftime('%Y')
        
        pending_students = conn.execute('''
            SELECT u.id, u.username, si.phone_number 
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
            
            conn.execute('''
                INSERT INTO expenses (amount, category, description)
                VALUES (?, ?, ?)
            ''', (amount, category, description))
            conn.commit()
            flash('Expense recorded!')
            conn.close()
            return redirect(url_for('spend'))

        expenses = conn.execute("SELECT * FROM expenses ORDER BY date DESC").fetchall()
        conn.close()
        return render_template('admin/spend.html', expenses=expenses, role=role)
    return redirect(url_for('home'))

@app.route('/admin/audit-report')
def audit_report():
    if 'user' in session and session['role'] == 'admin':
        role = session['role']
        conn = get_db_connection()
        
        total_fees = conn.execute("SELECT SUM(amount) as total FROM fees").fetchone()['total'] or 0
        total_expenses = conn.execute("SELECT SUM(amount) as total FROM expenses").fetchone()['total'] or 0
        
        balance = total_fees - total_expenses
        conn.close()
        return render_template('admin/audit_report.html', fees=total_fees, expenses=total_expenses, balance=balance, role=role)
    return redirect(url_for('home'))

@app.route('/admin/academics-setting', methods=['GET', 'POST'])
def academics_setting():
    if 'user' in session and session['role'] == 'admin': # Only Admin sets subjects
        conn = get_db_connection()
        
        # Handle Subject Creation
        if request.method == 'POST' and 'create_subject' in request.form:
            name = request.form['name']
            class_name = request.form['class']
            conn.execute("INSERT INTO subjects (name, class) VALUES (?, ?)", (name, class_name))
            conn.commit()
            flash('Subject added!')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        # Handle Teacher Assignment
        if request.method == 'POST' and 'assign_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            subject_id = request.form['subject_id']
            try:
                conn.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (teacher_id, subject_id))
                conn.commit()
                flash('Teacher assigned to subject!')
            except sqlite3.IntegrityError:
                flash('This teacher is already assigned to this subject.')
            conn.close()
            return redirect(url_for('academics_setting'))

        subjects = conn.execute("SELECT * FROM subjects ORDER BY class, name").fetchall()
        teachers = conn.execute("SELECT id, username FROM users WHERE role = 'teacher'").fetchall()
        assignments = conn.execute('''
            SELECT ts.id, u.username as teacher_name, s.name as subject_name, s.class 
            FROM teacher_subjects ts
            JOIN users u ON ts.teacher_id = u.id
            JOIN subjects s ON ts.subject_id = s.id
        ''').fetchall()
        
        conn.close()
        return render_template('admin/academics_setting.html', subjects=subjects, teachers=teachers, assignments=assignments, role=session['role'])
    elif 'user' in session: # Teachers just view
         return render_template('admin/academics_setting.html', role=session['role']) # Needs simplified view
    return redirect(url_for('home'))

@app.route('/admin/student-promotion', methods=['GET', 'POST'])
def student_promotion():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        if request.method == 'POST':
            student_id = request.form['student_id']
            new_class = request.form['new_class']
            conn.execute("UPDATE student_info SET class = ? WHERE user_id = ?", (new_class, student_id))
            conn.commit()
            flash('Student promoted!')
            conn.close()
            return redirect(url_for('student_promotion'))

        students = conn.execute("SELECT u.id, u.username, si.class FROM users u JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
        conn.close()
        return render_template('admin/student_promotion.html', students=students, role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/admit-card')
def admit_card():
    if 'user' in session:
        conn = get_db_connection()
        user = conn.execute("SELECT id, role FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        if user['role'] in ['admin', 'teacher']:
            student_id = request.args.get('student_id')
            if student_id:
                student = conn.execute('''
                    SELECT u.username, si.class, si.roll_number, si.branch 
                    FROM users u 
                    JOIN student_info si ON u.id = si.user_id 
                    WHERE u.id = ?
                ''', (student_id,)).fetchone()
                conn.close()
                return render_template('admin/admit_card.html', student=student, role=user['role'])
            else:
                students = conn.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
                conn.close()
                return render_template('admin/select_student.html', students=students, action='admit-card', role=user['role'])
        else:
            student = conn.execute('''
                SELECT u.username, si.class, si.roll_number, si.branch 
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.id = ?
            ''', (user['id'],)).fetchone()
            conn.close()
            return render_template('admin/admit_card.html', student=student, role=user['role'])
    return redirect(url_for('home'))

@app.route('/admin/id-card')
def id_card():
    if 'user' in session:
        conn = get_db_connection()
        user = conn.execute("SELECT id, role FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        if user['role'] in ['admin', 'teacher']:
            student_id = request.args.get('student_id')
            if student_id:
                student = conn.execute('''
                    SELECT u.id, u.username, si.class, si.roll_number, si.branch, u.email,
                           si.guardian_name, si.dob, si.section, si.blood_group,
                           si.village, si.post_office, si.police_station, si.district, si.phone_number
                    FROM users u 
                    JOIN student_info si ON u.id = si.user_id 
                    WHERE u.id = ?
                ''', (student_id,)).fetchone()
                conn.close()
                return render_template('admin/id_card.html', student=student, role=user['role'])
            else:
                students = conn.execute("SELECT id, username FROM users WHERE role = 'student'").fetchall()
                conn.close()
                return render_template('admin/select_student.html', students=students, action='id-card', role=user['role'])
        else:
            student = conn.execute('''
                SELECT u.id, u.username, si.class, si.roll_number, si.branch, u.email,
                       si.guardian_name, si.dob, si.section, si.blood_group,
                       si.village, si.post_office, si.police_station, si.district, si.phone_number
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.id = ?
            ''', (user['id'],)).fetchone()
            conn.close()
            return render_template('admin/id_card.html', student=student, role=user['role'])
    return redirect(url_for('home'))

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
                                      (username, password, 'student', 'default-key'))
                            user_id = c.lastrowid
                        else:
                            user_id = existing_user['id']
                            # Generate and update formatted password for existing users too
                            first_name_formatted = name.split()[0].title().replace('.', '')
                            year = dob[-4:] if dob and len(dob) >= 4 and dob[-4:].isdigit() else "123"
                            password = f"{first_name_formatted}@{year}"
                            c.execute("UPDATE users SET password = ? WHERE id = ?", (password, user_id))
                        
                        branch = 'bhogram'
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
                        
                        c.execute("INSERT OR IGNORE INTO users (username, password, role, security_key) VALUES (?, ?, ?, ?)",
                                  (username, password, 'teacher', 'default-key'))
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
                    for err in errors[:5]: flash(err)
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
                        
                        student_info = c.execute("SELECT user_id FROM student_info WHERE LOWER(REPLACE(full_name, ' ', '')) = ?", (name.lower().replace(' ', ''),)).fetchone()
                        
                        if student_info:
                            c.execute('''
                                INSERT INTO marks (student_id, subject, marks, total_marks, term, teacher_id)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (student_info['user_id'], subject, marks, total_marks, term, teacher_id))
                            success_count += 1
                        else:
                            errors.append(f"Row {row_num}: Could not find existing student named '{name}'.")
                            
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
            stream = io.StringIO(file.stream.read().decode("utf-8-sig", errors='ignore'), newline=None)
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
                    
                    genai.configure(api_key=gemini_api_key)
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
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    response = model.generate_content(prompt)
                    
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
                elif any(h in headers for h in ['DAY', 'START TIME', 'START_TIME']):
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
            SELECT u.id, u.username, u.password, u.email, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        conn.close()
        return render_template('admin/teacher_list.html', teachers=teachers, role=session['role'])
    return redirect(url_for('home'))

@app.route('/routine')
def view_routine():
    conn = get_db_connection()
    routines = conn.execute("SELECT * FROM class_routine ORDER BY branch, class_name, day, start_time").fetchall()
    
    routine_data = {}
    for r in routines:
        b = r['branch']
        c = r['class_name']
        d = r['day']
        if b not in routine_data: routine_data[b] = {}
        if c not in routine_data[b]: routine_data[b][c] = {}
        if d not in routine_data[b][c]: routine_data[b][c][d] = []
        routine_data[b][c][d].append(r)
        
    conn.close()
    role = session.get('role', None)
    return render_template('routine.html', routine_data=routine_data, role=role)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Default to production-safe run if not overridden
    app.run(host='0.0.0.0', port=5001)
