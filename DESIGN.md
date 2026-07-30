# Enterprise Apple Liquid Glass Design System
## Al-Hidayet Mission Digital Infrastructure (2026 Architectural Audit & Refactor)

---

## Executive Summary & System Inventory

This document defines the production design architecture for the **Al-Hidayet Mission Management Platform**. All pages, templates, components, and interactive controllers follow ONE unified **Apple WWDC Liquid Glass Design System**.

---

## Phase 1 — Project Inventory Audit

### 1. Website Structure & Route Inventory (86 Pages & Templates)
- **Public Core**: Home (`/`), Services (`/services`), Gallery (`/gallery`), Routine (`/routine`), Application Portal (`/register`), User Login (`/login`), Reviews (`/reviews`).
- **Auth & Account Management**: Login (`login.html`), Register (`register.html`), Forgot Password (`forgot_password.html`), Forgot Username (`forgot_username.html`), Reset Password (`reset_password.html`), OTP Verification (`verify_otp.html`, `verify_review_otp.html`).
- **Dashboards**: Main Dashboard (`dashboard.html`), Branch Head Dashboard (`dashboard_branch_head.html`).
- **Admin Management Suite (56 Modules)**:
  - *User & Student Directory*: `student_list.html`, `add_student.html`, `edit_student.html`, `select_student.html`, `print_students.html`, `student_promotion.html`.
  - *Teacher & Staff Directory*: `teacher_list.html`, `edit_teacher.html`, `print_teachers.html`, `add_user.html`, `manage_staff.html`, `managing_committee.html`, `manage_admins.html`.
  - *Admissions*: `application_list.html`, `admin_form_view.html`.
  - *Cash Manager & Finance*: `set_fees.html`, `get_fees.html`, `fee_receipt.html`, `fee_matrix.html`, `reminder_fees.html`, `set_salary.html`, `give_salary.html`, `spend.html`, `finance_manage.html`.
  - *Academic Settings & Results*: `academics_setting.html`, `marks_setup.html`, `full_marks_config.html`, `marks_entry.html`, `bulk_marks.html`, `approve_marks.html`, `input_result.html`, `result_sheet.html`, `question_papers.html`, `bulk_routine.html`.
  - *Attendance & Meetings*: `attendance.html`, `attendance_charts.html`, `guardian_meetings.html`, `guardian_meeting_attendance.html`, `leaves.html`.
  - *Docs & Cards Generation*: `admit_card.html`, `admit_locked.html`, `bulk_admit_card.html`, `id_card.html`, `marksheet.html`, `marksheet_locked.html`, `bulk_marksheet.html`.
  - *Certificates Suite*: `manage_certificates.html`, `create_certificate.html`, `edit_certificate.html`, `print_certificate.html`.
  - *Audit & Library*: `audit_logs.html`, `audit_report.html`, `print_audit.html`, `library.html`, `bulk_upload.html`, `profile_edit_list.html`.
- **Teacher Workspace**: `teacher/complaints.html`, `teacher/edit_info.html`, `teacher/leaves.html`, `teacher/my_certificates.html`.
- **Student Workspace**: `student/edit_info.html`, `student/leaves.html`, `student/my_certificates.html`.

### 2. Component & UI Element Inventory
- **Navigation & Layout**: `main-header`, `main-nav`, `sidebar`, `top-bar`, `main-footer`, `mobile-menu-btn`, `sidebar-toggle-btn`.
- **Glass Surfaces**: `glass-panel`, `card`, `dash-card`, `custom-card`, `stat-card`, `widget-card`, `table-card`, `profile-card`, `auth-card`, `cert-card`, `form-card`, `stat-box`, `info-box`, `quick-action-card`.
- **Buttons**: `btn-primary`, `btn-outline`, `btn-secondary`, `btn-danger`, `cert-btn-print`, `cert-btn-edit`, `cert-btn-delete`, `theme-toggle-btn`.
- **Form Controls**: `input`, `select`, `textarea`, `search-select`, `.ts-control`, `.ts-dropdown`, `checkbox`, `file-upload`.
- **Data & Tables**: `table`, `thead`, `th`, `tbody`, `td`, `table-container`, `table-responsive`, `badge`, `status-badge`, `cert-badge`.
- **Printable Document Mockups**: `cert-mock`, `certificate-paper`, `id-card-paper`, `marksheet-box`, `admit-card-box`, `printable-doc`.

---

## Phase 2 — System Architecture & Design Tokens

### 1. Typography Hierarchy (`static/style.css`)
- **Primary Display Font**: `'Outfit', 'Plus Jakarta Sans', sans-serif`
- **Body & Controls**: `'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif`
- **Headings**: `h1` (32px / 1.2), `h2` (24px / 1.25), `h3` (18px / 1.3), `h4` (15px / 1.35).
- **Body Scale**: Regular (14px / 1.5), Small (13px / 1.4), Micro (11px / 1.3).

### 2. Centralized CSS Custom Properties
```css
:root {
    --primary-color: #1f6f78;
    --primary-dark: #15535a;
    --secondary-color: #2f80ed;
    --accent-color: #d59f2f;
    --danger-color: #ef4444;
    --success-color: #10b981;
    
    /* Light Mode Glass Tokens */
    --bg-light: #f8fafc;
    --text-dark: #0f172a;
    --glass-bg-light: rgba(255, 255, 255, 0.68);
    --glass-border-light: rgba(255, 255, 255, 0.8);
    --glass-shadow-light: 0 12px 36px -6px rgba(31, 38, 135, 0.12);
    
    /* Apple Spring Motion */
    --ease-apple-fluid: cubic-bezier(0.16, 1, 0.3, 1);
}

html[data-theme="dark"] {
    --primary-color: #38bdf8;
    --bg-light: #090e17;
    --text-dark: #f8fafc;
    --glass-bg-dark: rgba(15, 23, 42, 0.64);
    --glass-border-dark: rgba(255, 255, 255, 0.16);
    --glass-shadow-dark: 0 12px 36px -6px rgba(0, 0, 0, 0.65);
}
```

### 3. Apple Liquid Glass Translucency Parameters
- **Backdrop Blur Spec**: `backdrop-filter: blur(24px) saturate(190%) contrast(105%);`
- **Specular Border Rim Light**: `inset 0 1.5px 0 rgba(255, 255, 255, 0.95)` (Light) / `inset 0 1px 1px rgba(255, 255, 255, 0.24)` (Dark).
- **Universal Active Press Feedback**: `transform: scale(0.96) translateY(0)` with `100ms var(--ease-apple-fluid)`.
- **Printable Paper Protection**: `.cert-mock`, `.printable-doc` remain authentic white paper (`#ffffff`) with `#0f172a` dark text in both themes.
- **Top-Stacking Dropdown Portals**: TomSelect dropdowns (`.ts-dropdown`) attach to `document.body` with `z-index: 999999 !important;`.

---

## System Verification

- [x] **Universal Route Script Injection**: `@app.after_request` in `app.py` automatically injects `ux_optimization.js` into 100% of HTML responses.
- [x] **Global Ambient Mesh Canvas**: `#apple-fluid-bg` mounts 4 morphing liquid blobs with 60fps GPU parallax floating animation.
- [x] **Interactive Touch Ripple**: `#liquid-ripple-canvas` renders tight 36px liquid glass ripple rings on pointerdown.
- [x] **Cross-Tab Theme Synchronization**: Instant real-time theme sync across open browser tabs via `storage` event.
