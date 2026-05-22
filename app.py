from flask import Flask, request, jsonify, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import json
from functools import wraps
import logging
import jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '../uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'expense-system-secret-key-2024'
app.config['JWT_SECRET_KEY'] = 'jwt-secret-key-2024'
app.config['JWT_EXPIRATION_HOURS'] = 24

db = SQLAlchemy(app)

# 精确配置 CORS
CORS(app,
     origins=["http://localhost:8080", "http://127.0.0.1:8080"],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 200

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    users = db.relationship('User', backref='role_ref', lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    
    department = db.relationship('Department', backref=db.backref('users', lazy=True))

    @property
    def role(self):
        return self.role_ref.code if self.role_ref else None

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20))   # 绝对没有 unique=True
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'), nullable=True)
    
    children = db.relationship('Department', backref=db.backref('parent', remote_side=[id]))
    legal_person = db.relationship('LegalPerson', backref='departments')

class LegalPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unified_code = db.Column(db.String(50), unique=True)
    address = db.Column(db.String(200))
    contact = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    enabled = db.Column(db.Boolean, default=True)

class Currency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    symbol = db.Column(db.String(10))
    rate = db.Column(db.Float, default=1.0)
    enabled = db.Column(db.Boolean, default=True)

class ExpenseType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)

class OperationType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)

class PayeeAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50), unique=True, nullable=False)
    bank_short_name = db.Column(db.String(100))
    bank_location = db.Column(db.String(100))
    enabled = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # 新增
    user = db.relationship('User', backref=db.backref('payee_accounts', lazy=True))  # 新增    

class ExpenseClaim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'))
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'), default=1)
    payee_account_id = db.Column(db.Integer, db.ForeignKey('payee_account.id'))
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')
    current_step = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)
    expense_items_json = db.Column(db.Text, nullable=True)  # 存储报销费用明细的JSON            
    
    user = db.relationship('User', backref=db.backref('claims', lazy=True))
    department = db.relationship('Department', backref=db.backref('claims', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('claims', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('claims', lazy=True))
    payee_account = db.relationship('PayeeAccount', backref=db.backref('claims', lazy=True))

class Receipt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    
    claim = db.relationship('ExpenseClaim', backref=db.backref('receipts', lazy=True))

class ApprovalFlow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50))
    steps = db.Column(db.Text)
    enabled = db.Column(db.Boolean, default=True)

class ApprovalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    step = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20))
    comment = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    
    claim = db.relationship('ExpenseClaim', backref=db.backref('approvals', lazy=True))
    approver = db.relationship('User', backref=db.backref('approval_records', lazy=True))

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'))
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'), default=1)
    payee_account_id = db.Column(db.Integer, db.ForeignKey('payee_account.id'))
    amount = db.Column(db.Float, nullable=False)
    purpose = db.Column(db.Text)                  # 借款用途说明
    category = db.Column(db.String(50))           # 借款类别（可选用费用类型）
    status = db.Column(db.String(20), default='pending')
    current_step = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)
    loan_items_json = db.Column(db.Text, nullable=True)   # 👈 加这一行，用来存借款明细        
    total_reimbursed = db.Column(db.Float, default=0.0)  # 累计已核销冲账金额

    user = db.relationship('User', backref=db.backref('loans', lazy=True))
    department = db.relationship('Department', backref=db.backref('loans', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('loans', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('loans', lazy=True))
    payee_account = db.relationship('PayeeAccount', backref=db.backref('loans', lazy=True))
    
class LoanApprovalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loan.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    step = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20))
    comment = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)

    loan = db.relationship('Loan', backref=db.backref('approvals', lazy=True))
    approver = db.relationship('User', backref=db.backref('loan_approval_records', lazy=True))

class LoanReimburseDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    loan_id = db.Column(db.Integer, db.ForeignKey('loan.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    claim = db.relationship('ExpenseClaim', backref=db.backref('loan_details', lazy=True))
    loan = db.relationship('Loan', backref=db.backref('reimburse_details', lazy=True))  

# ========== 资产采购申请模型 ==========
class AssetPurchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'))
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'), default=1)
    payment_remark = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    current_step = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)    

    user = db.relationship('User', backref=db.backref('purchases', lazy=True))
    department = db.relationship('Department', backref=db.backref('purchases', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('purchases', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('purchases', lazy=True))

class AssetPurchaseContract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    contract_number = db.Column(db.String(50))
    contract_name = db.Column(db.String(200))
    supplier_name = db.Column(db.String(200))
    purchase = db.relationship('AssetPurchase', backref=db.backref('contracts', lazy=True, cascade='all, delete-orphan'))

class AssetPurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    payment_unit = db.Column(db.String(100))
    purchase_type = db.Column(db.String(50))
    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer)
    contract_total_amount = db.Column(db.Float)
    requested_amount = db.Column(db.Float)
    purchase = db.relationship('AssetPurchase', backref=db.backref('items', lazy=True, cascade='all, delete-orphan'))

class AssetPurchaseAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    purchase = db.relationship('AssetPurchase', backref=db.backref('attachments', lazy=True, cascade='all, delete-orphan'))

class AssetPurchaseApprovalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    step = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20))
    comment = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    purchase = db.relationship('AssetPurchase', backref=db.backref('approvals', lazy=True))
    approver = db.relationship('User', backref=db.backref('purchase_approval_records', lazy=True))

def generate_loan_number():
    prefix = 'JK'
    last_loan = Loan.query.order_by(Loan.id.desc()).first()
    if last_loan:
        last_num = int(last_loan.document_number.replace(prefix, ''))
        next_num = last_num + 1
    else:
        next_num = 1
    return f'{prefix}{str(next_num).zfill(9)}'

def generate_purchase_number():
    prefix = 'ZC'
    last = AssetPurchase.query.order_by(AssetPurchase.id.desc()).first()
    if last:
        last_num = int(last.document_number.replace(prefix, ''))
        next_num = last_num + 1
    else:
        next_num = 1
    return f'{prefix}{str(next_num).zfill(9)}'
    
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': '未登录，请先登录'}), 401
        
        try:
            token = token.replace('Bearer ', '')
            payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            user = User.query.get(payload['user_id'])
            if not user:
                return jsonify({'error': '用户不存在'}), 401
            request.user = user
        except jwt.ExpiredSignatureError:
            return jsonify({'error': '登录已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': '无效的token'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return jsonify({'error': '未登录，请先登录'}), 401
            
            try:
                token = token.replace('Bearer ', '')
                payload = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
                user = User.query.get(payload['user_id'])
                if not user:
                    return jsonify({'error': '用户不存在'}), 401
                if user.role not in roles:
                    return jsonify({'error': '权限不足'}), 403
                request.user = user
            except jwt.ExpiredSignatureError:
                return jsonify({'error': '登录已过期'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'error': '无效的token'}), 401
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/api/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username and request.json:
        username = request.json.get('username')
    if not password and request.json:
        password = request.json.get('password')
            
    logger.info(f"登录请求 - username: {username}")
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '用户名或密码错误'}), 401
    
    if user.password != password:
        return jsonify({'error': '用户名或密码错误'}), 401
    
    expires = datetime.utcnow() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS'])
    token = jwt.encode({
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'exp': expires
    }, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'message': '登录成功',
        'token': token,
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'email': user.email,
            'role': user.role,
            'department_id': user.department_id,
            'department': user.department.name if user.department else None
        }
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message': '退出登录成功'})

@app.route('/api/next_loan_number', methods=['GET'])
@login_required
def get_next_loan_number():
    return jsonify({'document_number': generate_loan_number()})

@app.route('/api/loans', methods=['POST'])
@login_required
def create_loan():
    data = request.form
    is_draft_val = data.get('is_draft')
    if isinstance(is_draft_val, str):
        is_draft = is_draft_val.lower() == 'true'
    else:
        is_draft = bool(is_draft_val)

    document_number = generate_loan_number()
    loan = Loan(
        document_number=document_number,
        user_id=int(data['user_id']),
        department_id=int(data['department_id']) if data.get('department_id') else None,
        legal_person_id=int(data['legal_person_id']) if data.get('legal_person_id') else None,
        currency_id=int(data['currency_id']) if data.get('currency_id') else 1,
        payee_account_id=int(data['payee_account_id']) if data.get('payee_account_id') else None,
        amount=float(data['amount']),
        purpose=data.get('purpose', ''),
        category=data.get('category', '其他'),
        status='pending',
        current_step=1,
        is_draft=is_draft,
        loan_items_json=data.get('loan_items', '[]')   # 👈 加上这一行，接收前端传来的借款明细
    )
    db.session.add(loan)
    db.session.commit()
    return jsonify({'id': loan.id, 'document_number': document_number, 'message': '借款申请创建成功'}), 201

