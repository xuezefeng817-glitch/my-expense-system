"""系统基础数据路由 — 用户/角色/部门/法人/币种/费用类型等 CRUD"""
from flask import Blueprint, request, jsonify
import logging

from ..models import db, User, Role, Department, LegalPerson, Currency, \
    ExpenseType, OperationType, PayeeAccount
from ..auth import login_required, role_required

system_bp = Blueprint('system', __name__)
logger = logging.getLogger(__name__)


# ── 公共辅助 ──

def _model_to_list(model_cls, enabled_only=True):
    """查询列表 → 序列化（自动识别字段）"""
    query = model_cls.query
    if enabled_only and hasattr(model_cls, 'enabled'):
        query = query.filter_by(enabled=True)
    return [obj.to_dict() if hasattr(obj, 'to_dict') else
            {c.name: getattr(obj, c.name) for c in model_cls.__table__.columns}
            for obj in query.all()]


# ── 用户 ──

@system_bp.route('/api/users', methods=['GET'])
@login_required
def get_users():
    return jsonify([u.to_dict() for u in User.query.all()])


@system_bp.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@system_bp.route('/api/users', methods=['POST'])
@role_required('admin')
def create_user():
    data = request.json
    user = User(
        name=data['name'], email=data['email'], username=data['username'],
        password=data.get('password', '123456'),
        role_id=data['role_id'], department_id=data.get('department_id'))
    db.session.add(user)
    db.session.commit()
    return jsonify({'id': user.id, 'message': '用户创建成功'}), 201


@system_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@role_required('admin')
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    for field in ('name', 'email', 'username', 'role_id', 'department_id'):
        if field in data:
            setattr(user, field, data[field])
    if 'password' in data and data['password']:
        user.password = data['password']  # 通过 setter 自动哈希
    db.session.commit()
    return jsonify({'message': '用户更新成功'})


@system_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    db.session.delete(User.query.get_or_404(user_id))
    db.session.commit()
    return jsonify({'message': '用户删除成功'})


# ── 角色 ──

@system_bp.route('/api/roles', methods=['GET'])
@login_required
def get_roles():
    return jsonify([{'id': r.id, 'name': r.name, 'code': r.code}
                    for r in Role.query.filter_by(enabled=True).all()])


@system_bp.route('/api/roles/all', methods=['GET'])
@role_required('admin')
def get_all_roles():
    return jsonify([{'id': r.id, 'name': r.name, 'code': r.code,
                     'description': r.description, 'enabled': r.enabled}
                    for r in Role.query.all()])


@system_bp.route('/api/roles/<int:role_id>', methods=['GET'])
@role_required('admin')
def get_role(role_id):
    r = Role.query.get_or_404(role_id)
    return jsonify({'id': r.id, 'name': r.name, 'code': r.code, 'description': r.description, 'enabled': r.enabled})


@system_bp.route('/api/roles', methods=['POST'])
@role_required('admin')
def create_role():
    data = request.json
    if Role.query.filter_by(code=data['code']).first():
        return jsonify({'error': '角色代码已存在'}), 400
    r = Role(name=data['name'], code=data['code'], description=data.get('description', ''), enabled=data.get('enabled', True))
    db.session.add(r)
    db.session.commit()
    return jsonify({'id': r.id, 'message': '角色创建成功'}), 201


@system_bp.route('/api/roles/<int:role_id>', methods=['PUT'])
@role_required('admin')
def update_role(role_id):
    role = Role.query.get_or_404(role_id)
    data = request.json
    if 'code' in data and data['code'] != role.code and Role.query.filter_by(code=data['code']).first():
        return jsonify({'error': '角色代码已存在'}), 400
    for field in ('name', 'code', 'description', 'enabled'):
        if field in data:
            setattr(role, field, data[field])
    db.session.commit()
    return jsonify({'message': '角色更新成功'})


@system_bp.route('/api/roles/<int:role_id>', methods=['DELETE'])
@role_required('admin')
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    if User.query.filter_by(role_id=role_id).first():
        return jsonify({'error': '该角色已被用户使用，无法删除'}), 400
    db.session.delete(role)
    db.session.commit()
    return jsonify({'message': '角色删除成功'})


# ── 部门（含树形） ──

@system_bp.route('/api/departments', methods=['GET'])
@login_required
def get_departments():
    if request.args.get('mode') == 'tree':
        all_depts = Department.query.all()
        dmap = {}
        for d in all_depts:
            dmap[d.id] = {
                'id': d.id, 'name': d.name, 'code': d.code,
                'description': d.description, 'enabled': d.enabled,
                'parent_id': d.parent_id, 'legal_person_id': d.legal_person_id,
                'legal_person_name': d.legal_person.name if d.legal_person else None,
                'children': [],
            }
        tree = []
        for d in all_depts:
            if not d.parent_id:
                tree.append(dmap[d.id])
            elif d.parent_id in dmap:
                dmap[d.parent_id]['children'].append(dmap[d.id])
        return jsonify(tree)
    depts = Department.query.filter_by(enabled=True).all()
    return jsonify([{
        'id': d.id, 'name': d.name, 'code': d.code, 'description': d.description,
        'enabled': d.enabled, 'parent_id': d.parent_id, 'legal_person_id': d.legal_person_id,
    } for d in depts])


