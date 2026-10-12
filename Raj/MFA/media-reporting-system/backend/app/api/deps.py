"""
Media Reporting System - Authentication & Authorization Dependencies
Provides server-side session extraction, validation, and role/permission checks.
Supports both HttpOnly cookies and Bearer token headers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from app.core.config import settings
from app.core.security import hash_token
from database.repository import Repository, db_repo

logger = logging.getLogger("auth-deps")

# Granular permissions supported by the system
ALL_PERMISSIONS: List[str] = [
    "dashboard.view",
    "monitoring.view",
    "monitoring.news",
    "monitoring.advertisements",
    "monitoring.changes",
    "reports.view",
    "reports.export",
    "mailer.view",
    "mailer.export",
    "settings.view",
    "admin.users",
    # Legacy / alias keys for backwards compatibility
    "news.view",
    "advertisements.view",
    "changes.view",
    "admin.users.view",
    "admin.users.approve",
    "admin.users.revoke",
]

DEFAULT_USER_PERMISSIONS: List[str] = [
    "dashboard.view",
    "monitoring.view",
    "monitoring.news",
    "monitoring.advertisements",
    "monitoring.changes",
    "reports.view",
    "reports.export",
    "mailer.view",
    "mailer.export",
    "settings.view",
    # Legacy aliases
    "news.view",
    "advertisements.view",
    "changes.view",
]

PERMISSIONS_USER: List[str] = list(DEFAULT_USER_PERMISSIONS)
PERMISSIONS_ADMIN: List[str] = list(ALL_PERMISSIONS)


def get_user_permissions(role: str) -> List[str]:
    """Returns the list of permissions granted to a given role."""
    if str(role).upper() == "ADMIN":
        return list(ALL_PERMISSIONS)
    return list(DEFAULT_USER_PERMISSIONS)


def extract_session_token(request: Request) -> Optional[str]:
    """
    Extracts the session token from:
    1. Authorization header ('Bearer <token>')
    2. HttpOnly cookie (settings.SESSION_COOKIE_NAME)

    An explicit Authorization header must win over a browser cookie. This is
    important for API clients and also prevents a stale cookie from silently
    changing the identity of a request that supplies a bearer token.
    """
    # 1. Explicit bearer token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # 2. Browser session cookie
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()

    return None


async def get_current_user_optional(
    request: Request,
    repo: Repository = Depends(lambda: db_repo),
) -> Optional[Dict[str, Any]]:
    """
    Validates the session token if present. Returns None if unauthenticated,
    without raising an HTTPException.
    """
    token = extract_session_token(request)
    if not token:
        return None

    token_h = hash_token(token)
    session_data = repo.get_session_with_user(token_h)
    if not session_data:
        return None

    # Check expiration
    expires_at_str = session_data.get("expires_at")
    if expires_at_str:
        try:
            exp_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt >= exp_dt:
                repo.delete_session_by_token_hash(token_h)
                return None
        except Exception:
            return None

    # Check user account status
    user_status = session_data.get("status")
    if user_status != "APPROVED":
        return None

    # Update session activity
    try:
        repo.touch_session(session_data["session_id"])
    except Exception:
        pass

    # An empty list is a valid, explicitly revoked permission set. Only the
    # administrator receives role-derived permissions.
    user_perms = (
        get_user_permissions(session_data["role"])
        if str(session_data["role"]).upper() == "ADMIN"
        else list(session_data.get("permissions") or [])
    )

    return {
        "id": session_data["user_id"],
        "email": session_data["email"],
        "full_name": session_data.get("full_name"),
        "role": session_data["role"],
        "status": session_data["status"],
        "permissions": user_perms,
    }


async def get_current_user(
    request: Request,
    repo: Repository = Depends(lambda: db_repo),
) -> Dict[str, Any]:
    """
    Strict server-side authentication dependency.
    Raises 401 if missing, invalid, or expired session.
    Raises 403 if account is not APPROVED.
    """
    token = extract_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_h = hash_token(token)
    session_data = repo.get_session_with_user(token_h)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    expires_at_str = session_data.get("expires_at")
    if expires_at_str:
        try:
            exp_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt >= exp_dt:
                repo.delete_session_by_token_hash(token_h)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has expired. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session timestamp.",
            )

    # Check account status
    user_status = session_data.get("status")
    if user_status == "PENDING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending administrator approval.",
        )
    if user_status == "SUSPENDED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact the administrator.",
        )
    if user_status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not approved.",
        )

    # Touch session activity
    try:
        repo.touch_session(session_data["session_id"])
    except Exception:
        pass

    user_perms = (
        get_user_permissions(session_data["role"])
        if str(session_data["role"]).upper() == "ADMIN"
        else list(session_data.get("permissions") or [])
    )

    return {
        "id": session_data["user_id"],
        "email": session_data["email"],
        "full_name": session_data.get("full_name"),
        "role": session_data["role"],
        "status": session_data["status"],
        "permissions": user_perms,
    }


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Enforces that the authenticated user is the single designated administrator.
    Rejects normal users or unauthorized callers with HTTP 403.
    """
    admin_email = settings.ADMIN_EMAIL.lower()
    user_email = str(current_user.get("email", "")).lower()
    user_role = str(current_user.get("role", "")).upper()

    if user_role != "ADMIN" or user_email != admin_email:
        logger.warning(
            "Access denied to admin endpoint: user '%s' (role: '%s')",
            user_email,
            user_role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return current_user


def require_permission(permission_key: str):
    """
    Dependency factory to check if the current user has a specific permission.
    The single administrator always has all permissions.
    """
    async def _perm_checker(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if current_user.get("role") == "ADMIN":
            return current_user
        perms = set(current_user.get("permissions", []))
        if permission_key not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: required '{permission_key}'",
            )
        return current_user

    return _perm_checker


# Named dependency aliases
require_authenticated_user = get_current_user
require_admin = get_current_admin
