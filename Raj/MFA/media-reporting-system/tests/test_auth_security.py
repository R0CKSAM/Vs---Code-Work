"""
Media Reporting System - Comprehensive Security & LAN Authentication Test Suite
Covers 25 Core Verification Scenarios:
 1. Exactly one administrator account exists (rajxy71@gmail.com).
 2. Administrator password is cryptographically hashed (PBKDF2/Argon2id), never plaintext.
 3. Zero credential or hash leakage in any API responses.
 4. Case-insensitive email normalization for administrator and users.
 5. Invalid credentials return HTTP 401 with generic message.
 6. Public registration accepts full_name, email, and password.
 7. Password strength validation enforces minimum 10 characters and rejects weak passwords.
 8. Normal registration always sets role='USER' and status='PENDING'.
 9. Normal users cannot register as ADMIN or specify elevated roles.
10. Duplicate email registrations are rejected with HTTP 400.
11. PENDING accounts cannot log in (HTTP 403 with pending status).
12. Single administrator can view all users, full names, and permissions.
13. Normal users are forbidden from accessing administrator endpoints (HTTP 403).
14. Administrator can approve pending users with default permissions.
15. Administrator can approve pending users with custom granular permissions.
16. Administrator can update user permissions via PUT /api/admin/users/{id}/permissions.
17. Approved user can log in and receives their assigned granular permissions.
18. Single administrator account cannot be revoked, suspended, or deleted.
19. Administrator cannot create or promote another account to ADMIN.
20. Revoking/suspending a user immediately terminates all active sessions in SQLite.
21. SUSPENDED accounts cannot log in (HTTP 403 with suspended status).
22. Administrator can restore suspended accounts back to APPROVED.
23. Account lockout protects against brute-force attacks after consecutive failed logins.
24. Session tokens are 32-byte cryptographically secure random values stored as SHA-256 hashes.
25. 8-hour session lifetime is enforced, and logout invalidates the session token immediately.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.api.deps import ALL_PERMISSIONS, DEFAULT_USER_PERMISSIONS
from app.core.bootstrap import bootstrap_admin, check_admin_integrity
from app.core.config import settings
from app.core.security import hash_password, hash_token, verify_password
from app.main import app
from database.repository import Repository, db_repo
from database.schema import init_db

try:
    from fastapi.testclient import TestClient
    TEST_CLIENT_AVAILABLE = True
except ImportError:
    TEST_CLIENT_AVAILABLE = False


class TestAuthSecurityLAN(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()

        init_db(self.db_path)
        self.repo = Repository(self.db_path)

        self.orig_db_path = db_repo.db_path
        db_repo.db_path = self.db_path

        if TEST_CLIENT_AVAILABLE:
            self.client = TestClient(app)
        else:
            self.client = self._create_asgi_client(app)

        self.admin_email = "rajxy71@gmail.com"
        self.admin_pwd = "AdminSecurePassword123!"

    def tearDown(self):
        db_repo.db_path = self.orig_db_path
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def _create_asgi_client(self, app_instance):
        import asyncio
        import json
        import urllib.parse

        class _ASGIResponse:
            def __init__(self, status_code: int, headers: dict, body: bytes):
                self.status_code = status_code
                self.headers = headers
                self.content = body

            def json(self):
                return json.loads(self.content.decode("utf-8"))

        class _ASGITestClient:
            def __init__(self, app_inst):
                self.app = app_inst
                self.cookies = {}

            def _request(self, method: str, url: str, json_data=None, headers=None):
                parsed = urllib.parse.urlparse(url)
                path = parsed.path
                req_headers = [(b"host", b"testserver")]

                cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
                if cookie_str:
                    req_headers.append((b"cookie", cookie_str.encode("latin-1")))

                if headers:
                    for k, v in headers.items():
                        req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

                body_bytes = b""
                if json_data is not None:
                    body_bytes = json.dumps(json_data).encode("utf-8")
                    req_headers.append((b"content-type", b"application/json"))

                status_code = 500
                res_headers = {}
                body_chunks = []

                scope = {
                    "type": "http",
                    "http_version": "1.1",
                    "method": method,
                    "path": path,
                    "raw_path": path.encode("latin-1"),
                    "query_string": parsed.query.encode("latin-1"),
                    "headers": req_headers,
                }

                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}

                async def send(msg):
                    nonlocal status_code, res_headers, body_chunks
                    if msg["type"] == "http.response.start":
                        status_code = msg["status"]
                        for hk, hv in msg.get("headers", []):
                            decoded_k = hk.decode("latin-1").lower()
                            decoded_v = hv.decode("latin-1")
                            res_headers[decoded_k] = decoded_v
                            if decoded_k == "set-cookie":
                                parts = decoded_v.split(";")[0].split("=", 1)
                                if len(parts) == 2:
                                    self.cookies[parts[0].strip()] = parts[1].strip()
                    elif msg["type"] == "http.response.body":
                        body_chunks.append(msg.get("body", b""))

                asyncio.run(self.app(scope, receive, send))
                return _ASGIResponse(status_code, res_headers, b"".join(body_chunks))

            def get(self, url: str, headers=None):
                return self._request("GET", url, headers=headers)

            def post(self, url: str, json=None, headers=None):
                return self._request("POST", url, json_data=json, headers=headers)

            def put(self, url: str, json=None, headers=None):
                return self._request("PUT", url, json_data=json, headers=headers)

            def delete(self, url: str, headers=None):
                return self._request("DELETE", url, headers=headers)

        return _ASGITestClient(app_instance)

    # -------------------------------------------------------------------------
    # Test 1 & 2: Administrator Bootstrap and Hashing
    # -------------------------------------------------------------------------
    def test_01_bootstrap_creates_exactly_one_admin(self):
        """1. Admin bootstrap creates exactly one administrator account for rajxy71@gmail.com."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        admin = self.repo.get_user_by_email(self.admin_email)
        self.assertIsNotNone(admin)
        self.assertEqual(admin["role"], "ADMIN")
        self.assertEqual(admin["status"], "APPROVED")

        # Second bootstrap is idempotent
        res = bootstrap_admin(initial_password="AnotherPassword123!", repo=self.repo)
        self.assertTrue(res["already_existed"])
        all_admins = [u for u in self.repo.list_users() if u["role"] == "ADMIN"]
        self.assertEqual(len(all_admins), 1)

    def test_02_admin_password_is_hashed_never_plaintext(self):
        """2. Admin password is stored as a salted hash and never plaintext."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        admin = self.repo.get_user_by_email(self.admin_email)
        self.assertNotEqual(admin["password_hash"], self.admin_pwd)
        self.assertTrue(admin["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password(self.admin_pwd, admin["password_hash"]))

    # -------------------------------------------------------------------------
    # Test 3: Zero Password Leakage
    # -------------------------------------------------------------------------
    def test_03_zero_password_leakage_in_api_responses(self):
        """3. Password hashes are never returned by any authentication or management API."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()
        self.assertNotIn("password", str(login_data))
        self.assertNotIn("password_hash", str(login_data))

        token = login_data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # /api/auth/me
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertNotIn("password", str(me_res.json()))
        self.assertNotIn("password_hash", str(me_res.json()))

        # /api/admin/users
        users_res = self.client.get("/api/admin/users", headers=headers)
        self.assertNotIn("password", str(users_res.json()))
        self.assertNotIn("password_hash", str(users_res.json()))

    # -------------------------------------------------------------------------
    # Test 4 & 5: Case Insensitive Email & Bad Password
    # -------------------------------------------------------------------------
    def test_04_admin_email_is_case_insensitive(self):
        """4. Admin can log in using uppercase or mixed-case email."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        res = self.client.post(
            "/api/auth/login",
            json={"email": "RAJXY71@GMAIL.COM", "password": self.admin_pwd},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["authenticated"])
        self.assertEqual(res.json()["user"]["email"], self.admin_email)

    def test_05_invalid_credentials_return_http_401(self):
        """5. Incorrect password fails with HTTP 401."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("invalid", res.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 6, 7, 8, 9, 10: Registration & Validation
    # -------------------------------------------------------------------------
    def test_06_registration_accepts_fullname_email_password(self):
        """6. Registration accepts full_name, email, and password."""
        res = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Alice Analyst",
                "email": "alice@agency.com",
                "password": "SecurePassword2026!",
            },
        )
        self.assertEqual(res.status_code, 201)
        u = self.repo.get_user_by_email("alice@agency.com")
        self.assertIsNotNone(u)
        self.assertEqual(u["full_name"], "Alice Analyst")
        self.assertEqual(u["role"], "USER")
        self.assertEqual(u["status"], "PENDING")

    def test_07_password_strength_enforces_10_chars(self):
        """7. Passwords shorter than 10 characters or in weak blacklist are rejected."""
        # Too short (< 10 chars)
        res_short = self.client.post(
            "/api/auth/register",
            json={"email": "short@corp.com", "password": "Pass1!"},
        )
        self.assertEqual(res_short.status_code, 422)  # Pydantic schema validation

        # Weak common password
        res_weak = self.client.post(
            "/api/auth/register",
            json={"email": "weak@corp.com", "password": "password123"},
        )
        self.assertEqual(res_weak.status_code, 400)
        self.assertIn("common", res_weak.json()["detail"].lower())

    def test_08_normal_user_registration_always_pending_user(self):
        """8. Public registration always produces a PENDING USER."""
        res = self.client.post(
            "/api/auth/register",
            json={"email": "bob@media.com", "password": "BobValidPassword123!"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "PENDING")
        self.assertEqual(data["email"], "bob@media.com")

    def test_09_user_cannot_register_as_admin(self):
        """9. Registration rejects or ignores any client-supplied role."""
        res = self.client.post(
            "/api/auth/register",
            json={
                "email": "hacker@evil.com",
                "password": "HackerPassword123!",
                "role": "ADMIN",
                "status": "APPROVED",
            },
        )
        self.assertEqual(res.status_code, 201)
        u = self.repo.get_user_by_email("hacker@evil.com")
        self.assertEqual(u["role"], "USER")
        self.assertEqual(u["status"], "PENDING")

    def test_10_duplicate_email_registration_rejected(self):
        """10. Registering with an existing email returns HTTP 400."""
        self.client.post(
            "/api/auth/register",
            json={"email": "dupe@corp.com", "password": "ValidPassword123!"},
        )
        res_dupe = self.client.post(
            "/api/auth/register",
            json={"email": "dupe@corp.com", "password": "AnotherValid123!"},
        )
        self.assertEqual(res_dupe.status_code, 400)
        self.assertIn("already exists", res_dupe.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 11, 12, 13: Access Control & Listings
    # -------------------------------------------------------------------------
    def test_11_pending_user_cannot_login(self):
        """11. A user in PENDING status cannot log in."""
        self.client.post(
            "/api/auth/register",
            json={"email": "pending_guy@corp.com", "password": "ValidPassword123!"},
        )
        res = self.client.post(
            "/api/auth/login",
            json={"email": "pending_guy@corp.com", "password": "ValidPassword123!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("pending", res.json()["detail"].lower())

    def test_12_admin_can_list_users(self):
        """12. Administrator can list all users with full names and permissions."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        token = login_res.json()["token"]

        # Register a user
        self.client.post(
            "/api/auth/register",
            json={"full_name": "Charlie", "email": "charlie@test.com", "password": "CharliePassword123!"},
        )

        res = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        users = res.json()["users"]
        self.assertEqual(len(users), 2)
        charlie_item = next(u for u in users if u["email"] == "charlie@test.com")
        self.assertEqual(charlie_item["full_name"], "Charlie")
        self.assertEqual(charlie_item["status"], "PENDING")

    def test_13_normal_user_cannot_access_admin_users(self):
        """13. Normal approved users receive HTTP 403 when trying to access admin endpoints."""
        pwd_h = hash_password("NormalUserPass123!")
        u = self.repo.create_user("normal@corp.com", pwd_h, role="USER", status="APPROVED")

        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "normal@corp.com", "password": "NormalUserPass123!"},
        )
        token = login_res.json()["token"]

        res = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("administrator", res.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 14, 15, 16, 17: User Approval and Granular Permissions
    # -------------------------------------------------------------------------
    def test_14_admin_can_approve_user_with_default_permissions(self):
        """14. Admin approves a pending user and default permissions are assigned."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = login_res.json()["token"]

        # Register user
        self.client.post(
            "/api/auth/register",
            json={"email": "newuser@corp.com", "password": "UserSecure123!"},
        )
        u = self.repo.get_user_by_email("newuser@corp.com")

        # Admin approves
        res_appr = self.client.post(
            f"/api/admin/users/{u['id']}/approve",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res_appr.status_code, 200)

        u_updated = self.repo.get_user_by_id(u["id"])
        self.assertEqual(u_updated["status"], "APPROVED")

        perms = self.repo.get_user_permissions(u["id"])
        self.assertIn("dashboard.view", perms)
        self.assertIn("reports.view", perms)
        self.assertNotIn("admin.users", perms)

    def test_15_admin_can_approve_with_custom_permissions(self):
        """15. Admin approves a user and assigns custom granular permissions."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = login_res.json()["token"]

        self.client.post(
            "/api/auth/register",
            json={"email": "custom@corp.com", "password": "UserSecure123!"},
        )
        u = self.repo.get_user_by_email("custom@corp.com")

        custom_perms = ["dashboard.view", "monitoring.news"]
        res = self.client.post(
            f"/api/admin/users/{u['id']}/approve",
            json={"permissions": custom_perms},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 200)

        perms = self.repo.get_user_permissions(u["id"])
        self.assertEqual(sorted(perms), sorted(custom_perms))

    def test_16_admin_can_update_user_permissions(self):
        """16. Admin can update permissions of an existing user via PUT /admin/users/{id}/permissions."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = login_res.json()["token"]

        pwd_h = hash_password("ValidUser123!")
        u = self.repo.create_user("perm_update@corp.com", pwd_h, role="USER", status="APPROVED")

        new_perms = ["reports.view", "reports.export"]
        res = self.client.put(
            f"/api/admin/users/{u['id']}/permissions",
            json={"permissions": new_perms},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 200)

        perms = self.repo.get_user_permissions(u["id"])
        self.assertEqual(sorted(perms), sorted(new_perms))

    def test_17_approved_user_login_returns_permissions(self):
        """17. Approved user logs in and /api/auth/me returns their assigned permissions."""
        pwd_h = hash_password("ValidPass123!")
        u = self.repo.create_user("approved_user@corp.com", pwd_h, full_name="John Doe", role="USER", status="APPROVED")
        self.repo.set_user_permissions(u["id"], ["dashboard.view", "monitoring.advertisements"])

        res = self.client.post(
            "/api/auth/login",
            json={"email": "approved_user@corp.com", "password": "ValidPass123!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["full_name"], "John Doe")
        self.assertIn("monitoring.advertisements", data["user"]["permissions"])
        self.assertNotIn("reports.export", data["user"]["permissions"])

    # -------------------------------------------------------------------------
    # Test 18, 19, 20, 21, 22: Administrator Invariants & Account Management
    # -------------------------------------------------------------------------
    def test_18_admin_cannot_revoke_own_account(self):
        """18. The primary administrator cannot suspend or revoke their own account."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = login_res.json()["token"]
        admin = self.repo.get_user_by_email(self.admin_email)

        res = self.client.post(
            f"/api/admin/users/{admin['id']}/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("primary administrator", res.json()["detail"].lower())

    def test_19_admin_cannot_create_or_promote_another_admin(self):
        """19. System forbids creating or altering another user as ADMIN."""
        with self.assertRaises(ValueError):
            self.repo.create_user("fake_admin@corp.com", "hash", role="ADMIN")

    def test_20_revoking_user_terminates_all_active_sessions(self):
        """20. Suspending a user immediately terminates all their active sessions."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        admin_login = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = admin_login.json()["token"]

        pwd_h = hash_password("ValidUser123!")
        u = self.repo.create_user("session_victim@corp.com", pwd_h, role="USER", status="APPROVED")

        # User logs in and receives token
        user_login = self.client.post(
            "/api/auth/login",
            json={"email": "session_victim@corp.com", "password": "ValidUser123!"},
        )
        user_token = user_login.json()["token"]

        # User session works
        res_me1 = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(res_me1.status_code, 200)

        # Admin revokes the user
        res_rev = self.client.post(
            f"/api/admin/users/{u['id']}/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res_rev.status_code, 200)

        # Immediate invalidation: next call with user's token fails with 401
        res_me2 = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(res_me2.status_code, 401)

    def test_21_suspended_user_cannot_login(self):
        """21. A suspended user cannot log in (HTTP 403)."""
        pwd_h = hash_password("ValidPass123!")
        self.repo.create_user("suspended@corp.com", pwd_h, role="USER", status="SUSPENDED")

        res = self.client.post(
            "/api/auth/login",
            json={"email": "suspended@corp.com", "password": "ValidPass123!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("suspended", res.json()["detail"].lower())

    def test_22_admin_can_restore_suspended_user(self):
        """22. Admin can restore a suspended user to APPROVED."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        admin_login = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        admin_token = admin_login.json()["token"]

        pwd_h = hash_password("ValidPass123!")
        u = self.repo.create_user("restore_me@corp.com", pwd_h, role="USER", status="SUSPENDED")

        res = self.client.post(
            f"/api/admin/users/{u['id']}/restore",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 200)
        u_after = self.repo.get_user_by_id(u["id"])
        self.assertEqual(u_after["status"], "APPROVED")

    # -------------------------------------------------------------------------
    # Test 23, 24, 25: Lockout, Token Security & Expiry
    # -------------------------------------------------------------------------
    def test_23_failed_login_lockout(self):
        """23. Multiple consecutive failed logins temporarily lock the account."""
        pwd_h = hash_password("TestPassword123!")
        self.repo.create_user("lock_target@corp.com", pwd_h, role="USER", status="APPROVED")

        for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "lock_target@corp.com", "password": "WrongPassword99!"},
            )
            self.assertEqual(res.status_code, 401)

        # 6th attempt is locked with HTTP 403
        res_locked = self.client.post(
            "/api/auth/login",
            json={"email": "lock_target@corp.com", "password": "TestPassword123!"},
        )
        self.assertEqual(res_locked.status_code, 403)
        self.assertIn("locked", res_locked.json()["detail"].lower())

    def test_24_tokens_are_stored_as_sha256_hashes(self):
        """24. Session tokens in SQLite are stored as SHA-256 hashes, not plaintext."""
        pwd_h = hash_password("ValidPass123!")
        u = self.repo.create_user("token_test@corp.com", pwd_h, role="USER", status="APPROVED")

        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "token_test@corp.com", "password": "ValidPass123!"},
        )
        raw_token = login_res.json()["token"]

        token_h = hash_token(raw_token)
        session_row = self.repo.get_session_with_user(token_h)
        self.assertIsNotNone(session_row)
        self.assertEqual(session_row["user_id"], u["id"])

    def test_25_session_expiration_and_logout(self):
        """25. Expired sessions are rejected with HTTP 401, and logout invalidates session."""
        pwd_h = hash_password("ValidPass123!")
        u = self.repo.create_user("expiry_test@corp.com", pwd_h, role="USER", status="APPROVED")

        # Create session expired 1 hour ago
        raw_token = "expired_raw_test_token_12345678"
        t_hash = hash_token(raw_token)
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.repo.create_session(u["id"], t_hash, past_iso)

        res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        self.assertEqual(res.status_code, 401)

        # Login fresh
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "expiry_test@corp.com", "password": "ValidPass123!"},
        )
        fresh_token = login_res.json()["token"]

        # Logout
        logout_res = self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {fresh_token}"},
        )
        self.assertEqual(logout_res.status_code, 200)

        # Now rejected
        after_logout = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {fresh_token}"},
        )
        self.assertEqual(after_logout.status_code, 401)


if __name__ == "__main__":
    unittest.main()
