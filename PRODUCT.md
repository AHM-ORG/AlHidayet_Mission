# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

1. **School Administrators & Branch Heads**: Oversee daily operations, manage student enrollment, fee collections, academic schedules, financial aid, and staff assignments.
2. **Teachers**: Track attendance, input exam/test marks, view subject routines, and manage assigned classes.
3. **Students & Guardians**: Access academic performance, review schedules, inspect fee receipts, and submit application forms.

## Product Purpose

A complete, centralized Educational Institute Management System designed to streamline administrative workflows, automate fee ledgers and billing, simplify academic scheduling, and enhance guardian communication.

## Positioning

A localized, multi-branch school ERP tailored specifically for Al-Hidayet Educational Institutions, providing robust role-based access, automated fee ledger synchronization, and real-time administrative dashboards.

## Operating Context

- **Workflows**: Student admissions & application processing, class assignment, gradebook entry, monthly fee collection, billing worker execution, admit card generation, and guardian meeting logs.
- **Environment**: Web-based responsive portal accessed via desktop and mobile browsers across campus branches.
- **Tech Stack**: Python Flask server, SQLite database, Jinja2 template rendering, custom Vanilla CSS/JS design system with Apple Fluid motion design tokens.

## Capabilities and Constraints

- Role-based authentication (`admin`, `branch_head`, `teacher`, `student`, `guardian`).
- Dynamic academic routine, subject allocation, and class management.
- Automated monthly billing worker (`billing_worker.py`), dues reset, and payment tracking.
- Printable document generation (admit cards, report cards, ID cards).
- Built-in UX optimizations (intent pre-fetching, instant file previews, hardware-accelerated micro-interactions).

## Brand Commitments

- **Name**: Al-Hidayet Mission (AHM System)
- **Design Tokens**: Professional teal/cyan primary hierarchy (`#1f6f78`), Fredoka headings, Outfit body typography, Apple Fluid physical motion response.
- **Voice**: Professional, trustworthy, structured, and accessible.

## Evidence on Hand

- Core Flask application (`app.py`), database schemas (`schema.json`, `school.db`), administrative & student templates (`templates/`).
- Established design system assets (`static/style.css`, `static/js/ux_optimization.js`).
- Motion plans roadmap (`plans/README.md`).

## Product Principles

1. **Clarity & Efficiency**: Administrative workflows must minimize manual steps with fast, deterministic form processing.
2. **Data Integrity**: Fee transactions, student records, and gradebook entries must maintain strict transactional consistency across all branches.
3. **Responsive Craft**: Fast page loads, hardware-accelerated animations, and responsive layouts across desktop and mobile.