@app.route('/api/loans', methods=['GET'])
@login_required
def get_loans():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    view_mode = request.args.get('view_mode', 'all')
    current_user = request.user

    if view_mode == 'my':
        query = Loan.query.filter_by(user_id=current_user.id)
        loans = query.order_by(Loan.created_at.desc()).all()
    elif view_mode == 'pending_approval':
        all_pending = Loan.query.filter_by(status='pending').all()
        pending_loans = []
        for l in all_pending:
            if l.is_draft:
                continue            
            if l.user_id == current_user.id:
                continue
            dept_name = l.user.department.name if l.user.department else None
            flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
            if not flow:
                flow = ApprovalFlow.query.filter_by(enabled=True).first()
            if not flow:
                continue
            steps = json.loads(flow.steps)
            if l.current_step <= len(steps):
                needed_role = steps[l.current_step - 1].get('role_code')
                if current_user.role == needed_role:
                    pending_loans.append(l)
        pending_loans.sort(key=lambda x: x.created_at, reverse=True)
        loans = pending_loans
    else:
        query = Loan.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        loans = query.order_by(Loan.created_at.desc()).all()

    result = []
    for loan in loans:
        approvals = [{
            'step': a.step, 'action': a.action, 'comment': a.comment,
            'approver_name': a.approver.name if a.approver else '',
            'approved_at': a.approved_at.isoformat() if a.approved_at else None
        } for a in loan.approvals]
        result.append({
            'id': loan.id,
            'document_number': loan.document_number,
            'user_id': loan.user_id,
            'user_name': loan.user.name,
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
            'amount': loan.amount,
            'purpose': loan.purpose,
            'category': loan.category,
            'status': loan.status,
            'current_step': loan.current_step,
            'created_at': loan.created_at.isoformat(),
            'updated_at': loan.updated_at.isoformat(),
            'approvals': approvals,
            'is_draft': loan.is_draft,      
        })
    return jsonify(result)

@app.route('/api/loans/<int:loan_id>', methods=['GET'])
@login_required
def get_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    dept_name = loan.user.department.name if loan.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    steps = json.loads(flow.steps) if flow else []
    required_role = None
    if steps and loan.current_step <= len(steps):
        required_role = steps[loan.current_step - 1].get('role_code')
    approvals = [{
        'step': a.step, 'action': a.action, 'comment': a.comment,
        'approver_name': a.approver.name if a.approver else '',
        'approved_at': a.approved_at.isoformat() if a.approved_at else None
    } for a in loan.approvals]
    return jsonify({
        'id': loan.id,
        'document_number': loan.document_number,
        'user_id': loan.user_id,
        'user_name': loan.user.name,
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
        'amount': loan.amount,
        'purpose': loan.purpose,
        'category': loan.category,
        'status': loan.status,
        'current_step': loan.current_step,
        'created_at': loan.created_at.isoformat(),
        'updated_at': loan.updated_at.isoformat(),
        'approvals': approvals,
        'required_role': required_role,
        'loan_items': loan.loan_items_json or '[]' 
    })

@app.route('/api/loan_approvals/<int:loan_id>', methods=['POST'])
@login_required
def approve_loan(loan_id):
    if request.is_json:
        data = request.get_json()
        action = data.get('action')
        comment = data.get('comment', '')
    else:
        action = request.form.get('action')
        comment = request.form.get('comment', '')

    loan = Loan.query.get_or_404(loan_id)
    approver = request.user

    dept_name = loan.user.department.name if loan.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    if not flow:
        return jsonify({'error': '未找到审批流程'}), 400

    steps = json.loads(flow.steps)

    if loan.status == 'approved':
        return jsonify({'error': '该借款单已审批完成'}), 400
    if loan.status == 'rejected' and loan.current_step > 1:
        return jsonify({'error': '该单据已被驳回，请等待申请人重新提交'}), 400
    if approver.id == loan.user_id:
        return jsonify({'error': '不能审批自己的借款单'}), 400

    if loan.current_step < 1 or loan.current_step > len(steps):
        return jsonify({'error': '审批流程步骤异常'}), 400
    required_role_code = steps[loan.current_step - 1].get('role_code')
    if approver.role != required_role_code:
        return jsonify({'error': f'您没有权限进行此步骤的审批，需要角色：{required_role_code}'}), 403

    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400

    approval = LoanApprovalRecord(
        loan_id=loan_id,
        approver_id=approver.id,
        step=loan.current_step,
        action=action,
        comment=comment,
        approved_at=datetime.now()
    )
    db.session.add(approval)

    if action == 'approve':
        if loan.current_step == len(steps):
            loan.status = 'approved'
        else:
            loan.current_step += 1
            loan.status = 'pending'
    elif action == 'reject':
        loan.status = 'rejected'
        loan.current_step = 1
    else:
        return jsonify({'error': '无效的审批动作'}), 400

    loan.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '审批完成', 'status': loan.status, 'current_step': loan.current_step})

@app.route('/api/user_available_loans', methods=['GET'])
@login_required
def get_user_available_loans():
    user = request.user
    loans = Loan.query.filter_by(user_id=user.id, status='approved').all()
    result = []
    for loan in loans:
        remaining = loan.amount - (loan.total_reimbursed or 0)
        if remaining > 0:
            result.append({
                'id': loan.id,
                'document_number': loan.document_number,
                'total_amount': loan.amount,
                'total_reimbursed': loan.total_reimbursed or 0,
                'remaining': remaining,
                'purpose': loan.purpose,
                'category': loan.category
            })
    return jsonify(result)

@app.route('/api/loans/draft/<int:loan_id>', methods=['PUT'])
@login_required
def update_loan_draft(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    current_user = request.user
    if not loan.is_draft or loan.user_id != current_user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    if 'amount' in data:
        loan.amount = float(data['amount'])
    if 'purpose' in data:
        loan.purpose = data['purpose']
    if 'category' in data:
        loan.category = data['category']
    if 'legal_person_id' in data:
        loan.legal_person_id = data['legal_person_id']
    if 'currency_id' in data:
        loan.currency_id = data['currency_id']
    if 'payee_account_id' in data:
        loan.payee_account_id = data['payee_account_id']
    if 'department_id' in data:
        loan.department_id = data['department_id']
    if 'loan_items' in data:
        loan.loan_items_json = data['loan_items']        
    loan.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})

@app.route('/api/loans/<int:loan_id>', methods=['DELETE'])
@login_required
def delete_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    current_user = request.user
    # 管理员可以删除任何借款单
    if current_user.role == 'admin':
        pass
    # 申请人可以删除自己的、未进入审批流程的借款单
    elif loan.user_id == current_user.id and loan.status == 'pending' and loan.current_step == 1 and len(loan.approvals) == 0:
        pass
    else:
        return jsonify({'error': '无权删除此借款单'}), 403
    db.session.delete(loan)
    db.session.commit()
    return jsonify({'message': '借款申请删除成功'})

@app.route('/api/current_user', methods=['GET'])
@login_required
def get_current_user():
    user = request.user
    return jsonify({
        'id': user.id,
        'username': user.username,
        'name': user.name,
        'role': user.role,
        'department_id': user.department_id,
        'department': user.department.name if user.department else None
    })

def generate_document_number():
    try:
        prefix = 'BXZF'
        last_claim = ExpenseClaim.query.order_by(ExpenseClaim.id.desc()).first()
        if last_claim:
            last_num = int(last_claim.document_number.replace(prefix, ''))
            next_num = last_num + 1
        else:
            next_num = 1
        return f'{prefix}{str(next_num).zfill(9)}'
    except Exception as e:
        logger.error(f'生成单据号失败: {str(e)}')
        return f'{prefix}000000001'

@app.route('/api/next_document_number', methods=['GET'])
@login_required
def get_next_document_number():
    try:
        number = generate_document_number()
        return jsonify({'document_number': number})
    except Exception as e:
        logger.error(f'获取下一个单据号失败: {str(e)}')
        return jsonify({'document_number': 'BXZF000000001'})