@system_bp.route('/api/departments/all', methods=['GET'])
@role_required('admin')
def get_all_departments():
    return jsonify([{'id': d.id, 'name': d.name, 'code': d.code,
                     'description': d.description, 'enabled': d.enabled}
                    for d in Department.query.all()])


@system_bp.route('/api/departments/<int:dept_id>', methods=['GET'])
@role_required('admin')
def get_department(dept_id):
    d = Department.query.get_or_404(dept_id)
    return jsonify({'id': d.id, 'name': d.name, 'code': d.code,
                    'description': d.description, 'enabled': d.enabled})


@system_bp.route('/api/departments', methods=['POST'])
@role_required('admin')
def create_department():
    try:
        data = request.get_json()
        dept = Department(
            name=data['name'], code=data.get('code'),
            description=data.get('description', ''), enabled=data.get('enabled', True),
            parent_id=data.get('parent_id') or None,
            legal_person_id=data.get('legal_person_id') or None)
        db.session.add(dept)
        db.session.commit()
        return jsonify({'id': dept.id, 'message': '部门创建成功'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/departments/<int:dept_id>', methods=['PUT'])
@role_required('admin')
def update_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    data = request.get_json()
    for field in ('name', 'code', 'description', 'enabled'):
        if field in data:
            setattr(dept, field, data[field])
    if 'parent_id' in data:
        dept.parent_id = data['parent_id'] or None
    if 'legal_person_id' in data:
        dept.legal_person_id = data['legal_person_id'] or None
    db.session.commit()
    return jsonify({'message': '部门更新成功'})


@system_bp.route('/api/departments/<int:dept_id>', methods=['DELETE'])
@role_required('admin')
def delete_department(dept_id):
    try:
        db.session.delete(Department.query.get_or_404(dept_id))
        db.session.commit()
        return jsonify({'message': '部门删除成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/departments/<int:dept_id>/legal_path', methods=['GET'])
@login_required
def get_department_legal_path(dept_id):
    dept = Department.query.get_or_404(dept_id)
    legal = None
    cur = dept
    while cur:
        if cur.legal_person_id:
            legal = LegalPerson.query.get(cur.legal_person_id)
            break
        cur = cur.parent
    return jsonify({
        'department_id': dept.id, 'department_name': dept.name,
        'legal_person': {'id': legal.id, 'name': legal.name} if legal else None,
    })


# ── 法人 ──

@system_bp.route('/api/legal_persons', methods=['GET'])
@login_required
def get_legal_persons():
    return jsonify(_model_to_list(LegalPerson))


@system_bp.route('/api/legal_persons/all', methods=['GET'])
@login_required
def get_all_legal_persons():
    return jsonify(_model_to_list(LegalPerson, enabled_only=False))


@system_bp.route('/api/legal_persons/<int:person_id>', methods=['GET'])
@role_required('admin')
def get_legal_person(person_id):
    p = LegalPerson.query.get_or_404(person_id)
    return jsonify({c.name: getattr(p, c.name) for c in LegalPerson.__table__.columns})


@system_bp.route('/api/legal_persons', methods=['POST'])
@role_required('admin')
def create_legal_person():
    data = request.json
    p = LegalPerson(name=data['name'], unified_code=data.get('unified_code', ''),
                    address=data.get('address', ''), contact=data.get('contact', ''),
                    phone=data.get('phone', ''), enabled=data.get('enabled', True))
    db.session.add(p)
    db.session.commit()
    return jsonify({'id': p.id, 'message': '法人信息创建成功'}), 201


@system_bp.route('/api/legal_persons/<int:person_id>', methods=['PUT'])
@role_required('admin')
def update_legal_person(person_id):
    p = LegalPerson.query.get_or_404(person_id)
    data = request.json
    for field in ('name', 'unified_code', 'address', 'contact', 'phone', 'enabled'):
        if field in data:
            setattr(p, field, data[field])
    db.session.commit()
    return jsonify({'message': '法人信息更新成功'})


@system_bp.route('/api/legal_persons/<int:person_id>', methods=['DELETE'])
@role_required('admin')
def delete_legal_person(person_id):
    db.session.delete(LegalPerson.query.get_or_404(person_id))
    db.session.commit()
    return jsonify({'message': '法人信息删除成功'})


# ── 币种 ──

@system_bp.route('/api/currencies', methods=['GET'])
@login_required
def get_currencies():
    return jsonify(_model_to_list(Currency))


@system_bp.route('/api/currencies/all', methods=['GET'])
@login_required
def get_all_currencies():
    return jsonify(_model_to_list(Currency, enabled_only=False))


@system_bp.route('/api/currencies/<int:currency_id>', methods=['GET'])
@role_required('admin')
def get_currency(currency_id):
    c = Currency.query.get_or_404(currency_id)
    return jsonify({col.name: getattr(c, col.name) for col in Currency.__table__.columns})


@system_bp.route('/api/currencies', methods=['POST'])
@role_required('admin')
def create_currency():
    data = request.json
    c = Currency(code=data['code'], name=data['name'], symbol=data.get('symbol', ''),
                 rate=data.get('rate', 1.0), enabled=data.get('enabled', True))
    db.session.add(c)
    db.session.commit()
    return jsonify({'id': c.id, 'message': '币种信息创建成功'}), 201


@system_bp.route('/api/currencies/<int:currency_id>', methods=['PUT'])
@role_required('admin')
def update_currency(currency_id):
    c = Currency.query.get_or_404(currency_id)
    data = request.json
    for field in ('code', 'name', 'symbol', 'rate', 'enabled'):
        if field in data:
            setattr(c, field, data[field])
    db.session.commit()
    return jsonify({'message': '币种信息更新成功'})


@system_bp.route('/api/currencies/<int:currency_id>', methods=['DELETE'])
@role_required('admin')
def delete_currency(currency_id):
    db.session.delete(Currency.query.get_or_404(currency_id))
    db.session.commit()
    return jsonify({'message': '币种信息删除成功'})


# ── 费用类型 ──

@system_bp.route('/api/expense_types', methods=['GET'])
@login_required
def get_expense_types():
    return jsonify(_model_to_list(ExpenseType))


@system_bp.route('/api/expense_types/all', methods=['GET'])
@role_required('admin')
def get_all_expense_types():
    return jsonify(_model_to_list(ExpenseType, enabled_only=False))


@system_bp.route('/api/expense_types', methods=['POST'])
@role_required('admin')
def create_expense_type():
    data = request.json
    t = ExpenseType(code=data['code'], name=data['name'],
                    description=data.get('description', ''), enabled=data.get('enabled', True))
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'message': '费用类型创建成功'}), 201


@system_bp.route('/api/expense_types/<int:type_id>', methods=['PUT'])
@role_required('admin')
def update_expense_type(type_id):
    t = ExpenseType.query.get_or_404(type_id)
    data = request.json
    for field in ('code', 'name', 'description', 'enabled'):
        if field in data:
            setattr(t, field, data[field])
    db.session.commit()
    return jsonify({'message': '费用类型更新成功'})


@system_bp.route('/api/expense_types/<int:type_id>', methods=['DELETE'])
@role_required('admin')
def delete_expense_type(type_id):
    db.session.delete(ExpenseType.query.get_or_404(type_id))
    db.session.commit()
    return jsonify({'message': '费用类型删除成功'})


# ── 业务类型 ──

@system_bp.route('/api/operation_types', methods=['GET'])
@login_required
def get_operation_types():
    return jsonify(_model_to_list(OperationType))


@system_bp.route('/api/operation_types/all', methods=['GET'])
@role_required('admin')
def get_all_operation_types():
    return jsonify(_model_to_list(OperationType, enabled_only=False))


@system_bp.route('/api/operation_types', methods=['POST'])
@role_required('admin')
def create_operation_type():
    data = request.json
    t = OperationType(code=data['code'], name=data['name'],
                      description=data.get('description', ''), enabled=data.get('enabled', True))
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'message': '业务类型创建成功'}), 201


