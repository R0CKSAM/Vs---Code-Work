"""
Pydantic schemas for the Dashboard API and Monitoring Endpoints.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "media-reporting-system"
    version: str = "0.1.0"
    phase: str = "PHASE 2B - ET BRANDEQUITY DASHBOARD INTEGRATION"


class KPIData(BaseModel):
    websites_monitored: int
    articles_today: int
    new_articles: int
    advertisements_tracked: int
    articles_change_pct: float
    new_articles_period: str
    ads_change_pct: float


class WebsiteInfo(BaseModel):
    id: str
    name: str
    url: str
    status: str  # e.g., "AVAILABLE", "ONLINE", "DATA UNAVAILABLE"
    last_checked: str
    articles_detected: int
    domain: str
    category: str
    advertisements_detected: Optional[int] = 0
    response_time_ms: Optional[int] = 320


class NewsArticle(BaseModel):
    id: str
    headline: str
    summary: str
    source: str
    section: str
    published_time: str
    image_url: Optional[str] = None
    url: Optional[str] = None
    read_time: str = "3 min read"
    published_at: Optional[str] = None
    publication_label: Optional[str] = None
    is_exclusive: Optional[bool] = False
    scraped_at: Optional[str] = None
    content_hash: Optional[str] = None
    status: Optional[str] = "CURRENT"


class AdvertisementSummary(BaseModel):
    id: str
    brand_name: str
    format: str
    placement: str
    first_seen: str
    status: str


class SystemStatus(BaseModel):
    status: str
    subtitle: str
    current_date: str
    last_updated: str
    environment: str


class DashboardResponse(BaseModel):
    system_status: SystemStatus
    kpis: KPIData
    websites: List[WebsiteInfo]
    latest_news: List[NewsArticle]
    advertisements_summary: List[AdvertisementSummary]


# ---------------------------------------------------------------------------
# Dedicated ET BrandEquity Monitoring Schemas (Phase 2B)
# ---------------------------------------------------------------------------
class ETWebsiteMeta(BaseModel):
    key: str = "et_brand_equity"
    name: str = "ET BrandEquity"
    url: str = "https://brandequity.economictimes.indiatimes.com/"
    status: str = "AVAILABLE"


class ETArticleItem(BaseModel):
    id: str
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    section: str
    published_at: Optional[str] = None
    publication_label: Optional[str] = None
    is_exclusive: Optional[bool] = False
    scraped_at: str
    content_hash: str
    website: str = "ET BrandEquity"
    website_key: str = "et_brand_equity"
    status: str = "CURRENT"
    read_time: str = "3 min read"


class ETArticlesStats(BaseModel):
    articles_today: int
    articles_with_image: int
    articles_with_summary: int
    articles_with_published_at: int
    latest_scraped_at: Optional[str] = None


class ETArticlesResponse(BaseModel):
    website: ETWebsiteMeta
    generated_at: Optional[str] = None
    count: int
    sections: List[str]
    articles: List[ETArticleItem]
    stats: Optional[ETArticlesStats] = None
    source_file: Optional[str] = None
    is_available: bool = True


# ---------------------------------------------------------------------------
# Phase 3: Exchange4media Scraper Schemas
# ---------------------------------------------------------------------------
class E4MWebsiteMeta(BaseModel):
    key: str = "exchange4media"
    name: str = "Exchange4media"
    url: str = "https://www.exchange4media.com/"
    status: str = "AVAILABLE"


class E4MArticleItem(BaseModel):
    id: str
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    section: str
    published_at: Optional[str] = None
    publication_label: Optional[str] = None
    is_exclusive: Optional[bool] = False
    scraped_at: str
    content_hash: str
    website: str = "Exchange4media"
    website_key: str = "exchange4media"
    status: str = "CURRENT"
    read_time: str = "3 min read"


class E4MArticlesStats(BaseModel):
    articles_today: int
    articles_with_image: int
    articles_with_summary: int
    articles_with_published_at: int
    latest_scraped_at: Optional[str] = None


class E4MArticlesResponse(BaseModel):
    website: E4MWebsiteMeta
    generated_at: Optional[str] = None
    count: int
    sections: List[str]
    articles: List[E4MArticleItem]
    stats: Optional[E4MArticlesStats] = None
    source_file: Optional[str] = None
    is_available: bool = True


# ---------------------------------------------------------------------------
# Phase 4: Change Detection & Historical Tracking Schemas
# ---------------------------------------------------------------------------
class ArticleVersionItem(BaseModel):
    id: int
    article_id: int
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    section_name: Optional[str] = None
    published_at: Optional[str] = None
    content_hash: str
    detected_at: str
    change_type: str  # 'NEW' | 'UPDATED'


class ArticleHistoryResponse(BaseModel):
    article_id: int
    headline: str
    url: str
    status: str
    first_seen_at: str
    last_seen_at: str
    last_changed_at: str
    versions_count: int
    versions: List[ArticleVersionItem]


class ArticleChangeItem(BaseModel):
    version_id: int
    article_id: int
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    section: Optional[str] = None
    website_name: str
    website_key: str
    change_type: str  # 'NEW' | 'UPDATED' | 'REMOVED'
    detected_at: str
    current_status: str
    current_hash: str


class ChangeKPIsResponse(BaseModel):
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0


class ChangesResponse(BaseModel):
    timeframe: str
    count: int
    kpis: ChangeKPIsResponse
    changes: List[ArticleChangeItem]


class ScrapeRunItem(BaseModel):
    id: int
    website_name: str
    website_key: str
    started_at: str
    finished_at: Optional[str] = None
    status: str  # 'RUNNING' | 'SUCCESS' | 'FAILED'
    items_found: int = 0
    new_items: int = 0
    updated_items: int = 0
    unchanged_items: int = 0
    removed_items: int = 0
    duration: Optional[str] = "--"
    error_message: Optional[str] = None


class ScrapeRunsResponse(BaseModel):
    count: int
    runs: List[ScrapeRunItem]


# ---------------------------------------------------------------------------
# Phase 8: Generic Media Source Schemas
# ---------------------------------------------------------------------------
class SourceWebsiteMeta(BaseModel):
    key: str
    name: str
    url: str
    status: str = "AVAILABLE"


class SourceArticleItem(BaseModel):
    id: str
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    section: str
    published_at: Optional[str] = None
    publication_label: Optional[str] = None
    is_exclusive: Optional[bool] = False
    scraped_at: Optional[str] = ""
    content_hash: Optional[str] = ""
    website: str
    website_key: str
    status: str = "CURRENT"
    read_time: str = "3 min read"


class SourceArticlesStats(BaseModel):
    articles_today: int
    articles_with_image: int
    articles_with_summary: int
    articles_with_published_at: int
    latest_scraped_at: Optional[str] = None


class SourceArticlesResponse(BaseModel):
    website: SourceWebsiteMeta
    generated_at: Optional[str] = None
    count: int
    sections: List[str]
    articles: List[SourceArticleItem]
    stats: Optional[SourceArticlesStats] = None
    source_file: Optional[str] = None
    is_available: bool = True



