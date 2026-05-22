"""资产采购申请路由"""
import json
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

from ..models import (db, AssetPurchase, AssetPurchaseContract,
                      AssetPurchaseItem, AssetPurchaseAttachment,
                      AssetPurchaseApprovalRecord)
from ..auth import login_required, role_required
from ..services.approval import generate_number, get_approval_flow, validate_approval, process_approval

purchases_bp = Blueprint('purchases', __name__)


def _serialize_purchase(purchase, with_approval_role=False):
    """序列化采购单"""
    flow = get_approval_flow(purchase.user)
    steps = flow.get_steps() if flow else []
    required_role = None
    if steps and 1 <= purchase.current_step <= len(steps):
        required_role = steps[purchase.current_step - 1].get('role_code')

    contracts = [{'id': c.id, 'contract_number': c.contract_number,
                  'contract_name': c.contract_name, 'supplier_name': c.supplier_name}
                 for c in purchase.contracts]
    items = [{
        'id': i.id, 'payment_unit': i.payment_unit, 'purchase_type': i.purchase_type,
        'item_name': i.item_name, 'quantity': i.quantity,
        'contract_total_amount': i.contract_total_amount,
        'requested_amount': i.requested_amount,
    } for i in purchase.items]
    attachments = [{'id': a.id, 'filename': a.filename, 'original_name': a.original_name}
                   for a in purchase.attachments]
    approvals = [{
        'step': a.step, 'action': a.action, 'comment': a.comment,
        'approver_name': a.approver.name if a.approver else '',
        'approved_at': a.approved_at.isoformat() if a.approved_at else None,
    } for a in purchase.approvals]

    total_amount = sum(i.requested_amount for i in purchase.items)

    return {
        'id': purchase.id, 'document_number': purchase.document_number,
        'user_id': purchase.user_id, 'user_name': purchase.user.name,
        'user_department': purchase.user.department.name if purchase.user.department else None,
        'department_id': purchase.department_id,
        'legal_person_id': purchase.legal_person_id,
        'legal_person_name': purchase.legal_person.name if purchase.legal_person else None,
        'currency_id': purchase.currency_id,
        'currency_symbol': purchase.currency.symbol if purchase.currency else '¥',
        'payment_remark': purchase.payment_remark,
        'status': purchase.status, 'current_step': purchase.current_step,
        'total_amount': total_amount,
        'created_at': purchase.created_at.isoformat() if purchase.created_at else None,
        'updated_at': purchase.updated_at.isoformat() if purchase.updated_at else None,
        'contracts': contracts, 'items': items, 'attachments': attachments,
        'approvals': approvals, 'is_draft': purchase.is_draft,
        'required_role': required_role if with_approval_role else None,
    }


@purchases_bp.route('/api/next_purchase_number', methods=['GET'])
@login_required
def get_next_purchase_number():
    return jsonify({'document_number': generate_number('ZC', AssetPurchase)})


@purchases_bp.route('/api/purchases', methods=['POST'])
@login_required
def create_purchase():
    if not (request.content_type and 'multipart/form-data' in request.content_type):
        return jsonify({'error': '只支持 multipart/form-data'}), 400

    data = request.form
    is_draft = str(data.get('is_draft', '')).lower() == 'true' if isinstance(data.get('is_draft'), str) else bool(data.get('is_draft', False))
    contracts = json.loads(data.get('contracts', '[]'))
    items = json.loads(data.get('items', '[]'))

    doc_num = generate_number('ZC', AssetPurchase)
    purchase = AssetPurchase(
        document_number=doc_num,
        user_id=int(data['user_id']),
        department_id=int(data['department_id']) if data.get('department_id') else None,
        legal_person_id=int(data['legal_person_id']) if data.get('legal_person_id') else None,
        currency_id=int(data.get('currency_id') or 1),
        payment_remark=data.get('payment_remark', ''),
        status='pending', current_step=1, is_draft=is_draft,
    )
    db.session.add(purchase)
    db.session.flush()

    for c in contracts:
        db.session.add(AssetPurchaseContract(
            purchase_id=purchase.id,
            contract_number=c.get('contract_number', ''),
            contract_name=c.get('contract_name', ''),
            supplier_name=c.get('supplier_name', ''),
        ))
    for item in items:
        db.session.add(AssetPurchaseItem(
            purchase_id=purchase.id,
            payment_unit=item.get('payment_unit', ''),
            purchase_type=item.get('purchase_type', ''),
            item_name=item.get('item_name', ''),
            quantity=int(item.get('quantity', 0)),
            contract_total_amount=float(item.get('contract_total_amount', 0)),
            requested_amount=float(item.get('requested_amount', 0)),
        ))
    for f in request.files.getlist('attachments'):
        if f.filename:
            filename = f"purchase_{purchase.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{f.filename}"
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            db.session.add(AssetPurchaseAttachment(
                purchase_id=purchase.id, filename=filename, original_name=f.filename))

    db.session.commit()
    return jsonify({'id': purchase.id, 'document_number': doc_num, 'message': '采购申请创建成功'}), 201


