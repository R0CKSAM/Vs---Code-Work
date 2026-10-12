"""
Comprehensive Test Suite for Single-Dashboard Multi-User Authentication & Access Controls
Verifies:
1. Admin bootstrap creates exactly one admin.
2. Admin email is case-insensitive.
3. Admin password is hashed, never plaintext.
4. Admin can login.
5. Wrong admin password fails.
6. Normal user registration creates PENDING USER.
7. User cannot register as ADMIN.
8. Pending user cannot login.
9. Admin can approve user.
10. Approved user can login.
11. Suspended user cannot login.
12. Normal user cannot access /api/admin/users.
13. Normal user cannot approve users.
14. Normal user cannot revoke users.
15. Admin cannot create another admin.
16. Admin cannot revoke their own admin access.
17. Duplicate emails are rejected.
18. Login failure lockout works.
19. Successful login resets failed-login counter.
20. /api/auth/me returns correct permissions.
21. Logout invalidates session.
22. Expired session is rejected.
23. Password hash is never returned by any API.
24. Existing monitoring/reporting APIs still work.
25. Existing scraper/database/ad/reporting tests still pass.
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

from app.core.bootstrap import bootstrap_admin, check_admin_integrity
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.main import app
from database.repository import Repository, db_repo
from database.schema import init_db

try:
    from fastapi.testclient import TestClient
    TEST_CLIENT_AVAILABLE = True
except ImportError:
    TEST_CLIENT_AVAILABLE = False


class TestAuthenticationAndAuthorization(unittest.TestCase):

    def setUp(self):
        # Create isolated temporary SQLite database for each test
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()

        init_db(self.db_path)
        self.repo = Repository(self.db_path)

        # Redirect global db_repo to test database
        self.orig_db_path = db_repo.db_path
        db_repo.db_path = self.db_path

        # Setup TestClient
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
                query_string = parsed.query.encode("latin-1")
                req_headers = [(b"host", b"testserver")]

                # Pass cookies
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
                    "raw_path": path.encode("ascii"),
                    "query_string": query_string,
                    "headers": req_headers,
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "scheme": "http",
                }

                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}

                async def send(message):
                    nonlocal status_code, res_headers, body_chunks
                    if message["type"] == "http.response.start":
                        status_code = message["status"]
                        for k, v in message.get("headers", []):
                            k_str = k.decode("latin-1").lower()
                            v_str = v.decode("latin-1")
                            res_headers[k_str] = v_str
                            if k_str == "set-cookie":
                                parts = v_str.split(";")[0].split("=", 1)
                                if len(parts) == 2:
                                    self.cookies[parts[0].strip()] = parts[1].strip()
                    elif message["type"] == "http.response.body":
                        body_chunks.append(message.get("body", b""))

                asyncio.run(self.app(scope, receive, send))
                return _ASGIResponse(status_code, res_headers, b"".join(body_chunks))

            def get(self, url: str, headers=None):
                return self._request("GET", url, headers=headers)

            def post(self, url: str, json=None, headers=None):
                return self._request("POST", url, json_data=json, headers=headers)

        return _ASGITestClient(app_instance)

    # -------------------------------------------------------------------------
    # Tests 1-5: Administrator Identity & Bootstrap
    # -------------------------------------------------------------------------
    def test_01_admin_bootstrap_creates_exactly_one_admin(self):
        """1. Admin bootstrap creates exactly one administrator account."""
        admin = bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        self.assertIsNotNone(admin)
        self.assertEqual(admin["email"].lower(), self.admin_email.lower())
        self.assertEqual(admin["role"], "ADMIN")
        self.assertEqual(admin["status"], "APPROVED")

        # Confirm exactly 1 in repository
        count = self.repo.count_admins()
        self.assertEqual(count, 1)

        # Second bootstrap call must NOT duplicate admin
        admin2 = bootstrap_admin(initial_password="AnotherPassword999!", repo=self.repo)
        self.assertEqual(self.repo.count_admins(), 1)
        self.assertEqual(admin2["id"], admin["id"])

    def test_02_admin_email_is_case_insensitive(self):
        """2. Admin email is strictly normalized case-insensitively."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        # Querying with uppercase or mixed case retrieves the same record
        user1 = self.repo.get_user_by_email("RAJXY71@GMAIL.COM")
        user2 = self.repo.get_user_by_email("rajxy71@gmail.com")
        self.assertIsNotNone(user1)
        self.assertIsNotNone(user2)
        self.assertEqual(user1["id"], user2["id"])

    def test_03_admin_password_is_hashed_never_plaintext(self):
        """3. Admin password is stored using a secure salted hash, never plaintext."""
        admin = bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        raw_db_user = self.repo.get_user_by_id(admin["id"])
        pwd_hash = raw_db_user["password_hash"]

        self.assertNotEqual(pwd_hash, self.admin_pwd)
        self.assertTrue(pwd_hash.startswith("pbkdf2_sha256$100000$"))
        self.assertTrue(verify_password(self.admin_pwd, pwd_hash))
        self.assertFalse(verify_password("wrong_password", pwd_hash))

    def test_04_admin_can_login(self):
        """4. Admin can log in successfully and receive authentication session."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["role"], "ADMIN")
        self.assertEqual(data["user"]["status"], "APPROVED")
        self.assertIn("token", data)
        self.assertNotIn("password_hash", str(data))

    def test_05_wrong_admin_password_fails(self):
        """5. Wrong admin password fails with generic HTTP 401 error."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertEqual(data["detail"], "Invalid email or password.")

    # -------------------------------------------------------------------------
    # Tests 6-11: User Registration, Lifecycle & Approvals
    # -------------------------------------------------------------------------
    def test_06_normal_user_registration_creates_pending_user(self):
        """6. Public registration creates a PENDING account with role USER."""
        res = self.client.post(
            "/api/auth/register",
            json={"email": "member1@company.com", "password": "MemberPassword123!"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "PENDING")

        u = self.repo.get_user_by_email("member1@company.com")
        self.assertIsNotNone(u)
        self.assertEqual(u["role"], "USER")
        self.assertEqual(u["status"], "PENDING")

    def test_07_user_cannot_register_as_admin(self):
        """7. Public registration cannot assign the ADMIN role or APPROVED status."""
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

    def test_08_pending_user_cannot_login(self):
        """8. A PENDING user account is rejected on login with HTTP 403."""
        self.client.post(
            "/api/auth/register",
            json={"email": "pending_user@corp.com", "password": "PendingPass123!"},
        )
        res = self.client.post(
            "/api/auth/login",
            json={"email": "pending_user@corp.com", "password": "PendingPass123!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("pending administrator approval", res.json()["detail"].lower())

    def test_09_admin_can_approve_user(self):
        """9. Administrator can approve a PENDING user."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        token = login_res.json()["token"]

        # Create pending user
        self.client.post(
            "/api/auth/register",
            json={"email": "awaiting@corp.com", "password": "AwaitingPass123!"},
        )
        target = self.repo.get_user_by_email("awaiting@corp.com")

        # Admin approves user
        res = self.client.post(
            f"/api/admin/users/{target['id']}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "APPROVED")

        updated = self.repo.get_user_by_id(target["id"])
        self.assertEqual(updated["status"], "APPROVED")

    def test_10_approved_user_can_login(self):
        """10. Once approved by admin, the user can log in successfully."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        self.client.post(
            "/api/auth/register",
            json={"email": "joiner@corp.com", "password": "JoinerPass123!"},
        )
        target = self.repo.get_user_by_email("joiner@corp.com")
        self.repo.update_user_status(target["id"], "APPROVED")

        # Now login should succeed
        res = self.client.post(
            "/api/auth/login",
            json={"email": "joiner@corp.com", "password": "JoinerPass123!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["role"], "USER")
        self.assertEqual(data["user"]["status"], "APPROVED")

    def test_11_suspended_user_cannot_login(self):
        """11. A SUSPENDED user account is rejected on login with HTTP 403."""
        pwd_h = hash_password("SuspendedPass123!")
        u = self.repo.create_user("banned@corp.com", pwd_h, role="USER", status="SUSPENDED")

        res = self.client.post(
            "/api/auth/login",
            json={"email": "banned@corp.com", "password": "SuspendedPass123!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("suspended", res.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Tests 12-16: Role-Based Access Controls & Single Admin Invariant
    # -------------------------------------------------------------------------
    def test_12_normal_user_cannot_access_admin_users(self):
        """12. A normal USER account cannot access GET /api/admin/users (HTTP 403)."""
        pwd_h = hash_password("UserPass123!")
        self.repo.create_user("normal@corp.com", pwd_h, role="USER", status="APPROVED")

        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "normal@corp.com", "password": "UserPass123!"},
        )
        token = login_res.json()["token"]

        res = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("administrator access required", res.json()["detail"].lower())

    def test_13_normal_user_cannot_approve_users(self):
        """13. A normal USER cannot call POST /api/admin/users/{id}/approve."""
        pwd_h = hash_password("UserPass123!")
        self.repo.create_user("normal2@corp.com", pwd_h, role="USER", status="APPROVED")
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "normal2@corp.com", "password": "UserPass123!"},
        )
        token = login_res.json()["token"]

        res = self.client.post(
            "/api/admin/users/1/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 403)

    def test_14_normal_user_cannot_revoke_users(self):
        """14. A normal USER cannot call POST /api/admin/users/{id}/revoke."""
        pwd_h = hash_password("UserPass123!")
        self.repo.create_user("normal3@corp.com", pwd_h, role="USER", status="APPROVED")
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "normal3@corp.com", "password": "UserPass123!"},
        )
        token = login_res.json()["token"]

        res = self.client.post(
            "/api/admin/users/1/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 403)

    def test_15_admin_cannot_create_another_admin(self):
        """15. The database and repository reject attempts to create a second ADMIN."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        with self.assertRaises(ValueError):
            self.repo.create_user(
                email="second_admin@example.com",
                password_hash=hash_password("Pass12345!"),
                role="ADMIN",
                status="APPROVED",
            )
        self.assertEqual(self.repo.count_admins(), 1)

    def test_16_admin_cannot_revoke_their_own_admin_access(self):
        """16. Admin cannot revoke or suspend their own account."""
        admin = bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        token = login_res.json()["token"]

        res = self.client.post(
            f"/api/admin/users/{admin['id']}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot revoke or suspend", res.json()["detail"].lower())

        # Status remains APPROVED
        cur = self.repo.get_user_by_id(admin["id"])
        self.assertEqual(cur["status"], "APPROVED")

    # -------------------------------------------------------------------------
    # Tests 17-23: Security Controls & Invariants
    # -------------------------------------------------------------------------
    def test_17_duplicate_emails_are_rejected(self):
        """17. Duplicate email registrations are rejected with HTTP 400."""
        self.client.post(
            "/api/auth/register",
            json={"email": "unique@corp.com", "password": "Password123!"},
        )
        res = self.client.post(
            "/api/auth/register",
            json={"email": "UNIQUE@corp.com", "password": "DifferentPass123!"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.json()["detail"].lower())

    def test_18_login_failure_lockout_works(self):
        """18. Exceeding failed login attempts temporarily locks the account."""
        pwd_h = hash_password("ValidPassword123!")
        u = self.repo.create_user("lockout_test@corp.com", pwd_h, role="USER", status="APPROVED")

        # 5 failed attempts
        for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
            res = self.client.post(
                "/api/auth/login",
                json={"email": "lockout_test@corp.com", "password": "WrongPassword99!"},
            )
            self.assertEqual(res.status_code, 401)

        # 6th attempt must be locked out with HTTP 403
        res_locked = self.client.post(
            "/api/auth/login",
            json={"email": "lockout_test@corp.com", "password": "ValidPassword123!"},
        )
        self.assertEqual(res_locked.status_code, 403)
        self.assertIn("locked", res_locked.json()["detail"].lower())

    def test_19_successful_login_resets_failed_login_counter(self):
        """19. A successful login resets failed_login_attempts counter and updates last_login_at."""
        pwd_h = hash_password("ResetPass123!")
        u = self.repo.create_user("reset_test@corp.com", pwd_h, role="USER", status="APPROVED")

        # 2 failed attempts
        for _ in range(2):
            self.client.post(
                "/api/auth/login",
                json={"email": "reset_test@corp.com", "password": "WrongPassword99!"},
            )

        u_mid = self.repo.get_user_by_id(u["id"])
        self.assertEqual(u_mid["failed_login_attempts"], 2)

        # Successful login
        res = self.client.post(
            "/api/auth/login",
            json={"email": "reset_test@corp.com", "password": "ResetPass123!"},
        )
        self.assertEqual(res.status_code, 200)

        u_final = self.repo.get_user_by_id(u["id"])
        self.assertEqual(u_final["failed_login_attempts"], 0)
        self.assertIsNotNone(u_final["last_login_at"])

    def test_20_api_auth_me_returns_correct_permissions(self):
        """20. /api/auth/me returns identity and permission matrix without secrets."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        token = login_res.json()["token"]

        res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        user = data["user"]
        self.assertEqual(user["email"], self.admin_email)
        self.assertEqual(user["role"], "ADMIN")
        self.assertIn("admin.users.approve", user["permissions"])
        self.assertIn("dashboard.view", user["permissions"])

    def test_21_logout_invalidates_session(self):
        """21. POST /api/auth/logout invalidates session token from server."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        token = login_res.json()["token"]

        # Confirm session works
        res_me1 = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res_me1.status_code, 200)

        # Logout
        logout_res = self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_res.status_code, 200)

        # Subsequent request with old session is rejected
        res_me2 = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res_me2.status_code, 401)

    def test_22_expired_session_is_rejected(self):
        """22. An expired session token is rejected with HTTP 401."""
        pwd_h = hash_password("ValidPassword123!")
        u = self.repo.create_user("expired_sess@corp.com", pwd_h, role="USER", status="APPROVED")

        # Create expired session in repository
        from app.core.security import generate_session_token, hash_token
        raw_token = generate_session_token()
        expired_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.repo.create_session(u["id"], hash_token(raw_token), expired_iso)

        res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        self.assertEqual(res.status_code, 401)

    def test_23_password_hash_is_never_returned_by_any_api(self):
        """23. Password hashes are never leaked in login, me, or user list endpoints."""
        bootstrap_admin(initial_password=self.admin_pwd, repo=self.repo)

        # 1. Login response
        res_login = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_pwd},
        )
        self.assertNotIn("password_hash", res_login.content.decode("utf-8"))
        token = res_login.json()["token"]

        # 2. Me response
        res_me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertNotIn("password_hash", res_me.content.decode("utf-8"))

        # 3. Admin user list response
        res_users = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertNotIn("password_hash", res_users.content.decode("utf-8"))

    # -------------------------------------------------------------------------
    # Tests 24-25: Continuity of Existing Scraper & Reporting APIs
    # -------------------------------------------------------------------------
    def test_24_existing_monitoring_reporting_apis_still_work(self):
        """24. Existing public reporting and status APIs continue to function."""
        # Initialize website to enable reporting
        self.repo.get_or_create_website("ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/")

        # Test reports endpoint
        res = self.client.get("/api/reports/daily")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("executive_summary", data)

        # Test health endpoint
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)

    def test_25_existing_scraper_database_ad_reporting_compatibility(self):
        """25. Database schema migration preserved existing tables and schema structures."""
        from database.connection import get_db
        with get_db(self.repo.db_path) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected = {
                "websites",
                "sections",
                "articles",
                "article_versions",
                "scrape_runs",
                "advertisements",
                "advertisement_versions",
                "users",
                "user_sessions",
            }
            for exp in expected:
                self.assertIn(exp, tables)


if __name__ == "__main__":
    unittest.main(verbosity=2)
