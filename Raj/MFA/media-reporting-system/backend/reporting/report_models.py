"""
Media Reporting System - Report Models & Schemas
Defines structured data contracts for executive briefs, publisher breakdowns,
weekly volumes, custom dossiers, and export requests.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ArticleReportItem(BaseModel):
    id: int
    website_id: int
    website_name: str
    website_key: str
    section_name: str = "Overall"
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    published_at: Optional[str] = None
    first_seen_at: str
    last_seen_at: str
    last_changed_at: str
    status: str
    content_hash: str


class PublisherBreakdown(BaseModel):
    website_name: str
    website_key: str
    article_count: int = 0
    percentage: float = 0.0
    new_count: int = 0
    updated_count: int = 0
    removed_count: int = 0


class SectionBreakdown(BaseModel):
    section_name: str
    website_name: str
    website_key: str
    article_count: int = 0
    new_count: int = 0
    updated_count: int = 0


class DailyVolumeItem(BaseModel):
    date: str
    et_count: int = 0
    e4m_count: int = 0
    total_count: int = 0


class MonitoringRunSummary(BaseModel):
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_run_time: Optional[str] = None
    status_summary: str = "No monitoring activity"


class ExecutiveSummary(BaseModel):
    reporting_date: str
    total_articles: int = 0
    et_article_count: int = 0
    e4m_article_count: int = 0
    sections_count: int = 0
    new_articles_count: int = 0
    updated_articles_count: int = 0
    removed_articles_count: int = 0
    monitoring_status: str = "Nominal"


class DailyReportResponse(BaseModel):
    executive_summary: ExecutiveSummary
    publisher_breakdown: List[PublisherBreakdown] = Field(default_factory=list)
    section_breakdown: List[SectionBreakdown] = Field(default_factory=list)
    top_stories: List[ArticleReportItem] = Field(default_factory=list)
    new_articles: List[ArticleReportItem] = Field(default_factory=list)
    updated_articles: List[ArticleReportItem] = Field(default_factory=list)
    removed_articles: List[ArticleReportItem] = Field(default_factory=list)
    monitoring_runs: MonitoringRunSummary = Field(default_factory=MonitoringRunSummary)


class WeeklyReportResponse(BaseModel):
    date_range: Dict[str, str]
    total_articles: int = 0
    et_article_count: int = 0
    e4m_article_count: int = 0
    sections_count: int = 0
    new_articles_count: int = 0
    updated_articles_count: int = 0
    removed_articles_count: int = 0
    publisher_breakdown: List[PublisherBreakdown] = Field(default_factory=list)
    daily_volume: List[DailyVolumeItem] = Field(default_factory=list)
    section_breakdown: List[SectionBreakdown] = Field(default_factory=list)
    top_stories: List[ArticleReportItem] = Field(default_factory=list)
    new_articles: List[ArticleReportItem] = Field(default_factory=list)
    updated_articles: List[ArticleReportItem] = Field(default_factory=list)
    removed_articles: List[ArticleReportItem] = Field(default_factory=list)
    monitoring_runs: MonitoringRunSummary = Field(default_factory=MonitoringRunSummary)


class CustomReportResponse(BaseModel):
    filters: Dict[str, Any]
    total_matching: int = 0
    publisher_breakdown: List[PublisherBreakdown] = Field(default_factory=list)
    section_breakdown: List[SectionBreakdown] = Field(default_factory=list)
    status_breakdown: Dict[str, int] = Field(default_factory=dict)
    articles: List[ArticleReportItem] = Field(default_factory=list)
