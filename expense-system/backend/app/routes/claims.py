"""报销单路由"""
import json
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import logging

from ..models import (db, User, Department, ExpenseClaim, Receipt,
                      ApprovalRecord, Loan, LoanReimburseDetail)
from ..auth import login_required, role_required
from ..services.approval import generate_number, get_approval_flow, validate_approval, process_approval

claims_bp = Blueprint('claims', __name__)
logger = logging.getLogger(__name__)


# ── 工具函数：序列化单据 ──

def _serialize_claim(claim, with_approval_role=False):
    """将 ExpenseClaim 转为 dict"""
    dept_name = claim.user.department.name if claim.user.department else None
    flow = get_approval_flow(claim.user)
    steps = flow.get_steps() if flow else []
    required_role = None
    if steps and 1 <= claim.current_step <= len(steps):
        required_role = steps[claim.current_step - 1].get('role_code')

    return {
        'id': claim.id,
        'document_number': claim.document_number,
        'user_id': claim.user_id,
        'user_name': claim.user.name,
        'user_department': dept_name,
        'department_id': claim.department_id,
        'legal_person_id': claim.legal_person_id,
        'legal_person_name': claim.legal_person.name if claim.legal_person else None,
        'currency_id': claim.currency_id,
        'currency_code': claim.currency.code if claim.currency else 'CNY',
        'currency_symbol': claim.currency.symbol if claim.currency else '¥',
        'payee_account_id': claim.payee_account_id,
        'payee_account_name': claim.payee_account.account_name if claim.payee_account else None,
        'payee_account_number': claim.payee_account.account_number if claim.payee_account else None,
        'amount': claim.amount,
        'description': claim.description,
        'category': claim.category,
        'status': claim.status,
        'current_step': claim.current_step,
        'created_at': claim.created_at.isoformat() if claim.created_at else None,
        'updated_at': claim.updated_at.isoformat() if claim.updated_at else None,
        'is_draft': claim.is_draft,
        'receipts': [{'id': r.id, 'filename': r.filename, 'original_name': r.original_name}
                      for r in claim.receipts],
        'approvals': [{
            'step': a.step, 'action': a.action, 'comment': a.comment,
            'approver_name': a.approver.name if a.approver else '',
            'approved_at': a.approved_at.isoformat() if a.approved_at else None
        } for a in claim.approvals],
        'required_role': required_role if with_approval_role else None,
        'expense_items': claim.expense_items_json,
    }


@claims_bp.route('/api/next_document_number', methods=['GET'])
@login_required
def get_next_document_number():
    return jsonify({'document_number': generate_number('BXZF', ExpenseClaim)})


@claims_bp.route('/api/claims', methods=['GET'])
@login_required
def get_claims():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    view_mode = request.args.get('view_mode', 'all')
    current_user = request.user

    if view_mode == 'my':
        query = ExpenseClaim.query.filter_by(user_id=current_user.id)
    elif view_mode == 'pending_approval':
        all_pending = ExpenseClaim.query.filter_by(status='pending').all()
        pending = []
        for c in all_pending:
            if c.is_draft or c.user_id == current_user.id:
                continue
            flow = get_approval_flow(c.user)
            if not flow:
                continue
            steps = flow.get_steps()
            if c.current_step <= len(steps):
                needed_role = steps[c.current_step - 1]['role_code']
                if current_user.role == needed_role:
                    pending.append(c)
        pending.sort(key=lambda x: x.created_at, reverse=True)
        return jsonify([_serialize_claim(c, with_approval_role=True) for c in pending])
    else:
        query = ExpenseClaim.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)

    claims = query.order_by(ExpenseClaim.created_at.desc()).all()
    return jsonify([_serialize_claim(c) for c in claims])


@claims_bp.route('/api/claims/<int:claim_id>', methods=['GET'])
@login_required
def get_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    result = _serialize_claim(claim, with_approval_role=True)

    # 借款冲账明细
    loan_details = []
    total_offset = 0.0
    for ld in claim.loan_details:
        loan = Loan.query.get(ld.loan_id)
        if loan:
            remaining_before = loan.amount - (loan.total_reimbursed or 0)
            loan_details.append({
                'document_number': loan.document_number,
                'offset_amount': ld.amount,
                'remaining_after_offset': remaining_before - ld.amount,
            })
            total_offset += ld.amount
    result['loan_details'] = loan_details
    result['total_offset'] = total_offset
    result['actual_payee_amount'] = claim.amount - total_offset
    return jsonify(result)


