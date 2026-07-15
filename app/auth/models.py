from datetime import datetime
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # "user" | "admin"
    is_active = Column(Boolean, default=True)
    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentJob(Base):
    """Tracks an upload's background parsing/chunking/embedding, so the upload
    request itself can return immediately instead of blocking on CPU embedding
    long enough to risk Vercel's ~120s proxy timeout (see /upload-and-index)."""
    __tablename__ = "document_jobs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    source_file = Column(String, nullable=False)
    status = Column(String, default="processing")  # "processing" | "ready" | "failed"
    error_message = Column(Text, nullable=True)
    total_chunks = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    """A saved chat/compare conversation, scoped to one user. Messages live in
    ChatMessage (looked up by session_id — no ORM relationship() is used
    anywhere in this file, so deletes/joins are done manually)."""
    __tablename__ = "chat_sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=True)
    uploaded_files = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)
    extra = Column(JSON, nullable=True)  # compare-only fields: isComparison, comparedDocs, weakEvidence
    created_at = Column(DateTime, default=datetime.utcnow)
