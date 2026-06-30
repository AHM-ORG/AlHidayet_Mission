import os
import sys

# Ensure we're in the correct directory to import app
sys.path.append(os.getcwd())

from app import app, get_db_connection

def reset_all_dues_and_custom_fees():
    with app.app_context():
        conn = get_db_connection()
        
        try:
            # 1. Reset all custom fees and set previous dues to 0 for all students
            conn.execute('''
                UPDATE student_info
                SET is_custom_fee = 0,
                    custom_monthly_fee = 0,
                    custom_admission_fee = 0,
                    custom_readmission_fee = 0,
                    prev_dues = 0,
                    remaining_fee = 0
            ''')
            
            # 2. Clear all unpaid ledger transactions so they don't count towards dues
            conn.execute('''
                DELETE FROM ledger_transactions
                WHERE is_paid = 0
            ''')
            
            # 3. Reset billing cycles to prevent immediate recalculation of past dues
            conn.execute('''
                UPDATE student_info
                SET billing_cycle_months = 0,
                    billing_cycle_years = 0
            ''')
            
            conn.commit()
            print("Success! All student dues and custom fees have been reset to 0.")
            print("Please refresh the Audit Report page.")
            
        except Exception as e:
            print(f"Error occurred: {e}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == '__main__':
    reset_all_dues_and_custom_fees()
