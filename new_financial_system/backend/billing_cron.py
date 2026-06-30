import os
import sys
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from flask import Flask
from models import db, Student, LedgerTransaction, TransactionType, AidType

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financial_audit.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def run_monthly_billing():
    app = create_app()
    with app.app_context():
        print(f"[{datetime.utcnow().isoformat()}] Starting automated monthly billing...")
        
        students = Student.query.all()
        for student in students:
            monthly_fee = student.class_fee.monthly_fee_amount
            
            # 1. Generate the full fee transaction
            fee_tx = LedgerTransaction(
                student_id=student.id,
                transaction_type=TransactionType.fee_generation,
                amount=monthly_fee,  # Dues are positive
                description=f"Monthly Fee for {datetime.utcnow().strftime('%B %Y')}"
            )
            db.session.add(fee_tx)
            
            # 2. Check for active financial aid
            aid = student.financial_aid
            if aid and aid.is_active:
                deduction = 0.0
                if aid.aid_type == AidType.percentage:
                    deduction = monthly_fee * (aid.amount / 100.0)
                elif aid.aid_type == AidType.flat:
                    deduction = aid.amount
                
                if deduction > 0:
                    aid_tx = LedgerTransaction(
                        student_id=student.id,
                        transaction_type=TransactionType.aid_deduction,
                        amount=-deduction,  # Reductions are negative
                        description=f"Financial Aid Deduction ({aid.aid_type.value})"
                    )
                    db.session.add(aid_tx)
                    
        db.session.commit()
        print(f"[{datetime.utcnow().isoformat()}] Monthly billing completed successfully.")

if __name__ == '__main__':
    # For testing purposes, you can uncomment to run immediately:
    # run_monthly_billing()
    
    scheduler = BlockingScheduler()
    # Runs on the 1st day of every month at midnight
    scheduler.add_job(run_monthly_billing, 'cron', day=1, hour=0, minute=0)
    
    print("Starting billing cron scheduler. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
