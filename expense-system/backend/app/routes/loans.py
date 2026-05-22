"""借款单路由"""
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import logging

from ..models import db, Loan, LoanApprovalRecord, User
from ..auth import login_required, role_required
from ..services.approval import generate_number, get_approval_flow, validate_approval, process_approval

loans_bp = Blueprint('loans', __name__)
logger = logging.getLogger(__name__)


def _serialize_loan(loan, with_approval_role=False):
    """序列化借款单"""
    flow = get_approval_flow(loan.user)
    steps = flow.get_steps() if flow else []
    required_role = None
    if steps and 1 <= loan.current_step <= len(steps):
        required_role = steps[loan.current_step - 1].get('role_code')

    return {
        'id': loan.id, 'document_number': loan.document_number,
        'user_id': loan.user_id, 'user_name': loan.user.name,
        'user_department': loan.user.department.name if loan.user.department else None,
        'department_id': loan.department_id,
        'legal_person_id': loan.legal_person_id,
        'legal_person_name': loan.legal_person.name if loan.legal_person else None,
        'currency_id': loan.currency_id,
        'currency_code': loan.currency.code if loan.currency else 'CNY',
        'currency_symbol': loan.currency.symbol if loan.currency else '¥',
        'payee_account_id': loan.payee_account_id,
        'payee_account_name': loan.payee_account.account_name if loan.payee_account else None,
        'payee_account_number': loan.payee_account.account_number if loan.payee_account else None,
        'amount': loan.amount, 'purpose': loan.purpose, 'category': loan.category,
        'status': loan.status, 'current_step': loan.current_step,
        'created_at': loan.created_at.isoformat() if loan.created_at else None,
        'updated_at': loan.updated_at.isoformat() if loan.updated_at else None,
        'is_draft': loan.is_draft, 'loan_items': loan.loan_items_json or '[]',
        'approvals': [{'step': a.step, 'action': a.action, 'comment': a.comment,
                       'approver_name': a.approver.name if a.approver else '',
                       'approved_at': a.approved_at.isoformat() if a.approved_at else None}
                      for a in loan.approvals],
        'required_role': required_role if with_approval_role else None,
    }


@loans_bp.route('/api/next_loan_number', methods=['GET'])
@login_required
def get_next_loan_number():
    return jsonify({'document_number': generate_number('JK', Loan)})


@loans_bp.route('/api/loans', methods=['GET'])
@login_required
def get_loans():
    view_mode = request.args.get('view_mode', 'all')
    current_user = request.user

    if view_mode == 'my':
        loans = Loan.query.filter_by(user_id=current_user.id).order_by(Loan.created_at.desc()).all()
        return jsonify([_serialize_loan(l) for l in loans])
    elif view_mode == 'pending_approval':
        all_pending = Loan.query.filter_by(status='pending').all()
        pending = []
        for l in all_pending:
            if l.is_draft or l.user_id == current_user.id:
                continue
            flow = get_approval_flow(l.user)
            if not flow:
                continue
            steps = flow.get_steps()
            if l.current_step <= len(steps):
                if current_user.role == steps[l.current_step - 1].get('role_code'):
                    pending.append(l)
        pending.sort(key=lambda x: x.created_at, reverse=True)
        return jsonify([_serialize_loan(l, with_approval_role=True) for l in pending])

    query = Loan.query
    if request.args.get('user_id'):
        query = query.filter_by(user_id=request.args['user_id'])
    if request.args.get('status'):
        query = query.filter_by(status=request.args['status'])
    loans = query.order_by(Loan.created_at.desc()).all()
    return jsonify([_serialize_loan(l) for l in loans])


@loans_bp.route('/api/loans/<int:loan_id>', methods=['GET'])
@login_required
def get_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    return jsonify(_serialize_loan(loan, with_approval_role=True))


@loans_bp.route('/api/loans', methods=['POST'])
@login_required
def create_loan():
    if request.is_json:
        data = request.json
    else:
        data = request.form
    is_draft = str(data.get('is_draft', '')).lower() == 'true' if isinstance(data.get('is_draft'), str) else bool(data.get('is_draft', False))

    doc_num = generate_number('JK', Loan)
    loan = Loan(
        document_number=doc_num,
        user_id=int(data['user_id']),
        department_id=int(data['department_id']) if data.get('department_id') else None,
        legal_person_id=int(data['legal_person_id']) if data.get('legal_person_id') else None,
        currency_id=int(data.get('currency_id') or 1),
        payee_account_id=int(data['payee_account_id']) if data.get('payee_account_id') else None,
        amount=float(data['amount']),
        purpose=data.get('purpose', ''),
        category=data.get('category', '其他'),
        status='pending', current_step=1, is_draft=is_draft,
        loan_items_json=data.get('loan_items', '[]'),
    )
    db.session.add(loan)
    db.session.commit()
    return jsonify({'id': loan.id, 'document_number': doc_num, 'message': '借款申请创建成功'}), 201


@loans_bp.route('/api/loans/draft/<int:loan_id>', methods=['PUT'])
@login_required
def update_loan_draft(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if not loan.is_draft or loan.user_id != request.user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    for field in ('amount', 'purpose', 'category', 'legal_person_id', 'currency_id',
                  'payee_account_id', 'department_id', 'loan_items'):
        if field in data:
            setattr(loan, field, data[field])
    if 'amount' in data:
        loan.amount = float(data['amount'])
    loan.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})


@loans_bp.route('/api/loans/<int:loan_id>', methods=['DELETE'])
@login_required
def delete_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    current_user = request.user
    can_delete = (current_user.role == 'admin') or \
                 (loan.user_id == current_user.id and loan.status == 'pending' and loan.current_step == 1 and not loan.approvals)
    if not can_delete:
        return jsonify({'error': '无权删除此借款单'}), 403
    db.session.delete(loan)
    db.session.commit()
    return jsonify({'message': '借款申请删除成功'})


@loans_bp.route('/api/user_available_loans', methods=['GET'])
@login_required
def get_user_available_loans():
    user = request.user
    loans = Loan.query.filter_by(user_id=user.id, status='approved').all()
    result = []
    for loan in loans:
        remaining = loan.amount - (loan.total_reimbursed or 0)
        if remaining > 0:
            result.append({
                'id': loan.id, 'document_number': loan.document_number,
                'total_amount': loan.amount, 'total_reimbursed': loan.total_reimbursed or 0,
                'remaining': remaining, 'purpose': loan.purpose, 'category': loan.category,
            })
    return jsonify(result)


# ── 借款审批 ──

@loans_bp.route('/api/loan_approvals/<int:loan_id>', methods=['POST'])
@login_required
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    approver = request.user

    ok, err = validate_approval(loan, approver)
    if not ok:
        return jsonify({'error': err}), 400 if '步骤' in err or '流程' in err else 403

    data = request.get_json() if request.is_json else request.form
    action, comment = data.get('action'), data.get('comment', '')
    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400
    if action not in ('approve', 'reject'):
        return jsonify({'error': '无效的审批动作'}), 400

    record = LoanApprovalRecord(
        loan_id=loan_id, approver_id=approver.id, step=loan.current_step,
        action=action, comment=comment, approved_at=datetime.now())
    db.session.add(record)
    process_approval(loan, action)
    db.session.commit()
    return jsonify({'message': '审批完成', 'status': loan.status, 'current_step': loan.current_step})
