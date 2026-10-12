"""
Media Reporting System - Authentication & User Management Schemas
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=10, max_length=128, description="User password (min 10 chars)")
    full_name: Optional[str] = Field(None, description="User full name")


class RegisterResponse(BaseModel):
    message: str
    status: str = "PENDING"
    email: str


class AccountStatusResponse(BaseModel):
    email: str
    status: str
    authenticated: bool = False
    can_sign_in: bool = False
    message: str


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserInfo(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    permissions: List[str] = []


class LoginResponse(BaseModel):
    authenticated: bool = True
    user: UserInfo
    token: str
    message: str = "Login successful"


class MeResponse(BaseModel):
    authenticated: bool = True
    user: UserInfo


class AdminUserItem(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    permissions: List[str] = []
    created_at: str
    last_login_at: Optional[str] = None


class AdminUsersListResponse(BaseModel):
    count: int
    users: List[AdminUserItem]


class UserApproveRequest(BaseModel):
    permissions: Optional[List[str]] = Field(None, description="Permissions assigned to user upon approval")


class UserActionResponse(BaseModel):
    message: str
    user_id: int
    status: str
