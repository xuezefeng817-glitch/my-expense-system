"""数据模型 — 所有 SQLAlchemy ORM 模型"""
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from . import db


# ═══════════════════════════════════════════════════════════════════
# 基础数据
# ═══════════════════════════════════════════════════════════════════

class Role(db.Model):
    __tablename__ = 'role'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    users = db.relationship('User', backref='role_ref', lazy=True)


class Department(db.Model):
    __tablename__ = 'department'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20))
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'), nullable=True)
    children = db.relationship('Department', backref=db.backref('parent', remote_side=[id]))
    legal_person = db.relationship('LegalPerson', backref='departments')


class LegalPerson(db.Model):
    __tablename__ = 'legal_person'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unified_code = db.Column(db.String(50), unique=True)
    address = db.Column(db.String(200))
    contact = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    enabled = db.Column(db.Boolean, default=True)


class Currency(db.Model):
    __tablename__ = 'currency'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    symbol = db.Column(db.String(10))
    rate = db.Column(db.Float, default=1.0)
    enabled = db.Column(db.Boolean, default=True)


class ExpenseType(db.Model):
    __tablename__ = 'expense_type'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)


class OperationType(db.Model):
    __tablename__ = 'operation_type'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    enabled = db.Column(db.Boolean, default=True)


class PayeeAccount(db.Model):
    __tablename__ = 'payee_account'
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(50), unique=True, nullable=False)
    bank_short_name = db.Column(db.String(100))
    bank_location = db.Column(db.String(100))
    enabled = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('payee_accounts', lazy=True))


# ═══════════════════════════════════════════════════════════════════
# 用户（密码自动哈希）
# ═══════════════════════════════════════════════════════════════════

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    department = db.relationship('Department', backref=db.backref('users', lazy=True))

    # ── password 属性：自动完成哈希 ──
    @property
    def password(self):
        raise AttributeError('密码不可读')

    @password.setter
    def password(self, plaintext):
        self.password_hash = generate_password_hash(plaintext)

    def check_password(self, plaintext):
        return check_password_hash(self.password_hash, plaintext)

    @property
    def role(self):
        return self.role_ref.code if self.role_ref else None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'username': self.username,
            'role': self.role,
            'role_id': self.role_id,
            'role_name': self.role_ref.name if self.role_ref else '',
            'department_id': self.department_id,
            'department': self.department.name if self.department else None,
        }


# ═══════════════════════════════════════════════════════════════════
# 审批流程
# ═══════════════════════════════════════════════════════════════════

class ApprovalFlow(db.Model):
    __tablename__ = 'approval_flow'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50))
    steps = db.Column(db.Text)  # JSON 字符串
    enabled = db.Column(db.Boolean, default=True)

    def get_steps(self):
        return json.loads(self.steps) if self.steps else []


# ═══════════════════════════════════════════════════════════════════
# 报销单
# ═══════════════════════════════════════════════════════════════════

class ExpenseClaim(db.Model):
    __tablename__ = 'expense_claim'
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
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)
    expense_items_json = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref=db.backref('claims', lazy=True))
    department = db.relationship('Department', backref=db.backref('claims', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('claims', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('claims', lazy=True))
    payee_account = db.relationship('PayeeAccount', backref=db.backref('claims', lazy=True))


class Receipt(db.Model):
    __tablename__ = 'receipt'
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    claim = db.relationship('ExpenseClaim', backref=db.backref('receipts', lazy=True))


class ApprovalRecord(db.Model):
    __tablename__ = 'approval_record'
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    step = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20))
    comment = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    claim = db.relationship('ExpenseClaim', backref=db.backref('approvals', lazy=True))
    approver = db.relationship('User', backref=db.backref('approval_records', lazy=True))


# ═══════════════════════════════════════════════════════════════════
# 借款单
# ═══════════════════════════════════════════════════════════════════

class Loan(db.Model):
    __tablename__ = 'loan'
    id = db.Column(db.Integer, primary_key=True)
    document_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    legal_person_id = db.Column(db.Integer, db.ForeignKey('legal_person.id'))
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'), default=1)
    payee_account_id = db.Column(db.Integer, db.ForeignKey('payee_account.id'))
    amount = db.Column(db.Float, nullable=False)
    purpose = db.Column(db.Text)
    category = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')
    current_step = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)
    loan_items_json = db.Column(db.Text, nullable=True)
    total_reimbursed = db.Column(db.Float, default=0.0)

    user = db.relationship('User', backref=db.backref('loans', lazy=True))
    department = db.relationship('Department', backref=db.backref('loans', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('loans', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('loans', lazy=True))
    payee_account = db.relationship('PayeeAccount', backref=db.backref('loans', lazy=True))


class LoanApprovalRecord(db.Model):
    __tablename__ = 'loan_approval_record'
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
    __tablename__ = 'loan_reimburse_detail'
    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('expense_claim.id'), nullable=False)
    loan_id = db.Column(db.Integer, db.ForeignKey('loan.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    claim = db.relationship('ExpenseClaim', backref=db.backref('loan_details', lazy=True))
    loan = db.relationship('Loan', backref=db.backref('reimburse_details', lazy=True))


# ═══════════════════════════════════════════════════════════════════
# 资产采购单
# ═══════════════════════════════════════════════════════════════════

class AssetPurchase(db.Model):
    __tablename__ = 'asset_purchase'
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
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    payment_date = db.Column(db.DateTime, nullable=True)
    is_draft = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref=db.backref('purchases', lazy=True))
    department = db.relationship('Department', backref=db.backref('purchases', lazy=True))
    legal_person = db.relationship('LegalPerson', backref=db.backref('purchases', lazy=True))
    currency = db.relationship('Currency', backref=db.backref('purchases', lazy=True))


class AssetPurchaseContract(db.Model):
    __tablename__ = 'asset_purchase_contract'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    contract_number = db.Column(db.String(50))
    contract_name = db.Column(db.String(200))
    supplier_name = db.Column(db.String(200))
    purchase = db.relationship('AssetPurchase', backref=db.backref('contracts', lazy=True, cascade='all, delete-orphan'))


class AssetPurchaseItem(db.Model):
    __tablename__ = 'asset_purchase_item'
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
    __tablename__ = 'asset_purchase_attachment'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200))
    purchase = db.relationship('AssetPurchase', backref=db.backref('attachments', lazy=True, cascade='all, delete-orphan'))


class AssetPurchaseApprovalRecord(db.Model):
    __tablename__ = 'asset_purchase_approval_record'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('asset_purchase.id'), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    step = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20))
    comment = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    purchase = db.relationship('AssetPurchase', backref=db.backref('approvals', lazy=True))
    approver = db.relationship('User', backref=db.backref('purchase_approval_records', lazy=True))