# 初始化数据库表和数据
with app.app_context():
    db.create_all() # 重建所有表

    # 初始化角色（如果还没有）
    if not Role.query.first():
        db.session.add_all([
            Role(name='员工', code='employee', description='普通员工'),
            Role(name='部门主管', code='department_manager', description='部门经理'),
            Role(name='财务会计', code='finance_staff', description='财务人员'),
            Role(name='财务经理', code='finance_manager', description='财务经理'),
            Role(name='总经理', code='general_manager', description='总经理'),
            Role(name='系统管理员', code='admin', description='管理员'),
        ])
        db.session.commit()

    if not Department.query.first():
        tech_dept = Department(name='技术部', code='TECH', description='负责技术研发和维护')
        finance_dept = Department(name='财务部', code='FIN', description='负责财务管理和报销审核')
        admin_dept = Department(name='管理层', code='ADMIN', description='公司管理层')
        hr_dept = Department(name='人力资源部', code='HR', description='负责人员招聘和管理')
        db.session.add_all([tech_dept, finance_dept, admin_dept, hr_dept])
        db.session.commit()

    if not User.query.first():
        # 获取角色
        role_emp = Role.query.filter_by(code='employee').first()
        role_dept = Role.query.filter_by(code='department_manager').first()
        role_fin = Role.query.filter_by(code='finance_staff').first()
        role_fin_mgr = Role.query.filter_by(code='finance_manager').first()
        role_gm = Role.query.filter_by(code='general_manager').first()
        role_admin = Role.query.filter_by(code='admin').first()

        db.session.add(User(name='张三', email='zhangsan@company.com', username='zhangsan', password='123456', role_id=role_emp.id, department_id=1))
        db.session.add(User(name='李四', email='lisi@company.com', username='lisi', password='123456', role_id=role_dept.id, department_id=1))
        db.session.add(User(name='王五', email='wangwu@company.com', username='wangwu', password='123456', role_id=role_fin.id, department_id=2))
        db.session.add(User(name='赵六', email='zhaoliu@company.com', username='zhaoliu', password='123456', role_id=role_fin_mgr.id, department_id=3))
        db.session.add(User(name='陈七', email='chenqi@company.com', username='chenqi', password='123456', role_id=role_gm.id, department_id=3))
        db.session.add(User(name='薛总', email='xuezf@company.com', username='xuezf', password='123123', role_id=role_admin.id, department_id=3))
        db.session.commit()

    if not ExpenseType.query.first():
        db.session.add(ExpenseType(code='TRAVEL', name='差旅费', description='出差相关费用'))
        db.session.add(ExpenseType(code='OFFICE', name='办公用品', description='办公物资采购'))
        db.session.add(ExpenseType(code='MEAL', name='餐饮费', description='业务招待餐饮'))
        db.session.add(ExpenseType(code='TRANSPORT', name='交通费', description='交通出行费用'))
        db.session.add(ExpenseType(code='OTHER', name='其他', description='其他费用'))
        db.session.commit()

    if not OperationType.query.first():
        db.session.add(OperationType(code='SALES', name='销售业务', description='产品销售相关业务'))
        db.session.add(OperationType(code='PRODUCTION', name='生产业务', description='产品生产相关业务'))
        db.session.add(OperationType(code='MANUFACTURE', name='制造业务', description='制造加工相关业务'))
        db.session.add(OperationType(code='MANAGEMENT', name='管理业务', description='企业管理相关业务'))
        db.session.add(OperationType(code='PRE_SALES', name='售前业务', description='售前支持相关业务'))
        db.session.add(OperationType(code='R_D', name='研发业务', description='研究开发相关业务'))
        db.session.commit()

    if not LegalPerson.query.first():
        db.session.add(LegalPerson(name='北京科技有限公司', unified_code='91110108MA00000000', address='北京市海淀区中关村科技园', contact='张三', phone='13800138000'))
        db.session.add(LegalPerson(name='上海贸易有限公司', unified_code='91310109MA11111111', address='上海市浦东新区陆家嘴', contact='李四', phone='13900139000'))
        db.session.commit()

    if not Currency.query.first():
        db.session.add(Currency(code='CNY', name='人民币', symbol='¥', rate=1.0))
        db.session.add(Currency(code='USD', name='美元', symbol='$', rate=7.24))
        db.session.add(Currency(code='EUR', name='欧元', symbol='€', rate=7.86))
        db.session.add(Currency(code='GBP', name='英镑', symbol='£', rate=9.12))
        db.session.commit()

    if not PayeeAccount.query.first():
        admin_user = User.query.filter_by(username='xuezf').first()
        admin_id = admin_user.id if admin_user else 1
        db.session.add(PayeeAccount(account_name='北京科技有限公司', account_number='6222021234567890123', bank_short_name='工商银行', bank_location='北京', user_id=admin_id))
        db.session.add(PayeeAccount(account_name='上海贸易有限公司', account_number='6228481234567890456', bank_short_name='农业银行', bank_location='上海', user_id=admin_id))
        db.session.commit()

    if not ApprovalFlow.query.first():
        tech_flow = ApprovalFlow(
            name='标准报销流程-技术部',
            department='技术部',
            steps='[{"step": 1, "role_code": "department_manager", "description": "部门经理审批"}, {"step": 2, "role_code": "finance_staff", "description": "财务会计审核"}, {"step": 3, "role_code": "finance_manager", "description": "财务经理审批"}, {"step": 4, "role_code": "general_manager", "description": "总经理审批"}]'
        )
        general_flow = ApprovalFlow(
            name='标准报销流程-通用',
            department='',
            steps='[{"step": 1, "role_code": "department_manager", "description": "部门经理审批"}, {"step": 2, "role_code": "finance_staff", "description": "财务会计审核"}, {"step": 3, "role_code": "finance_manager", "description": "财务经理审批"}, {"step": 4, "role_code": "general_manager", "description": "总经理审批"}]'
        )
        db.session.add_all([tech_flow, general_flow])
        db.session.commit()


# ---------- 用户管理 ----------
@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'username': u.username,
        'role': u.role,                     # 使用 property
        'role_id': u.role_id,
        'role_name': u.role_ref.name if u.role_ref else '',
        'department_id': u.department_id,
        'department': u.department.name if u.department else None      
    } for u in users])

@app.route('/api/users/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'username': user.username,
        'role': user.role,
        'role_id': user.role_id,
        'role_name': user.role_ref.name if user.role_ref else '',
        'department_id': user.department_id,
        'department': user.department.name if user.department else None
    })

@app.route('/api/users', methods=['POST'])
@role_required(['admin'])
def create_user():
    data = request.json
    user = User(
        name=data['name'],
        email=data['email'],
        username=data['username'],
        password=data.get('password', '123456'),
        role_id=data['role_id'],               # 改为 role_id
        department_id=data.get('department_id')
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'id': user.id, 'message': '用户创建成功'}), 201

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@role_required(['admin'])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    if 'name' in data:
        user.name = data['name']
    if 'email' in data:
        user.email = data['email']
    if 'username' in data:
        user.username = data['username']
    if 'password' in data:
        user.password = data['password']
    if 'role_id' in data:                     # 改为 role_id
        user.role_id = data['role_id']
    if 'department_id' in data:
        user.department_id = data['department_id']
    db.session.commit()
    return jsonify({'message': '用户更新成功'})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': '用户删除成功'})

# ---------- 角色管理（仅管理员） ----------
@app.route('/api/roles', methods=['GET'])
@login_required
def get_roles():
    roles = Role.query.filter_by(enabled=True).all()
    return jsonify([{'id': r.id, 'name': r.name, 'code': r.code} for r in roles])

@app.route('/api/roles/all', methods=['GET'])
@role_required(['admin'])
def get_all_roles():
    roles = Role.query.all()
    return jsonify([{'id': r.id, 'name': r.name, 'code': r.code, 'description': r.description, 'enabled': r.enabled} for r in roles])

@app.route('/api/roles/<int:role_id>', methods=['GET'])
@role_required(['admin'])
def get_role(role_id):
    role = Role.query.get_or_404(role_id)
    return jsonify({'id': role.id, 'name': role.name, 'code': role.code, 'description': role.description, 'enabled': role.enabled})

@app.route('/api/roles', methods=['POST'])
@role_required(['admin'])
def create_role():
    data = request.json
    if Role.query.filter_by(code=data['code']).first():
        return jsonify({'error': '角色代码已存在'}), 400
    role = Role(
        name=data['name'],
        code=data['code'],
        description=data.get('description', ''),
        enabled=data.get('enabled', True)
    )
    db.session.add(role)
    db.session.commit()
    return jsonify({'id': role.id, 'message': '角色创建成功'}), 201

@app.route('/api/roles/<int:role_id>', methods=['PUT'])
@role_required(['admin'])
def update_role(role_id):
    role = Role.query.get_or_404(role_id)
    data = request.json
    if 'name' in data:
        role.name = data['name']
    if 'code' in data and data['code'] != role.code:
        if Role.query.filter_by(code=data['code']).first():
            return jsonify({'error': '角色代码已存在'}), 400
        role.code = data['code']
    if 'description' in data:
        role.description = data['description']
    if 'enabled' in data:
        role.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '角色更新成功'})

@app.route('/api/roles/<int:role_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    if User.query.filter_by(role_id=role_id).first():
        return jsonify({'error': '该角色已被用户使用，无法删除'}), 400
    db.session.delete(role)
    db.session.commit()
    return jsonify({'message': '角色删除成功'})

# ---------- 费用类型 ----------
@app.route('/api/expense_types', methods=['GET'])
@login_required
def get_expense_types():
    types = ExpenseType.query.filter_by(enabled=True).all()
    return jsonify([{
        'id': t.id,
        'code': t.code,
        'name': t.name,
        'description': t.description,
        'enabled': t.enabled
    } for t in types])

@app.route('/api/expense_types/all', methods=['GET'])
@role_required(['admin'])
def get_all_expense_types():
    types = ExpenseType.query.all()
    return jsonify([{
        'id': t.id,
        'code': t.code,
        'name': t.name,
        'description': t.description,
        'enabled': t.enabled
    } for t in types])

@app.route('/api/expense_types', methods=['POST'])
@role_required(['admin'])
def create_expense_type():
    data = request.json
    expense_type = ExpenseType(
        code=data['code'],
        name=data['name'],
        description=data.get('description', ''),
        enabled=data.get('enabled', True)
    )
    db.session.add(expense_type)
    db.session.commit()
    return jsonify({'id': expense_type.id, 'message': '费用类型创建成功'}), 201

@app.route('/api/expense_types/<int:type_id>', methods=['GET'])
@role_required(['admin'])
def get_expense_type(type_id):
    expense_type = ExpenseType.query.get_or_404(type_id)
    return jsonify({
        'id': expense_type.id,
        'code': expense_type.code,
        'name': expense_type.name,
        'description': expense_type.description,
        'enabled': expense_type.enabled
    })

@app.route('/api/expense_types/<int:type_id>', methods=['PUT'])
@role_required(['admin'])
def update_expense_type(type_id):
    expense_type = ExpenseType.query.get_or_404(type_id)
    data = request.json
    if 'code' in data:
        expense_type.code = data['code']
    if 'name' in data:
        expense_type.name = data['name']
    if 'description' in data:
        expense_type.description = data['description']
    if 'enabled' in data:
        expense_type.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '费用类型更新成功'})

