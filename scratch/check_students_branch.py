import sqlite3
conn = sqlite3.connect("users.db")
conn.row_factory = sqlite3.Row

print("=== DISTINCT CLASSES IN STUDENT_INFO ===")
classes = conn.execute("SELECT DISTINCT class FROM student_info").fetchall()
for c in classes:
    print(dict(c))

print("\n=== DISTINCT BRANCHES IN STUDENT_INFO ===")
branches = conn.execute("SELECT DISTINCT branch FROM student_info").fetchall()
for b in branches:
    print(dict(b))

print("\n=== DISTINCT BRANCHES IN USERS ===")
u_branches = conn.execute("SELECT DISTINCT branch FROM users").fetchall()
for ub in u_branches:
    print(dict(ub))

print("\n=== TOTAL STUDENTS ===")
st_count = conn.execute("SELECT COUNT(*) FROM student_info").fetchone()[0]
print(st_count)

print("\n=== TOTAL TEACHERS ===")
tch_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher'").fetchone()[0]
print(tch_count)

conn.close()
