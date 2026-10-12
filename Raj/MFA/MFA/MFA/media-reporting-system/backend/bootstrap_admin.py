"""
Media Reporting System - CLI Administrator Bootstrap Utility
Usage:
    python backend/bootstrap_admin.py
Or:
    ADMIN_INITIAL_PASSWORD=YourSecurePassword python backend/bootstrap_admin.py

This script:
1. Verifies the single administrator guarantee.
2. Prompts for or reads the initial password securely (never echoed or logged).
3. Hashes the password immediately using PBKDF2-HMAC-SHA256.
4. Provisions the single administrator account (rajxy71@gmail.com).
5. If the administrator already exists, reports status without modifying credentials.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

# Add project root and backend to sys.path
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.bootstrap import bootstrap_admin, check_admin_integrity, get_target_admin_email
from app.core.security import validate_password_strength
from database.schema import init_db


def main() -> int:
    print("=" * 70)
    print("  MEDIA REPORTING SYSTEM - ADMINISTRATOR PROVISIONING")
    print("=" * 70)

    # 1. Initialize schema
    init_db()

    target_email = get_target_admin_email()
    print(f"Target Administrator Email: {target_email}")

    # 2. Check current status
    integrity = check_admin_integrity()
    if integrity["conflict"]:
        print(f"\n[!] CONFLICT: {integrity['message']}")
        print("Please resolve existing admin conflicts before proceeding.")
        return 1

    if integrity["admin_count"] == 1:
        print("\n[OK] The single administrator account already exists.")
        print(f"Account: {target_email} (Role: ADMIN, Status: APPROVED)")
        print("Existing credentials are preserved. No changes made.")
        return 0

    # 3. Read password securely
    password = os.getenv("ADMIN_INITIAL_PASSWORD")
    if not password:
        print(f"\nProvisioning administrator account for: {target_email}")
        while True:
            try:
                p1 = getpass.getpass("Enter initial administrator password (min 10 chars): ")
                is_valid, err = validate_password_strength(p1)
                if not is_valid:
                    print(f"Password error: {err}")
                    continue
                p2 = getpass.getpass("Confirm administrator password: ")
                if p1 != p2:
                    print("Passwords do not match. Please try again.")
                    continue
                password = p1
                break
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled.")
                return 1

    # 4. Bootstrap
    try:
        admin_user = bootstrap_admin(initial_password=password)
        password = None  # Clear reference
        print("\n[SUCCESS] Administrator account successfully created.")
        print(f"  Email:  {admin_user['email']}")
        print(f"  Role:   {admin_user['role']}")
        print(f"  Status: {admin_user['status']}")
        print("\nYou can now log in at http://127.0.0.1:8000/ with this account.")
        return 0
    except Exception as exc:
        print(f"\n[ERROR] Bootstrap failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
