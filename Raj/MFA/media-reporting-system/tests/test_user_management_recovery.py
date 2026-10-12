from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
for _path in (str(_ROOT), str(_BACKEND)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.core.security import hash_password
from app.main import app
from database.repository import Repository, db_repo
from database.schema import init_db


class TestUserManagementRecovery(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(tmp.name)
        tmp.close()
        init_db(self.db_path)
        self.repo = Repository(self.db_path)
        self.original_db_path = db_repo.db_path
        db_repo.db_path = self.db_path
        self.client = TestClient(app)

        self.admin_password = "AdminSecure987!"
        self.admin = self.repo.create_user(
            "rajxy71@gmail.com",
            hash_password(self.admin_password),
            role="ADMIN",
            status="APPROVED",
        )
        login = self.client.post(
            "/api/auth/login",
            json={"email": self.admin["email"], "password": self.admin_password},
        )
        self.admin_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    def tearDown(self):
        self.client.close()
        db_repo.db_path = self.original_db_path
        try:
            self.db_path.unlink(missing_ok=True)
        except PermissionError:
            pass

    def create_approved_user(self, email: str, password: str = "UserSecure987!"):
        return self.repo.create_user(
            email,
            hash_password(password),
            role="USER",
            status="APPROVED",
        )

    def test_revoked_permissions_apply_to_existing_session(self):
        user = self.create_approved_user("permissions@example.com")
        self.repo.set_user_permissions(user["id"], ["monitoring.news"])
        login = self.client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "UserSecure987!"},
        )
        user_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        self.assertEqual(login.json()["user"]["permissions"], ["monitoring.news"])

        update = self.client.put(
            f"/api/admin/users/{user['id']}/permissions",
            json={"permissions": []},
            headers=self.admin_headers,
        )
        self.assertEqual(update.status_code, 200)
        me = self.client.get("/api/auth/me", headers=user_headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["permissions"], [])
        self.assertEqual(self.client.get("/api/news/search", headers=user_headers).status_code, 403)

    def test_admin_can_delete_normal_user_and_active_sessions(self):
        user = self.create_approved_user("delete-me@example.com")
        login = self.client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "UserSecure987!"},
        )
        user_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        response = self.client.delete(
            f"/api/admin/users/{user['id']}", headers=self.admin_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.repo.get_user_by_id(user["id"]))
        self.assertEqual(self.client.get("/api/auth/me", headers=user_headers).status_code, 401)

    def test_admin_cannot_be_deleted(self):
        response = self.client.delete(
            f"/api/admin/users/{self.admin['id']}", headers=self.admin_headers
        )
        self.assertEqual(response.status_code, 400)

    def test_report_export_permission_is_enforced_separately(self):
        user = self.create_approved_user("report-viewer@example.com")
        self.repo.set_user_permissions(user["id"], ["reports.view"])
        login = self.client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "UserSecure987!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        self.assertEqual(self.client.get("/api/reports/daily", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/reports/export", headers=headers).status_code, 403)

    def test_password_reset_email_token_is_single_use(self):
        user = self.create_approved_user("recovery@example.com")
        delivered = []

        def capture_email(recipient, reset_url):
            delivered.append((recipient, reset_url))
            return True

        with patch("app.services.email_service.send_password_reset_email", side_effect=capture_email):
            response = self.client.post(
                "/api/auth/forgot-password", json={"email": user["email"]}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(delivered), 1)
        token = parse_qs(urlparse(delivered[0][1]).query)["reset_token"][0]

        reset = self.client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "ChangedSecure987!"},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/reset-password",
                json={"token": token, "password": "AnotherSecure987!"},
            ).status_code,
            400,
        )
        login = self.client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "ChangedSecure987!"},
        )
        self.assertEqual(login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
