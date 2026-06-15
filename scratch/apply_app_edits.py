import os

app_path = "app.py"
print(f"Reading {app_path} ...")

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Let's find and replace the marksheet() route (lines 2003 to 2112)
target_marksheet_start = "@app.route('/admin/marksheet')"
target_marksheet_end = "@app.route('/admin/bulk-marks', methods=['GET', 'POST'])"

start_idx = content.find(target_marksheet_start)
end_idx = content.find(target_marksheet_end)

if start_idx == -1 or end_idx == -1:
    print("Error: Could not find marksheet route start/end landmarks.")
    exit(1)

print(f"Found marksheet route at range {start_idx} to {end_idx}.")

new_marksheet_code = """@app.route('/admin/marksheet')
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
            
            # Query class tests config to isolate monthly tests
            class_tests_rows = conn.execute("SELECT DISTINCT test_name FROM class_test_configs").fetchall()
            class_test_names = [r['test_name'] for r in class_tests_rows]
            
            # Standard monthly tests keywords matching fallback
            def is_monthly_test(term_name):
                if term_name in class_test_names:
                    return True
                term_lower = term_name.lower()
                return 'monthly' in term_lower or 'class test' in term_lower or 'test' in term_lower
            
            monthly_marks = []
            term_marks = []
            annual_marks = []
            
            for m in marks_rows:
                term_name = m['term']
                if is_monthly_test(term_name):
                    monthly_marks.append(m)
                elif 'annual' in term_name.lower():
                    annual_marks.append(m)
                else:
                    term_marks.append(m)
                    
            # Combine Annual Exam + Monthly Test Gross
            ct_by_sub = {}
            for m in monthly_marks:
                sub = m['subject'].strip().title()
                if sub not in ct_by_sub:
                    ct_by_sub[sub] = {'obt': 0.0, 'full': 0.0}
                ct_by_sub[sub]['obt'] += float(m['marks'] or 0)
                ct_by_sub[sub]['full'] += float(m['total_marks'] or 0)
                
            annual_composite = []
            meta = dict(marks_rows[0]) if marks_rows else {}
            
            # Get list of all distinct subjects from the student's marks
            all_subjects = sorted(list(set(m['subject'].strip().title() for m in marks_rows)))
            
            for sub in all_subjects:
                # Find Annual Exam mark for this subject
                ann_mark = next((m for m in annual_marks if m['subject'].strip().title() == sub), None)
                
                # Fetch monthly class test data
                ct_data = ct_by_sub.get(sub, {'obt': 0.0, 'full': 0.0})
                
                # Scale Class Test Gross to 20% weight
                if ct_data['full'] > 0:
                    ct_obt_scaled = round((ct_data['obt'] / ct_data['full']) * 20.0, 2)
                    ct_full = 20.0
                    ct_pct = round((ct_data['obt'] / ct_data['full']) * 100.0, 1)
                else:
                    ct_obt_scaled = 0.0
                    ct_full = 20.0
                    ct_pct = 0.0
                    
                # Scale Annual Exam to 80% weight
                if ann_mark:
                    ann_obt = float(ann_mark['marks'] or 0)
                    ann_total = float(ann_mark['total_marks'] or 100.0)
                    ann_obt_scaled = round((ann_obt / ann_total) * 80.0, 2)
                    ann_full = 80.0
                    ann_raw = ann_obt
                    ann_raw_full = ann_total
                else:
                    ann_obt_scaled = 0.0
                    ann_full = 80.0
                    ann_raw = 0.0
                    ann_raw_full = 100.0
                    
                # Gross combined score out of 100
                if ct_data['full'] > 0 and ann_mark:
                    gross_total = round(ct_obt_scaled + ann_obt_scaled, 2)
                elif ann_mark:
                    # If no class test, scale Annual Exam to 100
                    gross_total = round((ann_raw / ann_raw_full) * 100.0, 2)
                elif ct_data['full'] > 0:
                    # If only class test, scale Class Test to 100
                    gross_total = round((ct_data['obt'] / ct_data['full']) * 100.0, 2)
                else:
                    gross_total = 0.0
                    
                # Compute grade based on Gross Total
                grade = 'F'
                if gross_total >= 90: grade = 'A+'
                elif gross_total >= 80: grade = 'A'
                elif gross_total >= 70: grade = 'B+'
                elif gross_total >= 60: grade = 'B'
                elif gross_total >= 50: grade = 'C'
                elif gross_total >= 40: grade = 'D'
                
                annual_composite.append({
                    'subject': sub,
                    'ct_obtained': ct_obt_scaled,
                    'ct_full': ct_full,
                    'ct_percentage': ct_pct,
                    'ann_raw_obtained': ann_raw,
                    'ann_raw_full': ann_raw_full,
                    'ann_obtained': ann_obt_scaled,
                    'ann_full': ann_full,
                    'gross_total': gross_total,
                    'grade': grade,
                    **{k: meta.get(k, 'N/A') for k in ['student_name', 'class', 'roll_number', 'branch', 'guardian_name', 'dob', 'section']}
                })
                
            conn.close()
            logo_url = url_for('static', filename='images/logo.png')
            return render_template('admin/marksheet.html', 
                                   marks=term_marks, 
                                   monthly_marks=monthly_marks, 
                                   annual_composite=annual_composite, 
                                   student_info=meta,
                                   role=role,
                                   logo_url=logo_url)
        
        # Load students list if not specifying a student
        if session.get('branch'):
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student' AND si.branch = ?", (session['branch'],)).fetchall()
        else:
            students = conn.execute("SELECT u.id, u.username, si.full_name, si.roll_number, si.class, si.guardian_name FROM users u LEFT JOIN student_info si ON u.id = si.user_id WHERE u.role = 'student'").fetchall()
        conn.close()
        return render_template('admin/marksheet.html', marks=None, students=students, role=role)
    return redirect(url_for('home'))

"""

