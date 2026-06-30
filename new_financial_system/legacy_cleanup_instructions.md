# Legacy Code Cleanup Instructions

To safely remove the old deprecated Audit Report system from your existing Flask monolith and prevent conflicting endpoints, please follow these steps from your main project root directory (`AlHidayet_Mission`).

### 1. Remove Old HTML Templates
First, delete the old Jinja template file that rendered the audit report:
```bash
rm templates/admin/audit_report.html
```

### 2. Locate and Remove Flask Routes
You need to grep your `app.py` file to find where the old `/admin/audit-report` route was defined.

**Grep Command:**
```bash
grep -n "@app.route('/admin/audit-report'" app.py
```
*Expected Output:* You should see something like `app.py:8450:@app.route('/admin/audit-report', methods=['GET', 'POST'])`

**Action:**
Open `app.py` in your editor, go to that line number, and safely delete the entire `def audit_report():` function block up until the next `@app.route` definition.

### 3. Clean up the Sidebar Navigation
The old audit report was linked in the sidebar. You need to remove the HTML link from all your templates.

**Grep Command:**
```bash
grep -rnw 'templates/' -e '/admin/audit-report'
```

**Action:**
Open the affected files (such as `templates/admin/get_fees.html`, `templates/admin/dashboard.html`, etc.) and delete the line containing:
`<a href="/admin/audit-report" class="sidebar-item">...</a>`

### 4. Note on React Router
Your prompt mentioned removing endpoints from "React router". Based on a scan of your existing `AlHidayet_Mission` repository, your current application uses pure Jinja2 templating and does **not** have React Router installed. If you have a separate frontend repository for a different module, simply ensure that any `<Route path="/admin/audit-report" ... />` elements are deleted from your `App.jsx` or `Router.jsx` file.

### 5. Final Verification
Run a final grep to ensure the route string no longer exists anywhere in your backend:
```bash
grep -rnw '.' -e '/admin/audit-report' --exclude-dir=new_financial_system --exclude-dir=.venv --exclude-dir=.git
```
If this returns nothing, the old system is completely ripped out!
