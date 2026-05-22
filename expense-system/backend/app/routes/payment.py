"""付款处理中心路由"""
from datetime import datetime
from flask import Blueprint, request, jsonify

from ..models import db, ExpenseClaim, Loan, AssetPurchase
from ..auth import login_required

payment_bp = Blueprint('payment', __name__)


@payment_bp.route('/api/payment_center', methods=['GET'])
@login_required
def get_payment_center():
    status_filter = request.args.get('status')
    if status_filter not in ('unpaid', 'paid'):
        return jsonify({'error': '缺少 status 参数'}), 400

    if status_filter == 'unpaid':
        claims = ExpenseClaim.query.filter_by(status='approved', payment_date=None).all()
        loans = Loan.query.filter_by(status='approved', payment_date=None).all()
        purchases = AssetPurchase.query.filter_by(status='approved', payment_date=None).all()
    else:
        claims = ExpenseClaim.query.filter(ExpenseClaim.payment_date.isnot(None)).all()
        loans = Loan.query.filter(Loan.payment_date.isnot(None)).all()
        purchases = AssetPurchase.query.filter(AssetPurchase.payment_date.isnot(None)).all()

    result = []
    for c in claims:
        total_offset = sum(ld.amount for ld in c.loan_details)
        result.append({
            'id': c.id, 'type': 'reimbursement', 'type_name': '报销',
            'document_number': c.document_number,
            'applicant': c.user.name,
            'apply_date': c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
            'payee_name': c.payee_account.account_name if c.payee_account else '',
            'payee_account': c.payee_account.account_number if c.payee_account else '',
            'bank_name': c.payee_account.bank_short_name if c.payee_account else '',
            'amount': c.amount - total_offset,
            'legal_person': c.legal_person.name if c.legal_person else '',
            'payment_date': c.payment_date.strftime('%Y-%m-%d') if c.payment_date else None,
        })
    for l in loans:
        result.append({
            'id': l.id, 'type': 'loan', 'type_name': '借款',
            'document_number': l.document_number,
            'applicant': l.user.name,
            'apply_date': l.created_at.strftime('%Y-%m-%d') if l.created_at else '',
            'payee_name': l.payee_account.account_name if l.payee_account else '',
            'payee_account': l.payee_account.account_number if l.payee_account else '',
            'bank_name': l.payee_account.bank_short_name if l.payee_account else '',
            'amount': l.amount,
            'legal_person': l.legal_person.name if l.legal_person else '',
            'payment_date': l.payment_date.strftime('%Y-%m-%d') if l.payment_date else None,
        })
    for p in purchases:
        total_amount = sum(item.requested_amount for item in p.items)
        result.append({
            'id': p.id, 'type': 'purchase', 'type_name': '采购申请',
            'document_number': p.document_number,
            'applicant': p.user.name,
            'apply_date': p.created_at.strftime('%Y-%m-%d') if p.created_at else '',
            'payee_name': '', 'payee_account': '', 'bank_name': '',
            'amount': total_amount,
            'legal_person': p.legal_person.name if p.legal_person else '',
            'payment_date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else None,
        })

    result.sort(key=lambda x: x['apply_date'], reverse=True)
    return jsonify(result)


@payment_bp.route('/api/payment_register', methods=['POST'])
@login_required
def payment_register():
    data = request.json
    items = data.get('items', [])
    payment_date_str = data.get('payment_date')

    if not items:
        return jsonify({'error': '请选择要登记的单据'}), 400

    try:
        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d') if payment_date_str else datetime.now()
    except ValueError:
        return jsonify({'error': '日期格式错误'}), 400

    success_count = 0
    for item in items:
        type_ = item.get('type')
        id_ = item.get('id')
        model_map = {'reimbursement': ExpenseClaim, 'loan': Loan, 'purchase': AssetPurchase}
        model_cls = model_map.get(type_)
        if not model_cls:
            continue
        record = model_cls.query.get(id_)
        if record and record.status == 'approved' and record.payment_date is None:
            record.payment_date = payment_date
            success_count += 1

    db.session.commit()
    return jsonify({'message': f'成功登记 {success_count} 笔付款'}), 200
