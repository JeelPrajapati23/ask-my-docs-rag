from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminItem(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuditLogItem(BaseModel):
    id: int
    user_id: Optional[str]
    action: str
    detail: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageItem(BaseModel):
    id: str
    role: str
    content: str
    citations: Optional[list] = None
    verification: Optional[dict] = None
    extra: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionItem(BaseModel):
    id: str
    name: Optional[str]
    uploaded_files: list
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionDetail(ChatSessionItem):
    messages: list[ChatMessageItem]


class ChatSessionCreateRequest(BaseModel):
    name: Optional[str] = None
    uploaded_files: list = []


class ChatSessionUpdateRequest(BaseModel):
    name: Optional[str] = None
    uploaded_files: Optional[list] = None
