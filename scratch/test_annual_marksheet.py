import sys
import os
import unittest
import sqlite3

# Insert project path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db_connection, init_db, calculate_grade, calculate_overall_grade

class TestAnnualMarksheet(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'testing_secret_key'
        self.client = app.test_client()
        
        # Initialize/Verify database migration
        init_db()

    def test_database_schema(self):
        """Verify the database schema contains all component marks columns."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(marks)")
        columns = [c[1] for c in cursor.fetchall()]
        self.assertIn('oral_marks', columns)
        self.assertIn('written_marks', columns)
        self.assertIn('ct_marks', columns)
        
        conn.close()

    def test_grading_helpers(self):
        """Test the grade mapping algorithms."""
        self.assertEqual(calculate_grade(95), 'AA')
        self.assertEqual(calculate_grade(85), 'A+')
        self.assertEqual(calculate_grade(65), 'A')
        self.assertEqual(calculate_grade(50), 'B+')
        self.assertEqual(calculate_grade(38), 'B')
        self.assertEqual(calculate_grade(28), 'C')
        self.assertEqual(calculate_grade(20), 'D')
        self.assertEqual(calculate_grade('AB'), 'D')
        
        self.assertEqual(calculate_overall_grade(95), 'AA')
        self.assertEqual(calculate_overall_grade(85), 'A+')

    def test_save_and_render_component_marks(self):
        """Test saving components for a student and verifying marksheet calculations."""
        conn = get_db_connection()
        
        # 1. Create a dummy student user
        conn.execute("INSERT OR IGNORE INTO users (id, username, password, role, security_key, branch) VALUES (999, 'teststudent', 'pass', 'student', 'key', 'bhogram')")
        conn.execute("INSERT OR REPLACE INTO student_info (user_id, branch, class, roll_number, full_name, section) VALUES (999, 'bhogram', 'One', '12', 'Test Student Name', 'A')")
        
        # Ensure subjects are seeded
        from app import seed_default_subjects
        seed_default_subjects(conn)
        
        conn.commit()
        conn.close()

        with self.client as c:
            # Login as Headmaster Admin
            with c.session_transaction() as sess:
                sess['user'] = 'headmaster'
                sess['role'] = 'admin'
                sess['branch'] = None # Admin does not have branch restrictions

            # 2. Save 1st Unit marks (Oral: 8, Written: 32 -> Tot 40)
            response1 = c.post('/admin/save-bulk-marks', data={
                'class': 'One',
                'branch': 'bhogram',
                'term': '1st Unit',
                'full_marks': '50',
                'oral_marks_999_English': '8',
                'written_marks_999_English': '32',
                'marks_999_Art': '45', # Art is entered as marks_ directly
            })
            if response1.status_code != 302:
                print("Response content:", response1.data.decode('utf-8'))
            with c.session_transaction() as sess:
                print("Flashed messages 1:", sess.get('_flashes'))
            self.assertEqual(response1.status_code, 302)

            # 3. Save Final Exam marks (Oral: 15, Written: 55, CT: 8 -> Tot 78)
            response2 = c.post('/admin/save-bulk-marks', data={
                'class': 'One',
                'branch': 'bhogram',
                'term': 'Final Exam',
                'full_marks': '100',
                'oral_marks_999_English': '15',
                'written_marks_999_English': '55',
                'ct_marks_999_English': '8',
                'marks_999_Art': '85',
                'marks_999_Physical_Education': '18', # Additional subject
            })
            if response2.status_code != 302:
                print("Response 2 content:", response2.data.decode('utf-8'))
            with c.session_transaction() as sess:
                print("Flashed messages 2:", sess.get('_flashes'))
            self.assertEqual(response2.status_code, 302)

            # 4. View student marksheet and verify context data
            response_view = c.get('/admin/marksheet?student_id=999')
            self.assertEqual(response_view.status_code, 200)
            
            # Let's inspect the DB to make sure calculations are correct
            conn = get_db_connection()
            all_marks = conn.execute("SELECT * FROM marks WHERE student_id = 999").fetchall()
            for row in all_marks:
                print("DB ROW:", dict(row))
            eng_1st = conn.execute("SELECT obtained_marks, oral_marks, written_marks FROM marks WHERE student_id = 999 AND subject_name = 'English' AND term_name = '1st Unit'").fetchone()
            eng_final = conn.execute("SELECT obtained_marks, oral_marks, written_marks, ct_marks FROM marks WHERE student_id = 999 AND subject_name = 'English' AND term_name = 'Final Exam'").fetchone()
            art_final = conn.execute("SELECT obtained_marks FROM marks WHERE student_id = 999 AND subject_name = 'Art' AND term_name = 'Final Exam'").fetchone()
            pe_final = conn.execute("SELECT obtained_marks FROM marks WHERE student_id = 999 AND subject_name = 'Physical Education' AND term_name = 'Final Exam'").fetchone()
            print("PE_FINAL query result:", pe_final)
            conn.close()
            
            self.assertIsNotNone(eng_1st)
            self.assertEqual(eng_1st['oral_marks'], 8.0)
            self.assertEqual(eng_1st['written_marks'], 32.0)
            self.assertEqual(eng_1st['obtained_marks'], 40.0)
            
            self.assertIsNotNone(eng_final)
            self.assertEqual(eng_final['oral_marks'], 15.0)
            self.assertEqual(eng_final['written_marks'], 55.0)
            self.assertEqual(eng_final['ct_marks'], 8.0)
            self.assertEqual(eng_final['obtained_marks'], 78.0)
            
            self.assertIsNotNone(art_final)
            self.assertEqual(art_final['obtained_marks'], 85.0)
            
            self.assertIsNotNone(pe_final)
            self.assertEqual(pe_final['obtained_marks'], 18.0)

            # Assert output HTML rendering contains A4 design marksheet components
            html = response_view.data.decode('utf-8')
            self.assertIn('AL - HIDAYET MISSION', html)
            self.assertIn('BHOGRAM BRANCH', html)
            self.assertIn('1ST UNIT', html)
            self.assertIn('2ND UNIT', html)
            self.assertIn('FINAL EXAM', html)
            self.assertIn('ART', html)
            self.assertIn('ADDITIONAL SUBJECTS', html)
            self.assertIn('RESULT ABSTRACT', html)
            self.assertIn('PASSED', html)

if __name__ == '__main__':
    unittest.main()