@app.route('/api/expense_types/<int:type_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_expense_type(type_id):
    expense_type = ExpenseType.query.get_or_404(type_id)
    db.session.delete(expense_type)
    db.session.commit()
    return jsonify({'message': '费用类型删除成功'})


# ---------- 业务类型 ----------
@app.route('/api/operation_types', methods=['GET'])
@login_required
def get_operation_types():
    types = OperationType.query.filter_by(enabled=True).all()
    return jsonify([{
        'id': t.id,
        'code': t.code,
        'name': t.name,
        'description': t.description,
        'enabled': t.enabled
    } for t in types])

@app.route('/api/operation_types/all', methods=['GET'])
@role_required(['admin'])
def get_all_operation_types():
    types = OperationType.query.all()
    return jsonify([{
        'id': t.id,
        'code': t.code,
        'name': t.name,
        'description': t.description,
        'enabled': t.enabled
    } for t in types])

@app.route('/api/operation_types', methods=['POST'])
@role_required(['admin'])
def create_operation_type():
    data = request.json
    operation_type = OperationType(
        code=data['code'],
        name=data['name'],
        description=data.get('description', ''),
        enabled=data.get('enabled', True)
    )
    db.session.add(operation_type)
    db.session.commit()
    return jsonify({'id': operation_type.id, 'message': '业务类型创建成功'}), 201

@app.route('/api/operation_types/<int:type_id>', methods=['GET'])
@role_required(['admin'])
def get_operation_type(type_id):
    operation_type = OperationType.query.get_or_404(type_id)
    return jsonify({
        'id': operation_type.id,
        'code': operation_type.code,
        'name': operation_type.name,
        'description': operation_type.description,
        'enabled': operation_type.enabled
    })

@app.route('/api/operation_types/<int:type_id>', methods=['PUT'])
@role_required(['admin'])
def update_operation_type(type_id):
    operation_type = OperationType.query.get_or_404(type_id)
    data = request.json
    if 'code' in data:
        operation_type.code = data['code']
    if 'name' in data:
        operation_type.name = data['name']
    if 'description' in data:
        operation_type.description = data['description']
    if 'enabled' in data:
        operation_type.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '业务类型更新成功'})

@app.route('/api/operation_types/<int:type_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_operation_type(type_id):
    operation_type = OperationType.query.get_or_404(type_id)
    db.session.delete(operation_type)
    db.session.commit()
    return jsonify({'message': '业务类型删除成功'})


# ---------- 部门管理 ----------
@app.route('/api/departments', methods=['GET'])
@login_required
def get_departments():
    mode = request.args.get('mode', 'list')
    if mode == 'tree':
        all_depts = Department.query.all()
        dept_map = {}
        for d in all_depts:
            dept_map[d.id] = {
                'id': d.id,
                'name': d.name,
                'code': d.code,
                'description': d.description,
                'enabled': d.enabled,
                'parent_id': d.parent_id,
                'legal_person_id': d.legal_person_id,
                'legal_person_name': d.legal_person.name if d.legal_person else None,
                'children': []
            }
        tree = []
        for d in all_depts:
            if d.parent_id is None or d.parent_id == 0:
                tree.append(dept_map[d.id])
            else:
                if d.parent_id in dept_map:
                    dept_map[d.parent_id]['children'].append(dept_map[d.id])
        return jsonify(tree)
    else:
        departments = Department.query.filter_by(enabled=True).all()
        return jsonify([{
            'id': d.id,
            'name': d.name,
            'code': d.code,
            'description': d.description,
            'enabled': d.enabled,
            'parent_id': d.parent_id,
            'legal_person_id': d.legal_person_id
        } for d in departments])

@app.route('/api/departments/all', methods=['GET'])
@role_required(['admin'])
def get_all_departments():
    departments = Department.query.all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'code': d.code,
        'description': d.description,
        'enabled': d.enabled
    } for d in departments])

@app.route('/api/departments', methods=['POST'])
@role_required(['admin'])
def create_department():
    try:
        data = request.get_json()
        # 处理空字符串为 None
        parent_id = data.get('parent_id') if data.get('parent_id') else None
        legal_person_id = data.get('legal_person_id') if data.get('legal_person_id') else None
        
        dept = Department(
            name=data['name'],
            code=data.get('code') or None,          # 允许为空，不违反唯一约束
            description=data.get('description', ''),
            enabled=data.get('enabled', True),
            parent_id=parent_id,
            legal_person_id=legal_person_id
        )
        db.session.add(dept)
        db.session.commit()
        return jsonify({"id": dept.id, "message": "部门创建成功"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/departments/<int:dept_id>', methods=['GET'])
@role_required(['admin'])
def get_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    return jsonify({
        'id': department.id,
        'name': department.name,
        'code': department.code,
        'description': department.description,
        'enabled': department.enabled
    })

@app.route('/api/departments/<int:dept_id>', methods=['PUT'])
@role_required(['admin'])
def update_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    data = request.get_json()
    if 'name' in data:
        department.name = data['name']
    if 'code' in data:
        department.code = data['code']
    if 'description' in data:
        department.description = data['description']
    if 'enabled' in data:
        department.enabled = data['enabled']
    if 'parent_id' in data:
        department.parent_id = data['parent_id'] if data['parent_id'] else None
    if 'legal_person_id' in data:
        department.legal_person_id = data['legal_person_id'] if data['legal_person_id'] else None
    db.session.commit()
    return jsonify({'message': '部门更新成功'})

@app.route('/api/departments/<int:dept_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_department(dept_id):
    try:
        dept = Department.query.get_or_404(dept_id)
        db.session.delete(dept)
        db.session.commit()
        return jsonify({"message": "部门删除成功"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ---------- 法人信息 ----------
@app.route('/api/legal_persons', methods=['GET'])
@login_required
def get_legal_persons():
    persons = LegalPerson.query.filter_by(enabled=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'unified_code': p.unified_code,
        'address': p.address,
        'contact': p.contact,
        'phone': p.phone,
        'enabled': p.enabled
    } for p in persons])

@app.route('/api/legal_persons/all', methods=['GET'])
@login_required
def get_all_legal_persons():
    persons = LegalPerson.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'unified_code': p.unified_code,
        'address': p.address,
        'contact': p.contact,
        'phone': p.phone,
        'enabled': p.enabled
    } for p in persons])

@app.route('/api/legal_persons', methods=['POST'])
@role_required(['admin'])
def create_legal_person():
    data = request.json
    person = LegalPerson(
        name=data['name'],
        unified_code=data.get('unified_code', ''),
        address=data.get('address', ''),
        contact=data.get('contact', ''),
        phone=data.get('phone', ''),
        enabled=data.get('enabled', True)
    )
    db.session.add(person)
    db.session.commit()
    return jsonify({'id': person.id, 'message': '法人信息创建成功'}), 201

@app.route('/api/legal_persons/<int:person_id>', methods=['GET'])
@role_required(['admin'])
def get_legal_person(person_id):
    person = LegalPerson.query.get_or_404(person_id)
    return jsonify({
        'id': person.id,
        'name': person.name,
        'unified_code': person.unified_code,
        'address': person.address,
        'contact': person.contact,
        'phone': person.phone,
        'enabled': person.enabled
    })

@app.route('/api/legal_persons/<int:person_id>', methods=['PUT'])
@role_required(['admin'])
def update_legal_person(person_id):
    person = LegalPerson.query.get_or_404(person_id)
    data = request.json
    if 'name' in data:
        person.name = data['name']
    if 'unified_code' in data:
        person.unified_code = data['unified_code']
    if 'address' in data:
        person.address = data['address']
    if 'contact' in data:
        person.contact = data['contact']
    if 'phone' in data:
        person.phone = data['phone']
    if 'enabled' in data:
        person.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '法人信息更新成功'})

