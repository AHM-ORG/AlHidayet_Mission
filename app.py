import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3

app = Flask(__name__)
app.secret_key = 'secret_key_for_mission'

# Database Configuration
DB_NAME = "users.db"

import random
import string

import random
import string
import smtplib
from email.mime.text import MIMEText

# Email Configuration
SENDER_EMAIL = "missionalhidayet@gmail.com" # Placeholder: Please update if different
SENDER_PASSWORD = "kvmwecfrzqbnrbxb"

# Helper: Real Email Sender for OTP
def send_otp_email(to_email, otp):
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

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
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
# Upload Configuration
# Use dynamic path relative to the current file
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
    return dict(logo_url=LOGO_URL, estd_year=ESTD_YEAR)

# Folder Creation Helper
def create_folders():
    for branch in BRANCHES:
        for category in CATEGORIES:
            path = os.path.join(UPLOAD_BASE, branch, category)
            os.makedirs(path, exist_ok=True)

# Create folders on startup
create_folders()

# Routes

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/services')
def services():
    return render_template('services.html')
    
# ... (Previous code)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Access columns by name
    c = conn.cursor()
    # ... (Schema creation - existing is fine)
    
    # ... (Default admin creation)

    conn.commit()
    conn.close()

# ... (Config, folders, branding)

# Routes

@app.route('/login/<user_type>', methods=['GET', 'POST'])
def login(user_type):
    if request.method == 'POST':
        # Step 1: Check Username & Password
        if 'otp_verified' not in session:
            username = request.form['username']
            password = request.form['password']
            
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row # Use Row Factory
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = c.fetchone()
            conn.close()

            if user:
                # User found, Generate OTP
                otp = generate_otp()
                email = user['email'] if user['email'] else "no-email-set" # Access by Name
                session['temp_user'] = {'username': user['username'], 'role': user['role']}
                session['otp'] = otp
                session['otp_email'] = email
                
                send_otp_email(email, otp)
                return render_template('verify_otp.html', email=email, context='login')
            else:
                flash('Invalid Username or Password!')

        # Step 2: Verify OTP (Logic handled in verify_otp route)
            
    return render_template('login.html', user_type=user_type)

@app.route('/verify-otp/<context>', methods=['GET', 'POST'])
def verify_otp(context):
    # ... (Existing OTP verification logic is fine)
    if request.method == 'POST':
        user_otp = request.form['otp']
        generated_otp = session.get('otp')

        if user_otp == generated_otp:
            # Success
            session.pop('otp', None)
            if context == 'login':
                temp_user = session.get('temp_user')
                session['user'] = temp_user['username']
                session['role'] = temp_user['role']
                session.pop('temp_user', None)
                flash('Login Successful!')
                return redirect(url_for('dashboard'))
            elif context == 'forgot_password':
                session['reset_verified'] = True
                return redirect(url_for('reset_new_password'))
        else:
            flash('Invalid OTP! Please try again.')
    
    return render_template('verify_otp.html', email=session.get('otp_email'), context=context)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... (Register logic is fine)
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        security_key = request.form['security_key']

        conn = sqlite3.connect(DB_NAME)
        # No need for row_factory here as we are inserting
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                      (username, email, password, role, security_key))
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login', user_type='student')) # Default redirect
        except sqlite3.IntegrityError:
            flash('Username already exists!')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row # Use Row Factory
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user:
            email = user['email'] # Access by name
            if not email:
                flash('No email found for this user. Cannot send OTP.')
                return render_template('forgot_password.html')

            otp = generate_otp()
            session['otp'] = otp
            session['otp_email'] = email
            session['reset_user_id'] = user['id'] # Access by name
            
            send_otp_email(email, otp)
            return render_template('verify_otp.html', email=email, context='forgot_password')
        else:
            flash('User not found!')

    return render_template('forgot_password.html')

@app.route('/reset-new-password', methods=['GET', 'POST'])
def reset_new_password():
    # ... (Reset logic is fine)
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
        return redirect(url_for('home'))

    return render_template('reset_password.html')

@app.route('/dashboard')
def dashboard():
    if 'user' in session:
        role = session['role']
        
        # সব ফাইল রিড করে ড্যাশবোর্ডে পাঠানো
        content = {}
        for branch in BRANCHES:
            content[branch] = {}
            for category in CATEGORIES:
                path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
                # ফাইল লিস্ট তৈরি করা
                files = os.listdir(path) if os.path.exists(path) else []
                content[branch][category] = files

        return render_template('dashboard.html', role=role, content=content)
    return redirect(url_for('home'))

@app.route('/gallery')
def gallery():
    content = {}
    for branch in BRANCHES:
        content[branch] = {}
        for category in CATEGORIES:
            path = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
            # List files
            files = os.listdir(path) if os.path.exists(path) else []
            content[branch][category] = files
    return render_template('gallery.html', content=content)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'user' in session and session['role'] == 'admin':
        if 'file' not in request.files:
            return 'No file part'
        
        file = request.files['file']
        branch = request.form.get('branch') # ফর্ম থেকে ব্রাঞ্চ নেওয়া
        category = request.form.get('category') # ফর্ম থেকে ক্যাটাগরি নেওয়া (photo/video)

        if file.filename == '':
            return 'No selected file'
        
        if file and branch and category:
            # সঠিক ফোল্ডারে সেভ করা
            target_folder = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
            file.save(os.path.join(target_folder, file.filename))
            flash(f'{branch.title()} শাখায় {category} সফলভাবে আপলোড হয়েছে!')
            return redirect(url_for('dashboard'))
    
    return "অনুমতি নেই বা ভুল তথ্য দেওয়া হয়েছে।"

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)