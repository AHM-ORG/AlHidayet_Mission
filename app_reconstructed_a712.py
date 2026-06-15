import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import json
import random
import string
import smtplib
import hmac
import secrets
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps
from dotenv import load_dotenv
import csv
import io
import google.generativeai as genai
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    import razorpay
except ImportError:
    razorpay = None

# Load environment variables
load_dotenv()

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

# Database Configuration
DB_NAME = "users.db"
VALID_ROLES = {'admin', 'teacher', 'student'}
PRIVATE_PATH_PREFIXES = ('/dashboard', '/admin', '/upload', '/profile')
PASSWORD_HASH_PREFIXES = ('scrypt:', 'pbkdf2:', 'argon2:')
ADMIN_SECURITY_KEY = os.getenv('ADMIN_SECURITY_KEY') or os.getenv('REGISTRATION_SECURITY_KEY')
DEFAULT_ADMIN_PASSWORD = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin123')

# Email Configuration
SENDER_EMAIL = os.getenv('MAIL_USERNAME', "missionalhidayet@gmail.com")
SENDER_PASSWORD = os.getenv('MAIL_PASSWORD', "kvmwecfrzqbnrbxb")
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')

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
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def get_razorpay_client():
    if not razorpay or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return None
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

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
    if request.path.startswith(PRIVATE_PATH_PREFIXES) and not get_session_user():
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
    Auto-populates the subjects table with default subjects for all classes if they do not exist.
    """
    classes = ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
    default_subjects = ["English", "Bengali", "Arabic", "Mathematics", "Science"]
    c = conn.cursor()
    inserted_count = 0
    for class_name in classes:
        for subject_name in default_subjects:
            c.execute("SELECT id FROM subjects WHERE name = ? AND class = ?", (subject_name, class_name))
            if not c.fetchone():
                c.execute("INSERT INTO subjects (name, class) VALUES (?, ?)", (subject_name, class_name))
                inserted_count += 1
    if inserted_count > 0:
        print(f" [SEED] Pre-populated {inserted_count} new subject(s) in subjects table.")

def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    c = conn.cursor()
    
    # Tables creation
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
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (uploaded_by) REFERENCES users (id),
            UNIQUE(student_id, term_name, subject_name)
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
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            branch TEXT
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
    
    # Dynamic Alter Statements for Schema Migrations
    for table in ['users', 'expenses', 'notices', 'applications']:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN branch TEXT")
            print(f" [DB MIGRATE] Added branch column to {table}")
        except sqlite3.OperationalError:
            pass # Column already exists
            
    # Default Admin
    c.execute('SELECT * FROM users WHERE username = ?', ('headmaster',))
    if not c.fetchone():
        c.execute('INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)',
                  ('headmaster', 'rmdaswif@gmail.com', hash_password(DEFAULT_ADMIN_PASSWORD), 'admin', ADMIN_SECURITY_KEY or 'admin-created'))

    migrate_plaintext_passwords(c)
    seed_default_subjects(conn)
    
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
    return dict(
        logo_url=LOGO_URL, 
        estd_year=ESTD_YEAR, 
        role=session.get('role'),
        user_branch=session.get('branch')
    )

# Folder Creation Helper
def create_folders():
    for branch in BRANCHES:
        for category in CATEGORIES:
            path = os.path.join(UPLOAD_BASE, branch, category)
            os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'temp'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_BASE, 'avatars'), exist_ok=True)

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
        SELECT ti.full_name, ti.qualification, u.id 
        FROM users u 
        JOIN teacher_info ti ON u.id = ti.user_id 
        WHERE u.username = ?
    ''', (username,)).fetchone()
    
    if teacher_info:
        teacher_id = teacher_info['id']
        
        # 1. Parse from qualification column
        qual = teacher_info['qualification']
        parsed_quals = parse_teacher_qualifications(qual)
        for assignment in parsed_quals:
            for branch in BRANCHES:
                for sub in assignment['subjects']:
                    allowed_subjects.append({
                        'branch': branch,
                        'class': assignment['class'],
                        'name': sub
                    })
                    
        # 2. Fetch from teacher_subjects table
        ts_rows = conn.execute('''
            SELECT s.name as subject_name, s.class as subject_class
            FROM teacher_subjects ts
            JOIN subjects s ON ts.subject_id = s.id
            WHERE ts.teacher_id = ?
        ''', (teacher_id,)).fetchall()
        for r in ts_rows:
            for branch in BRANCHES:
                exists = any(x['branch'] == branch and x['class'] == r['subject_class'] and x['name'] == r['subject_name'] for x in allowed_subjects)
                if not exists:
                    allowed_subjects.append({
                        'branch': branch,
                        'class': r['subject_class'],
                        'name': r['subject_name']
                    })
                    
        # 3. Fetch from class_routine table (if name exists)
        if teacher_info['full_name']:
            cr_rows = conn.execute('''
                SELECT DISTINCT branch, class_name, subject 
                FROM class_routine 
                WHERE LOWER(teacher_name) = LOWER(?)
            ''', (teacher_info['full_name'],)).fetchall()
            for r in cr_rows:
                exists = any(x['branch'] == r['branch'] and x['class'] == r['class_name'] and x['name'] == r['subject'] for x in allowed_subjects)
                if not exists:
                    allowed_subjects.append({
                        'branch': r['branch'],
                        'class': r['class_name'],
                        'name': r['subject']
                    })
                    
    return allowed_subjects

def get_db_class_names(selected_class):
    mapping = {
        'I': ['I', 'One', 'ONE'],
        'II': ['II', 'Two', 'TWO'],
        'III': ['III', 'Three', 'THREE'],
        'IV': ['IV', 'Four', 'FOUR'],
        'V': ['V', 'Five', 'FIVE'],
        'VI': ['VI', 'Six', 'SIX'],
        'VII': ['VII', 'Seven', 'SEVEN'],
        'VIII': ['VIII', 'Eight', 'EIGHT'],
        'IX': ['IX', 'Nine', 'NINE'],
        'X': ['X', 'Ten', 'TEN'],
        'KG': ['KG', 'U/N', 'UN'],
        'Nursery': ['Nursery', 'NURSERY']
    }
    return mapping.get(selected_class, [selected_class])

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

    return render_template('gallery.html', content=gallery_data)

@app.route('/branches')
def branch_selection():
    return render_template('branch_selection.html')

@app.route('/branch/<branch_name>')
def set_branch(branch_name):
    if branch_name not in BRANCHES:
        flash('Please choose a valid campus.')
        return redirect(url_for('branch_selection'))
    session['selected_branch'] = branch_name
    flash(f'{branch_name.title()} campus selected.')
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
                conn.close()
                
                # =========================================================
                # TEMPORARY 2FA BYPASS: Direct Login Session
                # =========================================================
                session.clear()
                session.permanent = True
                session['user'] = user['username']
                session['role'] = user['role']
                session['branch'] = branch
                flash('Login Successful! (Two-Factor Authentication temporarily disabled)')
                if is_safe_next_url(next_url):
                    return redirect(next_url)
                return redirect(url_for('dashboard'))
                # =========================================================
            else:
                conn.close()
                flash('Invalid Username or Password!')
            
    return render_template('login.html', user_type=user_type)

@app.route('/resend-otp/<context>')
def resend_otp(context):
    email = session.get('otp_email')
    if not email:
        flash('Session expired. Please start over.')
        if context == 'login':
            return redirect(url_for('login', user_type='student'))
        return redirect(url_for('register' if context == 'register' else 'forgot_password'))
        
    otp = generate_otp()
    if send_otp_email(email, otp):
        session['otp'] = otp
        flash('A new code has been sent to your email.')
    else:
        flash('Failed to resend code. Check system logs.')
        
    return redirect(url_for('verify_otp', context=context))

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
    
    return render_template('verify_otp.html', email=session.get('otp_email'), context=context)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        security_key = request.form['security_key']

        if role not in {'student', 'teacher'}:
            flash('Invalid account type.')
            return render_template('register.html')

        if not ADMIN_SECURITY_KEY:
            flash('Public registration is not enabled. Please contact admin.')
            return render_template('register.html')

        if not hmac.compare_digest(security_key, ADMIN_SECURITY_KEY):
            flash('Invalid security key.')
            return render_template('register.html')

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                      (username, email, hash_password(password), role, 'verified'))
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

"@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        mobile = request.form.get('mobile')
        dob = request.form.get('dob')
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if not user:
            conn.close()
            flash('User not found!')
            return render_template('forgot_password.html')
            
        if user['role'] == 'student':
            if mobile and dob:
                # Verify student's phone and DOB
                student = conn.execute('''
                    SELECT * FROM student_info 
                    WHERE user_id = ? AND phone_number = ? AND dob = ?
                ''', (user['id'], mobile.strip(), dob.strip())).fetchone()
                conn.close()
                
                if student:
                    session['reset_verified'] = True
                    session['reset_user_id'] = user['id']
                    return redirect(url_for('reset_new_password'))
                else:
                    flash('Incorrect Mobile Number or Date of Birth!')
                    return render_template('forgot_password.html', is_student=True, username=username)
            else:
                conn.close()
                return render_template('forgot_password.html', is_student=True, username=username)
        else:
            email = user['email']
            if not email:
                conn.close()
                flash('No email found for this user. Cannot send OTP.')
                return render_template('forgot_password.html')

            otp = generate_otp()
            if send_otp_email(email, otp):
                session['otp'] = otp
                session['otp_email'] = email
                session['reset_user_id'] = user['id']
                conn.close()
                return re
<truncated 308 bytes>

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
        user_id = session.get('reset_user_id')
        
        conn = sqlite3.connect(DB_NAME)
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

        if role == 'admin':
            if session.get('branch'):
                # Branch Admin (Manager)
                all_users = c.execute('''
                    SELECT u.id, u.username, u.email, u.role 
                    FROM users u
                    LEFT JOIN student_info si ON u.id = si.user_id
                    WHERE si.branch = ? OR u.role = 'teacher' OR u.username = ?
                ''', (session['branch'], username)).fetchall()
                
                all_notices = c.execute('''
                    SELECT * FROM notices 
                    WHERE branch IS NULL OR branch = ? 
                    ORDER BY created_at DESC
                ''', (session['branch'],)).fetchall()
                
                pending_forms = c.execute('''
                    SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                    FROM applications a 
                    LEFT JOIN users u ON a.user_id = u.id 
                    WHERE a.branch = ?
                    ORDER BY a.submitted_at DESC
                ''', (session['branch'],)).fetchall()
                
                pending_gallery = c.execute('''
                    SELECT pm.*, u.username 
                    FROM pending_media pm 
                    JOIN users u ON pm.user_id = u.id 
                    WHERE pm.status = 'Pending' AND pm.branch = ?
                    ORDER BY pm.submitted_at DESC
                ''', (session['branch'],)).fetchall()
            else:
                # Super Admin
                all_users = c.execute("SELECT id, username, email, role FROM users").fetchall()
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
                JOIN users u ON m.uploaded_by = u.id 
                WHERE m.student_id = (SELECT id FROM users WHERE username = ?)
                ORDER BY m.uploaded_at DESC LIMIT 5
            ''', (username,)).fetchall()
            
            all_notices = c.execute("SELECT * FROM notices ORDER BY created_at DESC LIMIT 3").fetchall()

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
"        return render_template('dashboard.html', 
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

@app.route('/student/edit-info', methods=['GET', 'POST'])
@login_required
def student_edit_info():
    user = get_session_user()
    if user['role'] != 'student':
        flash('Access denied: Only students can edit profile info.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    c = conn.cursor()
    
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
        
        if not full_name or not guardian_name or not mothers_name or not phone_number or not dob:
            flash('Error: Please fill in all required fields.')
            conn.close()
            return redirect(url_for('student_edit_info'))
            
        if
<truncated 3135 bytes>
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
        if len(new_password) < 6:
            conn.close()
            flash('New password must be at least 6 characters.')
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

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    saved_name = f"{user['id']}_{timestamp}_{filename}"
    avatar_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')
    os.makedirs(avatar_folder, exist_ok=True)
    file.save(os.path.join(avatar_folder, saved_name))
    session['avatar_url'] = url_for('static', filename=f'uploads/avatars/{saved_name}')
    flash('Profile photo uploaded successfully.')
    return redirect(url_for('profile'))

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

    # Extract and normalize branch from form data
    raw_branch = form_data.get('branch', '').lower()
    branch = 'surangapur' if 'surangapur' in raw_branch else 'bhogram' if 'bhogram' in raw_branch else None

    conn = sqlite3.connect(DB_NAME)
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
                WHERE a.branch = ?
                ORDER BY a.submitted_at DESC
            ''', (session['branch'],)).fetchall()
        else:
            applications = conn.execute('''
                SELECT a.id, a.type, a.status, a.submitted_at, u.username 
                FROM applications a 
                LEFT JOIN users u ON a.user_id = u.id 
                ORDER BY a.submitted_at DESC
            ''').fetchall()
        conn.close()
        return render_template('admin/application_list.html', applications=applications)
    return redirect(url_for('home'))

"@app.route('/admin/view-form/<int:form_id>')
def view_form(form_id):
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        form = conn.execute("SELECT * FROM applications WHERE id = ?", (form_id,)).fetchone()
        
        if form:
            if session.get('branch') and form['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: This application belongs to another campus.')
                return redirect(url_for('dashboard'))
            
            data = json.loads(form['data'])
            current_info = None
            if form['type'] == 'student_info_edit':
                current_info = conn.execute("SELECT * FROM student_info WHERE user_id = ?", (form['user_id'],)).fetchone()
            
            conn.close()
            return render_template('admin_form_view.html', form=form, data=data, current_info=current_info)
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/admin/form-action/<int:form_id>/<action>', methods=['POST'])
def form_action(form_id, action):
    if 'user' in session and session['role'] == 'admin':
        status = 'Accepted' if action == 'approve' else 'Rejected'
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        
        form = conn.execute("SELECT * FROM applications WHERE id = ?", (form_id,)).fetchone()
        if not form:
            conn.close()
            flash('Error: Application request not found.')
            return redirect(url_for('admin_applications'))
            
        # Check permissions for Branch Admin
        if session.get('branch') and form['branch'] != session['branch']:
            conn.close()
            flash('Permission denied: This application belongs to another campus.')
            return redirect(url_for('dashboard'))

        if action == 'approve' and form['type'] == 'student_info_edit':
            # Write student profile upda
<truncated 1483 bytes>

@app.route('/admin/delete-application/<int:form_id>', methods=['POST'])
def delete_application(form_id):
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        
        # Check permissions for Branch Admin
        if session.get('branch'):
            form = conn.execute("SELECT branch FROM applications WHERE id = ?", (form_id,)).fetchone()
            if not form or form['branch'] != session['branch']:
                conn.close()
                flash('Permission denied: This application belongs to another campus.')
                return redirect(url_for('admin_applications'))

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
        new_password = 'mission' + ''.join(random.choices(string.digits, k=6))
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE users SET password = ?, temp_password = ? WHERE id = ?", (hash_password(new_password), new_password, user_id))
        conn.commit()
        conn.close()
        flash(f'Password reset successfully. Temporary password: {new_password}')
    next_endpoint = request.form.get('next')
    if next_endpoint == 'teacher_list':
        return redirect(url_for('teacher_list'))
    if next_endpoint == 'student_list':
        return redirect(url_for('student_list'))
    return redirect(url_for('dashboard'))

@app.route('/admin/media-action/<int:media_id>/<action>', methods=['POST'])
@app.route('/admin/gallery-action/<int:media_id>/<action>', methods=['POST'])
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
        if session.get('branch'):
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.full_name, si.branch, si.class, si.roll_number, si.unique_code,
                       si.guardian_name, si.dob, si.section, si.blood_group, si.village, si.post_office, si.police_station, 
                       si.district, si.phone_number, si.aadhaar_number, si.mothers_name, si.date_of_admission, si.monthly_fee,
                       si.allow_marksheet, si.allow_admit
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student' AND si.branch = ?
                ORDER BY si.class, si.roll_number
            ''', (session['branch'],)).fetchall()
        else:
            students = conn.execute('''
                SELECT u.id, u.username, u.email, si.full_name, si.branch, si.class, si.roll_number, si.unique_code,
                       si.guardian_name, si.dob, si.section, si.blood_group, si.village, si.post_office, si.police_station, 
                       si.district, si.phone_number, si.aadhaar_number, si.mothers_name, si.date_of_admission, si.monthly_fee,
                       si.allow_marksheet, si.allow_admit
                FROM users u 
                LEFT JOIN student_info si ON u.id = si.user_id 
                WHERE u.role = 'student'
                ORDER BY si.class, si.roll_number
            ''').fetchall()
        teachers = conn.execute('''
            SELECT u.id, u.username, u.email, u.temp_password, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date, ti.address
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
        ''').fetchall()
        
        conn.close()
        
        class_order = [
            'Nursery', 'L/N', 'U/N', 'UN', 'KG',
            'One', 'I', 'Two', 'II', 'Three', 'III',
            'Four', 'IV', 'Five', 'V', 'Six', 'VI',
            'Seven', 'VII', 'Eight', 'VIII', 'Nine', 'IX',
            'Ten', 'X'
        ]
        
        def get_class_sort_index(cls_name):
            if not cls_name:
                return len(class_order) + 2
            cls_upper = cls_name.strip().upper()
            for idx, c in enumerate(class_order):
                if c.upper() == cls_upper:
                    return idx
            return len(class_order) + 1

        # Convert sqlite3.Row to dict to make it mutable/sortable
        students_list = [dict(s) for s in students]
        
        def get_student_sort_key(student):
            cls_idx = get_class_sort_index(student['class'])
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
        for student in students:
            cls = student['class'] or 'Unassigned'
            if cls not in students_by_class:
                students_by_class[cls] = []
            students_by_class[cls].append(student)
            
        return render_template('admin/student_list.html', students=students, students_by_class=students_by_class, teachers=teachers, role=session['role'])
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
            role = 'student'
            security_key = 'admin-created'

            conn = get_db_connection()
            try:
                # Insert into users
                conn.execute("INSERT INTO users (username, email, password, role, security_key) VALUES (?, ?, ?, ?, ?)",
                          (username, email, hash_password(password), role, security_key))
                user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

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
                    'phone_number': request.form.get('phone_number'),
                    'aadhaar_number': request.form.get('aadhaar_number'),
                    'mothers_name': request.form.get('mothers_name'),
                    'date_of_admission': request.form.get('date_of_admission'),
                    'monthly_fee': float(request.form.get('monthly_fee') or 0)
                }

                unique_code = generate_unique_student_code(conn)
                
                conn.execute('''
                    INSERT INTO student_info (user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number, unique_code, aadhaar_number, mothers_name, date_of_admission, monthly_fee)
                    VALUES (:user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number, :unique_code, :aadhaar_number, :mothers_name, :date_of_admission, :monthly_fee)
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
            password = request.form.get('password', '').strip()
            
            try:
                if password:
                    conn.execute("UPDATE users SET username = ?, email = ?, password = ? WHERE id = ?", 
                                 (username, email, hash_password(password), user_id))
                else:
                    conn.execute("UPDATE users SET username = ?, email = ? WHERE id = ?", 
                                 (username, email, user_id))
                
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
                    'phone_number': request.form.get('phone_number'),
                    'aadhaar_number': request.form.get('aadhaar_number'),
                    'mothers_name': request.form.get('mothers_name'),
                    'date_of_admission': request.form.get('date_of_admission'),
                    'monthly_fee': float(request.form.get('monthly_fee') or 0)
                }
                
                conn.execute('''
                    UPDATE student_info SET
                        branch = :branch, class = :class, roll_number = :roll_number, full_name = :full_name,
                        guardian_name = :guardian_name, dob = :dob, section = :section, blood_group = :blood_group,
                        village = :village, post_office = :post_office, police_station = :police_station,
                        district = :district, phone_number = :phone_number, aadhaar_number = :aadhaar_number,
                        mothers_name = :mothers_name, date_of_admission = :date_of_admission, monthly_fee = :monthly_fee
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
            SELECT u.username, u.email, si.* 
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
                INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name      = excluded.full_name,
                    phone_number   = excluded.phone_number,
                    qualification  = excluded.qualification,
                    joining_date   = excluded.joining_date,
                    address        = excluded.address
            ''', (user_id, full_name or None, phone or None, qual or None, joining or None, address or None))

            conn.commit()
            flash(f'Teacher "{full_name or username}" updated successfully!')
            return redirect(url_for('teacher_list'))
        except sqlite3.IntegrityError:
            flash('Username already exists or database error!')
        finally:
            conn.close()
        return redirect(url_for('edit_teacher', user_id=user_id))

    teacher = conn.execute('''
        SELECT u.id, u.username, u.email, ti.full_name, ti.phone_number,
               ti.qualification, ti.joining_date, ti.address
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.id = ? AND u.role = 'teacher'
    ''', (user_id,)).fetchone()
    conn.close()

    if not teacher:
        flash('Teacher not found!')
        return redirect(url_for('teacher_list'))

    logo_url = url_for('static', filename='images/logo.png')
    return render_template('admin/edit_teacher.html', teacher=teacher, role=session['role'], logo_url=logo_url)

@app.route('/admin/add-user', methods=['GET', 'POST'])
def add_user():
    if 'user' in session and session['role'] == 'admin':
        if request.method == 'POST':
            username = request.form['username']
            email = request.form.get('email', '')
            password = request.form['password']
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
                    conn.execute('''
                        INSERT INTO teacher_info (user_id, full_name, phone_number, qualification, joining_date, address)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, full_name, phone_number, qualification, joining_date, address))
                elif role == 'student':
                    unique_code = generate_unique_student_code(conn)
                    info = {
                        'branch': branch,
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
                        'phone_number': request.form.get('student_phone'),
                        'aadhaar_number': request.form.get('aadhaar_number'),
                        'mothers_name': request.form.get('mothers_name'),
                        'date_of_admission': request.form.get('date_of_admission'),
                        'monthly_fee': float(request.form.get('monthly_fee') or 0),
                        'unique_code': unique_code
                    }
                    conn.execute('''
                        INSERT INTO student_info (user_id, branch, class, roll_number, full_name, guardian_name, dob, section, blood_group, village, post_office, police_station, district, phone_number, unique_code, aadhaar_number, mothers_name, date_of_admission, monthly_fee)
                        VALUES (:user_id, :branch, :class, :roll_number, :full_name, :guardian_name, :dob, :section, :blood_group, :village, :post_office, :police_station, :district, :phone_number, :unique_code, :aadhaar_number, :mothers_name, :date_of_admission, :monthly_fee)
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
    return redirect(url_for('bulk_marks'))

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

            marks_rows = conn.execute('''
                SELECT m.obtained_marks AS marks,
                       m.full_marks AS total_marks,
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
            
            # Query class tests to separate
            class_tests_rows = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
            class_test_names = [r['test_name'] for r in class_tests_rows]
            
            term_marks = []
            class_test_marks = []
            for m in marks_rows:
                if m['term'] in class_test_names:
                    class_test_marks.append(m)
                else:
                    term_marks.append(m)
            
            # Calculate scaled class tests (out of 100) per subject
            ct_by_sub = {}
            for m in class_test_marks:
                sub = m['subject'].strip().title()
                if sub not in ct_by_sub:
                    ct_by_sub[sub] = {'obt': 0.0, 'full': 0.0}
                ct_by_sub[sub]['obt'] += float(m['marks'] or 0)
                ct_by_sub[sub]['full'] += float(m['total_marks'] or 0)
                
            has_annual = any(m['term'] == 'Annual' for m in term_marks)
            
            if has_annual:
                term_marks_dicts = [dict(m) for m in term_marks]
                for sub, data in ct_by_sub.items():
                    if data['full'] > 0:
                        scaled_obt = round((data['obt'] / data['full']) * 100.0, 2)
                        
                        meta = dict(term_marks[0]) if term_marks else (dict(class_test_marks[0]) if class_test_marks else {})
                        
                        virtual_row = {
                            'marks': scaled_obt,
                            'total_marks': 100.0,
                            'subject': sub,
                            'term': 'Class Test (Scaled)',
                            'submitted_at': meta.get('submitted_at', ''),
                            'student_id': meta.get('student_id', student_id),
                            'class_name': meta.get('class_name', ''),
                            'uploaded_by': meta.get('uploaded_by', None),
                            'student_name': meta.get('student_name', ''),
                            'class': meta.get('class', ''),
                            'roll_number': meta.get('roll_number', ''),
                            'branch': meta.get('branch', ''),
                            'guardian_name': meta.get('guardian_name', ''),
                            'dob': meta.get('dob', ''),
                            'section': meta.get('section', '')
                        }
                        term_marks_dicts.append(virtual_row)
                term_marks = term_marks_dicts
                
            conn.close()
            return render_template('admin/marksheet.html', marks=term_marks, class_test_marks=class_test_marks, role=role)
        
        if session.get('branch'):
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
        else:
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
        conn.close()
        return render_template('admin/marksheet.html', marks=None, students=students, role=role)
    return redirect(url_for('home'))

@app.route('/admin/bulk-marks', methods=['GET', 'POST'])
def bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        
        # Query class tests
        class_tests_rows = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
        class_test_names = [r['test_name'] for r in class_tests_rows]
        
        # Determine the user's role and fetch allowed subjects if teacher
        role = session['role']
        username = session['user']
        allowed_subjects = []
        
        if role == 'teacher':
             allowed_subjects = get_teacher_allowed_subjects(conn, username)

        students = []
        if session.get('branch'):
            selected_branch = session['branch']
        else:
            selected_branch = request.args.get('branch')
        selected_class = request.args.get('class')
        selected_subject = request.args.get('subject') # Optional pre-fill for admin or selected subject
        selected_term = request.args.get('term', '1st Term')
        
        is_class_test = selected_term in class_test_names
        subject_full_marks = {}
        configured_class_test_subjects = []
        class_test_default_fm = 20.0
        if is_class_test and selected_class:
            configs = conn.execute("SELECT subject_name, full_marks FROM class_test_configs WHERE test_name = ? AND class_name = ?", (selected_term, selected_class)).fetchall()
            if configs:
                class_test_default_fm = max(c['full_marks'] for c in configs)
            for c in configs:
                name_norm = c['subject_name'].strip().title()
                subject_full_marks[name_norm] = c['full_marks']
                configured_class_test_subjects.append(name_norm)
                
        if is_class_test:
            if class_test_default_fm == int(class_test_default_fm):
                full_marks_val = str(int(class_test_default_fm))
            else:
                full_marks_val = str(class_test_default_fm)
        else:
            full_marks_val = request.args.get('full_marks', '100')

        assigned_class = request.args.get('assigned_class')
        if role == 'teacher' and assigned_class:
            parts = assigned_class.split('|')
            if len(parts) == 3:
                selected_branch, selected_class, selected_subject = parts
                
        subject_names = []
        marks_dict = {}
        
        if selected_branch and selected_class:
            # 2. Fetch students using normalized class names (e.g. 'I' matches 'One' or 'I')
            db_classes = get_db_class_names(selected_class)
            placeholders = ', '.join('?' for _ in db_classes)

            # 1. Fetch all subjects listed in the database subjects table for this class
            subjects_rows = conn.execute(f"SELECT DISTINCT name FROM subjects WHERE class IN ({placeholders}) ORDER BY name", db_classes).fetchall()
            subject_names = [r['name'].strip().title() for r in subjects_rows if r['name']]
            
            # Combine with the standard default subjects to ensure they are always present
            default_subs = ["English", "Bengali", "Arabic", "Mathematics", "Science"]
            for s in default_subs:
                s_norm = s.strip().title()
                if s_norm not in subject_names:
                    subject_names.append(s_norm)
                    
            # Add any subjects assigned to this specific teacher for this class
            if role == 'teacher':
                for x in allowed_subjects:
                    if x['class'].lower() in [c.lower() for c in db_classes]:
                        name_norm = x['name'].strip().title()
                        if name_norm not in subject_names:
                            subject_names.append(name_norm)
            else:
                # For admin, also add subjects assigned to any teacher for this class
                teachers_list = conn.execute("SELECT username FROM users WHERE role = 'teacher'").fetchall()
                for t in teachers_list:
                    t_allowed = get_teacher_allowed_subjects(conn, t['username'])
                    for x in t_allowed:
                        if x['class'].lower() in [c.lower() for c in db_classes]:
                            name_norm = x['name'].strip().title()
                            if name_norm not in subject_names:
                                subject_names.append(name_norm)
                                
            # Add any subjects that already have marks recorded in this class
            existing_marks_subs = conn.execute(f"SELECT DISTINCT subject_name FROM marks WHERE class_name IN ({placeholders})", db_classes).fetchall()
            for r in existing_marks_subs:
                if r['subject_name']:
                    name_norm = r['subject_name'].strip().title()
                    if name_norm not in subject_names:
                        subject_names.append(name_norm)
                    
            # Sort subject names alphabetically
            subject_names = sorted(list(set(subject_names)))
            
            students = conn.execute(f'''
                SELECT u.id, u.username, si.full_name, si.roll_number 
                FROM users u 
                JOIN student_info si ON u.id = si.user_id 
                WHERE si.branch = ? AND si.class IN ({placeholders})
                ORDER BY CAST(si.roll_number AS INTEGER)
            ''', [selected_branch] + db_classes).fetchall()
            
            # 3. Fetch existing marks for these students and term matching any class representation
            marks_rows = conn.execute(f'''
                SELECT student_id, subject_name, obtained_marks, full_marks 
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
                    'full': row['full_marks']
                }
                if sub_norm and row['full_marks'] is not None:
                    if sub_norm not in subject_full_marks:
                        subject_full_marks[sub_norm] = row['full_marks']
            
        conn.close()
        
        return render_template('admin/bulk_marks.html', 
                               students=students, 
                               branches=BRANCHES, 
                               classes=['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'],
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
                               subject_full_marks=subject_full_marks,
                               configured_class_test_subjects=configured_class_test_subjects)
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

    conn = get_db_connection()
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

            # Insert or update
            conn.execute('''
                INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                    obtained_marks = excluded.obtained_marks,
                    full_marks = excluded.full_marks,
                    uploaded_by = excluded.uploaded_by,
                    uploaded_at = CURRENT_TIMESTAMP
            ''', (student_id, class_name, term_name, subject_name, obt, full, user['id']))

        conn.commit()
        return jsonify({'status': 'success', 'message': 'Marks saved successfully.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/admin/save-bulk-marks', methods=['POST'])
def save_bulk_marks():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        selected_class = request.form.get('class')
        selected_branch = session['branch'] if session.get('branch') else request.form.get('branch')
        selected_term = request.form.get('term', '1st Term')
        full_marks_val = request.form.get('full_marks') or request.form.get('total_marks') or '100'
        
        if not selected_class or not selected_branch:
            flash('Invalid class or branch selection.', 'error')
            return redirect(url_for('bulk_marks'))
            
        try:
            full_marks = float(full_marks_val)
        except ValueError:
            flash('Invalid full marks value.', 'error')
            return redirect(url_for('bulk_marks'))

        conn = get_db_connection()
        user = conn.execute("SELECT id FROM users WHERE username = ?", (session['user'],)).fetchone()
        
        # Query configured class tests to see if this term is a custom test
        class_tests_rows = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
        class_test_names = [r['test_name'] for r in class_tests_rows]
        is_class_test = selected_term in class_test_names
        
        subject_full_marks = {}
        configured_class_test_subjects = []
        if is_class_test:
            class_test_default_fm = 20.0
            configs = conn.execute("SELECT subject_name, full_marks FROM class_test_configs WHERE test_name = ? AND class_name = ?", (selected_term, selected_class)).fetchall()
            if configs:
                class_test_default_fm = max(c['full_marks'] for c in configs)
            for c in configs:
                name_norm = c['subject_name'].strip().title()
                subject_full_marks[name_norm] = c['full_marks']
                configured_class_test_subjects.append(name_norm)
                
            # Override full_marks and full_marks_val for class tests
            full_marks = class_test_default_fm
            if class_test_default_fm == int(class_test_default_fm):
                full_marks_val = str(int(class_test_default_fm))
            else:
                full_marks_val = str(class_test_default_fm)
        
        # Security check for teacher using parsed qualifications and assigned subjects
        allowed_subjects_list = []
        if session['role'] == 'teacher':
            allowed = get_teacher_allowed_subjects(conn, session['user'])
            allowed_subjects_list = [
                x['name'].strip().title() for x in allowed
                if x['branch'].lower() == selected_branch.lower() and x['class'].lower() == selected_class.lower()
            ]

        saved_count = 0
        try:
            for key, value in request.form.items():
                if key.startswith('marks_') and value != '':
                    parts = key.split('_')
                    if len(parts) >= 3:
                        student_id = parts[1]
                        subject_name = '_'.join(parts[2:]).strip().title() # handle subjects with underscores or spaces
                        
                        # If teacher, only let them save their assigned subjects
                        if session['role'] == 'teacher' and subject_name not in allowed_subjects_list:
                            continue
                            
                        # If class test, block saving marks for unconfigured subjects
                        if is_class_test and subject_name not in configured_class_test_subjects:
                            continue
                            
                        # Security check: verify that the student actually belongs to this branch
                        student_chk = conn.execute("SELECT user_id FROM student_info WHERE user_id = ? AND branch = ?", (student_id, selected_branch)).fetchone()
                        if not student_chk:
                            continue

                        try:
                            obtained_marks = float(value)
                        except ValueError:
                            continue
                            
                        # Get subject-specific full marks from the form, fallback to configured or global
                        form_fm = request.form.get(f'fm_{subject_name}')
                        if form_fm:
                            try:
                                subject_fm = float(form_fm)
                            except ValueError:
                                subject_fm = subject_full_marks.get(subject_name, full_marks)
                        else:
                            subject_fm = subject_full_marks.get(subject_name, full_marks)
                            
                        # Logical validation: obtained_marks cannot be greater than subject_fm
                        if obtained_marks > subject_fm:
                            std_row = conn.execute("SELECT full_name, username FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                            std_name = std_row['full_name'] or std_row['username'] if std_row else f"ID {student_id}"
                            flash(f"Logical Error: Obtained marks ({obtained_marks}) cannot exceed Full Marks ({subject_fm}) for student '{std_name}' in subject '{subject_name}'.", "error")
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
                            
                        conn.execute('''
                            INSERT INTO marks (student_id, class_name, term_name, subject_name, obtained_marks, full_marks, uploaded_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(student_id, term_name, subject_name) DO UPDATE SET
                                obtained_marks = excluded.obtained_marks,
                                full_marks = excluded.full_marks,
                                uploaded_by = excluded.uploaded_by,
                                uploaded_at = CURRENT_TIMESTAMP
                        ''', (student_id, selected_class, selected_term, subject_name, obtained_marks, subject_fm, user['id']))
                        saved_count += 1
                        
            conn.commit()
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

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    saved_name = f"{timestamp}_{filename}"

    if user['role'] == 'admin':
        target_folder = os.path.join(app.config['UPLOAD_FOLDER'], branch, category)
        os.makedirs(target_folder, exist_ok=True)
        file.save(os.path.join(target_folder, saved_name))
        flash(f'{branch.title()} {category} uploaded successfully.')
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

    return redirect(url_for('dashboard'))

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

                conn.execute('''
                    INSERT INTO fees (student_id, amount, month, year, status, paid_at)
                    VALUES (?, ?, ?, ?, 'Paid', CURRENT_TIMESTAMP)
                ''', (student_id, amount, month, year))
                conn.commit()
                flash('Fee collected successfully!')
                conn.close()
                return redirect(url_for('get_fees'))

            if session.get('branch'):
                students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
                recent_fees = conn.execute('''
                    SELECT f.*, u.username as student_name 
                    FROM fees f 
                    JOIN users u ON f.student_id = u.id 
                    JOIN student_info si ON u.id = si.user_id
                    WHERE si.branch = ?
                    ORDER BY f.paid_at DESC
                ''', (session['branch'],)).fetchall()
            else:
                students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
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
            
            student_info = conn.execute('''
                SELECT monthly_fee FROM student_info si
                JOIN users u ON si.user_id = u.id
                WHERE u.username = ?
            ''', (username,)).fetchone()
            
            conn.close()
            return render_template(
                'admin/get_fees.html',
                recent_fees=my_fees,
                role=role,
                student_info=student_info,
                razorpay_key_id=RAZORPAY_KEY_ID,
                username=username,
                email=''
            )
            
    return redirect(url_for('home'))

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
    receipt = f"fee_{user['id']}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

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
    conn.execute('''
        INSERT INTO fees (student_id, amount, month, year, status, paid_at)
        VALUES (?, ?, ?, ?, 'Paid', CURRENT_TIMESTAMP)
    ''', (student_id, amount, month, year))
    conn.commit()
    conn.close()
    session.pop('pending_fee_payment', None)

    return {'status': 'success'}

@app.route('/admin/set-fees', methods=['GET', 'POST'])
def set_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        if request.method == 'POST':
            update_type = request.form.get('update_type', 'class')
            amount = request.form.get('amount')
            
            if update_type == 'class':
                branch = session['branch'] if session.get('branch') else request.form.get('branch')
                class_name = request.form.get('class')
                conn.execute('''
                    UPDATE student_info 
                    SET monthly_fee = ? 
                    WHERE branch = ? AND class = ?
                ''', (amount, branch, class_name))
                flash(f'Successfully updated monthly fee for {branch.title()} - Class {class_name} to ₹{amount}')
            elif update_type == 'student':
                student_id = request.form.get('student_id')
                
                # Check permissions for Branch Admin
                if session.get('branch'):
                    student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                    if not student or student['branch'] != session['branch']:
                        conn.close()
                        flash('Permission denied: Student does not belong to your campus.')
                        return redirect(url_for('set_fees'))

                conn.execute('''
                    UPDATE student_info 
                    SET monthly_fee = ? 
                    WHERE user_id = ?
                ''', (amount, student_id))
                flash(f'Successfully updated monthly fee for student ID {student_id} to ₹{amount}')
                
            conn.commit()
            conn.close()
            return redirect(url_for('set_fees'))
            
        if session.get('branch'):
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
        else:
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
        conn.close()
        return render_template('admin/set_fees.html', branches=BRANCHES, classes=['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'], students=students, role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/set-salary', methods=['GET', 'POST'])
def set_salary():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        if request.method == 'POST':
            teacher_id = request.form['teacher_id']
            amount = request.form['amount']
            
            conn.execute('''
                UPDATE teacher_info 
                SET salary = ? 
                WHERE user_id = ?
            ''', (amount, teacher_id))
            conn.commit()
            conn.close()
            flash(f'Successfully updated salary to ₹{amount}')
            return redirect(url_for('set_salary'))
            
        teachers = conn.execute('''
            SELECT u.id, u.username, ti.full_name, ti.salary 
            FROM users u 
            JOIN teacher_info ti ON u.id = ti.user_id 
            WHERE u.role = 'teacher'
        ''').fetchall()
        conn.close()
        return render_template('admin/set_salary.html', teachers=teachers, role=session['role'])
    return redirect(url_for('home'))

@app.route('/admin/reminder-fees')
def reminder_fees():
    if 'user' in session and session['role'] == 'admin':
        conn = get_db_connection()
        from datetime import datetime
        month = datetime.now().strftime('%B')
        year = datetime.now().strftime('%Y')
        
        pending_students = conn.execute('''
            SELECT u.id, u.username, si.full_name, si.phone_number, si.class, si.guardian_name 
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
            
            conn.execute('''
                INSERT INTO expenses (amount, category, description, branch)
                VALUES (?, ?, ?, ?)
            ''', (amount, category, description, branch))
            conn.commit()
            flash('Expense recorded!')
            conn.close()
            return redirect(url_for('spend'))

        if session.get('branch'):
            expenses = conn.execute("SELECT * FROM expenses WHERE branch = ? ORDER BY date DESC", (session['branch'],)).fetchall()
        else:
            expenses = conn.execute("SELECT * FROM expenses ORDER BY date DESC").fetchall()
        conn.close()
        return render_template('admin/spend.html', expenses=expenses, role=role)
    return redirect(url_for('home'))

@app.route('/admin/audit-report')
def audit_report():
    if 'user' in session and session['role'] == 'admin':
        role = session['role']
        conn = get_db_connection()
        
        if session.get('branch'):
            total_fees = conn.execute('''
                SELECT SUM(f.amount) as total 
                FROM fees f 
                JOIN student_info si ON f.student_id = si.user_id
                WHERE si.branch = ?
            ''', (session['branch'],)).fetchone()['total'] or 0
            
            total_expenses = conn.execute('''
                SELECT SUM(amount) as total 
                FROM expenses 
                WHERE branch = ?
            ''', (session['branch'],)).fetchone()['total'] or 0
        else:
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
        
        if request.method == 'POST' and 'create_subject' in request.form:
            name_input = request.form['name']
            classes = request.form.getlist('classes')
            if not classes:
                flash('Please select at least one class.')
            else:
                # Support comma-separated input for manual bulk entry of class subjects
                subject_names = [s.strip() for s in name_input.split(',') if s.strip()]
                if not subject_names:
                    flash('Please enter a valid subject name.')
                else:
                    added_count = 0
                    for subject_name in subject_names:
                        for class_name in classes:
                            existing = conn.execute("SELECT id FROM subjects WHERE name = ? AND class = ?", (subject_name, class_name)).fetchone()
                            if not existing:
                                conn.execute("INSERT INTO subjects (name, class) VALUES (?, ?)", (subject_name, class_name))
                                added_count += 1
                    conn.commit()
                    flash(f'Successfully added {added_count} subject-class record(s) manually!')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        if request.method == 'POST' and 'assign_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            subject_name = request.form['subject_name']
            classes = request.form.getlist('classes')
            if not classes:
                flash('Please select at least one class.')
            else:
                assigned_count = 0
                for class_name in classes:
                    subject = conn.execute("SELECT id FROM subjects WHERE name = ? AND class = ?", (subject_name, class_name)).fetchone()
                    if subject:
                        try:
                            conn.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (teacher_id, subject['id']))
                            assigned_count += 1
                        except sqlite3.IntegrityError:
                            pass
                conn.commit()
                if assigned_count > 0:
                    flash(f'Teacher assigned to {assigned_count} class(es) for {subject_name}!')
                else:
                    flash('No new assignments made. Make sure the subject exists for the selected classes.')
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'delete_subject' in request.form:
            subject_id = request.form['subject_id']
            conn.execute("DELETE FROM teacher_subjects WHERE subject_id = ?", (subject_id,))
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            conn.commit()
            flash('Subject deleted successfully.')
            conn.close()
            return redirect(url_for('academics_setting'))
            
        if request.method == 'POST' and 'delete_assignment' in request.form:
            assignment_id = request.form['assignment_id']
            conn.execute("DELETE FROM teacher_subjects WHERE id = ?", (assignment_id,))
            conn.commit()
            flash('Teacher assignment deleted successfully.')
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'create_class_test_config' in request.form:
            test_name = request.form['test_name'].strip()
            class_name = request.form['class_name']
            subject_name = request.form['subject_name']
            try:
                full_marks = float(request.form['full_marks'])
            except ValueError:
                full_marks = 20.0
                
            if not test_name:
                flash('Please enter a valid class test name.')
            else:
                existing = conn.execute("SELECT id FROM class_test_configs WHERE test_name = ? AND class_name = ? AND subject_name = ?", (test_name, class_name, subject_name)).fetchone()
                if existing:
                    conn.execute("UPDATE class_test_configs SET full_marks = ? WHERE id = ?", (full_marks, existing['id']))
                    flash(f'Updated configuration for {test_name} - Class {class_name} - {subject_name} to F.M. {full_marks}!')
                else:
                    conn.execute("INSERT INTO class_test_configs (test_name, class_name, subject_name, full_marks) VALUES (?, ?, ?, ?)", (test_name, class_name, subject_name, full_marks))
                    flash(f'Configured {test_name} for Class {class_name} - {subject_name} with F.M. {full_marks}!')
                conn.commit()
            conn.close()
            return redirect(url_for('academics_setting'))

        if request.method == 'POST' and 'delete_class_test_config' in request.form:
            config_id = request.form['config_id']
            conn.execute("DELETE FROM class_test_configs WHERE id = ?", (config_id,))
            conn.commit()
            flash('Class test configuration deleted.')
            conn.close()
            return redirect(url_for('academics_setting'))

        subjects = conn.execute("SELECT * FROM subjects ORDER BY class, name").fetchall()
        distinct_subjects = conn.execute("SELECT DISTINCT name FROM subjects ORDER BY name").fetchall()
        teachers = conn.execute("SELECT id, username FROM users WHERE role = 'teacher'").fetchall()
        assignments = conn.execute('''
            SELECT ts.id, u.username as teacher_name, s.name as subject_name, s.class 
            FROM teacher_subjects ts
            JOIN users u ON ts.teacher_id = u.id
            JOIN subjects s ON ts.subject_id = s.id
        ''').fetchall()
        class_test_configs = conn.execute("SELECT * FROM class_test_configs ORDER BY class_name, test_name, subject_name").fetchall()
        
        conn.close()
        return render_template('admin/academics_setting.html', subjects=subjects, distinct_subjects=distinct_subjects, teachers=teachers, assignments=assignments, class_test_configs=class_test_configs, role=session['role'])
    elif 'user' in session and session['role'] == 'teacher': # Teachers just view
         conn = get_db_connection()
         class_test_configs = conn.execute("SELECT * FROM class_test_configs ORDER BY class_name, test_name, subject_name").fetchall()
         conn.close()
         return render_template('admin/academics_setting.html', class_test_configs=class_test_configs, role=session['role']) # Needs simplified view
    return redirect(url_for('home'))

"@app.route('/admin/student-promotion', methods=['GET', 'POST'])
def student_promotion():
    if 'user' in session and session['role'] in ['admin', 'teacher']:
        conn = get_db_connection()
        
        CLASSES = ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
        
        # Determine branch filter
        if session.get('branch'):
            branch_filter = session['branch']
        else:
            branch_filter = request.args.get('branch', 'surangapur').strip().lower()
            if branch_filter not in ['surangapur', 'bhogram']:
                branch_filter = 'surangapur'
                
        class_filter = request.args.get('class_filter', '').strip()
        
        if request.method == 'POST':
            student_ids = request.form.getlist('student_ids') or request.form.getlist('student_ids[]')
            new_class = request.form.get('new_class', '').strip()
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
                # Security check for Branch Admin
                if session.get('branch'):
                    student = conn.execute("SELECT branch FROM student_info WHERE user_id = ?", (student_id,)).fetchone()
                    if not student or student['branch'] != session['branch']:
                        continue
                
                # Execute promotion
        
<truncated 1785 bytes>

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
                
                # Check permissions for Branch Admin
                if session.get('branch') and student and student['branch'] != session['branch']:
                    conn.close()
                    flash('Permission denied: Student does not belong to your campus.')
                    return redirect(url_for('dashboard'))

                conn.close()
                return render_template('admin/admit_card.html', student=student, role=user['role'])
            else:
                if session.get('branch'):
                    students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
                else:
                    students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
                conn.close()
                return render_template('admin/select_student.html', students=students, action='admit-card', role=user['role'])
        else:
            # Check student permission
            student_perm = conn.execute("SELECT allow_admit FROM student_info WHERE user_id = ?", (user['id'],)).fetchone()
            if not student_perm or not student_perm['allow_admit']:
                conn.close()
                return render_template('admin/admit_locked.html', role=user['role'])
                
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
                        branch = form_branch.strip().lower() if form_branch else (raw_branch.strip().lower() if raw_branch else (session.get('branch') or 'surangapur'))
                        if branch not in ['surangapur', 'bhogram']:
                            branch = session.get('branch') or 'surangapur'
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
            SELECT u.id, u.username, u.email, u.temp_password, ti.full_name, ti.phone_number, ti.qualification, ti.joining_date
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE u.role = 'teacher'
            ORDER BY COALESCE(ti.full_name, u.username)
        ''').fetchall()
        conn.close()
        logo_url = url_for('static', filename='images/logo.png')
        return render_template('admin/teacher_list.html', teachers=teachers, role=session['role'], logo_url=logo_url)
    return redirect(url_for('home'))


"@app.route('/routine', methods=['GET', 'POST'])
@login_required
def view_routine():
    user = get_session_user()
    conn = get_db_connection()
    
    CLASSES = ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    if request.method == 'POST' and user['role'] == 'admin':
        if 'add_slot' in request.form:
            branch = request.form.get('branch', 'surangapur').strip().lower()
            if session.get('branch'):
                branch = session['branch']
            class_name = request.form.get('class_name')
            day = request.form.get('day')
            start_time = request.form.get('start_time').strip()
            end_time = request.form.get('end_time').strip()
            subject = request.form.get('subject')
            teacher_name = request.form.get('teacher_name')
            
            conn.execute('''
                INSERT INTO class_routine (branch, class_name, day, start_time, end_time, subject, teacher_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (branch, class_name, day, start_time, end_time, subject, teacher_name))
            conn.commit()
            flash('Routine slot added successfully!')
            
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
        
    routines = conn.execute("SELECT * FROM class_routine ORDER BY branch, class_name, CASE day WHEN
<truncated 1410 bytes>

"# ================= ATTENDANCE ROUTES =================

@app.route('/admin/attendance', methods=['GET', 'POST'])
@login_required
def admin_attendance():
    user = get_session_user()
    if user['role'] not in ['admin', 'teacher']:
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    CLASSES = ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
    
    if session.get('branch'):
        branch_filter = session['branch']
    else:
        branch_filter = request.args.get('branch', 'surangapur').strip().lower()
        if branch_filter not in ['surangapur', 'bhogram']:
            branch_filter = 'surangapur'
            
    role_filter = request.args.get('role_filter', 'student').strip().lower()
    class_filter = request.args.get('class_filter', '').strip()
    date_filter = request.args.get('date_filter', datetime.today().strftime('%Y-%m-%d')).strip()
    
    if request.method == 'POST':
        role_type = request.form.get('role_type')
        date_val = request.form.get('date')
        user_ids = request.form.getlist('user_ids')
        
        if not user_ids:
            flash('No records to save.')
            conn.close()
            return redirect(url_for('admin_attendance', branch=branch_filter, role_filter=role_filter, class_filter=class_filter, date_filter=date_val))
            
        for uid in user_ids:
            status = request.form.get(f'status_{uid}', 'Present')
            remarks = request.form.get(f'remarks_{uid}', '').strip()
            
            conn.execute('''
                INSERT OR REPLACE INTO attendance (user_id, role, date, status, remarks)
                VALUES (?, ?, ?, ?, ?)
            ''', (uid, role_type, date_val, status, remarks))
            
        conn.commit()
        conn.close()
        flash('Attendance saved successfully!')
        return redirect(url_for('admin_attendance', branch=bran
<truncated 16062 bytes>
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Default to production-safe run if not overridden
    app.run(host='0.0.0.0', port=5001, debug=True)
