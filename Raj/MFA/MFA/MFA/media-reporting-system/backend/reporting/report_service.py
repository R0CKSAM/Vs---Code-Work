"""
Media Reporting System - Report Service
Synthesizes professional executive daily briefs, weekly industry roll-ups,
and parametric custom report dossiers directly from database records.
"""
from __future__ import annotations

import collections
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from backend.reporting.report_models import (
        ArticleReportItem,
        PublisherBreakdown,
        SectionBreakdown,
        DailyVolumeItem,
        MonitoringRunSummary,
        ExecutiveSummary,
        DailyReportResponse,
        WeeklyReportResponse,
        CustomReportResponse,
    )
    from backend.reporting.report_queries import ReportQueries
except ImportError:
    from reporting.report_models import (
        ArticleReportItem,
        PublisherBreakdown,
        SectionBreakdown,
        DailyVolumeItem,
        MonitoringRunSummary,
        ExecutiveSummary,
        DailyReportResponse,
        WeeklyReportResponse,
        CustomReportResponse,
    )
    from reporting.report_queries import ReportQueries


class ReportService:
    """Core reporting service engine."""

    def __init__(self, db_path: Optional[Path] = None):
        self.queries = ReportQueries(db_path)

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------
    @staticmethod
    def _to_article_item(row: Dict[str, Any]) -> ArticleReportItem:
        return ArticleReportItem(
            id=row["id"],
            website_id=row["website_id"],
            website_name=row.get("website_name") or "Unknown Publisher",
            website_key=row.get("website_key") or "unknown",
            section_name=row.get("section_name") or "Overall",
            headline=row.get("headline") or "Untitled",
            url=row.get("url") or "",
            image_url=row.get("image_url"),
            summary=row.get("summary"),
            published_at=row.get("published_at"),
            first_seen_at=row.get("first_seen_at") or "",
            last_seen_at=row.get("last_seen_at") or "",
            last_changed_at=row.get("last_changed_at") or "",
            status=row.get("status") or "ACTIVE",
            content_hash=row.get("content_hash") or "",
        )

    def _build_publisher_breakdown(
        self,
        articles: List[Dict[str, Any]],
        new_articles: List[Dict[str, Any]],
        updated_articles: List[Dict[str, Any]],
        removed_articles: List[Dict[str, Any]],
    ) -> List[PublisherBreakdown]:
        total = len(articles)
        known_publishers = [
            ("ET BrandEquity", "et_brand_equity"),
            ("Exchange4media", "exchange4media"),
        ]

        # Counts
        pub_counts: Dict[str, int] = collections.defaultdict(int)
        for a in articles:
            k = a.get("website_key") or a.get("website_name") or "unknown"
            pub_counts[k] += 1

        new_counts: Dict[str, int] = collections.defaultdict(int)
        for a in new_articles:
            k = a.get("website_key") or a.get("website_name") or "unknown"
            new_counts[k] += 1

        upd_counts: Dict[str, int] = collections.defaultdict(int)
        for a in updated_articles:
            k = a.get("website_key") or a.get("website_name") or "unknown"
            upd_counts[k] += 1

        rem_counts: Dict[str, int] = collections.defaultdict(int)
        for a in removed_articles:
            k = a.get("website_key") or a.get("website_name") or "unknown"
            rem_counts[k] += 1

        results: List[PublisherBreakdown] = []
        for name, key in known_publishers:
            count = pub_counts.get(key, 0)
            pct = round((count / total) * 100.0, 1) if total > 0 else 0.0
            results.append(
                PublisherBreakdown(
                    website_name=name,
                    website_key=key,
                    article_count=count,
                    percentage=pct,
                    new_count=new_counts.get(key, 0),
                    updated_count=upd_counts.get(key, 0),
                    removed_count=rem_counts.get(key, 0),
                )
            )

        # Include any additional publisher keys if present in DB
        for k, count in pub_counts.items():
            if k not in [p[1] for p in known_publishers]:
                pct = round((count / total) * 100.0, 1) if total > 0 else 0.0
                results.append(
                    PublisherBreakdown(
                        website_name=k.title(),
                        website_key=k,
                        article_count=count,
                        percentage=pct,
                        new_count=new_counts.get(k, 0),
                        updated_count=upd_counts.get(k, 0),
                        removed_count=rem_counts.get(k, 0),
                    )
                )

        return results

    def _build_section_breakdown(
        self,
        articles: List[Dict[str, Any]],
        new_articles: List[Dict[str, Any]],
        updated_articles: List[Dict[str, Any]],
    ) -> List[SectionBreakdown]:
        sec_counts: Dict[tuple, int] = collections.defaultdict(int)
        for a in articles:
            sec = a.get("section_name") or "Overall"
            wname = a.get("website_name") or "Unknown"
            wkey = a.get("website_key") or "unknown"
            sec_counts[(sec, wname, wkey)] += 1

        new_map: Dict[tuple, int] = collections.defaultdict(int)
        for a in new_articles:
            sec = a.get("section_name") or "Overall"
            wname = a.get("website_name") or "Unknown"
            wkey = a.get("website_key") or "unknown"
            new_map[(sec, wname, wkey)] += 1

        upd_map: Dict[tuple, int] = collections.defaultdict(int)
        for a in updated_articles:
            sec = a.get("section_name") or "Overall"
            wname = a.get("website_name") or "Unknown"
            wkey = a.get("website_key") or "unknown"
            upd_map[(sec, wname, wkey)] += 1

        results: List[SectionBreakdown] = []
        for (sec, wname, wkey), count in sorted(sec_counts.items(), key=lambda x: -x[1]):
            results.append(
                SectionBreakdown(
                    section_name=sec,
                    website_name=wname,
                    website_key=wkey,
                    article_count=count,
                    new_count=new_map.get((sec, wname, wkey), 0),
                    updated_count=upd_map.get((sec, wname, wkey), 0),
                )
            )
        return results

    # -------------------------------------------------------------------------
    # 1. Daily Report
    # -------------------------------------------------------------------------
    def generate_daily_report(self, date_str: Optional[str] = None) -> DailyReportResponse:
        """Generates a complete daily media intelligence report for date_str (YYYY-MM-DD)."""
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Fetch articles
        articles_raw = self.queries.get_articles_for_date(date_str)
        new_raw = self.queries.get_lifecycle_articles_for_date(date_str, "NEW")
        updated_raw = self.queries.get_lifecycle_articles_for_date(date_str, "UPDATED")
        removed_raw = self.queries.get_lifecycle_articles_for_date(date_str, "REMOVED")
        runs_raw = self.queries.get_scrape_runs_summary(date_str)

        # Breakdowns
        pub_breakdown = self._build_publisher_breakdown(
            articles_raw, new_raw, updated_raw, removed_raw
        )
        sec_breakdown = self._build_section_breakdown(articles_raw, new_raw, updated_raw)

        # Counts
        total_count = len(articles_raw)
        et_count = sum(
            1 for a in articles_raw if "et" in (a.get("website_key") or "").lower()
        )
        e4m_count = sum(
            1 for a in articles_raw if "exchange" in (a.get("website_key") or "").lower()
        )
        distinct_sections = len({a.get("section_name") or "Overall" for a in articles_raw})

        exec_summary = ExecutiveSummary(
            reporting_date=date_str,
            total_articles=total_count,
            et_article_count=et_count,
            e4m_article_count=e4m_count,
            sections_count=distinct_sections,
            new_articles_count=len(new_raw),
            updated_articles_count=len(updated_raw),
            removed_articles_count=len(removed_raw),
            monitoring_status=runs_raw.get("status_summary", "Nominal"),
        )

        return DailyReportResponse(
            executive_summary=exec_summary,
            publisher_breakdown=pub_breakdown,
            section_breakdown=sec_breakdown,
            top_stories=[self._to_article_item(a) for a in articles_raw[:20]],
            new_articles=[self._to_article_item(a) for a in new_raw],
            updated_articles=[self._to_article_item(a) for a in updated_raw],
            removed_articles=[self._to_article_item(a) for a in removed_raw],
            monitoring_runs=MonitoringRunSummary(**runs_raw),
        )

    # -------------------------------------------------------------------------
    # 2. Weekly Report
    # -------------------------------------------------------------------------
    def generate_weekly_report(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> WeeklyReportResponse:
        """Generates a weekly industry roll-up report across a date range."""
        today = datetime.now(timezone.utc).date()
        if not start_date or not end_date:
            # Default to past 7 days (including today)
            start_dt = today - timedelta(days=6)
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

        articles_raw = self.queries.get_articles_for_date_range(start_date, end_date)
        new_raw = self.queries.get_lifecycle_articles_for_range(start_date, end_date, "NEW")
        updated_raw = self.queries.get_lifecycle_articles_for_range(
            start_date, end_date, "UPDATED"
        )
        removed_raw = self.queries.get_lifecycle_articles_for_range(
            start_date, end_date, "REMOVED"
        )
        runs_raw = self.queries.get_scrape_runs_summary(start_date, end_date)

        # Breakdowns
        pub_breakdown = self._build_publisher_breakdown(
            articles_raw, new_raw, updated_raw, removed_raw
        )
        sec_breakdown = self._build_section_breakdown(articles_raw, new_raw, updated_raw)

        # Calculate daily volume
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        daily_volume: List[DailyVolumeItem] = []
        curr = start_d
        while curr <= end_d:
            d_str = curr.strftime("%Y-%m-%d")
            d_articles = [
                a
                for a in articles_raw
                if (a.get("published_at") or "").startswith(d_str)
                or (a.get("first_seen_at") or "").startswith(d_str)
                or (a.get("last_seen_at") or "").startswith(d_str)
            ]
            et_c = sum(
                1 for a in d_articles if "et" in (a.get("website_key") or "").lower()
            )
            e4m_c = sum(
                1 for a in d_articles if "exchange" in (a.get("website_key") or "").lower()
            )
            tot_c = et_c + e4m_c
            daily_volume.append(
                DailyVolumeItem(
                    date=d_str,
                    et_count=et_c,
                    e4m_count=e4m_c,
                    total_count=tot_c,
                )
            )
            curr += timedelta(days=1)

        total_count = len(articles_raw)
        et_count = sum(
            1 for a in articles_raw if "et" in (a.get("website_key") or "").lower()
        )
        e4m_count = sum(
            1 for a in articles_raw if "exchange" in (a.get("website_key") or "").lower()
        )
        distinct_sections = len({a.get("section_name") or "Overall" for a in articles_raw})

        return WeeklyReportResponse(
            date_range={"start_date": start_date, "end_date": end_date},
            total_articles=total_count,
            et_article_count=et_count,
            e4m_article_count=e4m_count,
            sections_count=distinct_sections,
            new_articles_count=len(new_raw),
            updated_articles_count=len(updated_raw),
            removed_articles_count=len(removed_raw),
            publisher_breakdown=pub_breakdown,
            daily_volume=daily_volume,
            section_breakdown=sec_breakdown,
            top_stories=[self._to_article_item(a) for a in articles_raw[:25]],
            new_articles=[self._to_article_item(a) for a in new_raw],
            updated_articles=[self._to_article_item(a) for a in updated_raw],
            removed_articles=[self._to_article_item(a) for a in removed_raw],
            monitoring_runs=MonitoringRunSummary(**runs_raw),
        )

    # -------------------------------------------------------------------------
    # 3. Custom Report
    # -------------------------------------------------------------------------
    def generate_custom_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        website: Optional[str] = None,
        section: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> CustomReportResponse:
        """Generates a parametric custom report matching multi-criteria filters."""
        articles_raw = self.queries.query_custom_articles(
            start_date=start_date,
            end_date=end_date,
            website=website,
            section=section,
            status=status,
            search=search,
            limit=limit,
        )

        pub_breakdown = self._build_publisher_breakdown(articles_raw, [], [], [])
        sec_breakdown = self._build_section_breakdown(articles_raw, [], [])

        status_counts: Dict[str, int] = collections.defaultdict(int)
        for a in articles_raw:
            st = a.get("status") or "ACTIVE"
            status_counts[st] += 1

        filters_echo = {
            "start_date": start_date,
            "end_date": end_date,
            "website": website or "all",
            "section": section or "all",
            "status": status or "ALL",
            "search": search or "",
        }

        return CustomReportResponse(
            filters=filters_echo,
            total_matching=len(articles_raw),
            publisher_breakdown=pub_breakdown,
            section_breakdown=sec_breakdown,
            status_breakdown=dict(status_counts),
            articles=[self._to_article_item(a) for a in articles_raw],
        )


# Global default instance
report_service = ReportService()