@system_bp.route('/api/operation_types/<int:type_id>', methods=['PUT'])
@role_required('admin')
def update_operation_type(type_id):
    t = OperationType.query.get_or_404(type_id)
    data = request.json
    for field in ('code', 'name', 'description', 'enabled'):
        if field in data:
            setattr(t, field, data[field])
    db.session.commit()
    return jsonify({'message': '业务类型更新成功'})


@system_bp.route('/api/operation_types/<int:type_id>', methods=['DELETE'])
@role_required('admin')
def delete_operation_type(type_id):
    db.session.delete(OperationType.query.get_or_404(type_id))
    db.session.commit()
    return jsonify({'message': '业务类型删除成功'})


# ── 收款账户 ──

@system_bp.route('/api/payee_accounts', methods=['GET'])
@login_required
def get_payee_accounts():
    if request.user.role == 'admin':
        accounts = PayeeAccount.query.filter_by(enabled=True).all()
    else:
        accounts = PayeeAccount.query.filter_by(user_id=request.user.id, enabled=True).all()
    return jsonify([{
        'id': a.id, 'account_name': a.account_name, 'account_number': a.account_number,
        'bank_short_name': a.bank_short_name, 'bank_location': a.bank_location, 'enabled': a.enabled,
    } for a in accounts])