@app.route('/api/legal_persons/<int:person_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_legal_person(person_id):
    person = LegalPerson.query.get_or_404(person_id)
    db.session.delete(person)
    db.session.commit()
    return jsonify({'message': '法人信息删除成功'})


# ---------- 币种管理 ----------
@app.route('/api/currencies', methods=['GET'])
@login_required
def get_currencies():
    currencies = Currency.query.filter_by(enabled=True).all()
    return jsonify([{
        'id': c.id,
        'code': c.code,
        'name': c.name,
        'symbol': c.symbol,
        'rate': c.rate,
        'enabled': c.enabled
    } for c in currencies])

@app.route('/api/currencies/all', methods=['GET'])
@login_required
def get_all_currencies():
    currencies = Currency.query.all()
    return jsonify([{
        'id': c.id,
        'code': c.code,
        'name': c.name,
        'symbol': c.symbol,
        'rate': c.rate,
        'enabled': c.enabled
    } for c in currencies])

@app.route('/api/currencies', methods=['POST'])
@role_required(['admin'])
def create_currency():
    data = request.json
    currency = Currency(
        code=data['code'],
        name=data['name'],
        symbol=data.get('symbol', ''),
        rate=data.get('rate', 1.0),
        enabled=data.get('enabled', True)
    )
    db.session.add(currency)
    db.session.commit()
    return jsonify({'id': currency.id, 'message': '币种信息创建成功'}), 201

@app.route('/api/currencies/<int:currency_id>', methods=['GET'])
@role_required(['admin'])
def get_currency(currency_id):
    currency = Currency.query.get_or_404(currency_id)
    return jsonify({
        'id': currency.id,
        'code': currency.code,
        'name': currency.name,
        'symbol': currency.symbol,
        'rate': currency.rate,
        'enabled': currency.enabled
    })

@app.route('/api/currencies/<int:currency_id>', methods=['PUT'])
@role_required(['admin'])
def update_currency(currency_id):
    currency = Currency.query.get_or_404(currency_id)
    data = request.json
    if 'code' in data:
        currency.code = data['code']
    if 'name' in data:
        currency.name = data['name']
    if 'symbol' in data:
        currency.symbol = data['symbol']
    if 'rate' in data:
        currency.rate = data['rate']
    if 'enabled' in data:
        currency.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '币种信息更新成功'})

@app.route('/api/currencies/<int:currency_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_currency(currency_id):
    currency = Currency.query.get_or_404(currency_id)
    db.session.delete(currency)
    db.session.commit()
    return jsonify({'message': '币种信息删除成功'})


# ---------- 收款信息 ----------
@app.route('/api/payee_accounts', methods=['GET'])
@login_required
def get_payee_accounts():
    current_user = request.user
    if current_user.role == 'admin':
        accounts = PayeeAccount.query.filter_by(enabled=True).all()
    else:
        accounts = PayeeAccount.query.filter_by(user_id=current_user.id, enabled=True).all()
    return jsonify([{
        'id': a.id,
        'account_name': a.account_name,
        'account_number': a.account_number,
        'bank_short_name': a.bank_short_name,
        'bank_location': a.bank_location,
        'enabled': a.enabled
    } for a in accounts])

@app.route('/api/payee_accounts/all', methods=['GET'])
@role_required(['admin'])
def get_all_payee_accounts():
    accounts = PayeeAccount.query.all()
    return jsonify([{
        'id': a.id,
        'account_name': a.account_name,
        'account_number': a.account_number,
        'bank_short_name': a.bank_short_name,
        'bank_location': a.bank_location,
        'enabled': a.enabled,
        'user_id': a.user_id,
        'user_name': a.user.name if a.user else None
    } for a in accounts])

@app.route('/api/payee_accounts', methods=['POST'])
@login_required
def create_payee_account():
    data = request.json
    account = PayeeAccount(
        account_name=data['account_name'],
        account_number=data['account_number'],
        bank_short_name=data.get('bank_short_name', ''),
        bank_location=data.get('bank_location', ''),
        enabled=data.get('enabled', True),
        user_id=request.user.id  # 新增
    )
    db.session.add(account)
    db.session.commit()
    return jsonify({'id': account.id, 'message': '收款信息创建成功'}), 201

@app.route('/api/payee_accounts/<int:account_id>', methods=['GET'])
@role_required(['admin'])
def get_payee_account(account_id):
    account = PayeeAccount.query.get_or_404(account_id)
    return jsonify({
        'id': account.id,
        'account_name': account.account_name,
        'account_number': account.account_number,
        'bank_short_name': account.bank_short_name,
        'bank_location': account.bank_location,
        'enabled': account.enabled
    })

@app.route('/api/payee_accounts/<int:account_id>', methods=['PUT'])
@login_required
def update_payee_account(account_id):
    account = PayeeAccount.query.get_or_404(account_id)
    current_user = request.user
    if current_user.role != 'admin' and account.user_id != current_user.id:
        return jsonify({'error': '无权修改他人的收款信息'}), 403
    data = request.json
    if 'account_name' in data:
        account.account_name = data['account_name']
    if 'account_number' in data:
        account.account_number = data['account_number']
    if 'bank_short_name' in data:
        account.bank_short_name = data['bank_short_name']
    if 'bank_location' in data:
        account.bank_location = data['bank_location']
    if 'enabled' in data:
        account.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '收款信息更新成功'})

@app.route('/api/payee_accounts/<int:account_id>', methods=['DELETE'])
@role_required(['admin'])  # 或者也可以允许本人删除，改为 @login_required 并检查
def delete_payee_account(account_id):
    account = PayeeAccount.query.get_or_404(account_id)
    current_user = request.user
    if current_user.role != 'admin' and account.user_id != current_user.id:
        return jsonify({'error': '无权删除他人的收款信息'}), 403
    db.session.delete(account)
    db.session.commit()
    return jsonify({'message': '收款信息删除成功'})
# ---------- 报销单据 ----------
@app.route('/api/claims', methods=['GET'])
@login_required
def get_claims():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    view_mode = request.args.get('view_mode', 'all')
    
    current_user = request.user
    
    if view_mode == 'my':
        query = ExpenseClaim.query.filter_by(user_id=current_user.id)
        claims = query.order_by(ExpenseClaim.created_at.desc()).all()
    elif view_mode == 'pending_approval':
        # 找出所有 pending 状态且当前步骤所需角色与当前用户匹配的单据
        all_pending = ExpenseClaim.query.filter_by(status='pending').all()
        pending_claims = []
        for c in all_pending:
            if c.is_draft:
                continue            
            if c.user_id == current_user.id:
                continue
            # 获取该单的适用流程（根据申请人部门名称）
            dept_name = c.user.department.name if c.user.department else None
            flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
            if not flow:
                flow = ApprovalFlow.query.filter_by(enabled=True).first()
            if not flow:
                continue
            steps = json.loads(flow.steps)
            if c.current_step <= len(steps):
                needed_role = steps[c.current_step - 1]['role_code']
                if current_user.role == needed_role:
                    pending_claims.append(c)
        # 按创建时间倒序
        pending_claims.sort(key=lambda x: x.created_at, reverse=True)
        claims = pending_claims
    else:
        query = ExpenseClaim.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        claims = query.order_by(ExpenseClaim.created_at.desc()).all()
    
    result = []
    for claim in claims:
        # 获取该 claim 的流程 steps（与之前 pending_approval 逻辑类似）
        dept_name = claim.user.department.name if claim.user.department else None
        flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
        if not flow:
            flow = ApprovalFlow.query.filter_by(enabled=True).first()
        steps = json.loads(flow.steps) if flow and flow.steps else []
        required_role = None
        if steps and claim.current_step <= len(steps):
            required_role = steps[claim.current_step - 1].get('role_code')
        
        receipts = [{'id': r.id, 'filename': r.filename, 'original_name': r.original_name} for r in claim.receipts]
        approvals = [{'step': a.step, 'action': a.action, 'comment': a.comment, 'approver_name': a.approver.name if a.approver else '', 'approved_at': a.approved_at.isoformat() if a.approved_at else None} for a in claim.approvals]
        
        result.append({
            'id': claim.id,
            'document_number': claim.document_number,
            'user_id': claim.user_id,
            'user_name': claim.user.name,
            'user_department': claim.user.department.name if claim.user.department else None,
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
            'created_at': claim.created_at.isoformat(),
            'updated_at': claim.updated_at.isoformat(),
            'receipts': receipts,
            'approvals': approvals,
            'required_role': required_role,
            'is_draft': claim.is_draft,
            'expense_items': claim.expense_items_json,        
        })
    return jsonify(result)

