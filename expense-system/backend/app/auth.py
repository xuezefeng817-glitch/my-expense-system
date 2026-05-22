"""认证装饰器和工具函数"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import jwt
from flask import request, jsonify, current_app

from .models import User


def login_required(f):
    """要求登录的装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if user is None:
            return jsonify({'error': '未登录，请先登录'}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """要求指定角色才能访问的装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = _get_current_user()
            if user is None:
                return jsonify({'error': '未登录，请先登录'}), 401
            if user.role not in roles:
                return jsonify({'error': '权限不足'}), 403
            request.user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


def _get_current_user():
    """从请求头解析 token 并返回 User 对象，认证失败返回 None"""
    token = request.headers.get('Authorization')
    if not token:
        return None
    try:
        token = token.replace('Bearer ', '')
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return User.query.get(payload['user_id'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def create_token(user):
    """为用户签发 JWT token"""
    expires = datetime.now(timezone.utc) + timedelta(
        hours=current_app.config['JWT_EXPIRATION_HOURS']
    )
    token = jwt.encode({
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'exp': expires,
    }, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
    return token