patched_content = content[:start_idx] + new_marksheet_code + "\n" + content[end_idx:]
print("Marksheet route patched successfully.")

# 2. Let's patch from line 3550 (view_routine) to the end of the file with the recovered routes
routine_start = patched_content.find("@app.route('/routine')")
if routine_start == -1:
    print("Error: Could not find routine route in patched content.")
    exit(1)

print(f"Found routine route start in patched content at index {routine_start}. Truncating remainder and appending all recovered routes...")

base_rest_content = patched_content[:routine_start]

recovered_routes = """# ================= STUDENT INFO EDIT REQUESTS =================

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
            'district': district
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


# ================= CLASS ROUTINE SCHEDULER =================

@app.route('/routine', methods=['GET', 'POST'])
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
        
    class_order = ['Nursery', 'L/N', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
    def get_class_sort_index(cls_name):
        if not cls_name: return len(class_order) + 2
        cls_upper = cls_name.strip().upper()
        for idx, c in enumerate(class_order):
            if c.upper() == cls_upper:
                return idx
        return len(class_order) + 1

    routines = conn.execute("SELECT * FROM class_routine").fetchall()
    day_order = {d: i for i, d in enumerate(DAYS)}
    
    sorted_routines = sorted(
        [dict(r) for r in routines],
        key=lambda x: (x['branch'], get_class_sort_index(x['class_name']), day_order.get(x['day'], 99), x['start_time'])
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
        SELECT DISTINCT class FROM subjects WHERE class IS NOT NULL AND class != ''
    ''').fetchall()
    classes_list = sorted([c[0] for c in db_classes], key=get_class_sort_index)
    
    distinct_subjects = [r['name'] for r in conn.execute("SELECT DISTINCT name FROM subjects").fetchall()]
    teachers_list = conn.execute('''
        SELECT COALESCE(ti.full_name, u.username) as name
        FROM users u
        LEFT JOIN teacher_info ti ON u.id = ti.user_id
        WHERE u.role = 'teacher'
    ''').fetchall()
    teachers = [t['name'] for t in teachers_list]
    
    conn.close()
    logo_url = url_for('static', filename='images/logo.png')
    
    return render_template('routine.html', 
                           classes=classes_list, 
                           days=DAYS, 
                           distinct_subjects=distinct_subjects, 
                           teachers=teachers, 
                           routine_data=routine_data, 
                           role=user['role'], 
                           logo_url=logo_url)


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
    branches = ['surangapur', 'bhogram']
    
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
        if branch_filter not in ['surangapur', 'bhogram']:
            branch_filter = None
            
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
    logo_url = url_for('static', filename='images/logo.png')
    
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
    
    class_order = ['Nursery', 'L/N', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']
    def get_class_sort_index(cls_name):
        if not cls_name: return len(class_order) + 2
        cls_upper = cls_name.strip().upper()
        for idx, c in enumerate(class_order):
            if c.upper() == cls_upper:
                return idx
        return len(class_order) + 1
        
    classes_list = sorted([c['class'] for c in db_classes], key=get_class_sort_index)
    selected_class = request.args.get('class_name', classes_list[0] if classes_list else '')
    
    guardians_roster = []
    if selected_class:
        guardians_roster = conn.execute('''
            SELECT u.id as user_id, si.full_name as student_name, si.guardian_name, si.class, si.roll_number, ma.status, ma.remarks
            FROM users u
            JOIN student_info si ON u.id = si.user_id
            LEFT JOIN meeting_attendance ma ON u.id = ma.user_id AND ma.meeting_id = ? AND ma.attendee_type = 'guardian'
            WHERE u.role = 'student' AND si.branch = ? AND si.class = ?
            ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
        ''', (meeting_id, meeting['branch'], selected_class)).fetchall()
        
    others_roster = conn.execute('''
        SELECT * FROM meeting_attendance
        WHERE meeting_id = ? AND attendee_type = 'other'
        ORDER BY id DESC
    ''', (meeting_id,)).fetchall()
    
    active_tab = request.args.get('tab', 'teachers')
    conn.close()
    logo_url = url_for('static', filename='images/logo.png')
    
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
        return redirect(url_for('admin_attendance', branch=branch_filter, role_filter=role_type, class_filter=class_filter, date_filter=date_val))
        
    users_list = []
    if role_filter == 'student':
        if class_filter:
            users_list = conn.execute('''
                SELECT u.id, u.username, si.full_name, si.class, si.roll_number, att.status, att.remarks
                FROM users u
                JOIN student_info si ON u.id = si.user_id
                LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ?
                WHERE u.role = 'student' AND si.branch = ? AND si.class = ?
                ORDER BY CAST(si.roll_number AS INTEGER), si.roll_number
            ''', (date_filter, branch_filter, class_filter)).fetchall()
    elif role_filter == 'teacher':
        users_list = conn.execute('''
            SELECT u.id, u.username, ti.full_name, 'Teacher' as class, '' as roll_number, att.status, att.remarks
            FROM users u
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            LEFT JOIN attendance att ON u.id = att.user_id AND att.date = ?
            WHERE u.role = 'teacher' AND (u.branch = ? OR u.branch IS NULL OR u.branch = '')
            ORDER BY COALESCE(ti.full_name, u.username)
        ''', (date_filter, branch_filter)).fetchall()
        
    conn.close()
    logo_url = url_for('static', filename='images/logo.png')
    
    return render_template('admin/attendance.html',
                           users=users_list,
                           role=user['role'],
                           classes=CLASSES,
                           branches=['Surangapur', 'Bhogram'],
                           branch_filter=branch_filter,
                           role_filter=role_filter,
                           class_filter=class_filter,
                           date_filter=date_filter,
                           logo_url=logo_url)


# ================= LEAVE MANAGEMENT =================

@app.route('/admin/leaves', methods=['GET', 'POST'])
@login_required
def admin_leaves():
    user = get_session_user()
    if user['role'] != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        leave_id = request.form.get('leave_id')
        action = request.form.get('action')
        status = 'Approved' if action == 'approve' else 'Rejected'
        
        conn.execute("UPDATE leaves SET status = ? WHERE id = ?", (status, leave_id))
        conn.commit()
        flash(f'Leave application {status.lower()} successfully.')
        conn.close()
        return redirect(url_for('admin_leaves'))
        
    if session.get('branch'):
        pending_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as full_name, u.username, COALESCE(si.class, 'Teacher') as class
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status = 'Pending' AND (si.branch = ? OR ti.address LIKE '%' || ? || '%' OR u.branch = ?)
            ORDER BY l.submitted_at DESC
        ''', (session['branch'], session['branch'], session['branch'])).fetchall()
        
        resolved_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as full_name, u.username, COALESCE(si.class, 'Teacher') as class
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status != 'Pending' AND (si.branch = ? OR ti.address LIKE '%' || ? || '%' OR u.branch = ?)
            ORDER BY l.submitted_at DESC LIMIT 50
        ''', (session['branch'], session['branch'], session['branch'])).fetchall()
    else:
        pending_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as full_name, u.username, COALESCE(si.class, 'Teacher') as class
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status = 'Pending'
            ORDER BY l.submitted_at DESC
        ''').fetchall()
        
        resolved_leaves = conn.execute('''
            SELECT l.*, COALESCE(si.full_name, ti.full_name, u.username) as full_name, u.username, COALESCE(si.class, 'Teacher') as class
            FROM leaves l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN student_info si ON u.id = si.user_id
            LEFT JOIN teacher_info ti ON u.id = ti.user_id
            WHERE l.status != 'Pending'
            ORDER BY l.submitted_at DESC LIMIT 50
        ''').fetchall()
        
    conn.close()
    logo_url = url_for('static', filename='images/logo.png')
    
    return render_template('admin/leaves.html',
                           pending_leaves=pending_leaves,
                           resolved_leaves=resolved_leaves,
                           role=user['role'],
                           logo_url=logo_url)

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
    logo_url = url_for('static', filename='images/logo.png')
    
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
    logo_url = url_for('static', filename='images/logo.png')
    
    return render_template('teacher/leaves.html',
                           leave_history=leave_history,
                           attendance_log=attendance_log,
                           cl_quota=cl_quota,
                           cl_balance=cl_balance,
                           role=user['role'],
                           username=user['username'],
                           logo_url=logo_url)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
"""

final_content = base_rest_content + recovered_routes

with open(app_path, "w", encoding="utf-8") as f:
    f.write(final_content)

print("Patch complete! app.py successfully saved.")