@app.route('/api/claims/<int:claim_id>', methods=['GET'])
@login_required
def get_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    # 获取该单据的审批流程，并计算当前步骤需要的角色代码
    dept_name = claim.user.department.name if claim.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    steps = json.loads(flow.steps) if flow else []
    required_role = None
    if steps and claim.current_step <= len(steps):
        required_role = steps[claim.current_step - 1].get('role_code')
    
    # 查询借款冲账明细
    loan_details = []
    total_offset = 0.0
    for ld in claim.loan_details:
        loan = Loan.query.get(ld.loan_id)
        if loan:
            # 计算冲账后该借款单的剩余可核销金额（历史已核销 + 本次冲账）
            remaining_before = loan.amount - (loan.total_reimbursed or 0)
            loan_details.append({
                'document_number': loan.document_number,
                'offset_amount': ld.amount,
                'remaining_after_offset': remaining_before - ld.amount
            })
            total_offset += ld.amount
    actual_payee_amount = claim.amount - total_offset

    receipts = [{'id': r.id, 'filename': r.filename, 'original_name': r.original_name} for r in claim.receipts]
    approvals = [{'step': a.step, 'action': a.action, 'comment': a.comment, 'approver_name': a.approver.name if a.approver else '', 'approved_at': a.approved_at.isoformat() if a.approved_at else None} for a in claim.approvals]
    return jsonify({
        'id': claim.id,
        'document_number': claim.document_number,
        'user_id': claim.user_id,
        'user_name': claim.user.name,
        'user_department': claim.user.department.name if claim.user.department else None,
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
        'created_at': claim.created_at.isoformat(),
        'updated_at': claim.updated_at.isoformat(),
        'receipts': receipts,
        'approvals': approvals,
        'required_role': required_role,
        'is_draft': claim.is_draft,
        'loan_details': loan_details,
        'total_offset': total_offset,
        'actual_payee_amount': actual_payee_amount
    })

@app.route('/api/claims', methods=['POST'])
@login_required
def create_claim():
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
        files = request.files.getlist('receipts') if 'receipts' in request.files else []
        loan_details_str = data.get('loan_details', '[]')
        loan_details = json.loads(loan_details_str) if loan_details_str else []
    else:
        json_data = request.json
        files = []
        loan_details = json_data.get('loan_details', [])
        data = json_data

    # 获取 is_draft 参数
    is_draft_val = data.get('is_draft')
    if isinstance(is_draft_val, str):
        is_draft = is_draft_val.lower() == 'true'
    else:
        is_draft = bool(is_draft_val)

    document_number = generate_document_number()
    claim = ExpenseClaim(
        document_number=document_number,
        user_id=int(data.get('user_id')),
        department_id=int(data.get('department_id')) if data.get('department_id') else None,
        legal_person_id=int(data.get('legal_person_id')) if data.get('legal_person_id') else None,
        currency_id=int(data.get('currency_id')) if data.get('currency_id') else 1,
        payee_account_id=int(data.get('payee_account_id')) if data.get('payee_account_id') else None,
        amount=float(data.get('amount')),
        description=data.get('description', ''),
        category=data.get('category', '其他'),
        status='pending',
        current_step=1,
        is_draft=is_draft,
        expense_items_json=data.get('expense_items', '[]')
    )
    db.session.add(claim)
    db.session.flush()

    total_offset = 0.0
    for detail in loan_details:
        loan_id = detail['loan_id']
        offset_amount = float(detail['amount'])
        total_offset += offset_amount
        ld = LoanReimburseDetail(claim_id=claim.id, loan_id=loan_id, amount=offset_amount)
        db.session.add(ld)

    if total_offset > claim.amount:
        db.session.rollback()
        return jsonify({'error': '冲账总金额不能大于报销金额'}), 400

    if files:
        for receipt in files:
            if receipt.filename:
                filename = f"{claim.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{receipt.filename}"
                receipt.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                receipt_record = Receipt(claim_id=claim.id, filename=filename, original_name=receipt.filename)
                db.session.add(receipt_record)

    db.session.commit()
    return jsonify({'id': claim.id, 'document_number': document_number, 'message': '报销单创建成功'}), 201

@app.route('/api/claims/draft/<int:claim_id>', methods=['PUT'])
@login_required
def update_claim_draft(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    if not claim.is_draft or claim.user_id != current_user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    if 'amount' in data:
        claim.amount = float(data['amount'])
    if 'description' in data:
        claim.description = data['description']
    if 'category' in data:
        claim.category = data['category']
    if 'legal_person_id' in data:
        claim.legal_person_id = data['legal_person_id']
    if 'currency_id' in data:
        claim.currency_id = data['currency_id']
    if 'payee_account_id' in data:
        claim.payee_account_id = data['payee_account_id']
    if 'department_id' in data:
        claim.department_id = data['department_id']
    if 'expense_items' in data:
        claim.expense_items_json = data['expense_items']        
    claim.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})

@app.route('/api/claims/<int:claim_id>', methods=['PUT'])
@login_required
def update_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    
    if claim.status == 'rejected' and claim.user_id == current_user.id:
        data = request.json
        if 'amount' in data:
            claim.amount = float(data['amount'])
        if 'description' in data:
            claim.description = data['description']
        if 'category' in data:
            claim.category = data['category']
        if 'legal_person_id' in data:
            claim.legal_person_id = data['legal_person_id']
        if 'currency_id' in data:
            claim.currency_id = data['currency_id']
        if 'payee_account_id' in data:
            claim.payee_account_id = data['payee_account_id']
        claim.status = 'pending'
        claim.updated_at = datetime.now()
        db.session.commit()
        return jsonify({'message': '报销单已重新提交'})
    elif claim.user_id == current_user.id and claim.status == 'pending' and claim.current_step == 1 and not claim.approvals:
        data = request.json
        if 'amount' in data:
            claim.amount = float(data['amount'])
        if 'description' in data:
            claim.description = data['description']
        if 'category' in data:
            claim.category = data['category']
        if 'legal_person_id' in data:
            claim.legal_person_id = data['legal_person_id']
        if 'currency_id' in data:
            claim.currency_id = data['currency_id']
        if 'payee_account_id' in data:
            claim.payee_account_id = data['payee_account_id']
        claim.updated_at = datetime.now()
        db.session.commit()
        return jsonify({'message': '报销单更新成功'})
    else:
        return jsonify({'error': '只有申请人可以在特定条件下修改报销单'}), 403

@app.route('/api/claims/<int:claim_id>', methods=['DELETE'])
@login_required
def delete_claim(claim_id):
    claim = ExpenseClaim.query.get_or_404(claim_id)
    current_user = request.user
    # 允许管理员删除，或者申请人删除自己的且单据处于可删除状态（pending、第一步、无审批记录）
    if current_user.role == 'admin':
        # 管理员可以删除任何单据
        pass
    elif claim.user_id == current_user.id and claim.status == 'pending' and claim.current_step == 1 and len(claim.approvals) == 0:
        # 申请人可以删除自己未进入审批流程的单据
        pass
    else:
        return jsonify({'error': '无权删除此报销单'}), 403

    # 删除关联的票据文件
    for receipt in claim.receipts:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], receipt.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    db.session.delete(claim)
    db.session.commit()
    return jsonify({'message': '报销单删除成功'})


# ---------- 审批核心逻辑 ----------
@app.route('/api/approvals/<int:claim_id>', methods=['POST'])
@login_required
def approve_claim(claim_id):
    # 兼容 JSON 和 FormData
    if request.is_json:
        data = request.get_json()
        action = data.get('action')
        comment = data.get('comment', '')
    else:
        action = request.form.get('action')
        comment = request.form.get('comment', '')

    claim = ExpenseClaim.query.get_or_404(claim_id)
    approver = request.user

    # 获取申请人部门名称（字符串）
    dept_name = claim.user.department.name if claim.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    if not flow:
        return jsonify({'error': '未找到审批流程'}), 400

    steps = json.loads(flow.steps)

    # 状态检查
    if claim.status == 'approved':
        return jsonify({'error': '该报销单已审批完成'}), 400
    if claim.status == 'rejected' and claim.current_step > 1:
        return jsonify({'error': '该单据已被驳回，请等待申请人重新提交'}), 400

    # 不能审批自己的单子
    if approver.id == claim.user_id:
        return jsonify({'error': '不能审批自己的报销单'}), 400

    # 检查当前步骤权限
    if claim.current_step < 1 or claim.current_step > len(steps):
        return jsonify({'error': '审批流程步骤异常'}), 400
    required_role_code = steps[claim.current_step - 1]['role_code']
    if approver.role != required_role_code:
        return jsonify({'error': f'您没有权限进行此步骤的审批，需要角色：{required_role_code}'}), 403

    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400

    # 记录审批记录
    approval = ApprovalRecord(
        claim_id=claim_id,
        approver_id=approver.id,
        step=claim.current_step,
        action=action,
        comment=comment,
        approved_at=datetime.now()
    )
    db.session.add(approval)

    # 处理通过或驳回
    if action == 'approve':
        if claim.current_step == len(steps):
            claim.status = 'approved'
            # 更新借款单的已核销金额
            for detail in claim.loan_details:
                loan = Loan.query.get(detail.loan_id)
                if loan:
                    loan.total_reimbursed += detail.amount
        else:
            claim.current_step += 1
            claim.status = 'pending'
    elif action == 'reject':
        claim.status = 'rejected'
        claim.current_step = 1
    else:
        return jsonify({'error': '无效的审批动作'}), 400

    claim.updated_at = datetime.now()
    db.session.commit()

    return jsonify({'message': '审批完成', 'status': claim.status, 'current_step': claim.current_step})


