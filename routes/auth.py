"""
认证路由 - 用户登录/注册/登出/个人信息
"""
from datetime import datetime
import re
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
import bcrypt
from models import db
from models.user import User

auth_bp = Blueprint('auth', __name__)


def _generate_employee_id():
    """生成工号，格式：UTU + 年份 + 3位序号，如 UTU2026001"""
    year = datetime.now().strftime('%Y')
    prefix = f'UTU{year}'

    # 查找当前年份最大的工号
    last_user = User.query.filter(
        User.employee_id.like(f'{prefix}%')
    ).order_by(User.employee_id.desc()).first()

    if last_user and last_user.employee_id:
        # 提取序号部分并 +1
        seq = int(last_user.employee_id[len(prefix):]) + 1
    else:
        seq = 1

    return f'{prefix}{seq:03d}'


def _validate_password(password):
    """密码规则：8-12位，只允许 a-zA-Z0-9 和特殊字符 @._$"""
    if len(password) < 8:
        return '密码长度不能少于 8 位'
    if len(password) > 12:
        return '密码长度不能超过 12 位'
    if not re.match(r'^[a-zA-Z0-9@._$]+$', password):
        return '密码只能包含字母、数字和特殊字符 @ . _ $'
    return None


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': '请求数据为空'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400

    user = User.query.filter_by(username=username).first()
    print(str(user))
    # {user(id=xxxx,username=kkkkk,,,,,,,,,)}
    if not user:
        return jsonify({'code': 401, 'message': '用户名或密码错误'}), 401

    # 验证密码
    if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return jsonify({'code': 401, 'message': '用户名或密码错误'}), 401

    if not user.is_active:
        return jsonify({'code': 403, 'message': '账号已被禁用'}), 403
    # 登录成功后，将user对象保存到Cookie中
    login_user(user, remember=True)
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': user.to_dict()
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': '请求数据为空'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400

    if len(username) < 3 or len(username) > 50:
        return jsonify({'code': 400, 'message': '用户名长度应在 3-50 之间'}), 400

    pwd_err = _validate_password(password)
    if pwd_err:
        return jsonify({'code': 400, 'message': pwd_err}), 400

    # 检查用户名是否已存在
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'code': 409, 'message': '用户名已存在'}), 409

    # 密码加密 (论文 5.1节要求：12轮工作因子的 bcrypt 算法)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

    # 生成工号
    employee_id = _generate_employee_id()

    # 创建用户
    new_user = User(
        username=username,
        password_hash=password_hash,
        employee_id=employee_id,
        email=email if email else None
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        'code': 200,
        'message': f'注册成功，您的工号为 {employee_id}',
        'data': new_user.to_dict()
    })


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """用户登出"""
    logout_user()
    return jsonify({'code': 200, 'message': '登出成功'})


@auth_bp.route('/status', methods=['GET'])
def auth_status():
    """检查登录状态"""
    if current_user.is_authenticated:
        return jsonify({
            'code': 200,
            'logged_in': True,
            'data': current_user.to_dict()
        })
    return jsonify({'code': 200, 'logged_in': False})


@auth_bp.route('/profile', methods=['GET'])
@login_required
def get_profile():
    """获取个人信息"""
    return jsonify({
        'code': 200,
        'data': current_user.to_dict()
    })


@auth_bp.route('/profile', methods=['PUT'])
@login_required
def update_profile():
    """修改个人信息（手机号、邮箱、密码）"""
    data = request.get_json()
    if not data:
        return jsonify({'code': 400, 'message': '请求数据为空'}), 400

    # 更新邮箱
    if 'email' in data:
        current_user.email = data['email'].strip() or None

    # 更新手机号
    if 'phone' in data:
        current_user.phone = data['phone'].strip() or None

    # 更新密码
    if data.get('new_password'):
        old_password = data.get('old_password', '')
        if not old_password:
            return jsonify({'code': 400, 'message': '请输入旧密码'}), 400

        if not bcrypt.checkpw(old_password.encode('utf-8'), current_user.password_hash.encode('utf-8')):
            return jsonify({'code': 400, 'message': '旧密码不正确'}), 400

        new_password = data['new_password'].strip()
        pwd_err = _validate_password(new_password)
        if pwd_err:
            return jsonify({'code': 400, 'message': pwd_err}), 400

        # 修改密码时同样使用 12 轮 bcrypt
        current_user.password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'), bcrypt.gensalt(rounds=12)
        ).decode('utf-8')

    db.session.commit()

    return jsonify({
        'code': 200,
        'message': '个人信息更新成功',
        'data': current_user.to_dict()
    })
