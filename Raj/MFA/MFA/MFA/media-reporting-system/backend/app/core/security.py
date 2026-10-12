"""
Media Reporting System - Core Security & Cryptography Utilities
Provides salted PBKDF2-HMAC-SHA256 password hashing, cryptographically random
session tokens, token hashing, email normalization, and password validation.
Zero external C dependencies. 100% Python standard library.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
from typing import Tuple

PBKDF2_ITERATIONS = 100_000
SALT_BYTES = 16
HASH_PREFIX = "pbkdf2_sha256"

EMAIL_LOCAL_ALLOWED = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
EMAIL_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_email(email: str) -> str:
    """Normalizes an email address to lowercase and trimmed."""
    if not email:
        return ""
    return str(email).strip().lower()


def is_valid_email(email: str) -> bool:
    """Validates a normal company email address without domain allowlisting."""
    norm = normalize_email(email)
    if not norm or len(norm) > 255:
        return False
    if norm.count("@") != 1:
        return False

    local, domain = norm.rsplit("@", 1)
    if not local or not domain:
        return False
    if len(local) > 64 or len(domain) > 253:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if not EMAIL_LOCAL_ALLOWED.match(local):
        return False
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in norm):
        return False

    if domain.startswith("[") and domain.endswith("]"):
        try:
            ipaddress.ip_address(domain[1:-1])
            return True
        except ValueError:
            return False

    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    if len(labels[-1]) < 2 or not labels[-1].isalpha():
        return False
    # Reject single-letter company/domain labels such as eg1u@d.com.
    if len(labels[-2]) < 2:
        return False
    return all(EMAIL_DOMAIN_LABEL.match(label) for label in labels)


COMMON_WEAK_PASSWORDS = {
    "password123",
    "password1234",
    "1234567890",
    "12345678901",
    "administrator",
    "admin12345",
    "adminadmin1",
    "qwertyuiop",
    "welcome1234",
    "company1234",
}


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Enforces password complexity requirements:
    - Minimum 10 characters
    - Maximum 128 characters
    - Rejects common weak passwords
    - Cannot be empty or whitespace only
    """
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 10:
        return False, "Password must be at least 10 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    if password.strip() == "":
        return False, "Password cannot consist solely of whitespace."
    if password.lower() in COMMON_WEAK_PASSWORDS:
        return False, "Password is too weak or commonly used. Please choose a stronger password."
    return True, ""


def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a cryptographically
    secure 16-byte random salt.
    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Cannot hash an empty password.")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"{HASH_PREFIX}${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a plaintext password against a stored PBKDF2-HMAC-SHA256 hash
    using constant-time string comparison.
    """
    if not password or not hashed:
        return False

    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != HASH_PREFIX:
            return False

        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = bytes.fromhex(parts[3])

        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(candidate, expected_hash)
    except Exception:
        return False


def generate_session_token() -> str:
    """Generates a cryptographically random, URL-safe 32-byte session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """
    Derives a deterministic SHA-256 hash of a session token for secure database storage.
    Raw session tokens are never stored in the database.
    """
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
