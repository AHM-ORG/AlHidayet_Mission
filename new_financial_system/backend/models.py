from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import enum

db = SQLAlchemy()

class TransactionType(enum.Enum):
    previous_due = 'previous_due'
    monthly_fee = 'monthly_fee'
    readmission_fee = 'readmission_fee'
    adhoc_fee = 'adhoc_fee'
    payment = 'payment'
    aid_discount = 'aid_discount'

class ClassLevel(db.Model):
    __tablename__ = 'class_level'
    
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(100), nullable=False, unique=True)
    monthly_fee_amount = db.Column(db.Float, default=0.0)
    readmission_fee_amount = db.Column(db.Float, default=0.0)
    
    students = db.relationship('Student', backref='class_level', lazy=True)

class Student(db.Model):
    __tablename__ = 'student'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class_level.id'), nullable=False)
    current_balance = db.Column(db.Float, default=0.0)
    
    financial_aids = db.relationship('FinancialAid', backref='student', lazy=True)
    ledger_transactions = db.relationship('LedgerTransaction', backref='student', lazy=True)

class FinancialAid(db.Model):
    __tablename__ = 'financial_aid'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    reduction_amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

class LedgerTransaction(db.Model):
    __tablename__ = 'ledger_transaction'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    transaction_type = db.Column(db.Enum(TransactionType), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # Positive = due/fee, Negative = payment/aid
    reason = db.Column(db.Text, nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'transaction_type': self.transaction_type.value,
            'amount': self.amount,
            'reason': self.reason,
            'date_created': self.date_created.isoformat()
        }
