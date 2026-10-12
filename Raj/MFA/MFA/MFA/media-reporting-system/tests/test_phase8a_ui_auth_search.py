from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.security import hash_password, is_valid_email
from app.main import app
from database.repository import Repository, db_repo
from database.schema import init_db

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi TestClient unavailable")
class TestPhase8AAuthAndNewsSearch(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()
        init_db(self.db_path)

        self.orig_db_path = db_repo.db_path
        db_repo.db_path = self.db_path
        self.repo = Repository(self.db_path)
        self.client = TestClient(app)

        self.w_campaign = self.repo.get_or_create_website(
            "Campaign India", "campaign_india", "https://www.campaignindia.in/"
        )
        self.w_et = self.repo.get_or_create_website(
            "ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/"
        )
        self.s_marketing = self.repo.get_or_create_section(self.w_campaign["id"], "Marketing")
        self.s_digital = self.repo.get_or_create_section(self.w_et["id"], "Digital")

        self.repo.insert_article(
            website_id=self.w_campaign["id"],
            section_id=self.s_marketing["id"],
            headline="AI drives festive media planning for brands",
            url="https://www.campaignindia.in/article/ai-media",
            image_url=None,
            summary="Campaign India covers AI planning for agency teams.",
            published_at="2026-09-26T09:30:00+00:00",
            content_hash="phase8a-ai-campaign",
            detected_at="2026-09-26T09:35:00+00:00",
        )
        self.repo.insert_article(
            website_id=self.w_et["id"],
            section_id=self.s_digital["id"],
            headline="OTT measurement gets new framework",
            url="https://brandequity.economictimes.indiatimes.com/news/ott",
            image_url=None,
            summary="A digital measurement update without the AI keyword.",
            published_at="2026-09-15T09:30:00+00:00",
            content_hash="phase8a-ott",
            detected_at="2026-09-15T09:35:00+00:00",
        )

    def tearDown(self):
        db_repo.db_path = self.orig_db_path
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_invalid_short_company_domain_email_rejected(self):
        self.assertFalse(is_valid_email("eg1u@d.com"))
        response = self.client.post(
            "/api/auth/register",
            json={"email": "eg1u@d.com", "password": "StrongPass12345!", "full_name": "Bad Email"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please enter a valid email address.")

    def test_valid_registration_status_pending_then_approved(self):
        response = self.client.post(
            "/api/auth/register",
            json={"email": "person@company.co.in", "password": "StrongPass12345!", "full_name": "Person"},
        )
        self.assertEqual(response.status_code, 201)

        pending = self.client.get("/api/auth/status", params={"email": "person@company.co.in"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["status"], "PENDING")
        self.assertFalse(pending.json()["can_sign_in"])

        user = self.repo.get_user_by_email("person@company.co.in")
        self.repo.update_user_status(user["id"], "APPROVED")

        approved = self.client.get("/api/auth/status", params={"email": "person@company.co.in"})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "APPROVED")
        self.assertTrue(approved.json()["can_sign_in"])

    def test_combined_news_search_filters_keyword_source_section_and_date(self):
        response = self.client.get(
            "/api/news/search",
            params={
                "q": "AI",
                "source": "campaign_india",
                "section": "Marketing",
                "start_date": "2026-09-21",
                "end_date": "2026-09-28",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["articles"][0]["source"], "Campaign India")
        self.assertIn("AI", body["articles"][0]["headline"])

    def test_empty_and_no_result_news_search_are_clean(self):
        empty = self.client.get("/api/news/search")
        self.assertEqual(empty.status_code, 200)
        self.assertGreaterEqual(empty.json()["total"], 2)

        none = self.client.get("/api/news/search", params={"q": "definitely-not-present"})
        self.assertEqual(none.status_code, 200)
        self.assertEqual(none.json()["total"], 0)
        self.assertEqual(none.json()["articles"], [])

    def test_news_search_invalid_date_range_error(self):
        resp = self.client.get("/api/news/search", params={"start_date": "2026-09-30", "end_date": "2026-09-01"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("start_date cannot be after end_date", resp.json()["detail"])

    def test_news_search_by_source_alias(self):
        resp = self.client.get("/api/news/search", params={"source": "et"})
        self.assertEqual(resp.status_code, 200)
        for art in resp.json()["articles"]:
            self.assertEqual(art["website_key"], "et_brand_equity")

    def test_ui_assets_phase8a_elements_present(self):
        app_js_path = _BACKEND / "app" / "static" / "app.js"
        styles_css_path = _BACKEND / "app" / "static" / "styles.css"
        index_html_path = _BACKEND / "app" / "static" / "index.html"

        self.assertTrue(app_js_path.exists())
        self.assertTrue(styles_css_path.exists())
        self.assertTrue(index_html_path.exists())

        app_js_content = app_js_path.read_text(encoding="utf-8")
        styles_css_content = styles_css_path.read_text(encoding="utf-8")
        index_html_content = index_html_path.read_text(encoding="utf-8")

        self.assertIn("searchNewsResults", app_js_content)
        self.assertIn("Access Granted", app_js_content)
        self.assertIn("authGradientShift", styles_css_content)
        self.assertIn("prefers-reduced-motion", styles_css_content)
        self.assertIn("nav-item-scraper-status", index_html_content)

