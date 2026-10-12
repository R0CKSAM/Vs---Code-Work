"""
Media Reporting System - Phase 3 Direct Verification Script
Tests ET BrandEquity service, Exchange4media service, schema integrity,
failure isolation, and dashboard aggregation without requiring a network server.
"""
import sys
import os
import json
from pathlib import Path

# Add backend directory and project root to sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                           # backend/  → app.*
sys.path.insert(0, os.path.dirname(_HERE))          # project root → database.*

from app.services.et_brand_equity_service import load_et_brand_equity_data
from app.services.exchange4media_service import load_exchange4media_data, e4m_service
from app.services.mock_data import get_mock_dashboard_data


def run_checks():
    print("=" * 70)
    print("  PHASE 3: MULTI-PORTAL SCRAPER & DASHBOARD INTEGRATION VERIFICATION")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 1. ET BrandEquity Ingestion & Regression Test
    # -----------------------------------------------------------------------
    print("\n[1/4] Regression Testing: ET BrandEquity Scraper File Ingestion...")
    et_data = load_et_brand_equity_data()
    et_articles = et_data.get("articles", [])
    et_meta = et_data.get("website", {})
    et_stats = et_data.get("stats", {})

    print(f"  - Website Key:        {et_meta.get('key')}")
    print(f"  - Website Status:     {et_meta.get('status')}")
    print(f"  - Total Articles:     {len(et_articles)}")
    print(f"  - With Hero Image:    {et_stats.get('articles_with_image')}")
    print(f"  - With Summary:       {et_stats.get('articles_with_summary')}")
    print(f"  - Sections Present:   {et_data.get('sections')}")

    assert len(et_articles) >= 20, f"Expected >= 20 ET articles, got {len(et_articles)}"
    assert et_meta.get("status") == "AVAILABLE", "ET BrandEquity status should be AVAILABLE"
    print("  --> ET BrandEquity Ingestion: PASSED [OK]")

    # -----------------------------------------------------------------------
    # 2. Exchange4media Ingestion & Schema Test (Phase 3)
    # -----------------------------------------------------------------------
    print("\n[2/4] Testing: Exchange4media Scraper File Ingestion & Schemas...")
    e4m_data = load_exchange4media_data()
    e4m_articles = e4m_data.get("articles", [])
    e4m_meta = e4m_data.get("website", {})
    e4m_stats = e4m_data.get("stats", {})

    print(f"  - Website Key:        {e4m_meta.get('key')}")
    print(f"  - Website Status:     {e4m_meta.get('status')}")
    print(f"  - Total Articles:     {len(e4m_articles)}")
    print(f"  - With Hero Image:    {e4m_stats.get('articles_with_image')}")
    print(f"  - With Summary:       {e4m_stats.get('articles_with_summary')}")
    print(f"  - Sections Present:   {e4m_data.get('sections')}")

    assert len(e4m_articles) >= 20, f"Expected >= 20 E4M articles, got {len(e4m_articles)}"
    assert e4m_meta.get("status") == "AVAILABLE", "Exchange4media status should be AVAILABLE"

    # Validate article schema fields
    sample_e4m = e4m_articles[0]
    required_fields = ["id", "headline", "url", "section", "scraped_at", "content_hash", "website_key"]
    for field in required_fields:
        assert field in sample_e4m and sample_e4m[field], f"Missing or empty required field: {field}"
        print(f"  - Sample {field}: {str(sample_e4m[field])[:60]}")

    assert "published_at" in sample_e4m, "Field 'published_at' must be present in schema"
    assert sample_e4m["website_key"] == "exchange4media", "website_key must be 'exchange4media'"
    assert sample_e4m["status"] == "CURRENT", "Article status must be 'CURRENT'"
    assert len(sample_e4m["content_hash"]) == 64, "content_hash must be a valid 64-char SHA-256 string"

    print("  --> Exchange4media Ingestion & Schema Test: PASSED [OK]")

    # -----------------------------------------------------------------------
    # 3. Test Service Filtering & Pagination
    # -----------------------------------------------------------------------
    print("\n[3/4] Testing Exchange4media Service Endpoint Logic...")
    filtered_payload = e4m_service.get_articles(section="advertising", limit=5, skip=0)
    filtered_articles = filtered_payload.get("articles", [])
    print(f"  - Filtered by section='advertising': {len(filtered_articles)} articles returned")
    for a in filtered_articles:
        assert a["section"].lower() == "advertising", f"Expected section 'Advertising', got '{a['section']}'"
    print("  --> Service Filtering & Pagination Test: PASSED [OK]")

    # -----------------------------------------------------------------------
    # 4. Unified Dashboard Aggregation Test
    # -----------------------------------------------------------------------
    print("\n[4/4] Validating Dual-Portal Dashboard Aggregation...")
    dashboard_data = get_mock_dashboard_data()
    kpis = dashboard_data.kpis
    websites = dashboard_data.websites
    news = dashboard_data.latest_news

    print(f"  - Monitored Websites Count:    {kpis.websites_monitored}")
    print(f"  - Total Articles Ingested KPI: {kpis.new_articles}")
    print(f"  - Latest News Feed Items:      {len(news)}")

    assert kpis.websites_monitored == 7, f"Expected 7 websites monitored, got {kpis.websites_monitored}"
    assert len(websites) == 7, f"Expected 7 website cards, got {len(websites)}"

    # Verify website cards are present
    et_card = next((w for w in websites if "et" in w.id.lower()), None)
    e4m_card = next((w for w in websites if "exchange4media" in w.id.lower()), None)
    ci_card = next((w for w in websites if "campaign" in w.id.lower()), None)
    bmi_card = next((w for w in websites if "bestmedia" in w.id.lower()), None)
    ss_card = next((w for w in websites if "samosa" in w.id.lower()), None)
    adg_card = next((w for w in websites if "adgully" in w.id.lower()), None)
    mb_card = next((w for w in websites if "brief" in w.id.lower()), None)

    assert et_card is not None, "ET BrandEquity card missing from dashboard!"
    assert e4m_card is not None, "Exchange4media card missing from dashboard!"
    assert ci_card is not None, "Campaign India card missing from dashboard!"
    assert bmi_card is not None, "BestMediaInfo card missing from dashboard!"
    assert ss_card is not None, "Social Samosa card missing from dashboard!"
    assert adg_card is not None, "Adgully card missing from dashboard!"
    assert mb_card is not None, "MediaBrief card missing from dashboard!"

    print(f"  - ET Card:  status={et_card.status}, articles={et_card.articles_detected}")
    print(f"  - E4M Card: status={e4m_card.status}, articles={e4m_card.articles_detected}")

    assert et_card.status == "AVAILABLE", "ET card should be AVAILABLE"
    assert e4m_card.status == "AVAILABLE", "E4M card should be AVAILABLE"

    # Verify news feed contains articles from both publishers
    et_news_count = sum(1 for n in news if "ET" in n.source)
    e4m_news_count = sum(1 for n in news if "Exchange" in n.source)

    print(f"  - News feed breakdown: {et_news_count} ET stories, {e4m_news_count} E4M stories")
    assert et_news_count > 0, "News feed must contain ET stories"
    assert e4m_news_count > 0, "News feed must contain Exchange4media stories"

    print("  --> Dashboard Aggregation Test: PASSED [OK]")

    # -----------------------------------------------------------------------
    # 5. Test Refresh Endpoints & Zero Cross-Contamination
    # -----------------------------------------------------------------------
    print("\n[5/5] Testing Refresh Functions & Zero Cross-Site Contamination...")

    # Ensure the live (default-path) database has the Phase 4 schema before
    # the refresh functions attempt to use db_repo / change_detector singletons.
    from database.schema import init_db as _init_live_db
    _init_live_db()  # idempotent — CREATE TABLE IF NOT EXISTS

    from app.services.et_brand_equity_service import run_et_brand_equity_refresh
    from app.services.exchange4media_service import run_exchange4media_refresh

    print("  - Running live refresh for ET BrandEquity...")
    refreshed_et = run_et_brand_equity_refresh()
    assert refreshed_et["is_available"], "Refreshed ET data must be available"
    for art in refreshed_et["articles"]:
        assert "indiatimes.com" in art["url"] or "economictimes" in art["url"], f"Invalid ET URL: {art['url']}"
        assert art["website_key"] == "et_brand_equity", "Website key must be et_brand_equity"
    print("  - ET BrandEquity refresh executed: 0 cross-contamination errors [OK]")

    print("  - Running live refresh for Exchange4media...")
    refreshed_e4m = run_exchange4media_refresh()
    assert refreshed_e4m["is_available"], "Refreshed E4M data must be available"
    for art in refreshed_e4m["articles"]:
        assert "exchange4media.com" in art["url"], f"Invalid E4M URL: {art['url']}"
        assert art["website_key"] == "exchange4media", "Website key must be exchange4media"
    print("  - Exchange4media refresh executed: 0 cross-contamination errors [OK]")
    # -----------------------------------------------------------------------
    # 6. Phase 4: Database Persistence & Change Detection Verification
    # -----------------------------------------------------------------------
    print("\n[6/6] Testing Phase 4: Database Persistence & 2-Cycle Change Detection...")
    import tempfile
    from database.connection import get_db
    from database.schema import init_schema
    from database.repository import Repository
    from app.services.change_detector import ChangeDetector

    # Create temporary database to test 2-cycle change detection cleanly
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        t_db_path = f.name

    try:
        init_schema(t_db_path)
        t_repo = Repository(t_db_path)
        t_detector = ChangeDetector(t_db_path)

        # Initialize websites
        t_repo.get_or_create_website("ET BrandEquity", "et_brand_equity", "https://brandequity.economictimes.indiatimes.com/")
        t_repo.get_or_create_website("Exchange4media", "exchange4media", "https://www.exchange4media.com/")

        # Cycle 1: First Ingest (Expect 25 ET NEW, 25 E4M NEW)
        c1_et = t_detector.process_scrape_result("et_brand_equity", et_articles, scrape_success=True)
        c1_e4m = t_detector.process_scrape_result("exchange4media", e4m_articles, scrape_success=True)

        print(f"  - Cycle 1 (Initial Ingest): ET New={c1_et['new']}, E4M New={c1_e4m['new']}")
        assert c1_et["new"] == len(et_articles), f"Expected {len(et_articles)} new ET articles, got {c1_et['new']}"
        assert c1_e4m["new"] == len(e4m_articles), f"Expected {len(e4m_articles)} new E4M articles, got {c1_e4m['new']}"
        assert c1_et["updated"] == 0 and c1_et["unchanged"] == 0
        assert c1_e4m["updated"] == 0 and c1_e4m["unchanged"] == 0

        # Cycle 2: Second Ingest with identical data (Expect 25 ET UNCHANGED, 25 E4M UNCHANGED, 0 NEW)
        c2_et = t_detector.process_scrape_result("et_brand_equity", et_articles, scrape_success=True)
        c2_e4m = t_detector.process_scrape_result("exchange4media", e4m_articles, scrape_success=True)

        print(f"  - Cycle 2 (Repeat Ingest): ET Unchanged={c2_et['unchanged']}, E4M Unchanged={c2_e4m['unchanged']}")
        assert c2_et["new"] == 0, f"Expected 0 new ET articles on repeat run, got {c2_et['new']}"
        assert c2_et["unchanged"] == len(et_articles), f"Expected {len(et_articles)} unchanged ET articles, got {c2_et['unchanged']}"
        assert c2_e4m["new"] == 0, f"Expected 0 new E4M articles on repeat run, got {c2_e4m['new']}"
        assert c2_e4m["unchanged"] == len(e4m_articles), f"Expected {len(e4m_articles)} unchanged E4M articles, got {c2_e4m['unchanged']}"

        # Verify version history consistency
        versions_sample = t_repo.get_article_versions(1)
        assert len(versions_sample) == 1, "Expected exactly 1 version after unchanged cycle"
        assert versions_sample[0]["version_number"] == 1, "Initial version must be 1"

        # Verify scrape runs table
        runs = t_repo.get_recent_scrape_runs(limit=10)
        assert len(runs) == 4, f"Expected 4 scrape runs logged, got {len(runs)}"
        print(f"  - Scrape Runs Logged: {len(runs)} runs recorded successfully")

        # Verify false removal protection (0 articles or scrape failure must NOT mark removed)
        safe_result = t_detector.process_scrape_result("et_brand_equity", [], scrape_success=False, error_message="Network glitch")
        assert safe_result["removed"] == 0, "Failed scrape must not remove articles"
        print("  - False removal safeguard: Confirmed active")

        print("  --> Phase 4 Change Detection & Persistence: PASSED [OK]")

    finally:
        if os.path.exists(t_db_path):
            try:
                os.remove(t_db_path)
            except OSError:
                pass

    print("\n" + "=" * 70)
    print("  ALL VERIFICATION CHECKS (PHASE 1 - PHASE 4) PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_checks()
    except Exception as e:
        print(f"\n[FAIL] Verification error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