# ---------- 审批流程配置（管理员） ----------
@app.route('/api/flows', methods=['GET'])
@role_required(['admin'])
def get_flows():
    flows = ApprovalFlow.query.all()
    return jsonify([{
        'id': f.id,
        'name': f.name,
        'department': f.department,
        'steps': f.steps,
        'enabled': f.enabled
    } for f in flows])

@app.route('/api/flows', methods=['POST'])
@role_required(['admin'])
def create_flow():
    data = request.json
    # 确保 steps 中的每个步骤都有 role_code
    for step in data['steps']:
        if not step.get('role_code'):
            return jsonify({'error': '每个步骤必须选择角色'}), 400
    flow = ApprovalFlow(
        name=data['name'],
        department=data.get('department', ''),
        steps=json.dumps(data['steps']),
        enabled=data.get('enabled', True)
    )
    db.session.add(flow)
    db.session.commit()
    return jsonify({'id': flow.id, 'message': '审批流程创建成功'}), 201

@app.route('/api/flows/<int:flow_id>', methods=['GET'])
@role_required(['admin'])
def get_flow(flow_id):
    flow = ApprovalFlow.query.get_or_404(flow_id)
    return jsonify({
        'id': flow.id,
        'name': flow.name,
        'department': flow.department,
        'steps': flow.steps,
        'enabled': flow.enabled
    })

@app.route('/api/flows/<int:flow_id>', methods=['PUT'])
@role_required(['admin'])
def update_flow(flow_id):
    flow = ApprovalFlow.query.get_or_404(flow_id)
    data = request.json
    if 'name' in data:
        flow.name = data['name']
    if 'department' in data:
        flow.department = data['department']
    if 'steps' in data:
        # 校验步骤角色
        for step in data['steps']:
            if not step.get('role_code'):
                return jsonify({'error': '每个步骤必须选择角色'}), 400
        flow.steps = json.dumps(data['steps'])
    if 'enabled' in data:
        flow.enabled = data['enabled']
    db.session.commit()
    return jsonify({'message': '审批流程更新成功'})

@app.route('/api/flows/<int:flow_id>', methods=['DELETE'])
@role_required(['admin'])
def delete_flow(flow_id):
    flow = ApprovalFlow.query.get_or_404(flow_id)
    db.session.delete(flow)
    db.session.commit()
    return jsonify({'message': '审批流程删除成功'})


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/api/departments/<int:dept_id>/legal_path', methods=['GET'])
@login_required
def get_department_legal_path(dept_id):
    dept = Department.query.get_or_404(dept_id)
    legal_person = None
    # 向上找第一个有 legal_person_id 的部门（或自己）
    cur = dept
    while cur:
        if cur.legal_person_id:
            legal_person = LegalPerson.query.get(cur.legal_person_id)
            break
        cur = cur.parent
    return jsonify({
        'department_id': dept.id,
        'department_name': dept.name,
        'legal_person': {
            'id': legal_person.id,
            'name': legal_person.name
        } if legal_person else None
    })

# ---------- 资产采购申请 ----------
@app.route('/api/next_purchase_number', methods=['GET'])
@login_required
def get_next_purchase_number():
    return jsonify({'document_number': generate_purchase_number()})

@app.route('/api/purchases', methods=['POST'])
@login_required
def create_purchase():
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form
        files = request.files.getlist('attachments') if 'attachments' in request.files else []
        contracts_str = data.get('contracts', '[]')
        items_str = data.get('items', '[]')
        contracts = json.loads(contracts_str)
        items = json.loads(items_str)
    else:
        return jsonify({'error': '只支持 multipart/form-data'}), 400

    is_draft_val = data.get('is_draft')
    if isinstance(is_draft_val, str):
        is_draft = is_draft_val.lower() == 'true'
    else:
        is_draft = bool(is_draft_val)

    document_number = generate_purchase_number()
    purchase = AssetPurchase(
        document_number=document_number,
        user_id=int(data.get('user_id')),
        department_id=int(data.get('department_id')) if data.get('department_id') else None,
        legal_person_id=int(data.get('legal_person_id')) if data.get('legal_person_id') else None,
        currency_id=int(data.get('currency_id')) if data.get('currency_id') else 1,
        payment_remark=data.get('payment_remark', ''),
        status='pending',
        current_step=1,
        is_draft=is_draft
    )
    db.session.add(purchase)
    db.session.flush()

    # 合同和明细保存（不变）
    for c in contracts:
        contract = AssetPurchaseContract(
            purchase_id=purchase.id,
            contract_number=c.get('contract_number', ''),
            contract_name=c.get('contract_name', ''),
            supplier_name=c.get('supplier_name', '')
        )
        db.session.add(contract)
    for item in items:
        purchase_item = AssetPurchaseItem(
            purchase_id=purchase.id,
            payment_unit=item.get('payment_unit', ''),
            purchase_type=item.get('purchase_type', ''),
            item_name=item.get('item_name', ''),
            quantity=int(item.get('quantity', 0)),
            contract_total_amount=float(item.get('contract_total_amount', 0)),
            requested_amount=float(item.get('requested_amount', 0))
        )
        db.session.add(purchase_item)
    for file in files:
        if file.filename:
            filename = f"purchase_{purchase.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            att = AssetPurchaseAttachment(purchase_id=purchase.id, filename=filename, original_name=file.filename)
            db.session.add(att)
        # 保存文件...
    db.session.commit()
    return jsonify({'id': purchase.id, 'document_number': document_number, 'message': '采购申请创建成功'}), 201

@app.route('/api/purchases', methods=['GET'])
@login_required
def get_purchases():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    view_mode = request.args.get('view_mode', 'all')
    current_user = request.user

    if view_mode == 'my':
        query = AssetPurchase.query.filter_by(user_id=current_user.id)
        purchases = query.order_by(AssetPurchase.created_at.desc()).all()
    elif view_mode == 'pending_approval':
        all_pending = AssetPurchase.query.filter_by(status='pending').all()
        pending = []
        for p in all_pending:
            if p.is_draft:
                continue            
            if p.user_id == current_user.id:
                continue
            dept_name = p.user.department.name if p.user.department else None
            flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
            if not flow:
                flow = ApprovalFlow.query.filter_by(enabled=True).first()
            if not flow:
                continue
            steps = json.loads(flow.steps)
            if p.current_step <= len(steps):
                needed_role = steps[p.current_step - 1].get('role_code')
                if current_user.role == needed_role:
                    pending.append(p)
        pending.sort(key=lambda x: x.created_at, reverse=True)
        purchases = pending
    else:
        query = AssetPurchase.query
        if user_id:
            query = query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        purchases = query.order_by(AssetPurchase.created_at.desc()).all()

    result = []
    for p in purchases:
        total_amount = sum(item.requested_amount for item in p.items)
        result.append({
            'id': p.id,
            'document_number': p.document_number,
            'user_name': p.user.name,
            'user_department': p.user.department.name if p.user.department else None,
            'department_name': p.department.name if p.department else None, 
            'legal_person_name': p.legal_person.name if p.legal_person else None,
            'currency_symbol': p.currency.symbol if p.currency else '¥',
            'total_amount': total_amount,
            'status': p.status,
            'created_at': p.created_at.isoformat(),
            'payment_remark': p.payment_remark,
            'is_draft': p.is_draft,           
        })
    return jsonify(result)

