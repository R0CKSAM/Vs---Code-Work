"""
Phase 7 - Professional Reporting & Export Tests
Tests daily reporting, weekly aggregation, custom parametric filtering,
reconciliation invariants, and PDF/Excel/CSV export generation in an isolated test database.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add project root and backend to sys.path
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "backend"
for _p in (str(_ROOT), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database.schema import init_db
from database.repository import Repository
try:
    from backend.reporting.report_service import ReportService
    from backend.reporting.report_export import ReportExporter
    from backend.reporting.report_models import DailyReportResponse, WeeklyReportResponse, CustomReportResponse
except ImportError:
    from reporting.report_service import ReportService
    from reporting.report_export import ReportExporter
    from reporting.report_models import DailyReportResponse, WeeklyReportResponse, CustomReportResponse


class TestReportingEngine(unittest.TestCase):

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.temp_file.name)
        self.temp_file.close()

        init_db(self.db_path)
        self.repo = Repository(self.db_path)
        self.service = ReportService(self.db_path)

        self.temp_export_dir = tempfile.TemporaryDirectory()
        self.exporter = ReportExporter(export_dir=Path(self.temp_export_dir.name))

        # Seed standard websites
        self.w_et = self.repo.get_or_create_website("ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/")
        self.w_e4m = self.repo.get_or_create_website("Exchange4media", "exchange4media", "https://www.exchange4media.com/")

        # Seed sections
        self.s_mkt = self.repo.get_or_create_section(self.w_et["id"], "Marketing", "https://brandequity.economictimes.indiatimes.com/marketing")
        self.s_dig = self.repo.get_or_create_section(self.w_et["id"], "Digital", "https://brandequity.economictimes.indiatimes.com/digital")
        self.s_adv = self.repo.get_or_create_section(self.w_e4m["id"], "Advertising", "https://www.exchange4media.com/advertising")

        # Seed Articles on 2026-09-23
        self.a1 = self.repo.insert_article(
            website_id=self.w_et["id"],
            section_id=self.s_mkt["id"],
            headline="Samsung unveils innovative AI campaign in India",
            url="https://brandequity.economictimes.indiatimes.com/news/1",
            image_url="https://img.com/1.jpg",
            summary="Samsung has launched its latest AI campaign across Indian metros.",
            published_at="2026-09-23T08:00:00+00:00",
            content_hash="hash_art_1",
            detected_at="2026-09-23T08:05:00+00:00",
        )
        self.repo.insert_article_version(
            article_id=self.a1["id"],
            headline=self.a1["headline"],
            url=self.a1["url"],
            image_url=self.a1["image_url"],
            summary=self.a1["summary"],
            section_id=self.a1["section_id"],
            published_at=self.a1["published_at"],
            content_hash=self.a1["content_hash"],
            change_type="NEW",
            detected_at="2026-09-23T08:05:00+00:00",
        )

        self.a2 = self.repo.insert_article(
            website_id=self.w_et["id"],
            section_id=self.s_dig["id"],
            headline="Google expands generative search features in APAC",
            url="https://brandequity.economictimes.indiatimes.com/news/2",
            image_url="https://img.com/2.jpg",
            summary="Google is rolling out new AI generative capabilities in APAC.",
            published_at="2026-09-23T09:00:00+00:00",
            content_hash="hash_art_2",
            detected_at="2026-09-23T09:05:00+00:00",
        )
        self.repo.insert_article_version(
            article_id=self.a2["id"],
            headline=self.a2["headline"],
            url=self.a2["url"],
            image_url=self.a2["image_url"],
            summary=self.a2["summary"],
            section_id=self.a2["section_id"],
            published_at=self.a2["published_at"],
            content_hash=self.a2["content_hash"],
            change_type="NEW",
            detected_at="2026-09-23T09:05:00+00:00",
        )

        self.a3 = self.repo.insert_article(
            website_id=self.w_e4m["id"],
            section_id=self.s_adv["id"],
            headline="Tata Motors appoints new creative agency for EV lineup",
            url="https://www.exchange4media.com/news/3",
            image_url="https://img.com/3.jpg",
            summary="Tata Motors has consolidated its creative duties with top agency.",
            published_at="2026-09-23T10:00:00+00:00",
            content_hash="hash_art_3",
            detected_at="2026-09-23T10:05:00+00:00",
        )
        self.repo.insert_article_version(
            article_id=self.a3["id"],
            headline=self.a3["headline"],
            url=self.a3["url"],
            image_url=self.a3["image_url"],
            summary=self.a3["summary"],
            section_id=self.a3["section_id"],
            published_at=self.a3["published_at"],
            content_hash=self.a3["content_hash"],
            change_type="NEW",
            detected_at="2026-09-23T10:05:00+00:00",
        )

        # Seed an article on previous day 2026-09-22
        self.a4 = self.repo.insert_article(
            website_id=self.w_e4m["id"],
            section_id=self.s_adv["id"],
            headline="HDFC Bank festive advertising blitz begins",
            url="https://www.exchange4media.com/news/4",
            image_url="https://img.com/4.jpg",
            summary="HDFC Bank rolls out nationwide media blitz.",
            published_at="2026-09-22T14:00:00+00:00",
            content_hash="hash_art_4",
            detected_at="2026-09-22T14:05:00+00:00",
        )

        # Log a scrape run
        self.run_id = self.repo.start_scrape_run(self.w_et["id"], started_at="2026-09-23T08:00:00+00:00")
        self.repo.finish_scrape_run(
            run_id=self.run_id,
            status="SUCCESS",
            items_found=2,
            new_items=2,
            updated_items=0,
            unchanged_items=0,
            removed_items=0,
            finished_at="2026-09-23T08:01:00+00:00",
        )

    def tearDown(self):
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        self.temp_export_dir.cleanup()

    # -------------------------------------------------------------------------
    # Test Cases
    # -------------------------------------------------------------------------
    def test_01_daily_report_with_data(self):
        """1. Daily report synthesizes accurate executive summary and breakdowns for date with data."""
        rep = self.service.generate_daily_report("2026-09-23")
        self.assertEqual(rep.executive_summary.reporting_date, "2026-09-23")
        self.assertEqual(rep.executive_summary.total_articles, 3)
        self.assertEqual(rep.executive_summary.et_article_count, 2)
        self.assertEqual(rep.executive_summary.e4m_article_count, 1)
        self.assertEqual(rep.executive_summary.sections_count, 3)
        self.assertEqual(rep.executive_summary.new_articles_count, 3)
        self.assertEqual(len(rep.top_stories), 3)

    def test_02_daily_report_with_no_data(self):
        """2. Daily report returns clean empty state with 0 totals for date with no data without crashing."""
        rep = self.service.generate_daily_report("2020-01-01")
        self.assertEqual(rep.executive_summary.total_articles, 0)
        self.assertEqual(rep.executive_summary.et_article_count, 0)
        self.assertEqual(rep.executive_summary.e4m_article_count, 0)
        self.assertEqual(len(rep.top_stories), 0)
        self.assertEqual(len(rep.new_articles), 0)

    def test_03_weekly_aggregation_and_daily_volume(self):
        """3. Weekly report correctly aggregates multi-day articles and daily volume matrix."""
        rep = self.service.generate_weekly_report("2026-09-22", "2026-09-23")
        self.assertEqual(rep.total_articles, 4)
        self.assertEqual(rep.et_article_count, 2)
        self.assertEqual(rep.e4m_article_count, 2)
        self.assertEqual(len(rep.daily_volume), 2)

        # Check volume reconciliation
        vol_22 = next(v for v in rep.daily_volume if v.date == "2026-09-22")
        self.assertEqual(vol_22.et_count, 0)
        self.assertEqual(vol_22.e4m_count, 1)
        self.assertEqual(vol_22.total_count, 1)

        vol_23 = next(v for v in rep.daily_volume if v.date == "2026-09-23")
        self.assertEqual(vol_23.et_count, 2)
        self.assertEqual(vol_23.e4m_count, 1)
        self.assertEqual(vol_23.total_count, 3)

    def test_04_custom_date_filtering(self):
        """4. Custom report filters accurately by start_date and end_date."""
        rep = self.service.generate_custom_report(start_date="2026-09-22", end_date="2026-09-22")
        self.assertEqual(rep.total_matching, 1)
        self.assertEqual(rep.articles[0].headline, "HDFC Bank festive advertising blitz begins")

    def test_05_custom_publisher_filtering(self):
        """5. Custom report filters accurately by publisher key."""
        rep = self.service.generate_custom_report(website="et_brand_equity")
        self.assertEqual(rep.total_matching, 2)
        for a in rep.articles:
            self.assertEqual(a.website_key, "et_brand_equity")

    def test_06_custom_section_filtering(self):
        """6. Custom report filters accurately by section name."""
        rep = self.service.generate_custom_report(section="Marketing")
        self.assertEqual(rep.total_matching, 1)
        self.assertEqual(rep.articles[0].section_name, "Marketing")

    def test_07_custom_status_filtering(self):
        """7. Custom report filters accurately by article status."""
        rep = self.service.generate_custom_report(status="ACTIVE")
        self.assertEqual(rep.total_matching, 4)

    def test_08_custom_keyword_filtering(self):
        """8. Custom report filters accurately by keyword in headline or summary."""
        rep = self.service.generate_custom_report(search="Samsung")
        self.assertEqual(rep.total_matching, 1)
        self.assertIn("Samsung", rep.articles[0].headline)

    def test_09_combined_multi_filters(self):
        """9. Custom report accurately combines multiple simultaneous filters."""
        rep = self.service.generate_custom_report(
            website="et_brand_equity",
            section="Digital",
            search="Google",
            status="ACTIVE",
        )
        self.assertEqual(rep.total_matching, 1)
        self.assertEqual(rep.articles[0].headline, "Google expands generative search features in APAC")

    def test_10_totals_reconciliation(self):
        """10. Mathematical reconciliation: ET + E4M publisher totals always equal total articles."""
        rep_d = self.service.generate_daily_report("2026-09-23")
        self.assertEqual(
            rep_d.executive_summary.et_article_count + rep_d.executive_summary.e4m_article_count,
            rep_d.executive_summary.total_articles,
        )

        rep_w = self.service.generate_weekly_report("2026-09-20", "2026-09-25")
        self.assertEqual(
            rep_w.et_article_count + rep_w.e4m_article_count,
            rep_w.total_articles,
        )

    def test_11_daily_volume_reconciliation(self):
        """11. Daily volume progression: for each day, et_count + e4m_count == total_count."""
        rep_w = self.service.generate_weekly_report("2026-09-20", "2026-09-25")
        for v in rep_w.daily_volume:
            self.assertEqual(v.et_count + v.e4m_count, v.total_count)

    def test_12_pdf_export_generation(self):
        """12. ReportExporter successfully creates a valid PDF file with content."""
        rep = self.service.generate_daily_report("2026-09-23")
        pdf_path = self.exporter.export_pdf(rep, filename="test_daily.pdf")
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 500)

    def test_13_excel_export_generation(self):
        """13. ReportExporter successfully creates a valid multi-tab Excel workbook."""
        rep = self.service.generate_daily_report("2026-09-23")
        xlsx_path = self.exporter.export_excel(rep, filename="test_daily.xlsx")
        self.assertTrue(xlsx_path.exists())
        self.assertGreater(xlsx_path.stat().st_size, 500)

    def test_14_csv_export_generation(self):
        """14. ReportExporter successfully creates a valid CSV file with headers."""
        rep = self.service.generate_daily_report("2026-09-23")
        csv_path = self.exporter.export_csv(rep, filename="test_daily.csv")
        self.assertTrue(csv_path.exists())
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
            self.assertGreaterEqual(len(lines), 4) # Header + 3 articles
            self.assertIn("Website,Section,Headline", lines[0])

    def test_15_empty_export_handling(self):
        """15. Exporting an empty report creates valid files without raising exceptions."""
        rep = self.service.generate_daily_report("2010-01-01")
        pdf_path = self.exporter.export_pdf(rep, filename="empty.pdf")
        xlsx_path = self.exporter.export_excel(rep, filename="empty.xlsx")
        csv_path = self.exporter.export_csv(rep, filename="empty.csv")
        self.assertTrue(pdf_path.exists())
        self.assertTrue(xlsx_path.exists())
        self.assertTrue(csv_path.exists())

    def test_16_report_does_not_fabricate_data(self):
        """16. Reports strictly reflect real database values without fabricating stories or counts."""
        rep = self.service.generate_custom_report(search="NonExistentHeadline12345")
        self.assertEqual(rep.total_matching, 0)
        self.assertEqual(len(rep.articles), 0)

    def _get_client(self):
        from app.main import app
        try:
            from fastapi.testclient import TestClient
            return TestClient(app)
        except (ImportError, RuntimeError):
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
                def __init__(self, app_instance):
                    self.app = app_instance

                def get(self, url: str):
                    parsed = urllib.parse.urlparse(url)
                    path = parsed.path
                    query_string = parsed.query.encode("latin-1")

                    status_code = 500
                    headers = {}
                    body_chunks = []

                    scope = {
                        "type": "http",
                        "http_version": "1.1",
                        "method": "GET",
                        "path": path,
                        "raw_path": path.encode("ascii"),
                        "query_string": query_string,
                        "headers": [(b"host", b"testserver"), (b"user-agent", b"testclient")],
                        "client": ("127.0.0.1", 12345),
                        "server": ("testserver", 80),
                        "scheme": "http",
                    }

                    async def receive():
                        return {"type": "http.request", "body": b"", "more_body": False}

                    async def send(message):
                        nonlocal status_code, headers, body_chunks
                        if message["type"] == "http.response.start":
                            status_code = message["status"]
                            for k, v in message.get("headers", []):
                                headers[k.decode("latin-1").lower()] = v.decode("latin-1")
                        elif message["type"] == "http.response.body":
                            body_chunks.append(message.get("body", b""))

                    asyncio.run(self.app(scope, receive, send))
                    return _ASGIResponse(status_code, headers, b"".join(body_chunks))

            return _ASGITestClient(app)

    def test_17_api_daily_endpoint(self):
        """17. GET /api/reports/daily returns valid JSON with executive summary."""
        client = self._get_client()
        res = client.get("/api/reports/daily")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("executive_summary", data)
        self.assertIn("publisher_breakdown", data)
        self.assertIn("top_stories", data)

    def test_18_api_weekly_endpoint(self):
        """18. GET /api/reports/weekly returns valid JSON with daily volume tracking."""
        client = self._get_client()
        res = client.get("/api/reports/weekly?start_date=2026-09-20&end_date=2026-09-26")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("daily_volume", data)
        self.assertIn("total_articles", data)

    def test_19_api_custom_endpoint(self):
        """19. GET /api/reports/custom filters matching records."""
        client = self._get_client()
        res = client.get("/api/reports/custom?website=et_brand_equity")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("articles", data)
        self.assertIn("total_matching", data)

    def test_20_api_invalid_date_range_400(self):
        """20. Invalid date format or start_date > end_date returns HTTP 400."""
        client = self._get_client()
        # Inverted range
        res_inv = client.get("/api/reports/weekly?start_date=2026-09-30&end_date=2026-09-01")
        self.assertEqual(res_inv.status_code, 400)
        self.assertIn("start_date", res_inv.json()["detail"])

        # Invalid format
        res_fmt = client.get("/api/reports/daily?date=invalid-date")
        self.assertEqual(res_fmt.status_code, 400)

    def test_21_api_export_endpoint(self):
        """21. GET /api/reports/export returns file attachment."""
        client = self._get_client()
        res_csv = client.get("/api/reports/export?report_type=daily&format=csv")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers["content-type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
