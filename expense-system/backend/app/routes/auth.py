"""认证路由 — 登录 / 退出 / 当前用户"""
from flask import Blueprint, request, jsonify
import logging

from ..models import User
from ..auth import login_required, create_token

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


@auth_bp.route('/api/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    if not username and request.json:
        username = request.json.get('username')
    if not password and request.json:
        password = request.json.get('password')

    logger.info("登录请求 - username: %s", username)

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': '用户名或密码错误'}), 401

    token = create_token(user)

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
            'department': user.department.name if user.department else None,
        }
    })


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message': '退出登录成功'})


@auth_bp.route('/api/current_user', methods=['GET'])
@login_required
def get_current_user():
    user = request.user
    return jsonify(user.to_dict())
