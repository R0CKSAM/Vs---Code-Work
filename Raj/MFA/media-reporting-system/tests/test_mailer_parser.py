"""
Media Reporting System - Mailer Intelligence Test Suite
Tests parser accuracy, data extraction, duplicate detection, and database storage.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from database.repository import Repository
from database.schema import init_db
from mailer.best_media_info_parser import BestMediaInfoParser
from mailer.models import ParsedMailer
from mailer.service import MailerService


def load_fixture() -> str:
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "mailer"
        / "tests"
        / "fixtures"
        / "best_media_info_sample.html"
    )
    return fixture_path.read_text(encoding="utf-8")


def test_1_newsletter_heading_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    assert parsed.newsletter_heading is not None
    assert "Restore BARC" in parsed.newsletter_heading
    assert "EService Commerce" in parsed.newsletter_heading


def test_2_sender_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    meta = {
        "sender_name": "Best Media Info",
        "sender_email": "bmi@bestmediainfo.in",
        "date": "06 Oct 2026, 11:34 AM",
    }
    parsed = parser.parse_email_html(html_content, metadata=meta)
    assert parsed.sender_name == "Best Media Info"
    assert parsed.sender_email == "bmi@bestmediainfo.in"
    assert parsed.received_datetime == "06 Oct 2026, 11:34 AM"


def test_3_article_title_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    titles = [a.title for a in parsed.articles]
    assert any("Restore BARC or risk accelerating TV’s decline" in t for t in titles)
    assert any("Why EService Commerce is the next breaking news" in t for t in titles)
    assert any("56% of strategists fear AI will replace them" in t for t in titles)


def test_4_article_description_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    first_article = parsed.articles[0]
    assert first_article.description is not None
    assert len(first_article.description) > 30
    assert "FMCG" in first_article.description or "ministry" in first_article.description or "audience" in first_article.description


def test_5_article_url_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    for art in parsed.articles:
        assert art.source_url.startswith("http://") or art.source_url.startswith("https://")
        assert "gmail.com" not in art.source_url
        assert "bestmediainfo.com" in art.source_url


def test_6_article_image_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    images = [a.image_url for a in parsed.articles if a.image_url]
    assert len(images) >= 4
    assert any("barc_tv_ratings.jpg" in img for img in images)


def test_7_advertisement_extraction():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    assert len(parsed.advertisements) >= 2
    ad_targets = [ad.target_url for ad in parsed.advertisements if ad.target_url]
    assert any("fortuneonline.in" in u for u in ad_targets)
    assert any("doubleverify.com" in u for u in ad_targets)


def test_8_multiple_articles():
    html_content = load_fixture()
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(html_content)
    assert len(parsed.articles) >= 5
    # Verify sequential ordering
    orders = [a.order for a in parsed.articles]
    assert orders == sorted(orders)


def test_9_missing_image():
    sample = """
    <div class="article-card">
        <h3><a href="https://bestmediainfo.com/2026/10/text-only-story">Text Only Story Without Image</a></h3>
        <p>This story has no image tag whatsoever in its HTML block.</p>
    </div>
    """
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(sample)
    assert len(parsed.articles) == 1
    assert parsed.articles[0].image_url is None
    assert parsed.articles[0].title == "Text Only Story Without Image"


def test_10_missing_url():
    sample = """
    <div class="article-card">
        <h3>Story With Missing Link</h3>
        <p>This story is missing an anchor tag.</p>
    </div>
    """
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(sample)
    # Parser should safely discard non-linked items without throwing an exception
    assert isinstance(parsed.articles, list)


def test_11_malformed_html():
    malformed = "<div><h3><a href='https://bestmediainfo.com/malformed'>Unclosed tag sample<p>broken text</td>"
    parser = BestMediaInfoParser()
    parsed = parser.parse_email_html(malformed)
    assert parsed is not None
    assert isinstance(parsed.articles, list)


def test_12_duplicate_email():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = Path(tmp.name)
        init_db(db_path)
        repo = Repository(db_path)
        service = MailerService(repo)

        html_content = load_fixture()
        meta = {"sender_email": "bmi@bestmediainfo.in", "date": "2026-10-06T11:34:00"}

        # First insert
        res1 = service.process_email_html(html_content, metadata=meta)
        assert res1["status"] == "created"
        assert res1["is_duplicate"] is False
        first_id = res1["data"]["id"]

        # Second insert of exact same email
        res2 = service.process_email_html(html_content, metadata=meta)
        assert res2["status"] == "duplicate"
        assert res2["is_duplicate"] is True
        assert res2["data"]["id"] == first_id

        # Verify database has only 1 newsletter record
        listing = service.list_newsletters()
        assert len(listing) == 1


def test_13_multiple_newsletters():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = Path(tmp.name)
        init_db(db_path)
        repo = Repository(db_path)
        service = MailerService(repo)

        html_1 = load_fixture()
        html_2 = html_1.replace("As Navratri", "Navratri Part 2")

        res1 = service.process_email_html(html_1, metadata={"date": "2026-10-06T11:00:00"})
        res2 = service.process_email_html(html_2, metadata={"date": "2026-10-05T11:00:00"})

        assert res1["is_duplicate"] is False
        assert res2["is_duplicate"] is False

        newsletters = service.list_newsletters()
        assert len(newsletters) == 2


def test_14_search_filter_behavior():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = Path(tmp.name)
        init_db(db_path)
        repo = Repository(db_path)
        service = MailerService(repo)

        html_content = load_fixture()
        service.process_email_html(html_content, metadata={"date": "2026-10-06T11:34:00"})

        # Search for BARC
        found_barc = service.list_newsletters(search="BARC")
        assert len(found_barc) == 1

        # Search for advertiser DoubleVerify
        found_dv = service.list_newsletters(search="DoubleVerify")
        assert len(found_dv) == 1

        # Search for non-existent keyword
        empty = service.list_newsletters(search="NonExistentKeywordXYZ")
        assert len(empty) == 0


if __name__ == "__main__":
    test_1_newsletter_heading_extraction()
    test_2_sender_extraction()
    test_3_article_title_extraction()
    test_4_article_description_extraction()
    test_5_article_url_extraction()
    test_6_article_image_extraction()
    test_7_advertisement_extraction()
    test_8_multiple_articles()
    test_9_missing_image()
    test_10_missing_url()
    test_11_malformed_html()
    test_12_duplicate_email()
    test_13_multiple_newsletters()
    test_14_search_filter_behavior()
    print("ALL 14 MAILER TESTS PASSED SUCCESSFULLY!")
