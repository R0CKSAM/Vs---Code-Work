"""
Media Reporting System - Authentication Endpoints
Provides registration, login with lockout protection, logout, and identity inspection.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status

from app.api.deps import extract_session_token, get_current_user, get_user_permissions
from app.core.config import settings
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_token,
    is_valid_email,
    normalize_email,
    validate_password_strength,
    verify_password,
)
from app.schemas.auth import (
    AccountStatusResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    PasswordResetRequest,
    UserInfo,
)
from database.repository import Repository, db_repo, utc_now_iso

logger = logging.getLogger("auth-endpoints")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Email a one-time password reset link",
)
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    repo: Repository = Depends(lambda: db_repo),
) -> MessageResponse:
    # Always return the same response to prevent account enumeration.
    generic_message = "If an account exists for that email, a password reset link has been sent."
    norm_email = normalize_email(req.email)
    user = repo.get_user_by_email(norm_email) if is_valid_email(norm_email) else None
    if user:
        raw_token = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_MINUTES)
        ).isoformat()
        repo.create_password_reset_token(user["id"], hash_token(raw_token), expires_at)
        base_url = settings.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/?reset_token={raw_token}"
        from app.services.email_service import send_password_reset_email
        background_tasks.add_task(send_password_reset_email, user["email"], reset_url)
    return MessageResponse(message=generic_message)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Set a new password using a one-time reset token",
)
async def reset_password(
    req: PasswordResetRequest,
    repo: Repository = Depends(lambda: db_repo),
) -> MessageResponse:
    valid, password_error = validate_password_strength(req.password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)
    token_record = repo.consume_password_reset_token(hash_token(req.token))
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )
    repo.update_user_password(token_record["user_id"], hash_password(req.password))
    repo.delete_sessions_for_user(token_record["user_id"])
    logger.info("Password reset completed for user ID %d", token_record["user_id"])
    return MessageResponse(message="Password updated successfully. You can now sign in.")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account (defaults to PENDING approval)",
)
async def register(
    req: RegisterRequest,
    repo: Repository = Depends(lambda: db_repo),
) -> RegisterResponse:
    """
    Public registration endpoint.
    Guarantees:
    - Normalizes email case-insensitively.
    - Validates email and password constraints.
    - Every public registration gets role = 'USER' and status = 'PENDING'.
    - Users cannot select role, cannot select ADMIN, cannot select APPROVED.
    - Rejects duplicate email addresses.
    """
    norm_email = normalize_email(req.email)
    if not is_valid_email(norm_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter a valid email address.",
        )

    is_valid, pwd_err = validate_password_strength(req.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=pwd_err,
        )

    # Check duplicate
    existing = repo.get_user_by_email(norm_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # Hash password immediately
    pwd_hash = hash_password(req.password)

    # Enforce USER role and PENDING status
    try:
        repo.create_user(
            email=norm_email,
            password_hash=pwd_hash,
            full_name=req.full_name,
            role="USER",
            status="PENDING",
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    logger.info("New user registered (PENDING approval): %s", norm_email)
    return RegisterResponse(
        message="Registration submitted successfully. Your account is pending administrator approval.",
        status="PENDING",
        email=norm_email,
    )


@router.get(
    "/status",
    response_model=AccountStatusResponse,
    summary="Check registration/account approval status",
)
async def account_status(
    email: str,
    repo: Repository = Depends(lambda: db_repo),
) -> AccountStatusResponse:
    norm_email = normalize_email(email)
    if not is_valid_email(norm_email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter a valid email address.",
        )

    user = repo.get_user_by_email(norm_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account was found for this email address.",
        )

    account_status_value = str(user.get("status") or "PENDING").upper()
    if account_status_value == "APPROVED":
        message = "Access granted. You can continue to sign in."
    elif account_status_value == "SUSPENDED":
        message = "Your account access has been revoked. Please contact the administrator."
    elif account_status_value == "REJECTED":
        message = "Your registration was rejected. Please contact the administrator."
    else:
        message = "Your account is pending administrator approval."

    return AccountStatusResponse(
        email=norm_email,
        status=account_status_value,
        authenticated=False,
        can_sign_in=account_status_value == "APPROVED",
        message=message,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
)
async def login(
    req: LoginRequest,
    response: Response,
    repo: Repository = Depends(lambda: db_repo),
) -> LoginResponse:
    """
    User login endpoint.
    Rules:
    - Only APPROVED accounts can log in.
    - ADMIN is automatically APPROVED.
    - PENDING and SUSPENDED accounts are rejected.
    - Failed logins track attempts and trigger temporary lockout after threshold.
    - Generic failure message protects against email enumeration.
    - Issues cryptographically random session token stored as hash in database.
    - Sets secure HttpOnly cookie and returns token in response.
    """
    norm_email = normalize_email(req.email)
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    user = repo.get_user_by_email(norm_email)

    # Check lockout
    if user and user.get("locked_until"):
        try:
            locked_until_dt = datetime.fromisoformat(
                user["locked_until"].replace("Z", "+00:00")
            )
            if now_dt < locked_until_dt:
                remaining_mins = max(1, int((locked_until_dt - now_dt).total_seconds() / 60))
                logger.warning("Login attempt on locked account: %s", norm_email)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account is temporarily locked due to multiple failed login attempts. Please try again in {remaining_mins} minute(s).",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # Verify credentials
    password_ok = False
    if user and user.get("password_hash"):
        password_ok = verify_password(req.password, user["password_hash"])

    if not password_ok:
        if user:
            attempts = int(user.get("failed_login_attempts") or 0) + 1
            locked_until = None
            if attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                lockout_end = now_dt + timedelta(minutes=settings.LOCKOUT_MINUTES)
                locked_until = lockout_end.isoformat()
                logger.warning(
                    "User %s exceeded failed attempts threshold (%d); locked until %s",
                    norm_email,
                    attempts,
                    locked_until,
                )
            repo.update_user_failed_login(user["id"], attempts, locked_until)
        # Generic error message
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check user approval status
    user_status = str(user.get("status") or "").upper()
    if user_status == "PENDING":
        logger.info("Login rejected for PENDING user: %s", norm_email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending administrator approval. You will receive access once approved.",
        )
    if user_status == "SUSPENDED":
        logger.warning("Login rejected for SUSPENDED user: %s", norm_email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact the administrator.",
        )
    if user_status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not approved for login.",
        )

    # Successful login: reset failed attempts, update last login
    repo.update_user_login_success(user["id"])

    # Generate session token and store hash
    raw_token = generate_session_token()
    token_h = hash_token(raw_token)
    expires_dt = now_dt + timedelta(hours=settings.SESSION_DURATION_HOURS)
    expires_iso = expires_dt.isoformat()

    repo.create_session(
        user_id=user["id"],
        token_hash=token_h,
        expires_at=expires_iso,
    )

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_DURATION_HOURS * 3600,
        secure=False,  # False for local HTTP development
        path="/",
    )

    role = user.get("role", "USER")
    user_perms = (
        get_user_permissions(role)
        if str(role).upper() == "ADMIN"
        else repo.get_user_permissions(user["id"])
    )

    user_info = UserInfo(
        id=user["id"],
        email=user["email"],
        full_name=user.get("full_name"),
        role=role,
        status=user_status,
        permissions=user_perms,
    )

    logger.info("Successful login for user: %s (role: %s)", norm_email, role)
    return LoginResponse(
        authenticated=True,
        user=user_info,
        token=raw_token,
        message="Login successful",
    )


@router.post(
    "/logout",
    summary="Log out and invalidate session",
)
async def logout(
    request: Request,
    response: Response,
    repo: Repository = Depends(lambda: db_repo),
) -> Dict[str, Any]:
    """
    Logs out the current session by invalidating the session token in the database
    and clearing the session cookie.
    """
    token = extract_session_token(request)
    if token:
        token_h = hash_token(token)
        repo.delete_session_by_token_hash(token_h)

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
    )
    return {"authenticated": False, "message": "Logged out successfully"}


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get authenticated user details and permissions",
)
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> MeResponse:
    """
    Returns the current authenticated user's profile and permissions.
    Never returns password hash or internal secrets.
    """
    return MeResponse(
        authenticated=True,
        user=UserInfo(
            id=current_user["id"],
            email=current_user["email"],
            full_name=current_user.get("full_name"),
            role=current_user["role"],
            status=current_user["status"],
            permissions=current_user.get("permissions", []),
        ),
    )