@system_bp.route('/api/payee_accounts/all', methods=['GET'])
@role_required('admin')
def get_all_payee_accounts():
    accounts = PayeeAccount.query.all()
    return jsonify([{
        'id': a.id, 'account_name': a.account_name, 'account_number': a.account_number,
        'bank_short_name': a.bank_short_name, 'bank_location': a.bank_location,
        'enabled': a.enabled, 'user_id': a.user_id, 'user_name': a.user.name if a.user else None,
    } for a in accounts])


@system_bp.route('/api/payee_accounts', methods=['POST'])
@login_required
def create_payee_account():
    data = request.json
    a = PayeeAccount(
        account_name=data['account_name'], account_number=data['account_number'],
        bank_short_name=data.get('bank_short_name', ''),
        bank_location=data.get('bank_location', ''),
        enabled=data.get('enabled', True), user_id=request.user.id)
    db.session.add(a)
    db.session.commit()
    return jsonify({'id': a.id, 'message': '收款信息创建成功'}), 201


@system_bp.route('/api/payee_accounts/<int:account_id>', methods=['GET'])
@role_required('admin')
def get_payee_account(account_id):
    a = PayeeAccount.query.get_or_404(account_id)
    return jsonify({c.name: getattr(a, c.name) for c in PayeeAccount.__table__.columns})


@system_bp.route('/api/payee_accounts/<int:account_id>', methods=['PUT'])
@login_required
def update_payee_account(account_id):
    a = PayeeAccount.query.get_or_404(account_id)
    if request.user.role != 'admin' and a.user_id != request.user.id:
        return jsonify({'error': '无权修改他人的收款信息'}), 403
    data = request.json
    for field in ('account_name', 'account_number', 'bank_short_name', 'bank_location', 'enabled'):
        if field in data:
            setattr(a, field, data[field])
    db.session.commit()
    return jsonify({'message': '收款信息更新成功'})


@system_bp.route('/api/payee_accounts/<int:account_id>', methods=['DELETE'])
@role_required('admin')
def delete_payee_account(account_id):
    a = PayeeAccount.query.get_or_404(account_id)
    if request.user.role != 'admin' and a.user_id != request.user.id:
        return jsonify({'error': '无权删除他人的收款信息'}), 403
    db.session.delete(a)
    db.session.commit()
    return jsonify({'message': '收款信息删除成功'})


# ── 审批流程配置 ──

@system_bp.route('/api/flows', methods=['GET'])
@role_required('admin')
def get_flows():
    return jsonify([{
        'id': f.id, 'name': f.name, 'department': f.department,
        'steps': f.steps, 'enabled': f.enabled,
    } for f in ApprovalFlow.query.all()])


@system_bp.route('/api/flows', methods=['POST'])
@role_required('admin')
def create_flow():
    import json
    data = request.json
    for step in data['steps']:
        if not step.get('role_code'):
            return jsonify({'error': '每个步骤必须选择角色'}), 400
    f = ApprovalFlow(name=data['name'], department=data.get('department', ''),
                     steps=json.dumps(data['steps']), enabled=data.get('enabled', True))
    db.session.add(f)
    db.session.commit()
    return jsonify({'id': f.id, 'message': '审批流程创建成功'}), 201


@system_bp.route('/api/flows/<int:flow_id>', methods=['GET'])
@role_required('admin')
def get_flow(flow_id):
    f = ApprovalFlow.query.get_or_404(flow_id)
    return jsonify({'id': f.id, 'name': f.name, 'department': f.department,
                    'steps': f.steps, 'enabled': f.enabled})


@system_bp.route('/api/flows/<int:flow_id>', methods=['PUT'])
@role_required('admin')
def update_flow(flow_id):
    import json
    f = ApprovalFlow.query.get_or_404(flow_id)
    data = request.json
    if 'name' in data:
        f.name = data['name']
    if 'department' in data:
        f.department = data['department']
    if 'steps' in data:
        for step in data['steps']:
            if not step.get('role_code'):
                return jsonify({'error': '每个步骤必须选择角色'}), 400
        f.steps = json.dumps(data['steps'])
    if 'enabled' in data:
        f.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '审批流程更新成功'})


@system_bp.route('/api/flows/<int:flow_id>', methods=['DELETE'])
@role_required('admin')
def delete_flow(flow_id):
    db.session.delete(ApprovalFlow.query.get_or_404(flow_id))
    db.session.commit()
    return jsonify({'message': '审批流程删除成功'})