@app.route('/api/purchases/<int:purchase_id>', methods=['GET'])
@login_required
def get_purchase(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    dept_name = purchase.user.department.name if purchase.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    steps = json.loads(flow.steps) if flow else []
    required_role = None
    if steps and purchase.current_step <= len(steps):
        required_role = steps[purchase.current_step - 1].get('role_code')

    contracts = [{'id': c.id, 'contract_number': c.contract_number, 'contract_name': c.contract_name, 'supplier_name': c.supplier_name} for c in purchase.contracts]
    items = [{
        'id': i.id,
        'payment_unit': i.payment_unit,
        'purchase_type': i.purchase_type,
        'item_name': i.item_name,
        'quantity': i.quantity,
        'contract_total_amount': i.contract_total_amount,
        'requested_amount': i.requested_amount
    } for i in purchase.items]
    attachments = [{'id': a.id, 'filename': a.filename, 'original_name': a.original_name} for a in purchase.attachments]
    approvals = [{
        'step': a.step, 'action': a.action, 'comment': a.comment,
        'approver_name': a.approver.name if a.approver else '',
        'approved_at': a.approved_at.isoformat() if a.approved_at else None
    } for a in purchase.approvals]

    return jsonify({
        'id': purchase.id,
        'document_number': purchase.document_number,
        'user_id': purchase.user_id,
        'user_name': purchase.user.name,
        'user_department': purchase.user.department.name if purchase.user.department else None,
        'department_id': purchase.department_id,
        'legal_person_id': purchase.legal_person_id,
        'legal_person_name': purchase.legal_person.name if purchase.legal_person else None,
        'currency_id': purchase.currency_id,
        'currency_symbol': purchase.currency.symbol if purchase.currency else '¥',
        'payment_remark': purchase.payment_remark,
        'status': purchase.status,
        'current_step': purchase.current_step,
        'created_at': purchase.created_at.isoformat(),
        'contracts': contracts,
        'items': items,
        'attachments': attachments,
        'approvals': approvals,
        'required_role': required_role
    })

@app.route('/api/purchase_approvals/<int:purchase_id>', methods=['POST'])
@login_required
def approve_purchase(purchase_id):
    if request.is_json:
        data = request.get_json()
        action = data.get('action')
        comment = data.get('comment', '')
    else:
        action = request.form.get('action')
        comment = request.form.get('comment', '')

    purchase = AssetPurchase.query.get_or_404(purchase_id)
    approver = request.user

    dept_name = purchase.user.department.name if purchase.user.department else None
    flow = ApprovalFlow.query.filter_by(department=dept_name, enabled=True).first()
    if not flow:
        flow = ApprovalFlow.query.filter_by(enabled=True).first()
    if not flow:
        return jsonify({'error': '未找到审批流程'}), 400

    steps = json.loads(flow.steps)

    if purchase.status == 'approved':
        return jsonify({'error': '该采购单已审批完成'}), 400
    if purchase.status == 'rejected' and purchase.current_step > 1:
        return jsonify({'error': '该单据已被驳回，请等待申请人重新提交'}), 400
    if approver.id == purchase.user_id:
        return jsonify({'error': '不能审批自己的采购单'}), 400

    if purchase.current_step < 1 or purchase.current_step > len(steps):
        return jsonify({'error': '审批流程步骤异常'}), 400
    required_role_code = steps[purchase.current_step - 1].get('role_code')
    if approver.role != required_role_code:
        return jsonify({'error': f'您没有权限进行此步骤的审批，需要角色：{required_role_code}'}), 403

    if not action:
        return jsonify({'error': '缺少审批操作参数'}), 400

    approval = AssetPurchaseApprovalRecord(
        purchase_id=purchase_id,
        approver_id=approver.id,
        step=purchase.current_step,
        action=action,
        comment=comment,
        approved_at=datetime.now()
    )
    db.session.add(approval)

    if action == 'approve':
        if purchase.current_step == len(steps):
            purchase.status = 'approved'
        else:
            purchase.current_step += 1
            purchase.status = 'pending'
    elif action == 'reject':
        purchase.status = 'rejected'
        purchase.current_step = 1
    else:
        return jsonify({'error': '无效的审批动作'}), 400

    purchase.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '审批完成', 'status': purchase.status, 'current_step': purchase.current_step})

@app.route('/api/purchases/draft/<int:purchase_id>', methods=['PUT'])
@login_required
def update_purchase_draft(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    current_user = request.user
    if not purchase.is_draft or purchase.user_id != current_user.id:
        return jsonify({'error': '只有草稿且本人可以修改'}), 403
    data = request.json
    if 'legal_person_id' in data:
        purchase.legal_person_id = data['legal_person_id']
    if 'currency_id' in data:
        purchase.currency_id = data['currency_id']
    if 'payment_remark' in data:
        purchase.payment_remark = data['payment_remark']
    # 更新合同和明细（替换）
    for c in purchase.contracts:
        db.session.delete(c)
    for i in purchase.items:
        db.session.delete(i)
    contracts = data.get('contracts', [])
    for c in contracts:
        new_c = AssetPurchaseContract(
            purchase_id=purchase.id,
            contract_number=c.get('contract_number', ''),
            contract_name=c.get('contract_name', ''),
            supplier_name=c.get('supplier_name', '')
        )
        db.session.add(new_c)
    items = data.get('items', [])
    for i in items:
        new_i = AssetPurchaseItem(
            purchase_id=purchase.id,
            payment_unit=i.get('payment_unit', ''),
            purchase_type=i.get('purchase_type', ''),
            item_name=i.get('item_name', ''),
            quantity=i.get('quantity', 0),
            contract_total_amount=float(i.get('contract_total_amount', 0)),
            requested_amount=float(i.get('requested_amount', 0))
        )
        db.session.add(new_i)
    purchase.updated_at = datetime.now()
    db.session.commit()
    return jsonify({'message': '草稿更新成功'})

@app.route('/api/purchases/<int:purchase_id>', methods=['DELETE'])
@login_required
def delete_purchase(purchase_id):
    purchase = AssetPurchase.query.get_or_404(purchase_id)
    current_user = request.user
    # 允许：管理员 或 本人且是草稿
    if not (current_user.role == 'admin' or (purchase.user_id == current_user.id and purchase.is_draft)):
        return jsonify({'error': '无权删除'}), 403
    for att in purchase.attachments:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], att.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    db.session.delete(purchase)
    db.session.commit()
    return jsonify({'message': '采购申请删除成功'})

# ---------- 付款处理中心 ----------
@app.route('/api/payment_center', methods=['GET'])
@login_required
def get_payment_center():
    status_filter = request.args.get('status')
    if status_filter not in ['unpaid', 'paid']:
        return jsonify({'error': '缺少 status 参数'}), 400

    if status_filter == 'unpaid':
        claims = ExpenseClaim.query.filter_by(status='approved', payment_date=None).all()
        loans = Loan.query.filter_by(status='approved', payment_date=None).all()
        purchases = AssetPurchase.query.filter_by(status='approved', payment_date=None).all()
    else:
        claims = ExpenseClaim.query.filter(ExpenseClaim.payment_date != None).all()
        loans = Loan.query.filter(Loan.payment_date != None).all()
        purchases = AssetPurchase.query.filter(AssetPurchase.payment_date != None).all()

    result = []
    # 报销单
    for c in claims:
        total_offset = sum(ld.amount for ld in c.loan_details)
        actual_amount = c.amount - total_offset
        result.append({
            'id': c.id,
            'type': 'reimbursement',
            'type_name': '报销',
            'document_number': c.document_number,
            'applicant': c.user.name,
            'apply_date': c.created_at.strftime('%Y-%m-%d'),
            'payee_name': c.payee_account.account_name if c.payee_account else '',
            'payee_account': c.payee_account.account_number if c.payee_account else '',
            'bank_name': c.payee_account.bank_short_name if c.payee_account else '',
            'amount': actual_amount,
            'legal_person': c.legal_person.name if c.legal_person else '',
            'payment_date': c.payment_date.strftime('%Y-%m-%d') if c.payment_date else None
        })
    # 借款单
    for l in loans:
        result.append({
            'id': l.id,
            'type': 'loan',
            'type_name': '借款',
            'document_number': l.document_number,
            'applicant': l.user.name,
            'apply_date': l.created_at.strftime('%Y-%m-%d'),
            'payee_name': l.payee_account.account_name if l.payee_account else '',
            'payee_account': l.payee_account.account_number if l.payee_account else '',
            'bank_name': l.payee_account.bank_short_name if l.payee_account else '',
            'amount': l.amount,
            'legal_person': l.legal_person.name if l.legal_person else '',
            'payment_date': l.payment_date.strftime('%Y-%m-%d') if l.payment_date else None
        })
    # 采购申请
    for p in purchases:
        total_amount = sum(item.requested_amount for item in p.items)
        result.append({
            'id': p.id,
            'type': 'purchase',
            'type_name': '采购申请',
            'document_number': p.document_number,
            'applicant': p.user.name,
            'apply_date': p.created_at.strftime('%Y-%m-%d'),
            'payee_name': '',  # 采购申请没有收款账户信息，留空
            'payee_account': '',
            'bank_name': '',
            'amount': total_amount,
            'legal_person': p.legal_person.name if p.legal_person else '',
            'payment_date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else None
        })
    result.sort(key=lambda x: x['apply_date'], reverse=True)
    return jsonify(result)

@app.route('/api/payment_register', methods=['POST'])
@login_required
def payment_register():
    data = request.json
    items = data.get('items', [])
    payment_date_str = data.get('payment_date', None)
    if not items:
        return jsonify({'error': '请选择要登记的单据'}), 400

    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
        except:
            return jsonify({'error': '日期格式错误'}), 400
    else:
        payment_date = datetime.now().date()

    success_count = 0
    for item in items:
        type_ = item.get('type')
        id_ = item.get('id')
        if type_ == 'reimbursement':
            record = ExpenseClaim.query.get(id_)
        elif type_ == 'loan':
            record = Loan.query.get(id_)
        elif type_ == 'purchase':
            record = AssetPurchase.query.get(id_)            
        else:
            continue
        if record and record.status == 'approved' and record.payment_date is None:
            record.payment_date = payment_date
            success_count += 1
    db.session.commit()
    return jsonify({'message': f'成功登记 {success_count} 笔付款'}), 200
@app.route('/api/receipts/<int:receipt_id>', methods=['DELETE'])
@login_required
def delete_receipt(receipt_id):
    receipt = Receipt.query.get_or_404(receipt_id)
    claim = receipt.claim
    # 只有草稿状态且是本人或管理员可以删除附件
    if not claim.is_draft or (claim.user_id != request.user.id and request.user.role != 'admin'):
        return jsonify({'error': '无权删除此附件'}), 403
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], receipt.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(receipt)
    db.session.commit()
    return jsonify({'message': '附件删除成功'})
if __name__ == '__main__':
    app.run(debug=True)