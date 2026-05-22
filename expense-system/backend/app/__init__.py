"""报销支付系统 — Flask 应用工厂"""
import json
import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from .config import Config

db = SQLAlchemy()
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # 确保 instance 和 uploads 目录存在
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    CORS(app,
         origins=app.config['CORS_ORIGINS'],
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    # 注册蓝图
    from .routes.auth import auth_bp
    from .routes.system import system_bp
    from .routes.claims import claims_bp
    from .routes.loans import loans_bp
    from .routes.purchases import purchases_bp
    # admin 路由整合在 system 蓝图中
    from .routes.payment import payment_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(claims_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(payment_bp)

    # 上传文件访问
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # OPTIONS 预检通配
    @app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
    @app.route('/<path:path>', methods=['OPTIONS'])
    def options_handler(path):
        return '', 200

    # 初始化数据库与种子数据
    with app.app_context():
        _init_database(app)

    return app


def _init_database(app):
    from .models import (Role, User, Department, LegalPerson, Currency,
                         ExpenseType, OperationType, PayeeAccount,
                         ExpenseClaim, Receipt, ApprovalFlow, ApprovalRecord,
                         Loan, LoanApprovalRecord, LoanReimburseDetail,
                         AssetPurchase, AssetPurchaseContract,
                         AssetPurchaseItem, AssetPurchaseAttachment,
                         AssetPurchaseApprovalRecord)

    db.create_all()

    # ── 种子数据（仅在首次运行时生效） ──
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
        depts = [
            Department(name='技术部', code='TECH', description='负责技术研发和维护'),
            Department(name='财务部', code='FIN', description='负责财务管理和报销审核'),
            Department(name='管理层', code='ADMIN', description='公司管理层'),
            Department(name='人力资源部', code='HR', description='负责人员招聘和管理'),
        ]
        db.session.add_all(depts)
        db.session.commit()

    if not User.query.first():
        db.session.add_all([
            User(name='张三', email='zhangsan@company.com', username='zhangsan',
                 password='123456', role_id=Role.query.filter_by(code='employee').first().id,
                 department_id=1),
            User(name='李四', email='lisi@company.com', username='lisi',
                 password='123456',
                 role_id=Role.query.filter_by(code='department_manager').first().id,
                 department_id=1),
            User(name='王五', email='wangwu@company.com', username='wangwu',
                 password='123456', role_id=Role.query.filter_by(code='finance_staff').first().id,
                 department_id=2),
            User(name='赵六', email='zhaoliu@company.com', username='zhaoliu',
                 password='123456',
                 role_id=Role.query.filter_by(code='finance_manager').first().id,
                 department_id=3),
            User(name='陈七', email='chenqi@company.com', username='chenqi',
                 password='123456', role_id=Role.query.filter_by(code='general_manager').first().id,
                 department_id=3),
            User(name='薛总', email='xuezf@company.com', username='xuezf',
                 password='123123', role_id=Role.query.filter_by(code='admin').first().id,
                 department_id=3),
        ])
        db.session.commit()

    if not ExpenseType.query.first():
        db.session.add_all([
            ExpenseType(code='TRAVEL', name='差旅费', description='出差相关费用'),
            ExpenseType(code='OFFICE', name='办公用品', description='办公物资采购'),
            ExpenseType(code='MEAL', name='餐饮费', description='业务招待餐饮'),
            ExpenseType(code='TRANSPORT', name='交通费', description='交通出行费用'),
            ExpenseType(code='OTHER', name='其他', description='其他费用'),
        ])
        db.session.commit()

    if not OperationType.query.first():
        db.session.add_all([
            OperationType(code='SALES', name='销售业务', description='产品销售相关业务'),
            OperationType(code='PRODUCTION', name='生产业务', description='产品生产相关业务'),
            OperationType(code='MANUFACTURE', name='制造业务', description='制造加工相关业务'),
            OperationType(code='MANAGEMENT', name='管理业务', description='企业管理相关业务'),
            OperationType(code='PRE_SALES', name='售前业务', description='售前支持相关业务'),
            OperationType(code='R_D', name='研发业务', description='研究开发相关业务'),
        ])
        db.session.commit()

    if not LegalPerson.query.first():
        db.session.add_all([
            LegalPerson(name='北京科技有限公司',
                        unified_code='91110108MA00000000',
                        address='北京市海淀区中关村科技园', contact='张三',
                        phone='13800138000'),
            LegalPerson(name='上海贸易有限公司',
                        unified_code='91310109MA11111111',
                        address='上海市浦东新区陆家嘴', contact='李四',
                        phone='13900139000'),
        ])
        db.session.commit()

    if not Currency.query.first():
        db.session.add_all([
            Currency(code='CNY', name='人民币', symbol='¥', rate=1.0),
            Currency(code='USD', name='美元', symbol='$', rate=7.24),
            Currency(code='EUR', name='欧元', symbol='€', rate=7.86),
            Currency(code='GBP', name='英镑', symbol='£', rate=9.12),
        ])
        db.session.commit()

    if not PayeeAccount.query.first():
        admin_user = User.query.filter_by(username='xuezf').first()
        admin_id = admin_user.id if admin_user else 1
        db.session.add_all([
            PayeeAccount(account_name='北京科技有限公司',
                         account_number='6222021234567890123',
                         bank_short_name='工商银行', bank_location='北京',
                         user_id=admin_id),
            PayeeAccount(account_name='上海贸易有限公司',
                         account_number='6228481234567890456',
                         bank_short_name='农业银行', bank_location='上海',
                         user_id=admin_id),
        ])
        db.session.commit()

    if not ApprovalFlow.query.first():
        tech_steps = [
            {"step": 1, "role_code": "department_manager", "description": "部门经理审批"},
            {"step": 2, "role_code": "finance_staff", "description": "财务会计审核"},
            {"step": 3, "role_code": "finance_manager", "description": "财务经理审批"},
            {"step": 4, "role_code": "general_manager", "description": "总经理审批"},
        ]
        db.session.add_all([
            ApprovalFlow(name='标准报销流程-技术部', department='技术部',
                         steps=json.dumps(tech_steps)),
            ApprovalFlow(name='标准报销流程-通用', department='',
                         steps=json.dumps(tech_steps)),
        ])
        db.session.commit()

    logger.info('数据库初始化完成，种子数据已就绪')
