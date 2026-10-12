"""
Media Reporting System - Dashboard Data Service
Provides live and database-backed data for all 7 monitored media publications:
- ET BrandEquity
- Exchange4media
- Campaign India
- BestMediaInfo
- Social Samosa
- Adgully
- MediaBrief
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.schemas.dashboard import (
    AdvertisementSummary,
    DashboardResponse,
    KPIData,
    NewsArticle,
    SystemStatus,
    WebsiteInfo,
)
from app.services.et_brand_equity_service import load_et_brand_equity_data
from app.services.exchange4media_service import load_exchange4media_data
from app.services.generic_source_service import load_source_data


def format_relative_time(
    iso_str: Optional[str],
    publication_label: Optional[str] = None,
    is_exclusive: bool = False,
) -> str:
    """Formats publication time. Editorial badges never replace the time field."""
    if iso_str:
        try:
            dt = iso_str if isinstance(iso_str, datetime) else datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - dt
            seconds = int(diff.total_seconds())

            if seconds < 60:
                return "Just now"
            elif seconds < 3600:
                return f"{seconds // 60} mins ago"
            elif seconds < 86400:
                hours = seconds // 3600
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
            elif seconds < 172800:
                return "Yesterday"
            else:
                from datetime import timedelta
                ist = timezone(timedelta(hours=5, minutes=30))
                return dt.astimezone(ist).strftime("%d %b %Y, %I:%M %p IST")
        except Exception:
            pass
    if publication_label and publication_label.strip():
        return publication_label.strip()
    return "Time pending verification"


def _articles_to_news_models(articles: List[Dict[str, Any]], source_name: str) -> List[NewsArticle]:
    models: List[NewsArticle] = []
    for art in articles:
        rel_time = format_relative_time(
            art.get("published_at"),
            publication_label=art.get("publication_label"),
            is_exclusive=bool(art.get("is_exclusive")),
        )
        models.append(
            NewsArticle(
                id=art.get("id") or f"art-{abs(hash(art.get('url', '')))}",
                headline=art["headline"],
                summary=art.get("summary") or "Executive summary available on primary publication source.",
                source=source_name,
                section=art.get("section") or "Overall",
                published_time=rel_time,
                read_time="3 min read",
                image_url=art.get("image_url"),
                url=art.get("url"),
                published_at=art.get("published_at"),
                publication_label=art.get("publication_label"),
                is_exclusive=bool(art.get("is_exclusive")),
                scraped_at=art.get("scraped_at"),
                content_hash=art.get("content_hash"),
                status=art.get("status") or "CURRENT",
            )
        )
    return models


def get_mock_dashboard_data() -> DashboardResponse:
    now = datetime.now(timezone.utc)
    formatted_date = now.strftime("%A, %B %d, %Y")
    formatted_time = now.strftime("%H:%M UTC")

    # 1. ET BrandEquity
    et_data = load_et_brand_equity_data()
    is_et_available = et_data.get("is_available", False)
    et_articles = et_data.get("articles", [])
    et_count = et_data.get("count", 0)
    et_today = et_data.get("stats", {}).get("articles_today", 0)
    et_gen_at = et_data.get("generated_at")
    et_last_checked = format_relative_time(et_gen_at) if et_gen_at else "Pending ingest"

    # 2. Exchange4media
    e4m_data = load_exchange4media_data()
    is_e4m_available = e4m_data.get("is_available", False)
    e4m_articles = e4m_data.get("articles", [])
    e4m_count = e4m_data.get("count", 0)
    e4m_today = e4m_data.get("stats", {}).get("articles_today", 0)
    e4m_gen_at = e4m_data.get("generated_at")
    e4m_last_checked = format_relative_time(e4m_gen_at) if e4m_gen_at else "Pending ingest"

    # 3. Campaign India
    ci_data = load_source_data("campaign_india", "Campaign India", "https://www.campaignindia.in/news")
    is_ci_available = ci_data.get("is_available", False)
    ci_articles = ci_data.get("articles", [])
    ci_count = ci_data.get("count", 0)
    ci_today = ci_data.get("stats", {}).get("articles_today", 0)
    ci_gen_at = ci_data.get("generated_at")
    ci_last_checked = format_relative_time(ci_gen_at) if ci_gen_at else "Pending ingest"

    # 4. BestMediaInfo
    bmi_data = load_source_data("bestmediainfo", "BestMediaInfo", "https://bestmediainfo.com/")
    is_bmi_available = bmi_data.get("is_available", False)
    bmi_articles = bmi_data.get("articles", [])
    bmi_count = bmi_data.get("count", 0)
    bmi_today = bmi_data.get("stats", {}).get("articles_today", 0)
    bmi_gen_at = bmi_data.get("generated_at")
    bmi_last_checked = format_relative_time(bmi_gen_at) if bmi_gen_at else "Pending ingest"

    # 5. Social Samosa
    ss_data = load_source_data("social_samosa", "Social Samosa", "https://www.socialsamosa.com/")
    is_ss_available = ss_data.get("is_available", False)
    ss_articles = ss_data.get("articles", [])
    ss_count = ss_data.get("count", 0)
    ss_today = ss_data.get("stats", {}).get("articles_today", 0)
    ss_gen_at = ss_data.get("generated_at")
    ss_last_checked = format_relative_time(ss_gen_at) if ss_gen_at else "Pending ingest"

    # 6. Adgully
    adg_data = load_source_data("adgully", "Adgully", "https://www.adgully.com/")
    is_adg_available = adg_data.get("is_available", False)
    adg_articles = adg_data.get("articles", [])
    adg_count = adg_data.get("count", 0)
    adg_today = adg_data.get("stats", {}).get("articles_today", 0)
    adg_gen_at = adg_data.get("generated_at")
    adg_last_checked = format_relative_time(adg_gen_at) if adg_gen_at else "Pending ingest"

    # 7. MediaBrief
    mb_data = load_source_data("mediabrief", "MediaBrief", "https://mediabrief.com/")
    is_mb_available = mb_data.get("is_available", False)
    mb_articles = mb_data.get("articles", [])
    mb_count = mb_data.get("count", 0)
    mb_today = mb_data.get("stats", {}).get("articles_today", 0)
    mb_gen_at = mb_data.get("generated_at")
    mb_last_checked = format_relative_time(mb_gen_at) if mb_gen_at else "Pending ingest"

    # 8. Storyboard18
    sb_data = load_source_data("storyboard18", "Storyboard18", "https://www.storyboard18.com/")
    is_sb_available = sb_data.get("is_available", False)
    sb_articles = sb_data.get("articles", [])
    sb_count = sb_data.get("count", 0)
    sb_today = sb_data.get("stats", {}).get("articles_today", 0)
    sb_gen_at = sb_data.get("generated_at")
    sb_last_checked = format_relative_time(sb_gen_at) if sb_gen_at else "Pending ingest"

    # 9. Indian Television
    itv_data = load_source_data("indiantelevision", "Indian Television", "https://indiantelevision.com/")
    is_itv_available = itv_data.get("is_available", False)
    itv_articles = itv_data.get("articles", [])
    itv_count = itv_data.get("count", 0)
    itv_today = itv_data.get("stats", {}).get("articles_today", 0)
    itv_gen_at = itv_data.get("generated_at")
    itv_last_checked = format_relative_time(itv_gen_at) if itv_gen_at else "Pending ingest"

    # Total articles today across all 9 sources
    articles_today_total = et_today + e4m_today + ci_today + bmi_today + ss_today + adg_today + mb_today + sb_today + itv_today
    total_new_articles = et_count + e4m_count + ci_count + bmi_count + ss_count + adg_count + mb_count + sb_count + itv_count

    websites = [
        WebsiteInfo(
            id="et-brandequity",
            name="ET BrandEquity",
            url="https://brandequity.economictimes.indiatimes.com/",
            status="AVAILABLE" if is_et_available else "DATA UNAVAILABLE",
            last_checked=et_last_checked,
            articles_detected=et_count if is_et_available else 0,
            domain="brandequity.economictimes.indiatimes.com",
            category="Marketing & Brand Intelligence",
        ),
        WebsiteInfo(
            id="exchange4media",
            name="Exchange4media",
            url="https://www.exchange4media.com/",
            status="AVAILABLE" if is_e4m_available else "DATA UNAVAILABLE",
            last_checked=e4m_last_checked,
            articles_detected=e4m_count if is_e4m_available else 0,
            domain="exchange4media.com",
            category="Media, Advertising & Broadcasting",
        ),
        WebsiteInfo(
            id="campaign-india",
            name="Campaign India",
            url="https://www.campaignindia.in/news",
            status="AVAILABLE" if is_ci_available else "DATA UNAVAILABLE",
            last_checked=ci_last_checked,
            articles_detected=ci_count if is_ci_available else 0,
            domain="campaignindia.in",
            category="Advertising & Creative Campaigns",
        ),
        WebsiteInfo(
            id="bestmediainfo",
            name="BestMediaInfo",
            url="https://bestmediainfo.com/",
            status="AVAILABLE" if is_bmi_available else "DATA UNAVAILABLE",
            last_checked=bmi_last_checked,
            articles_detected=bmi_count if is_bmi_available else 0,
            domain="bestmediainfo.com",
            category="Media, Marketing & Advertising",
        ),
        WebsiteInfo(
            id="social-samosa",
            name="Social Samosa",
            url="https://www.socialsamosa.com/",
            status="AVAILABLE" if is_ss_available else "DATA UNAVAILABLE",
            last_checked=ss_last_checked,
            articles_detected=ss_count if is_ss_available else 0,
            domain="socialsamosa.com",
            category="Social Media & Digital Trends",
        ),
        WebsiteInfo(
            id="adgully",
            name="Adgully",
            url="https://www.adgully.com/",
            status="AVAILABLE" if is_adg_available else "DATA UNAVAILABLE",
            last_checked=adg_last_checked,
            articles_detected=adg_count if is_adg_available else 0,
            domain="adgully.com",
            category="Advertising, Media & Marketing Exclusives",
        ),
        WebsiteInfo(
            id="mediabrief",
            name="MediaBrief",
            url="https://mediabrief.com/",
            status="AVAILABLE" if is_mb_available else "DATA UNAVAILABLE",
            last_checked=mb_last_checked,
            articles_detected=mb_count if is_mb_available else 0,
            domain="mediabrief.com",
            category="Media, OTT & Entertainment Insights",
        ),
        WebsiteInfo(
            id="storyboard18",
            name="Storyboard18",
            url="https://www.storyboard18.com/",
            status="AVAILABLE" if is_sb_available else "DATA UNAVAILABLE",
            last_checked=sb_last_checked,
            articles_detected=sb_count if is_sb_available else 0,
            domain="storyboard18.com",
            category="Marketing, Brand Strategy & Culture",
        ),
        WebsiteInfo(
            id="indiantelevision",
            name="Indian Television",
            url="https://indiantelevision.com/",
            status="AVAILABLE" if is_itv_available else "DATA UNAVAILABLE",
            last_checked=itv_last_checked,
            articles_detected=itv_count if is_itv_available else 0,
            domain="indiantelevision.com",
            category="Broadcasting, Cable, DTH & Digital Media",
        ),
    ]

    all_articles_groups = [
        _articles_to_news_models(et_articles, "ET BrandEquity"),
        _articles_to_news_models(e4m_articles, "Exchange4media"),
        _articles_to_news_models(ci_articles, "Campaign India"),
        _articles_to_news_models(bmi_articles, "BestMediaInfo"),
        _articles_to_news_models(ss_articles, "Social Samosa"),
        _articles_to_news_models(adg_articles, "Adgully"),
        _articles_to_news_models(mb_articles, "MediaBrief"),
        _articles_to_news_models(sb_articles, "Storyboard18"),
        _articles_to_news_models(itv_articles, "Indian Television"),
    ]

    # Interleave articles fairly across all active publications
    merged_news: List[NewsArticle] = []
    max_len = max((len(g) for g in all_articles_groups), default=0)
    for i in range(max_len):
        for group in all_articles_groups:
            if i < len(group):
                merged_news.append(group[i])

    # 3. Load real advertisements from database
    real_ad_summaries: List[AdvertisementSummary] = []
    ad_count = 0
    try:
        from database.repository import db_repo
        db_ads = db_repo.get_advertisements(status="ACTIVE", limit=5, identified_only=True)
        for a in db_ads:
            rel_seen = format_relative_time(a.get("first_seen_at"))
            real_ad_summaries.append(
                AdvertisementSummary(
                    id=f"ad-{a['id']}",
                    brand_name=a.get("brand") or a.get("advertiser") or "Brand Unspecified",
                    format=f"{a.get('position')} ({a.get('ad_type')})",
                    placement=a.get("website_name") or "Homepage",
                    first_seen=rel_seen,
                    status=a.get("status", "ACTIVE"),
                )
            )
        ad_count = db_repo.get_advertisement_kpis(identified_only=True).get("total_ads", 0)
    except Exception:
        ad_count = len(real_ad_summaries)

    return DashboardResponse(
        system_status=SystemStatus(
            status="9-Source Monitoring Active",
            subtitle="Real-time multi-portal media monitoring and intelligence",
            current_date=formatted_date,
            last_updated=f"Today at {formatted_time}",
            environment="Local Production / LAN (Phase 8B Nine-Source Suite)",
        ),
        kpis=KPIData(
            websites_monitored=9,
            articles_today=articles_today_total,
            new_articles=total_new_articles,
            advertisements_tracked=ad_count,
            articles_change_pct=0,
            new_articles_period="9-source live scraper ingest",
            ads_change_pct=0,
        ),
        websites=websites,
        latest_news=merged_news[:90],
        advertisements_summary=real_ad_summaries,
    )
