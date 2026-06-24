from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from models import db


class User(UserMixin, db.Model):
    """用户模型"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    employee_id = Column(String(20), unique=True)
    email = Column(String(100))
    phone = Column(String(20))
    role = Column(String(20), default='employee')  # admin / employee
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    @property
    def is_admin(self):
        return self.role and self.role.strip() == 'admin'

    # 关联关系
    documents = db.relationship('Document', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_sessions = db.relationship('ChatSession', backref='user', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'employee_id': self.employee_id or '',
            'email': self.email or '',
            'phone': self.phone or '',
            'role': self.role or 'employee',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }

    def __repr__(self):
        return f'<User {self.username}>'
