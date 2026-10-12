"""
Media Reporting System - Report Database Query Layer
Executes safe, parameterized ANSI SQL queries for reporting and analytics.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database.connection import get_db, get_db_path


class ReportQueries:
    """Database query layer for daily, weekly, and custom reporting."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()

    def get_articles_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Retrieves articles associated with a specific date (YYYY-MM-DD).
        Matches articles published, first seen, or last seen on that date.
        """
        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT a.*, w.name AS website_name, w.website_key,
                       COALESCE(s.name, 'Overall') AS section_name
                FROM articles a
                JOIN websites w ON a.website_id = w.id
                LEFT JOIN sections s ON a.section_id = s.id
                WHERE SUBSTR(a.published_at, 1, 10) = ?
                   OR SUBSTR(a.first_seen_at, 1, 10) = ?
                   OR SUBSTR(a.last_seen_at, 1, 10) = ?
                ORDER BY a.published_at DESC, a.first_seen_at DESC, a.id DESC
                """,
                (date_str, date_str, date_str),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_articles_for_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Retrieves articles active or published within a date range (YYYY-MM-DD inclusive).
        """
        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT a.*, w.name AS website_name, w.website_key,
                       COALESCE(s.name, 'Overall') AS section_name
                FROM articles a
                JOIN websites w ON a.website_id = w.id
                LEFT JOIN sections s ON a.section_id = s.id
                WHERE (SUBSTR(a.published_at, 1, 10) BETWEEN ? AND ?)
                   OR (SUBSTR(a.first_seen_at, 1, 10) BETWEEN ? AND ?)
                   OR (SUBSTR(a.last_seen_at, 1, 10) BETWEEN ? AND ?)
                ORDER BY a.published_at DESC, a.first_seen_at DESC, a.id DESC
                """,
                (start_date, end_date, start_date, end_date, start_date, end_date),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_lifecycle_articles_for_date(
        self, date_str: str, change_type: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves articles that had a specific lifecycle event (NEW, UPDATED, REMOVED) on date_str.
        """
        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if change_type in ("NEW", "UPDATED"):
                rows = conn.execute(
                    """
                    SELECT DISTINCT a.*, w.name AS website_name, w.website_key,
                           COALESCE(s.name, 'Overall') AS section_name
                    FROM articles a
                    JOIN websites w ON a.website_id = w.id
                    LEFT JOIN sections s ON a.section_id = s.id
                    JOIN article_versions v ON a.id = v.article_id
                    WHERE v.change_type = ?
                      AND SUBSTR(v.detected_at, 1, 10) = ?
                    ORDER BY v.detected_at DESC
                    """,
                    (change_type, date_str),
                ).fetchall()
                return [dict(r) for r in rows]
            elif change_type == "REMOVED":
                rows = conn.execute(
                    """
                    SELECT a.*, w.name AS website_name, w.website_key,
                           COALESCE(s.name, 'Overall') AS section_name
                    FROM articles a
                    JOIN websites w ON a.website_id = w.id
                    LEFT JOIN sections s ON a.section_id = s.id
                    WHERE a.status = 'REMOVED'
                      AND SUBSTR(a.removed_at, 1, 10) = ?
                    ORDER BY a.removed_at DESC
                    """,
                    (date_str,),
                ).fetchall()
                return [dict(r) for r in rows]
            return []

    def get_lifecycle_articles_for_range(
        self, start_date: str, end_date: str, change_type: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves articles with lifecycle events (NEW, UPDATED, REMOVED) within a date range.
        """
        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if change_type in ("NEW", "UPDATED"):
                rows = conn.execute(
                    """
                    SELECT DISTINCT a.*, w.name AS website_name, w.website_key,
                           COALESCE(s.name, 'Overall') AS section_name
                    FROM articles a
                    JOIN websites w ON a.website_id = w.id
                    LEFT JOIN sections s ON a.section_id = s.id
                    JOIN article_versions v ON a.id = v.article_id
                    WHERE v.change_type = ?
                      AND SUBSTR(v.detected_at, 1, 10) BETWEEN ? AND ?
                    ORDER BY v.detected_at DESC
                    """,
                    (change_type, start_date, end_date),
                ).fetchall()
                return [dict(r) for r in rows]
            elif change_type == "REMOVED":
                rows = conn.execute(
                    """
                    SELECT a.*, w.name AS website_name, w.website_key,
                           COALESCE(s.name, 'Overall') AS section_name
                    FROM articles a
                    JOIN websites w ON a.website_id = w.id
                    LEFT JOIN sections s ON a.section_id = s.id
                    WHERE a.status = 'REMOVED'
                      AND SUBSTR(a.removed_at, 1, 10) BETWEEN ? AND ?
                    ORDER BY a.removed_at DESC
                    """,
                    (start_date, end_date),
                ).fetchall()
                return [dict(r) for r in rows]
            return []

    def get_scrape_runs_summary(
        self, start_date: str, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Summarizes scrape runs for a given date or date range."""
        end_date = end_date or start_date
        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT status, finished_at, started_at
                FROM scrape_runs
                WHERE SUBSTR(started_at, 1, 10) BETWEEN ? AND ?
                ORDER BY started_at DESC
                """,
                (start_date, end_date),
            ).fetchall()

            total_runs = len(rows)
            successful_runs = sum(1 for r in rows if r["status"] == "SUCCESS")
            failed_runs = sum(1 for r in rows if r["status"] == "FAILED")
            last_run_time = rows[0]["finished_at"] or rows[0]["started_at"] if rows else None

            if total_runs == 0:
                summary_text = "No scrape runs recorded in this timeframe"
            elif failed_runs == 0:
                summary_text = f"All {total_runs} scrape cycles completed successfully"
            else:
                summary_text = f"{successful_runs}/{total_runs} cycles succeeded ({failed_runs} failed)"

            return {
                "total_runs": total_runs,
                "successful_runs": successful_runs,
                "failed_runs": failed_runs,
                "last_run_time": last_run_time,
                "status_summary": summary_text,
            }

    def query_custom_articles(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        website: Optional[str] = None,
        section: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Performs parametric custom querying with multi-criteria filtering.
        """
        conditions: List[str] = []
        params: List[Any] = []

        if start_date and end_date:
            conditions.append(
                """(
                    (SUBSTR(a.published_at, 1, 10) BETWEEN ? AND ?)
                    OR (SUBSTR(a.first_seen_at, 1, 10) BETWEEN ? AND ?)
                    OR (SUBSTR(a.last_seen_at, 1, 10) BETWEEN ? AND ?)
                )"""
            )
            params.extend([start_date, end_date, start_date, end_date, start_date, end_date])
        elif start_date:
            conditions.append(
                """(
                    SUBSTR(a.published_at, 1, 10) >= ?
                    OR SUBSTR(a.first_seen_at, 1, 10) >= ?
                    OR SUBSTR(a.last_seen_at, 1, 10) >= ?
                )"""
            )
            params.extend([start_date, start_date, start_date])
        elif end_date:
            conditions.append(
                """(
                    SUBSTR(a.published_at, 1, 10) <= ?
                    OR SUBSTR(a.first_seen_at, 1, 10) <= ?
                    OR SUBSTR(a.last_seen_at, 1, 10) <= ?
                )"""
            )
            params.extend([end_date, end_date, end_date])

        if website and website != "all":
            conditions.append("(w.website_key = ? OR LOWER(w.name) LIKE ?)")
            params.extend([website, f"%{website.lower()}%"])

        if section and section != "all":
            conditions.append("LOWER(COALESCE(s.name, 'Overall')) = ?")
            params.append(section.lower())

        if status and status != "ALL":
            conditions.append("a.status = ?")
            params.append(status.upper())

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            conditions.append(
                """(
                    LOWER(a.headline) LIKE ?
                    OR LOWER(COALESCE(a.summary, '')) LIKE ?
                    OR LOWER(COALESCE(s.name, '')) LIKE ?
                    OR LOWER(w.name) LIKE ?
                )"""
            )
            params.extend([term, term, term, term])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT a.*, w.name AS website_name, w.website_key,
                   COALESCE(s.name, 'Overall') AS section_name
            FROM articles a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_clause}
            ORDER BY a.published_at DESC, a.first_seen_at DESC, a.id DESC
            LIMIT ?
        """
        params.append(limit)

        with get_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
