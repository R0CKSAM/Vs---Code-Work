"""
Media Reporting System - Administrator Bootstrap Command
Usage:
    python backend/create_admin.py

Guarantees:
1. Verifies if an ADMIN already exists. If yes, refuses to create another.
2. Prompts securely for administrator email and password.
3. Strictly validates that email matches 'rajxy71@gmail.com'.
4. Enforces strong password requirements (min 10 characters, rejects weak patterns).
5. Hashes the password immediately using salted PBKDF2-HMAC-SHA256.
6. Creates exactly one ADMIN with role='ADMIN' and status='APPROVED'.
7. Never prints or logs the plaintext password.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

# Setup paths
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.bootstrap import check_admin_integrity, get_target_admin_email
from app.core.security import hash_password, normalize_email, validate_password_strength
from database.repository import db_repo
from database.schema import init_db


def main() -> int:
    print("=" * 65)
    print("  MEDIA REPORTING - ADMINISTRATOR PROVISIONING")
    print("=" * 65)

    # 1. Initialize schema
    init_db()

    expected_admin_email = get_target_admin_email()

    # 2. Check if an ADMIN already exists
    integrity = check_admin_integrity(db_repo)
    if integrity["conflict"]:
        print(f"\n[ERROR] Integrity Conflict: {integrity['message']}")
        return 1

    if integrity["admin_count"] >= 1:
        print("\n[REFUSED] An administrator account already exists.")
        print(f"Registered Admin: {expected_admin_email}")
        print("Multiple administrators are strictly prohibited.")
        return 0

    # 3. Ask for admin email and validate
    print(f"\nTarget Administrator Email: {expected_admin_email}")
    try:
        input_email = input(f"Enter administrator email [{expected_admin_email}]: ").strip()
        if not input_email:
            input_email = expected_admin_email

        norm_email = normalize_email(input_email)
        if norm_email != expected_admin_email:
            print(f"\n[ERROR] Invalid administrator email: '{input_email}'.")
            print(f"Only '{expected_admin_email}' is authorized as system administrator.")
            return 1

        # 4. Prompt for password securely
        while True:
            pwd = getpass.getpass("Enter administrator password (min 10 chars): ")
            is_valid, err = validate_password_strength(pwd)
            if not is_valid:
                print(f"Password error: {err}")
                continue

            pwd_confirm = getpass.getpass("Confirm administrator password: ")
            if pwd != pwd_confirm:
                print("Passwords do not match. Please try again.")
                continue

            break

        # 5. Hash password immediately
        hashed = hash_password(pwd)
        pwd = None
        pwd_confirm = None

        # 6. Create administrator
        user = db_repo.create_user(
            email=norm_email,
            password_hash=hashed,
            full_name="System Administrator",
            role="ADMIN",
            status="APPROVED",
        )

        # 7. Grant all permissions
        from app.api.deps import ALL_PERMISSIONS
        db_repo.set_user_permissions(user["id"], ALL_PERMISSIONS)

        print("\n[SUCCESS] Administrator account successfully created.")
        print(f"Account: {user['email']} (Role: ADMIN, Status: APPROVED)")
        return 0

    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.")
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Failed to create administrator: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
