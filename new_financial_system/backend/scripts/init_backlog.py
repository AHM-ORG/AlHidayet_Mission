import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from models import db, Student, ClassFeeStructure, LedgerTransaction, TransactionType

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../financial_audit.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def init_backlog():
    app = create_app()
    with app.app_context():
        # Ensure tables exist for standalone testing
        db.create_all()
        
        students = Student.query.all()
        print(f"Found {len(students)} active students. Initializing 7-month backlog...")
        
        for student in students:
            # Check if an init transaction already exists to avoid duplicates
            existing_init = LedgerTransaction.query.filter_by(
                student_id=student.id,
                transaction_type=TransactionType.system_init
            ).first()
            
            if existing_init:
                print(f"Skipping student {student.id}, backlog already initialized.")
                continue

            monthly_fee = student.class_fee.monthly_fee_amount
            backlog_amount = monthly_fee * 7
            
            transaction = LedgerTransaction(
                student_id=student.id,
                transaction_type=TransactionType.system_init,
                amount=backlog_amount,
                description='Previous Dues (Months 1-7)',
                date_created=datetime.utcnow()
            )
            
            db.session.add(transaction)
            
        db.session.commit()
        print("Backlog initialization complete.")

if __name__ == '__main__':
    init_backlog()
