"""
Media Reporting System - Administrator User Management Endpoints
Provides user listing, approval, and revocation controls.
Strictly restricted to the single configured administrator.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api.deps import DEFAULT_USER_PERMISSIONS, get_current_admin
from app.core.config import settings
from app.schemas.auth import (
    AdminUserItem,
    AdminUsersListResponse,
    UserActionResponse,
    UserApproveRequest,
)
from database.repository import Repository, db_repo

logger = logging.getLogger("admin-endpoints")

router = APIRouter(prefix="/admin", tags=["Administrator Management"])


@router.get(
    "/users",
    response_model=AdminUsersListResponse,
    summary="List all users (Administrator only)",
)
async def list_users(
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> AdminUsersListResponse:
    """
    Returns all registered users with their account roles and statuses.
    Password hashes are never returned.
    """
    users = repo.list_users()
    items = [
        AdminUserItem(
            id=u["id"],
            email=u["email"],
            full_name=u.get("full_name"),
            role=u["role"],
            status=u["status"],
            permissions=u.get("permissions") or [],
            created_at=u["created_at"],
            last_login_at=u.get("last_login_at"),
        )
        for u in users
    ]
    return AdminUsersListResponse(count=len(items), users=items)


@router.post(
    "/users/{user_id}/approve",
    response_model=UserActionResponse,
    summary="Approve a user registration (Administrator only)",
)
async def approve_user(
    user_id: int,
    req: Optional[UserApproveRequest] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> UserActionResponse:
    """
    Approves a user registration and sets permissions.
    Rules:
    - Only USER accounts can be approved.
    - Cannot create, promote, or alter another ADMIN account.
    - Sets user status to 'APPROVED'.
    - Configures assigned permissions or defaults to standard user permissions.
    """
    target = repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    if target["role"] == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot alter administrator status.",
        )

    try:
        updated = repo.update_user_status(user_id, "APPROVED")
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    # Set permissions
    if req and req.permissions is not None:
        repo.set_user_permissions(user_id, req.permissions)
    else:
        existing = repo.get_user_permissions(user_id)
        if not existing:
            repo.set_user_permissions(user_id, DEFAULT_USER_PERMISSIONS)

    logger.info(
        "Admin '%s' APPROVED user '%s' (ID: %d)",
        admin["email"],
        target["email"],
        user_id,
    )
    return UserActionResponse(
        message=f"User '{target['email']}' has been approved successfully.",
        user_id=user_id,
        status="APPROVED",
    )


@router.put(
    "/users/{user_id}/permissions",
    response_model=UserActionResponse,
    summary="Update user permissions (Administrator only)",
)
async def update_user_permissions(
    user_id: int,
    req: UserApproveRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> UserActionResponse:
    """
    Updates the permissions of an approved user.
    """
    target = repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    if target["role"] == "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify administrator permissions directly.",
        )

    perms = req.permissions if req.permissions is not None else DEFAULT_USER_PERMISSIONS
    repo.set_user_permissions(user_id, perms)

    logger.info(
        "Admin '%s' updated permissions for user '%s' (ID: %d)",
        admin["email"],
        target["email"],
        user_id,
    )
    return UserActionResponse(
        message=f"Permissions updated for '{target['email']}'.",
        user_id=user_id,
        status=target["status"],
    )


@router.post(
    "/users/{user_id}/revoke",
    response_model=UserActionResponse,
    summary="Revoke or suspend user access (Administrator only)",
)
async def revoke_user(
    user_id: int,
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> UserActionResponse:
    """
    Revokes or suspends a user's access.
    Rules:
    - Normal user accounts can be suspended.
    - The primary administrator CANNOT revoke or suspend their own account.
    - Immediately invalidates all active sessions for the suspended user.
    """
    target = repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    # Protect administrator account
    if target["role"] == "ADMIN" or target["email"].lower() == settings.ADMIN_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke or suspend the primary administrator account.",
        )

    try:
        updated = repo.update_user_status(user_id, "SUSPENDED")
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    # Invalidate all active sessions for this user
    invalidated_count = repo.delete_sessions_for_user(user_id)
    logger.info(
        "Admin '%s' REVOKED user '%s' (ID: %d); %d active session(s) terminated",
        admin["email"],
        target["email"],
        user_id,
        invalidated_count,
    )

    return UserActionResponse(
        message=f"User '{target['email']}' has been suspended and their active sessions revoked.",
        user_id=user_id,
        status="SUSPENDED",
    )


@router.post(
    "/users/{user_id}/restore",
    response_model=UserActionResponse,
    summary="Restore suspended user access (Administrator only)",
)
async def restore_user(
    user_id: int,
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> UserActionResponse:
    """
    Restores an approved or suspended user's access to APPROVED.
    """
    target = repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    try:
        updated = repo.update_user_status(user_id, "APPROVED")
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    logger.info(
        "Admin '%s' RESTORED user '%s' (ID: %d)",
        admin["email"],
        target["email"],
        user_id,
    )
    return UserActionResponse(
        message=f"User '{target['email']}' has been restored to APPROVED status.",
        user_id=user_id,
        status="APPROVED",
    )


@router.delete(
    "/users/{user_id}",
    response_model=UserActionResponse,
    summary="Permanently delete a user (Administrator only)",
)
async def delete_user(
    user_id: int,
    admin: Dict[str, Any] = Depends(get_current_admin),
    repo: Repository = Depends(lambda: db_repo),
) -> UserActionResponse:
    target = repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target["role"] == "ADMIN" or target["email"].lower() == settings.ADMIN_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the primary administrator account.",
        )
    try:
        deleted = repo.delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    logger.info("Admin '%s' deleted user '%s' (ID: %d)", admin["email"], target["email"], user_id)
    return UserActionResponse(
        message=f"User '{target['email']}' has been permanently deleted.",
        user_id=user_id,
        status="DELETED",
    )