@purchases_bp.route('/api/purchases', methods=['GET'])
@login_required
def get_purchases():
    view_mode = request.args.get('view_mode', 'all')
    current_user = request.user

    if view_mode == 'my':
        purchases = AssetPurchase.query.filter_by(user_id=current_user.id).order_by(AssetPurchase.created_at.desc()).all()
        return jsonify([_serialize_purchase(p) for p in purchases])
    elif view_mode == 'pending_approval':
        all_pending = AssetPurchase.query.filter_by(status='pending').all()
        pending = []
        for p in all_pending:
            if p.is_draft or p.user_id == current_user.id:
                continue
            flow = get_approval_flow(p.user)
            if not flow:
                continue
            steps = flow.get_steps()
            if p.current_step <= len(steps):
                if current_user.role == steps[p.current_step - 1].get('role_code'):
                    pending.append(p)
        pending.sort(key=lambda x: x.created_at, reverse=True)
        return jsonify([_serialize_purchase(p, with_approval_role=True) for p in pending])

    query = AssetPurchase.query
    if request.args.get('user_id'):
        query = query.filter_by(user_id=request.args['user_id'])
    if request.args.get('status'):
        query = query.filter_by(status=request.args['status'])
    purchases = query.order_by(AssetPurchase.created_at.desc()).all()
    return jsonify([_serialize_purchase(p) for p in purchases])


@purchases_bp.route('/api/purchases/<int:purchase_id>', methods=['GET'])
@login_required
def get_purchase(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    return jsonify(_serialize_purchase(purchase, with_approval_role=True))


@purchases_bp.route('/api/purchases/draft/<int:purchase_id>', methods=['PUT'])
@login_required
def update_purchase_draft(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    if not purchase.is_draft or purchase.user_id != request.user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    for field in ('legal_person_id', 'currency_id', 'payment_remark'):
        if field in data:
            setattr(purchase, field, data[field])

    # 替换合同和明细
    for c in purchase.contracts:
        db.session.delete(c)
    for i in purchase.items:
        db.session.delete(i)
    for c in data.get('contracts', []):
        db.session.add(AssetPurchaseContract(
            purchase_id=purchase.id, contract_number=c.get('contract_number', ''),
            contract_name=c.get('contract_name', ''), supplier_name=c.get('supplier_name', '')))
    for i in data.get('items', []):
        db.session.add(AssetPurchaseItem(
            purchase_id=purchase.id, payment_unit=i.get('payment_unit', ''),
            purchase_type=i.get('purchase_type', ''), item_name=i.get('item_name', ''),
            quantity=int(i.get('quantity', 0)),
            contract_total_amount=float(i.get('contract_total_amount', 0)),
            requested_amount=float(i.get('requested_amount', 0))))
    purchase.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})


@purchases_bp.route('/api/purchases/<int:purchase_id>', methods=['DELETE'])
@login_required
def delete_purchase(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    can_delete = (request.user.role == 'admin') or \
                 (purchase.user_id == request.user.id and purchase.is_draft)
    if not can_delete:
        return jsonify({'error': '无权删除'}), 403
    for att in purchase.attachments:
        fp = os.path.join(current_app.config['UPLOAD_FOLDER'], att.filename)
        if os.path.exists(fp):
            os.remove(fp)
    db.session.delete(purchase)
    db.session.commit()
    return jsonify({'message': '采购申请删除成功'})


# ── 采购审批 ──

@purchases_bp.route('/api/purchase_approvals/<int:purchase_id>', methods=['POST'])
@login_required
def approve_purchase(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    approver = request.user

    ok, err = validate_approval(purchase, approver)
    if not ok:
        return jsonify({'error': err}), 400 if '步骤' in err or '流程' in err else 403

    data = request.get_json() if request.is_json else request.form
    action, comment = data.get('action'), data.get('comment', '')
    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400
    if action not in ('approve', 'reject'):
        return jsonify({'error': '无效的审批动作'}), 400

    record = AssetPurchaseApprovalRecord(
        purchase_id=purchase_id, approver_id=approver.id, step=purchase.current_step,
        action=action, comment=comment, approved_at=datetime.now())
    db.session.add(record)
    process_approval(purchase, action)
    db.session.commit()
    return jsonify({'message': '审批完成', 'status': purchase.status, 'current_step': purchase.current_step})