@claims_bp.route('/api/claims', methods=['POST'])
@login_required
def create_claim():
    if request.is_json:
        json_data = request.json
        data = json_data
        files = []
        loan_details = json_data.get('loan_details', [])
    else:
        data = request.form
        files = request.files.getlist('receipts') if 'receipts' in request.files else []
        loan_details = json.loads(data.get('loan_details', '[]'))

    is_draft = str(data.get('is_draft', '')).lower() == 'true' if isinstance(data.get('is_draft'), str) else bool(data.get('is_draft', False))

    doc_num = generate_number('BXZF', ExpenseClaim)
    claim = ExpenseClaim(
        document_number=doc_num,
        user_id=int(data.get('user_id')),
        department_id=int(data['department_id']) if data.get('department_id') else None,
        legal_person_id=int(data['legal_person_id']) if data.get('legal_person_id') else None,
        currency_id=int(data.get('currency_id') or 1),
        payee_account_id=int(data['payee_account_id']) if data.get('payee_account_id') else None,
        amount=float(data['amount']),
        description=data.get('description', ''),
        category=data.get('category', '其他'),
        status='pending', current_step=1, is_draft=is_draft,
        expense_items_json=data.get('expense_items', '[]'),
    )
    db.session.add(claim)
    db.session.flush()

    total_offset = 0.0
    for d in loan_details:
        amount = float(d['amount'])
        total_offset += amount
        db.session.add(LoanReimburseDetail(claim_id=claim.id, loan_id=d['loan_id'], amount=amount))

    if total_offset > claim.amount:
        db.session.rollback()
        return jsonify({'error': '冲账总金额不能大于报销金额'}), 400

    for f in files:
        if f.filename:
            filename = f"{claim.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{f.filename}"
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            db.session.add(Receipt(claim_id=claim.id, filename=filename, original_name=f.filename))

    db.session.commit()
    return jsonify({'id': claim.id, 'document_number': doc_num, 'message': '报销单创建成功'}), 201


@claims_bp.route('/api/claims/<int:claim_id>', methods=['PUT'])
@login_required
def update_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    data = request.json

    can_update = (claim.status == 'rejected' and claim.user_id == current_user.id) or \
                 (claim.user_id == current_user.id and claim.status == 'pending' and claim.current_step == 1 and not claim.approvals)
    if not can_update:
        return jsonify({'error': '只有申请人可以在特定条件下修改报销单'}), 403

    for field in ('amount', 'description', 'category', 'legal_person_id', 'currency_id', 'payee_account_id', 'department_id'):
        if field in data:
            setattr(claim, field, int(data[field]) if field.endswith('_id') and data[field] else data[field])
    if 'amount' in data:
        claim.amount = float(data['amount'])

    if claim.status == 'rejected':
        claim.status = 'pending'
    claim.updated_at = datetime.now()
    db.session.commit()
    msg = '报销单已重新提交' if claim.status == 'pending' else '报销单更新成功'
    return jsonify({'message': msg})


@claims_bp.route('/api/claims/draft/<int:claim_id>', methods=['PUT'])
@login_required
def update_claim_draft(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    if not claim.is_draft or claim.user_id != current_user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    for field in ('amount', 'description', 'category', 'legal_person_id', 'currency_id', 'payee_account_id', 'department_id', 'expense_items'):
        if field in data:
            setattr(claim, field, data[field] if field != 'expense_items' else json.dumps(data[field]) if not isinstance(data[field], str) else data[field])
    if 'amount' in data:
        claim.amount = float(data['amount'])
    claim.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})


@claims_bp.route('/api/claims/<int:claim_id>', methods=['DELETE'])
@login_required
def delete_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    can_delete = (current_user.role == 'admin') or \
                 (claim.user_id == current_user.id and claim.status == 'pending' and claim.current_step == 1 and not claim.approvals)
    if not can_delete:
        return jsonify({'error': '无权删除此报销单'}), 403

    for r in claim.receipts:
        fp = os.path.join(current_app.config['UPLOAD_FOLDER'], r.filename)
        if os.path.exists(fp):
            os.remove(fp)
    db.session.delete(claim)
    db.session.commit()
    return jsonify({'message': '报销单删除成功'})


# ── 审批 ──

@claims_bp.route('/api/approvals/<int:claim_id>', methods=['POST'])
@login_required
def approve_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    approver = request.user

    ok, err = validate_approval(claim, approver)
    if not ok:
        return jsonify({'error': err}), 400 if '步骤' in err or '流程' in err else 403

    data = request.get_json() if request.is_json else request.form
    action, comment = data.get('action'), data.get('comment', '')
    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400
    if action not in ('approve', 'reject'):
        return jsonify({'error': '无效的审批动作'}), 400

    record = ApprovalRecord(
        claim_id=claim_id, approver_id=approver.id, step=claim.current_step,
        action=action, comment=comment, approved_at=datetime.now())
    db.session.add(record)
    process_approval(claim, action)

    # 最终审批通过时更新借款核销金额
    if action == 'approve' and claim.status == 'approved':
        for detail in claim.loan_details:
            loan = Loan.query.get(detail.loan_id)
            if loan:
                loan.total_reimbursed = (loan.total_reimbursed or 0) + detail.amount

    db.session.commit()
    return jsonify({'message': '审批完成', 'status': claim.status, 'current_step': claim.current_step})


# ── 附件删除 ──

@claims_bp.route('/api/receipts/<int:receipt_id>', methods=['DELETE'])
@login_required
def delete_receipt(receipt_id):
    receipt = Receipt.query.get_or_404(receipt_id)
    claim = receipt.claim
    if not claim.is_draft or (claim.user_id != request.user.id and request.user.role != 'admin'):
        return jsonify({'error': '无权删除此附件'}), 403
    fp = os.path.join(current_app.config['UPLOAD_FOLDER'], receipt.filename)
    if os.path.exists(fp):
        os.remove(fp)
    db.session.delete(receipt)
    db.session.commit()
    return jsonify({'message': '附件删除成功'})
