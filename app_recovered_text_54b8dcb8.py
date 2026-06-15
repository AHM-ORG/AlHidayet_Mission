<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Academics Settings - Al Hidayet Mission</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <script src="https://unpkg.com/lucide@latest"></script>
    <link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@300;400;500;600&family=Outfit:wght@300;400;500;700&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/css/tom-select.css" rel="stylesheet">
</head>
<body class="bg-pattern">
    <div class="dashboard-container">
                                <!-- Sidebar -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <a href="/" style="display:flex; align-items:center; gap:10px; text-decoration:none; color:inherit;">
                    <img src="{{ logo_url }}" alt="AHM" style="width:36px; height:36px; border-radius:8px; object-fit:cover;">
                    <span style="font-weight:700; font-size:14px;">Al Hidayet Mission</span>
                </a>
            </div>
            <nav class="sidebar-nav">
                <a href="/dashboard" class="sidebar-item {% if request.path == '/dashboard' %}active{% endif %}"><i data-lucide="layout-dashboard"></i> Dashboard</a>

                {% if role == 'admin' %}
                <div class="sidebar-label">User Directory</div>
                <a href="/register" class="sidebar-item {% if request.path == '/register' %}active{% endif %}"><i data-lucide="user-plus"></i> Register</a>
                <a href="/admin/student-list" class="sidebar-item {% if request.path == '/admin/student-list' %}active{% endif %}"><i data-lucide="users"></i> Student Directory</a>
                <a href="/admin/teachers" class="sidebar-item {% if request.path == '/admin/teachers' %}active{% endif %}"><i data-lucide="graduation-cap"></i> Teacher Directory</a>
                <a href="/admin/applications" class="sidebar-item {% if request.path == '/admin/applications' %}active{% endif %}"><i data-lucide="file-check"></i> Admission Requests</a>

                <div class="sidebar-label">Cash Manager</div>
                <a href="/admin/set-fees" class="sidebar-item {% if request.path == '/admin/set-fees' %}active{% endif %}"><i data-lucide="indian-rupee"></i> Set Fees</a>
                <a href="/admin/set-salary" class="sidebar-item {% if request.path == '/admin/set-salary' %}active{% endif %}"><i data-lucide="banknote"></i> Set Salary</a>
                <a href="/admin/get-fees" class="sidebar-item {% if request.path == '/admin/get-fees' %}active{% endif %}"><i data-lucide="wallet"></i> Get Fees</a>
                <a href="/admin/reminder-fees" class="sidebar-item {% if request.path == '/admin/reminder-fees' %}active{% endif %}"><i data-lucide="bell-ring"></i> Reminder Fees</a>
                <a href="/admin/spend" class="sidebar-item {% if request.path == '/admin/spend' %}active{% endif %}"><i data-lucide="receipt"></i> Spend</a>

                <div class="sidebar-label">Audit</div>
                <a href="/admin/audit-report" class="sidebar-item {% if request.path == '/admin/audit-report' %}active{% endif %}"><i data-lucide="clipboard-check"></i> Audit Report</a>

                <div class="sidebar-label">Docs & Cards</div>
                <a href="/admin/admit-card" class="sidebar-item {% if request.path == '/admin/admit-card' %}active{% endif %}"><i data-lucide="ticket"></i> Admit & Seat Token</a>
                <a href="/admin/marksheet" class="sidebar-item {% if request.path == '/admin/marksheet' %}active{% endif %}"><i data-lucide="file-spreadsheet"></i> Marksheet</a>
                <a href="/admin/id-card" class="sidebar-item {% if request.path == '/admin/id-card' %}active{% endif %}"><i data-lucide="contact"></i> Id Card</a>

                <div class="sidebar-label">Academics</div>
                <a href="/admin/bulk-marks" class="sidebar-item {% if request.path == '/admin/bulk-marks' %}active{% endif %}"><i data-lucide="edit-3"></i> Bulk Mark Entry</a>
                <a href="/admin/academics-setting" class="sidebar-item {% if request.path == '/admin/academics-setting' %}active{% endif %}"><i data-lucide="settings"></i> Academic Setting</a>
                <a href="/admin/student-promotion" class="sidebar-item {% if request.path == '/admin/student-promotion' %}active{% endif %}"><i data-lucide="user-check"></i> Student Promotion</a>
                <a href="/admin/bulk-upload" class="sidebar-item {% if request.path == '/admin/bulk-upload' %}active{% endif %}"><i data-lucide="upload"></i> Bulk Data Upload</a>
                <a href="/routine" class="sidebar-item {% if request.path == '/routine' %}active{% endif %}"><i data-lucide="calendar"></i> Class Routine</a>
                {% endif %}

                {% if role == 'teacher' %}
                <div class="sidebar-label">Academic Tools</div>
                <a href="/admin/student-list" class="sidebar-item {% if request.path == '/admin/student-list' %}active{% endif %}"><i data-lucide="users"></i> My Students</a>
                <a href="/admin/bulk-marks" class="sidebar-item {% if request.path == '/admin/bulk-marks' %}active{% endif %}"><i data-lucide="edit-3"></i> Give Marks</a>
                <a href="/admin/marksheet" class="sidebar-item {% if request.path == '/admin/marksheet' %}active{% endif %}"><i data-lucide="file-spreadsheet"></i> Marksheets</a>
                <a href="/admin/academics-setting" class="sidebar-item {% if request.path == '/admin/academics-setting' %}active{% endif %}"><i data-lucide="settings"></i> Academic Setting</a>
                <a href="/admin/student-promotion" class="sidebar-item {% if request.path == '/admin/student-promotion' %}active{% endif %}"><i data-lucide="user-check"></i> Student Promotion</a>
                <a href="/admin/bulk-upload" class="sidebar-item {% if request.path == '/admin/bulk-upload' %}active{% endif %}"><i data-lucide="upload"></i> Bulk Data Upload</a>
                <a href="/routine" class="sidebar-item {% if request.path == '/routine' %}active{% endif %}"><i data-lucide="calendar"></i> Class Routine</a>
                <a href="/admin/id-card" class="sidebar-item {% if request.path == '/admin/id-card' %}active{% endif %}"><i data-lucide="contact"></i> ID Cards</a>
                <a href="/admin/admit-card" class="sidebar-item {% if request.path == '/admin/admit-card' %}active{% endif %}"><i data-lucide="ticket"></i> Admit Cards</a>
                {% endif %}

                {% if role == 'student' %}
                <div class="sidebar-label">My Desk</div>
                <a href="/admin/marksheet" class="sidebar-item {% if request.path == '/admin/marksheet' %}active{% endif %}"><i data-lucide="file-spreadsheet"></i> My Marksheet</a>
                <a href="/admin/get-fees" class="sidebar-item {% if request.path == '/admin/get-fees' %}active{% endif %}"><i data-lucide="wallet"></i> My Fee Status</a>
                <a href="/admin/id-card" class="sidebar-item {% if request.path == '/admin/id-card' %}active{% endif %}"><i data-lucide="contact"></i> My ID Card</a>
                <a href="/admin/admit-card" class="sidebar-item {% if request.path == '/admin/admit-card' %}active{% endif %}"><i data-lucide="ticket"></i> My Admit Card</a>
                <a href="/routine" class="sidebar-item {% if request.path == '/routine' %}active{% endif %}"><i data-lucide="calendar"></i> My Class Routine</a>
                {% endif %}

                <a href="/logout" class="sidebar-item" style="margin-top:50px; color:#ff7675;"><i data-lucide="log-out"></i> Logout</a>
            </nav>
        </aside>

        <main class="main-content">
            <header class="top-bar">
                <div class="top-bar-title">Academic Settings</div>
            </header>
            <div class="content-wrapper" style="padding: 20px;">
                <div class="auth-section" style="padding: 0;">
                    <div class="auth-container" style="max-width: 100%; margin: 0; box-shadow: var(--shadow-sm);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                            <h2 style="margin: 0; color: var(--primary-color);">
                                <i data-lucide="settings" style="vertical-align: middle;"></i> Academics Settings
                            </h2>
                        </div>

            <!-- Flash Messages -->
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                <div class="flash-messages" style="margin-bottom: 20px;">
                  {% for category, message in messages %}
                    <div class="alert alert-{{ category if category != 'error' else 'danger' }}" style="padding: 12px 20px; border-radius: var(--radius); margin-bottom: 10px; font-weight: 500; display: flex; align-items: center; gap: 10px; background: {% if category == 'error' %}#fdf2f2{% else %}#f0fdf4{% endif %}; color: {% if category == 'error' %}var(--danger-color){% else %}var(--success-color){% endif %}; border: 1px solid {% if category == 'error' %}#fca5a5{% else %}#bbf7d0{% endif %}; font-family: 'Outfit', sans-serif;">
                      <i data-lucide="{% if category == 'error' %}alert-circle{% else %}check-circle{% endif %}" style="width: 20px; height: 20px;"></i>
                      <span>{{ message }}</span>
                    </div>
                  {% endfor %}
                </div>
              {% endif %}
            {% endwith %}

            {% if role == 'admin' %}
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
                
                <!-- LEFT COLUMN: CREATE SUBJECTS -->
                <div>
                    <div class="auth-container" style="margin: 0; box-shadow: none; border: 1px solid #eee;">
                        <h3 style="color: #0984e3; margin-bottom: 15px;">Add New Subject</h3>
                        <form method="POST">
                            <input type="hidden" name="create_subject" value="1">
                            <div class="input-group">
                                <label>Subject Name</label>
                                <input type="text" name="name" placeholder="e.g. Mathematics" required>
                            </div>
                            <div class="input-group">
                                <label>Classes (Tick all that apply)</label>
                                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 10px; margin-top: 5px;">
                                    {% for c in ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'] %}
                                    <label style="display: flex; align-items: center; font-weight: normal; font-size: 14px; cursor: pointer;">
                                        <input type="checkbox" name="classes" value="{{ c }}" style="margin-right: 5px;"> {{ c }}
                                    </label>
                                    {% endfor %}
                                </div>
                            </div>
                            <button type="submit" class="auth-btn">Add Subject to Classes</button>
                        </form>
                    </div>

                    <div style="margin-top: 30px;">
                        <h3 style="margin-bottom: 10px;">Existing Subjects</h3>
                        <div style="max-height: 300px; overflow-y: auto; border: 1px solid #eee; border-radius: 8px;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                    <tr>
                                        <th style="padding: 10px; text-align: left;">Subject</th>
                                        <th style="padding: 10px; text-align: left;">Class</th>
                                        <th style="padding: 10px; text-align: center;">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for subject in subjects %}
                                    <tr style="border-bottom: 1px solid #eee;">
                                        <td style="padding: 10px;">{{ subject.name }}</td>
                                        <td style="padding: 10px;">{{ subject.class }}</td>
                                        <td style="padding: 10px; text-align: center;">
                                            <form method="POST" onsubmit="return confirm('Delete subject {{ subject.name }} for Class {{ subject.class }}?')" style="display: inline;">
                                                <input type="hidden" name="delete_subject" value="1">
                                                <input type="hidden" name="subject_id" value="{{ subject.id }}">
                                                <button type="submit" class="badge" style="background-color: #ff7675; border: none; cursor: pointer; color: white; padding: 4px 8px; border-radius: 4px;">
                                                    <i data-lucide="trash-2" style="width: 12px; height: 12px; vertical-align: middle;"></i> Delete
                                                </button>
                                            </form>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- RIGHT COLUMN: ASSIGN TEACHERS -->
                <div>
                    <div class="auth-container" style="margin: 0; box-shadow: none; border: 1px solid #eee;">
                        <h3 style="color: #00b894; margin-bottom: 15px;">Assign Teacher to Subject</h3>
                        <form method="POST">
                            <input type="hidden" name="assign_teacher" value="1">
                            <div class="input-group">
                                <label>Teacher</label>
                                <select name="teacher_id" required>
                                    <option value="">Select Teacher</option>
                                    {% for teacher in teachers %}
                                    <option value="{{ teacher.id }}">{{ teacher.username }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="input-group">
                                <label>Subject Name</label>
                                <select name="subject_name" required>
                                    <option value="">Select Subject</option>
                                    {% for subject in distinct_subjects %}
                                    <option value="{{ subject.name }}">{{ subject.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="input-group">
                                <label>Classes (Tick all that apply)</label>
                                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 10px; margin-top: 5px;">
                                    {% for c in ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'] %}
                                    <label style="display: flex; align-items: center; font-weight: normal; font-size: 14px; cursor: pointer;">
                                        <input type="checkbox" name="classes" value="{{ c }}" style="margin-right: 5px;"> {{ c }}
                                    </label>
                                    {% endfor %}
                                </div>
                            </div>
                            <button type="submit" class="auth-btn" style="background: #00b894;">Assign Teacher to Classes</button>
                        </form>
                    </div>

                    <div style="margin-top: 30px;">
                        <h3 style="margin-bottom: 10px;">Teacher Assignments</h3>
                        <div style="max-height: 300px; overflow-y: auto; border: 1px solid #eee; border-radius: 8px;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                    <tr>
                                        <th style="padding: 10px; text-align: left;">Teacher</th>
                                        <th style="padding: 10px; text-align: left;">Subject</th>
                                        <th style="padding: 10px; text-align: left;">Class</th>
                                        <th style="padding: 10px; text-align: center;">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for assign in assignments %}
                                    <tr style="border-bottom: 1px solid #eee;">
                                        <td style="padding: 10px;"><strong>{{ assign.teacher_name }}</strong></td>
                                        <td style="padding: 10px;">{{ assign.subject_name }}</td>
                                        <td style="padding: 10px;">{{ assign.class }}</td>
                                        <td style="padding: 10px; text-align: center;">
                                            <form method="POST" onsubmit="return confirm('Delete assignment for {{ assign.teacher_name }} teaching {{ assign.subject_name }} to Class {{ assign.class }}?')" style="display: inline;">
                                                <input type="hidden" name="delete_assignment" value="1">
                                                <input type="hidden" name="assignment_id" value="{{ assign.id }}">
                                                <button type="submit" class="badge" style="background-color: #ff7675; border: none; cursor: pointer; color: white; padding: 4px 8px; border-radius: 4px;">
                                                    <i data-lucide="trash-2" style="width: 12px; height: 12px; vertical-align: middle;"></i> Delete
                                                </button>
                                            </form>
                                        </td>
                                    </tr>
                                    {% else %}
                                    <tr><td colspan="4" style="padding:15px; text-align:center; color:#999;">No assignments made yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

            </div>

            <!-- CLASS TEST CONFIGURATIONS SECTION -->
            <div style="margin-top: 50px; border-top: 2px solid #eee; padding-top: 30px; width: 100%;">
                <h3 style="color: var(--primary-color); margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
                    <i data-lucide="clipboard-list"></i> Class Test Configurations
                </h3>
                
                <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 30px; margin-bottom: 30px;">
                    <!-- Create Config Form -->
                    <div class="auth-container" style="margin: 0; box-shadow: none; border: 1px solid #eee; background: #fafafa;">
                        <h4 style="color: #0984e3; margin-bottom: 15px;">Configure Class Test</h4>
                        <form method="POST">
                            <input type="hidden" name="create_class_test_config" value="1">
                            <div class="input-group">
                                <label>Test Name</label>
                                <input type="text" name="test_name" placeholder="e.g. Monthly Test 1" required style="padding: 10px; border: 2px solid var(--border-color); border-radius: var(--radius); width: 100%;">
                            </div>
                            <div class="input-group">
                                <label>Class</label>
                                <select name="class_name" required>
                                    <option value="">Select Class</option>
                                    {% for c in ['Nursery', 'U/N', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'] %}
                                    <option value="{{ c }}">{{ c }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="input-group">
                                <label>Subject</label>
                                <select name="subject_name" required>
                                    <option value="">Select Subject</option>
                                    {% for subject in distinct_subjects %}
                                    <option value="{{ subject.name }}">{{ subject.name }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="input-group">
                                <label>Full Marks</label>
                                <input type="number" name="full_marks" value="20" required min="1" max="100" style="padding: 10px; border: 2px solid var(--border-color); border-radius: var(--radius); width: 100%;">
                            </div>
                            <button type="submit" class="auth-btn">Save Configuration</button>
                        </form>
                    </div>
                    
                    <!-- Table View -->
                    <div>
                        <h4 style="margin-bottom: 15px;">Configured Tests</h4>
                        <div style="max-height: 400px; overflow-y: auto; border: 1px solid #eee; border-radius: 8px; background: white;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                    <tr>
                                        <th style="padding: 12px; text-align: left;">Test Name</th>
                                        <th style="padding: 12px; text-align: left;">Class</th>
                                        <th style="padding: 12px; text-align: left;">Subject</th>
                                        <th style="padding: 12px; text-align: center;">Full Marks</th>
                                        <th style="padding: 12px; text-align: center;">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for config in class_test_configs %}
                                    <tr style="border-bottom: 1px solid #eee;">
                                        <td style="padding: 12px;"><strong>{{ config.test_name }}</strong></td>
                                        <td style="padding: 12px;">Class {{ config.class_name }}</td>
                                        <td style="padding: 12px;">{{ config.subject_name }}</td>
                                        <td style="padding: 12px; text-align: center;"><span style="background: #e8f5e9; color: #166534; padding: 4px 10px; border-radius: 20px; font-weight: 600;">{{ config.full_marks }}</span></td>
                                        <td style="padding: 12px; text-align: center;">
                                            <form method="POST" onsubmit="return confirm('Delete config for {{ config.test_name }}?')" style="display: inline;">
                                                <input type="hidden" name="delete_class_test_config" value="1">
                                                <input type="hidden" name="config_id" value="{{ config.id }}">
                                                <button type="submit" class="badge" style="background-color: #ff7675; border: none; cursor: pointer; color: white; padding: 4px 8px; border-radius: 4px;">
                                                    <i data-lucide="trash-2" style="width: 12px; height: 12px;"></i> Delete
                                                </button>
                                            </form>
                                        </td>
                                    </tr>
                                    {% else %}
                                    <tr><td colspan="5" style="padding: 20px; text-align: center; color: #999;">No class tests configured yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            {% else %}
            <!-- Read-only View for Teachers -->
            <div style="background: white; border: 1px solid #eee; border-radius: 12px; padding: 20px; box-shadow: var(--shadow-sm);">
                <h3 style="color: var(--primary-color); margin-bottom: 20px; display: flex; align-items: center; gap: 8px; border-bottom: 2px solid #eee; padding-bottom: 12px;">
                    <i data-lucide="clipboard-list"></i> Configured Class Tests
                </h3>
                <div style="max-height: 500px; overflow-y: auto; border: 1px solid #eee; border-radius: 8px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead style="background: #f8f9fa; position: sticky; top: 0;">
                            <tr>
                                <th style="padding: 12px; text-align: left;">Test Name</th>
                                <th style="padding: 12px; text-align: left;">Class</th>
                                <th style="padding: 12px; text-align: left;">Subject</th>
                                <th style="padding: 12px; text-align: center;">Full Marks</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for config in class_test_configs %}
                            <tr style="border-bottom: 1px solid #eee;">
                                <td style="padding: 12px;"><strong>{{ config.test_name }}</strong></td>
                                <td style="padding: 12px;">Class {{ config.class_name }}</td>
                                <td style="padding: 12px;">{{ config.subject_name }}</td>
                                <td style="padding: 12px; text-align: center;"><span style="background: #e8f5e9; color: #166534; padding: 4px 10px; border-radius: 20px; font-weight: 600;">{{ config.full_marks }}</span></td>
                            </tr>
                            {% else %}
                            <tr><td colspan="4" style="padding: 20px; text-align: center; color: #999;">No class tests configured yet.</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
            {% endif %}

                    </div>
                </div>
            </div>
        </main>
    </div>
    <script>lucide.createIcons();</script>
    <script src="https://cdn.jsdelivr.net/npm/tom-select@2.2.2/dist/js/tom-select.complete.min.js"></script>

    <script>
        document.addEventListener("DOMContentLoaded", function() {
            document.querySelectorAll('select').forEach((el)=>{
                new TomSelect(el, {
                    create: false,
                    sortField: null
                });
            });
        });
    </script>
</body>
</html>