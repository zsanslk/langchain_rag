from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Enum,
    DateTime,
    ForeignKey,
    JSON,
    func,
)
from models import db


class Document(db.Model):
    """知识库文档模型"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=True, index=True)  # 用于查重
    file_path = Column(String(500), nullable=False)
    file_type = Column(Enum("txt", "doc", "docx", "pdf"), nullable=False)
    file_size = Column(Integer, nullable=False)
    chunk_count = Column(Integer, default=0)
    status = Column(
        Enum("pending", "processing", "completed", "failed"), default="pending"
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联关系
    chunks = db.relationship(
        "DocumentChunk", backref="document", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "chunk_count": self.chunk_count,
            "status": self.status,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at
                else None
            ),
            "updated_at": (
                self.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.updated_at
                else None
            ),
        }

    def __repr__(self):
        return f"<Document {self.file_name}>"


class DocumentChunk(db.Model):
    """文档切片模型"""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    chunk_content = Column(Text, nullable=False)
    embedding_vector = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<DocumentChunk {self.document_id}-{self.chunk_index}>"


class ChatSession(db.Model):
    """对话会话模型"""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_name = Column(String(100), default="新对话")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关联关系
    messages = db.relationship(
        "ChatMessage",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "session_name": self.session_name,
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at
                else None
            ),
            "updated_at": (
                self.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.updated_at
                else None
            ),
        }

    def __repr__(self):
        return f"<ChatSession {self.session_name}>"


class ChatMessage(db.Model):
    """对话消息模型"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(Enum("user", "assistant"), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON)  # 存储来源文档信息 list[dict]
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "sources": self.sources or [],
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at
                else None
            ),
        }

    def __repr__(self):
        return f"<ChatMessage {self.role}>"


class ChatFeedback(db.Model):
    """消息反馈模型"""

    __tablename__ = "chat_feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating = Column(Enum("up", "down"), nullable=False)  # 赞 / 踩
    comment = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    message = db.relationship(
        "ChatMessage", backref=db.backref("feedback", uselist=False)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "rating": self.rating,
            "comment": self.comment or "",
            "created_at": (
                self.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if self.created_at
                else None
            ),
        }

    def __repr__(self):
        return f"<ChatFeedback {self.rating}>"
