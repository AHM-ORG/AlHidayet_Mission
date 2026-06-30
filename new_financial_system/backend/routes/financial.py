from flask import Blueprint, request, jsonify
from ..models import db, ClassLevel, Student, FinancialAid, LedgerTransaction, TransactionType

financial_bp = Blueprint('financial', __name__, url_prefix='/api')

def update_student_balance(student):
    """Recalculates the student's current balance from ledger transactions."""
    total = db.session.query(db.func.sum(LedgerTransaction.amount)).filter_by(student_id=student.id).scalar()
    student.current_balance = total or 0.0
    db.session.commit()

def add_ledger_transaction(student_id, trans_type, amount, reason):
    transaction = LedgerTransaction(
        student_id=student_id,
        transaction_type=trans_type,
        amount=amount,
        reason=reason
    )
    db.session.add(transaction)
    db.session.commit()
    
    student = Student.query.get(student_id)
    if student:
        update_student_balance(student)
    return transaction

@financial_bp.route('/class/update_fees', methods=['POST'])
def update_class_fees():
    data = request.json
    class_id = data.get('class_id')
    monthly_fee = data.get('monthly_fee_amount')
    readmission_fee = data.get('readmission_fee_amount')
    
    if not class_id:
        return jsonify({'error': 'class_id is required'}), 400
        
    class_level = ClassLevel.query.get(class_id)
    if not class_level:
        return jsonify({'error': 'Class not found'}), 404
        
    if monthly_fee is not None:
        class_level.monthly_fee_amount = float(monthly_fee)
    if readmission_fee is not None:
        class_level.readmission_fee_amount = float(readmission_fee)
        
    db.session.commit()
    return jsonify({'message': 'Fees updated successfully'}), 200

@financial_bp.route('/fees/generate_monthly', methods=['POST'])
def generate_monthly_fees():
    data = request.json
    class_id = data.get('class_id')
    
    if not class_id:
        return jsonify({'error': 'class_id is required'}), 400
        
    class_level = ClassLevel.query.get(class_id)
    if not class_level:
        return jsonify({'error': 'Class not found'}), 404
        
    monthly_fee = class_level.monthly_fee_amount
    students = Student.query.filter_by(class_id=class_id).all()
    
    generated_count = 0
    for student in students:
        # Add monthly fee
        add_ledger_transaction(student.id, TransactionType.monthly_fee, monthly_fee, "Monthly Fee")
        generated_count += 1
        
        # Check for active financial aid
        aid = FinancialAid.query.filter_by(student_id=student.id, is_active=True).first()
        if aid and aid.reduction_amount > 0:
            add_ledger_transaction(student.id, TransactionType.aid_discount, -aid.reduction_amount, aid.reason or "Financial Aid Discount")
            
    return jsonify({'message': f'Monthly fees generated for {generated_count} students'}), 200

@financial_bp.route('/fees/add_previous_due', methods=['POST'])
def add_previous_due():
    data = request.json
    student_id = data.get('student_id')
    amount = data.get('amount')
    reason = data.get('reason', 'Before Website Launch Due')
    
    if not student_id or amount is None:
        return jsonify({'error': 'student_id and amount are required'}), 400
        
    add_ledger_transaction(student_id, TransactionType.previous_due, float(amount), reason)
    return jsonify({'message': 'Previous due added successfully'}), 200

@financial_bp.route('/fees/add_adhoc', methods=['POST'])
def add_adhoc_fee():
    data = request.json
    student_id = data.get('student_id')
    amount = data.get('amount')
    reason = data.get('reason')
    
    if not student_id or amount is None or not reason:
        return jsonify({'error': 'student_id, amount, and reason are required'}), 400
        
    add_ledger_transaction(student_id, TransactionType.adhoc_fee, float(amount), reason)
    return jsonify({'message': 'Adhoc fee added successfully'}), 200

@financial_bp.route('/fees/add_readmission', methods=['POST'])
def add_readmission_fee():
    data = request.json
    student_id = data.get('student_id')
    
    if not student_id:
        return jsonify({'error': 'student_id is required'}), 400
        
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'error': 'Student not found'}), 404
        
    class_level = student.class_level
    if not class_level:
        return jsonify({'error': 'Student not assigned to a valid class'}), 400
        
    amount = class_level.readmission_fee_amount
    add_ledger_transaction(student.id, TransactionType.readmission_fee, amount, "Readmission Fee")
    return jsonify({'message': 'Readmission fee added successfully'}), 200

@financial_bp.route('/aid/set', methods=['POST'])
def set_financial_aid():
    data = request.json
    student_id = data.get('student_id')
    reduction_amount = data.get('reduction_amount')
    reason = data.get('reason')
    is_active = data.get('is_active', True)
    
    if not student_id or reduction_amount is None:
        return jsonify({'error': 'student_id and reduction_amount are required'}), 400
        
    aid = FinancialAid.query.filter_by(student_id=student_id).first()
    if aid:
        aid.reduction_amount = float(reduction_amount)
        aid.reason = reason
        aid.is_active = bool(is_active)
    else:
        aid = FinancialAid(
            student_id=student_id,
            reduction_amount=float(reduction_amount),
            reason=reason,
            is_active=bool(is_active)
        )
        db.session.add(aid)
        
    db.session.commit()
    return jsonify({'message': 'Financial aid updated successfully'}), 200

@financial_bp.route('/ledger/<int:student_id>', methods=['GET'])
def get_ledger(student_id):
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'error': 'Student not found'}), 404
        
    transactions = LedgerTransaction.query.filter_by(student_id=student_id).order_by(LedgerTransaction.date_created.asc()).all()
    
    return jsonify({
        'student': {
            'id': student.id,
            'name': student.name,
            'current_balance': student.current_balance,
            'class': student.class_level.class_name if student.class_level else None
        },
        'transactions': [t.to_dict() for t in transactions]
    }), 200

@financial_bp.route('/audit/system', methods=['GET'])
def get_system_audit():
    # Return a flat array of all transactions with student and class info
    # Using a join for efficiency
    results = db.session.query(
        LedgerTransaction, 
        Student.name.label('student_name'), 
        ClassLevel.class_name
    ).join(Student, LedgerTransaction.student_id == Student.id)\
     .outerjoin(ClassLevel, Student.class_id == ClassLevel.id)\
     .order_by(LedgerTransaction.date_created.desc()).all()
     
    transactions = []
    for trans, student_name, class_name in results:
        t_dict = trans.to_dict()
        t_dict['student_name'] = student_name
        t_dict['class_name'] = class_name
        transactions.append(t_dict)
        
    return jsonify({'transactions': transactions}), 200
