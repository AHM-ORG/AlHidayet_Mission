import sys
import os
import unittest
import sqlite3

# Insert project path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db_connection, init_db

class TestFeeDocuments(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'testing_secret_key'
        self.client = app.test_client()
        
        # Initialize/Verify database migration
        init_db()

    def test_database_schema(self):
        """Verify the database schema contains all required fields and tables."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check classes table columns
        cursor.execute("PRAGMA table_info(classes)")
        columns = [c[1] for c in cursor.fetchall()]
        self.assertIn('admission_fee', columns)
        self.assertIn('monthly_fee', columns)
        
        # Check registration_documents table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registration_documents'")
        table_exists = cursor.fetchone()
        self.assertIsNotNone(table_exists)
        
        # Check visitor_reviews table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='visitor_reviews'")
        table_exists = cursor.fetchone()
        self.assertIsNotNone(table_exists)
        
        conn.close()

    def test_class_fee_update_endpoint(self):
        """Test update-class-fees POST endpoint."""
        with self.client as c:
            # Login as Headmaster Admin
            with c.session_transaction() as sess:
                sess['user'] = 'headmaster'
                sess['role'] = 'admin'
            
            # Update Class 1 (Nursery or whatever exists)
            response = c.post('/admin/update-class-fees', data={
                'class_id': 1,
                'admission_fee': 550.00,
                'monthly_fee': 110.00
            }, headers={'X-Requested-With': 'XMLHttpRequest'})
            
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data['status'], 'success')
            
            # Verify in DB
            conn = get_db_connection()
            cls_row = conn.execute("SELECT admission_fee, monthly_fee FROM classes WHERE id = 1").fetchone()
            conn.close()
            self.assertEqual(cls_row['admission_fee'], 550.00)
            self.assertEqual(cls_row['monthly_fee'], 110.00)

    def test_homepage_rendering(self):
        """Test that the homepage includes the fees chart and registration documents."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check Fees Chart title
        self.assertIn('Class Fee Structure', html)
        self.assertIn('Admission Fee', html)
        self.assertIn('Monthly Fee', html)
        
        # Check School Documents title
        self.assertIn('School Registration Documents', html)
        self.assertIn('Society Registration Certificate', html)
        self.assertIn('School Affiliation Board Certificate', html)

if __name__ == '__main__':
    unittest.main()
