"""
Media Reporting System - Administrator Bootstrap & Identity Enforcement
Ensures that exactly one administrator account exists, strictly bound to the configured
administrator email (rajxy71@gmail.com). Hashes the initial password immediately and
never persists or logs plaintext credentials.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.security import hash_password, normalize_email, validate_password_strength
from database.repository import Repository, db_repo

logger = logging.getLogger("auth-bootstrap")


class AdminConflictError(Exception):
    """Raised when an illegal admin configuration or multiple admins are detected."""
    pass


def get_target_admin_email() -> str:
    """Returns the normalized authoritative administrator email."""
    env_admin = os.getenv("ADMIN_EMAIL", settings.ADMIN_EMAIL)
    return normalize_email(env_admin or "rajxy71@gmail.com")


def check_admin_integrity(repo: Optional[Repository] = None) -> Dict[str, Any]:
    """
    Validates single-admin integrity in the database:
    - Counts existing ADMIN accounts.
    - If > 1 admin found, reports conflict.
    - If 1 admin found, checks if it matches configured ADMIN_EMAIL.
    """
    r = repo or db_repo
    target_email = get_target_admin_email()
    admin_count = r.count_admins()
    existing_admin = r.get_admin_user()

    if admin_count > 1:
        msg = (
            f"SECURITY CONFLICT: Detected {admin_count} ADMIN accounts in the database. "
            f"The Media Reporting System strictly mandates exactly ONE administrator ({target_email})."
        )
        logger.error(msg)
        return {
            "valid": False,
            "admin_count": admin_count,
            "conflict": True,
            "message": msg,
            "admin": None,
        }

    if admin_count == 1:
        if existing_admin and existing_admin["email"].lower() != target_email.lower():
            msg = (
                f"SECURITY CONFLICT: Existing admin '{existing_admin['email']}' does not match "
                f"the configured administrator email '{target_email}'."
            )
            logger.error(msg)
            return {
                "valid": False,
                "admin_count": 1,
                "conflict": True,
                "message": msg,
                "admin": existing_admin,
            }
        return {
            "valid": True,
            "admin_count": 1,
            "conflict": False,
            "message": "Valid single administrator configured.",
            "admin": existing_admin,
        }

    return {
        "valid": True,
        "admin_count": 0,
        "conflict": False,
        "message": "No administrator account exists yet. Bootstrap required.",
        "admin": None,
    }


def bootstrap_admin(
    initial_password: Optional[str] = None,
    repo: Optional[Repository] = None,
) -> Optional[Dict[str, Any]]:
    """
    Safely provisions the single administrator account if not present.
    Rules:
    - If admin already exists, DO NOT overwrite or reset password automatically.
    - If multiple admins exist, raises AdminConflictError.
    - If 0 admins exist and password is provided, creates the single ADMIN account.
    - Password is validated, immediately hashed, and never retained in memory or disk.
    """
    r = repo or db_repo
    target_email = get_target_admin_email()

    integrity = check_admin_integrity(r)
    if integrity["conflict"]:
        raise AdminConflictError(integrity["message"])

    if integrity["admin_count"] == 1:
        logger.info("Administrator account verified: %s", target_email)
        return {**integrity["admin"], "already_existed": True}

    # No admin exists yet: attempt bootstrap
    raw_pwd = initial_password or os.getenv("ADMIN_INITIAL_PASSWORD")
    if not raw_pwd:
        logger.info(
            "Admin account not yet created. Set ADMIN_INITIAL_PASSWORD or run bootstrap_admin script."
        )
        return None

    # Validate password
    is_valid, err = validate_password_strength(raw_pwd)
    if not is_valid:
        raise ValueError(f"Admin initial password does not meet requirements: {err}")

    # Immediately hash password
    pwd_hash = hash_password(raw_pwd)
    raw_pwd = None  # Clear reference

    # Insert into users table
    admin_user = r.create_user(
        email=target_email,
        password_hash=pwd_hash,
        role="ADMIN",
        status="APPROVED",
    )
    logger.info("Single administrator account successfully bootstrapped: %s", target_email)
    return {**admin_user, "already_existed": False}


def resolve_admin_conflicts_safely(
    keep_admin_email: Optional[str] = None,
    repo: Optional[Repository] = None,
) -> int:
    """
    Controlled repair utility: If rogue/extra admin records were created during previous tests,
    this demotes non-designated admins to 'USER' or removes duplicates to restore the single-admin guarantee.
    Never touches normal user accounts.
    """
    r = repo or db_repo
    target = normalize_email(keep_admin_email or get_target_admin_email())

    from database.connection import get_db
    with get_db(r.db_path) as conn:
        # Demote any admin that is NOT the target email to USER role
        cur = conn.execute(
            "UPDATE users SET role = 'USER' WHERE role = 'ADMIN' AND LOWER(email) != ?",
            (target,),
        )
        demoted = cur.rowcount
        if demoted > 0:
            logger.warning(
                "Admin conflict resolution: Demoted %d extra admin account(s) to 'USER' role.",
                demoted,
            )
        return demoted
