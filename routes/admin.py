"""
管理后台路由 - 数据统计、用户管理
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func as sa_func
from models import db
from models.user import User
from models.document import Document, ChatSession, ChatMessage, ChatFeedback

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """管理员权限装饰器"""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"code": 403, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/stats", methods=["GET"])
@login_required
@admin_required
def get_stats():
    """获取系统总览统计"""
    total_users = User.query.count()
    total_docs = Document.query.count()
    total_sessions = ChatSession.query.count()
    total_messages = ChatMessage.query.count()

    # 今日活跃用户（今天有发消息的不同用户数）
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    active_today = (
        db.session.query(sa_func.count(sa_func.distinct(ChatSession.user_id)))
        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .filter(ChatMessage.created_at >= today)
        .scalar()
        or 0
    )

    return jsonify(
        {
            "code": 200,
            "data": {
                "total_users": total_users,
                "total_docs": total_docs,
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "active_today": active_today,
            },
        }
    )


@admin_bp.route("/trend", methods=["GET"])
@login_required
@admin_required
def get_trend():
    """获取最近7天的对话消息趋势"""
    days = []
    counts = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for i in range(6, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        count = ChatMessage.query.filter(
            ChatMessage.created_at >= day_start, ChatMessage.created_at < day_end
        ).count()
        days.append(day_start.strftime("%m-%d"))
        counts.append(count)

    return jsonify(
        {
            "code": 200,
            "data": {
                "days": days,
                "counts": counts,
            },
        }
    )


@admin_bp.route("/doc-types", methods=["GET"])
@login_required
@admin_required
def get_doc_types():
    """获取文档类型分布"""
    results = (
        db.session.query(Document.file_type, sa_func.count(Document.id))
        .group_by(Document.file_type)
        .all()
    )

    return jsonify(
        {"code": 200, "data": [{"name": r[0], "value": r[1]} for r in results]}
    )


@admin_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def get_users():
    """获取所有用户列表及统计"""
    users = User.query.order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        doc_count = Document.query.filter_by(user_id=u.id).count()
        session_count = ChatSession.query.filter_by(user_id=u.id).count()
        user_data = u.to_dict()
        user_data["doc_count"] = doc_count
        user_data["session_count"] = session_count
        user_data["is_active"] = u.is_active
        result.append(user_data)

    return jsonify({"code": 200, "data": result})


@admin_bp.route("/users/<int:user_id>/role", methods=["PUT"])
@login_required
@admin_required
def toggle_role(user_id):
    """设置用户角色"""
    # select * from user where user_id = 8
    user = User.query.get(user_id)
    if not user:
        return jsonify({"code": 404, "message": "用户不存在"}), 404
    if user.id == current_user.id:
        return jsonify({"code": 400, "message": "不能修改自己的角色"}), 400

    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "").strip()

    if new_role not in ("admin", "employee"):
        return jsonify({"code": 400, "message": "无效的角色值"}), 400

    user.role = new_role
    db.session.commit()
    return jsonify(
        {"code": 200, "message": f"角色已设置为 {new_role}", "data": {"role": new_role}}
    )


@admin_bp.route("/users/<int:user_id>/status", methods=["PUT"])
@login_required
@admin_required
def toggle_status(user_id):
    """冻结/解冻用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"code": 404, "message": "用户不存在"}), 404
    if user.id == current_user.id:
        return jsonify({"code": 400, "message": "不能冻结自己"}), 400
    if user.role == "admin":
        return jsonify({"code": 400, "message": "无法冻结管理员账户"}), 400
    user.is_active = not user.is_active

    db.session.commit()

    status_text = "已启用" if user.is_active else "已冻结"
    return jsonify(
        {"code": 200, "message": status_text, "data": {"is_active": user.is_active}}
    )


@admin_bp.route("/feedback-stats", methods=["GET"])
@login_required
@admin_required
def feedback_stats():
    """获取反馈统计"""
    total = ChatFeedback.query.count()
    up_count = ChatFeedback.query.filter_by(rating="up").count()
    down_count = ChatFeedback.query.filter_by(rating="down").count()
    approval_rate = round(up_count / total * 100, 1) if total > 0 else 0

    # 最近差评列表（最多20条）
    bad_feedbacks = (
        db.session.query(ChatFeedback, ChatMessage, User)
        .join(ChatMessage, ChatFeedback.message_id == ChatMessage.id)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .join(User, ChatSession.user_id == User.id)
        .filter(ChatFeedback.rating == "down")
        .order_by(ChatFeedback.created_at.desc())
        .limit(20)
        .all()
    )

    bad_list = [
        {
            "username": u.username,
            "content": m.content,
            "created_at": (
                fb.created_at.strftime("%Y-%m-%d %H:%M") if fb.created_at else "-"
            ),
        }
        for fb, m, u in bad_feedbacks
    ]

    return jsonify(
        {
            "code": 200,
            "data": {
                "total": total,
                "up": up_count,
                "down": down_count,
                "approval_rate": approval_rate,
                "bad_list": bad_list,
            },
        }
    )
