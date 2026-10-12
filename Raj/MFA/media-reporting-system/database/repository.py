"""
Media Reporting System - Database Repository
Provides clean data access objects (DAO) for websites, sections, articles, versions, and scrape runs.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.connection import get_db, get_db_path


def utc_now_iso() -> str:
    """Returns current UTC time in ISO 8601 string format."""
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """Repository handling all database interactions with SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()

    # -------------------------------------------------------------------------
    # Websites
    # -------------------------------------------------------------------------
    def get_or_create_website(
        self,
        name: str,
        website_key: Optional[str] = None,
        base_url: str = "",
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        actual_key = website_key or key or name.lower().replace(" ", "_")
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM websites WHERE website_key = ?", (actual_key,)
            ).fetchone()
            if row:
                return dict(row)

            now = utc_now_iso()
            cur = conn.execute(
                """
                INSERT INTO websites (name, website_key, base_url, status, created_at, updated_at)
                VALUES (?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (name, actual_key, base_url, now, now),
            )
            created_row = conn.execute(
                "SELECT * FROM websites WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(created_row)

    def get_website_by_key(self, website_key: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM websites WHERE website_key = ?", (website_key,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_websites(self) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM websites ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Sections
    # -------------------------------------------------------------------------
    def get_or_create_section(self, website_id: int, name: str, url: str = "") -> Dict[str, Any]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sections WHERE website_id = ? AND name = ?",
                (website_id, name),
            ).fetchone()
            if row:
                return dict(row)

            now = utc_now_iso()
            cur = conn.execute(
                """
                INSERT INTO sections (website_id, name, url, active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (website_id, name, url or "", now, now),
            )
            created_row = conn.execute(
                "SELECT * FROM sections WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(created_row)

    def get_sections_for_website(self, website_id: int) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM sections WHERE website_id = ? AND active = 1 ORDER BY name ASC",
                (website_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Articles
    # -------------------------------------------------------------------------
    def get_article_by_url(self, website_id: int, url: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE website_id = ? AND url = ?",
                (website_id, url),
            ).fetchone()
            return dict(row) if row else None

    def get_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT a.*, w.name as website_name, w.website_key, s.name as section_name
                FROM articles a
                JOIN websites w ON a.website_id = w.id
                LEFT JOIN sections s ON a.section_id = s.id
                WHERE a.id = ?
                """,
                (article_id,),
            ).fetchone()
            return dict(row) if row else None

    def insert_article(
        self,
        website_id: int,
        section_id: Optional[int],
        headline: str,
        url: str,
        image_url: Optional[str],
        summary: Optional[str],
        published_at: Optional[str],
        content_hash: str,
        detected_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = detected_at or utc_now_iso()
        fixed_published_at = published_at
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO articles (
                    website_id, section_id, headline, url, image_url, summary,
                    published_at, first_seen_at, last_seen_at, last_changed_at,
                    content_hash, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (
                    website_id,
                    section_id,
                    headline,
                    url,
                    image_url,
                    summary,
                    fixed_published_at,
                    now,
                    now,
                    now,
                    content_hash,
                    now,
                    now,
                ),
            )
            created_row = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(created_row)

    def update_article_content(
        self,
        article_id: int,
        headline: str,
        image_url: Optional[str],
        summary: Optional[str],
        section_id: Optional[int],
        published_at: Optional[str],
        content_hash: str,
        detected_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE articles
                SET headline = ?,
                    image_url = ?,
                    summary = ?,
                    section_id = ?,
                    published_at = COALESCE(?, published_at),
                    content_hash = ?,
                    last_seen_at = ?,
                    last_changed_at = ?,
                    status = 'ACTIVE',
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    headline,
                    image_url,
                    summary,
                    section_id,
                    published_at,
                    content_hash,
                    now,
                    now,
                    now,
                    article_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
            return dict(row)

    def touch_article_seen(self, article_id: int, detected_at: Optional[str] = None) -> None:
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE articles
                SET last_seen_at = ?,
                    status = 'ACTIVE',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, article_id),
            )

    def update_article_published_at(
        self, article_id: int, published_at: str, detected_at: Optional[str] = None
    ) -> None:
        """Updates published_at on both article and its latest version without overwriting existing content."""
        if not published_at:
            return
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE articles
                SET published_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (published_at, now, article_id),
            )
            conn.execute(
                """
                UPDATE article_versions
                SET published_at = ?
                WHERE article_id = ? AND (published_at IS NULL OR published_at = '')
                """,
                (published_at, article_id),
            )

    def get_articles_missing_published_at(
        self, website_key: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Returns active articles currently missing a publication timestamp for backfill."""
        where = ["(a.published_at IS NULL OR a.published_at = '')", "UPPER(a.status) = 'ACTIVE'"]
        params: List[Any] = []
        if website_key:
            where.append("w.website_key = ?")
            params.append(website_key)
        where_sql = "WHERE " + " AND ".join(where)
        limit_sql = f"LIMIT {int(limit)}" if limit else ""
        query = f"""
            SELECT a.*, w.website_key, w.name as website_name
            FROM articles a
            JOIN websites w ON a.website_id = w.id
            {where_sql}
            ORDER BY a.id DESC
            {limit_sql}
        """
        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_article_labels(self, article_id: int, publication_label, is_exclusive: bool) -> None:
        with get_db(self.db_path) as conn:
            conn.execute(
                "UPDATE articles SET publication_label = ?, is_exclusive = ? WHERE id = ?",
                (publication_label, int(is_exclusive), article_id),
            )

    def mark_article_removed(self, article_id: int, detected_at: Optional[str] = None) -> None:
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE articles
                SET status = 'REMOVED',
                    removed_at = ?,
                    last_changed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, now, article_id),
            )

    def reactivate_articles_for_website(self, website_id: int) -> int:
        """Restores articles falsely removed after rotating off listing pages."""
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE articles
                SET status = 'ACTIVE', removed_at = NULL, updated_at = ?
                WHERE website_id = ? AND UPPER(status) = 'REMOVED'
                """,
                (now, website_id),
            )
            return int(cursor.rowcount or 0)

    def insert_version(
        self,
        article_id: int,
        version_number: int = 1,
        headline: str = "",
        url: str = "",
        content_hash: str = "",
        change_type: str = "NEW",
        detected_at: Optional[str] = None,
        image_url: Optional[str] = None,
        summary: Optional[str] = None,
        section_id: Optional[int] = None,
        published_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convenience alias delegating to insert_article_version."""
        return self.insert_article_version(
            article_id=article_id,
            headline=headline,
            url=url,
            image_url=image_url,
            summary=summary,
            section_id=section_id,
            published_at=published_at,
            content_hash=content_hash,
            change_type=change_type,
            detected_at=detected_at,
        )

    def insert_article_version(
        self,
        article_id: int,
        headline: str,
        url: str,
        image_url: Optional[str],
        summary: Optional[str],
        section_id: Optional[int],
        published_at: Optional[str],
        content_hash: str,
        change_type: str,
        detected_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            # Supersede previous active version if exists
            conn.execute(
                "UPDATE article_versions SET valid_to = ? WHERE article_id = ? AND valid_to IS NULL",
                (now, article_id),
            )
            # Determine next version_number
            v_row = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_v FROM article_versions WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            next_version = v_row["next_v"] if v_row else 1

            cur = conn.execute(
                """
                INSERT INTO article_versions (
                    article_id, version_number, headline, url, image_url, summary,
                    section_id, published_at, content_hash, detected_at, valid_from, valid_to, change_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    article_id,
                    next_version,
                    headline,
                    url,
                    image_url,
                    summary,
                    section_id,
                    published_at,
                    content_hash,
                    now,
                    now,
                    change_type,
                ),
            )
            row = conn.execute(
                "SELECT * FROM article_versions WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)

    def get_article_versions(self, article_id: int) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT v.*, s.name as section_name
                FROM article_versions v
                LEFT JOIN sections s ON v.section_id = s.id
                WHERE v.article_id = ?
                ORDER BY v.version_number ASC, v.id ASC
                """,
                (article_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_article_history(self, article_id: int) -> List[Dict[str, Any]]:
        return self.get_article_versions(article_id)

    def get_active_articles_by_website(self, website_id: int) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE website_id = ? AND UPPER(status) = 'ACTIVE'",
                (website_id,),
            ).fetchall()
            return [dict(r) for r in rows]


    # -------------------------------------------------------------------------
    # Active Articles Queries
    # -------------------------------------------------------------------------
    def get_articles(
        self,
        website_key: Optional[str] = None,
        section_name: Optional[str] = None,
        status: str = "active",
        limit: Optional[int] = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where_clauses: List[str] = []

        if website_key:
            where_clauses.append("w.website_key = ?")
            params.append(website_key)

        if section_name and section_name.lower() != "all":
            where_clauses.append("LOWER(s.name) = LOWER(?)")
            params.append(section_name)

        if status and status.lower() != "all":
            where_clauses.append("UPPER(a.status) = ?")
            params.append(status.upper())
        elif status and status.lower() == "all":
            where_clauses.append("UPPER(a.status) != 'IGNORED'")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        limit_sql = "LIMIT ? OFFSET ?" if limit is not None else ""
        query = f"""
            SELECT a.*, w.name as website_name, w.website_key, s.name as section_name
            FROM articles a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_sql}
            ORDER BY COALESCE(a.published_at, a.last_changed_at, a.first_seen_at) DESC
            {limit_sql}
        """
        if limit is not None:
            params.extend([limit, skip])

        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_articles(
        self,
        website_key: Optional[str] = None,
        section_name: Optional[str] = None,
        status: str = "active",
    ) -> int:
        params: List[Any] = []
        where_clauses: List[str] = []

        if website_key:
            where_clauses.append("w.website_key = ?")
            params.append(website_key)

        if section_name and section_name.lower() != "all":
            where_clauses.append("LOWER(s.name) = LOWER(?)")
            params.append(section_name)

        if status and status.lower() != "all":
            where_clauses.append("UPPER(a.status) = ?")
            params.append(status.upper())
        elif status and status.lower() == "all":
            where_clauses.append("UPPER(a.status) != 'IGNORED'")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = f"""
            SELECT COUNT(*) as cnt
            FROM articles a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_sql}
        """
        with get_db(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
            return row["cnt"] if row else 0

    def search_articles(
        self,
        search: Optional[str] = None,
        website_key: Optional[str] = None,
        section_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: str = "active",
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        params: List[Any] = []
        where_clauses: List[str] = []

        if website_key and website_key.lower() != "all":
            where_clauses.append("w.website_key = ?")
            params.append(website_key)

        if section_name and section_name.lower() != "all":
            where_clauses.append("LOWER(s.name) = LOWER(?)")
            params.append(section_name)

        if status and status.lower() != "all":
            where_clauses.append("UPPER(a.status) = ?")
            params.append(status.upper())
        elif status and status.lower() == "all":
            where_clauses.append("UPPER(a.status) != 'IGNORED'")

        if search:
            pattern = f"%{search.strip()}%"
            where_clauses.append(
                "(a.headline LIKE ? OR a.summary LIKE ? OR s.name LIKE ? OR w.name LIKE ? OR a.url LIKE ?)"
            )
            params.extend([pattern, pattern, pattern, pattern, pattern])

        if start_date:
            where_clauses.append("date(COALESCE(a.published_at, a.first_seen_at, a.created_at)) >= date(?)")
            params.append(start_date)

        if end_date:
            where_clauses.append("date(COALESCE(a.published_at, a.first_seen_at, a.created_at)) <= date(?)")
            params.append(end_date)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        base_sql = f"""
            FROM articles a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_sql}
        """

        with get_db(self.db_path) as conn:
            count_row = conn.execute(f"SELECT COUNT(*) as total {base_sql}", params).fetchone()
            rows = conn.execute(
                f"""
                SELECT a.*, w.name as website_name, w.website_key, s.name as section_name
                {base_sql}
                ORDER BY COALESCE(a.published_at, a.last_changed_at, a.first_seen_at) DESC, a.id DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, skip],
            ).fetchall()
        return {
            "total": int(count_row["total"]) if count_row else 0,
            "articles": [dict(r) for r in rows],
        }

    # -------------------------------------------------------------------------
    # Changes API Queries
    # -------------------------------------------------------------------------
    def get_recent_changes(
        self,
        website_key: Optional[str] = None,
        timeframe: Optional[str] = "all",
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves article modifications (NEW, UPDATED, REMOVED) across historical versions.
        """
        time_filter = ""
        now = datetime.now(timezone.utc)

        if timeframe == "today":
            today_start = now.strftime("%Y-%m-%d 00:00:00")
            time_filter = f"AND v.detected_at >= '{today_start}'"
        elif timeframe == "24h":
            from datetime import timedelta
            yesterday = (now - timedelta(hours=24)).isoformat()
            time_filter = f"AND v.detected_at >= '{yesterday}'"
        elif timeframe == "7d":
            from datetime import timedelta
            week_ago = (now - timedelta(days=7)).isoformat()
            time_filter = f"AND v.detected_at >= '{week_ago}'"

        site_filter = "AND w.website_key = ?" if website_key else ""
        params: List[Any] = [website_key] if website_key else []

        query = f"""
            SELECT
                v.id as version_id,
                v.article_id,
                v.headline,
                v.url,
                v.image_url,
                v.summary,
                v.change_type,
                v.detected_at,
                v.content_hash as current_hash,
                w.name as website_name,
                w.website_key,
                s.name as section_name,
                a.status as current_status,
                a.first_seen_at,
                a.last_seen_at
            FROM article_versions v
            JOIN articles a ON v.article_id = a.id
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON v.section_id = s.id
            WHERE 1=1 {site_filter} {time_filter}
            ORDER BY v.detected_at DESC, v.id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, skip])

        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_change_kpis(
        self,
        website_key: Optional[str] = None,
        timeframe: Optional[str] = "all",
    ) -> Dict[str, int]:
        """
        Aggregates New, Updated, Removed, and Unchanged counts from scrape_runs.
        """
        time_filter = ""
        now = datetime.now(timezone.utc)

        if timeframe == "today":
            today_start = now.strftime("%Y-%m-%d 00:00:00")
            time_filter = f"AND r.started_at >= '{today_start}'"
        elif timeframe == "24h":
            from datetime import timedelta
            yesterday = (now - timedelta(hours=24)).isoformat()
            time_filter = f"AND r.started_at >= '{yesterday}'"
        elif timeframe == "7d":
            from datetime import timedelta
            week_ago = (now - timedelta(days=7)).isoformat()
            time_filter = f"AND r.started_at >= '{week_ago}'"

        site_filter = "AND w.website_key = ?" if website_key else ""
        params: List[Any] = [website_key] if website_key else []

        query = f"""
            SELECT
                COALESCE(SUM(r.new_items), 0) as total_new,
                COALESCE(SUM(r.updated_items), 0) as total_updated,
                COALESCE(SUM(r.unchanged_items), 0) as total_unchanged,
                COALESCE(SUM(r.removed_items), 0) as total_removed
            FROM scrape_runs r
            JOIN websites w ON r.website_id = w.id
            WHERE r.status = 'SUCCESS' {site_filter} {time_filter}
        """
        with get_db(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
            if row:
                return {
                    "new": row["total_new"],
                    "updated": row["total_updated"],
                    "unchanged": row["total_unchanged"],
                    "removed": row["total_removed"],
                }
            return {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}

    # -------------------------------------------------------------------------
    # Scrape Runs
    # -------------------------------------------------------------------------
    def log_scrape_run(self, website_id: int, started_at: Optional[str] = None) -> int:
        """Alias for start_scrape_run."""
        return self.start_scrape_run(website_id, started_at=started_at)

    def start_scrape_run(self, website_id: int, started_at: Optional[str] = None) -> int:
        now = started_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO scrape_runs (website_id, started_at, status)
                VALUES (?, ?, 'RUNNING')
                """,
                (website_id, now),
            )
            return cur.lastrowid

    def finish_scrape_run(
        self,
        run_id: int,
        status: str,
        items_found: int = 0,
        new_items: int = 0,
        updated_items: int = 0,
        unchanged_items: int = 0,
        removed_items: int = 0,
        error_message: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        now = finished_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE scrape_runs
                SET finished_at = ?,
                    status = ?,
                    items_found = ?,
                    new_items = ?,
                    updated_items = ?,
                    unchanged_items = ?,
                    removed_items = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    now,
                    status,
                    items_found,
                    new_items,
                    updated_items,
                    unchanged_items,
                    removed_items,
                    error_message,
                    run_id,
                ),
            )

    def get_recent_scrape_runs(
        self, website_key: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        site_filter = "WHERE w.website_key = ?" if website_key else ""
        params = [website_key, limit] if website_key else [limit]

        query = f"""
            SELECT
                r.*,
                w.name as website_name,
                w.website_key
            FROM scrape_runs r
            JOIN websites w ON r.website_id = w.id
            {site_filter}
            ORDER BY r.started_at DESC, r.id DESC
            LIMIT ?
        """
        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                # Compute duration string if finished
                if d.get("started_at") and d.get("finished_at"):
                    try:
                        t1 = datetime.fromisoformat(d["started_at"])
                        t2 = datetime.fromisoformat(d["finished_at"])
                        secs = max(0.1, (t2 - t1).total_seconds())
                        d["duration"] = f"{secs:.1f}s"
                    except Exception:
                        d["duration"] = "--"
                else:
                    d["duration"] = "--"
                result.append(d)
            return result

    # -----------------------------------------------------------------------
    # Advertisement Operations
    # -----------------------------------------------------------------------
    def get_advertisement_by_hash(
        self, website_id: int, ad_hash: str
    ) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM advertisements WHERE website_id = ? AND ad_hash = ?"
        with get_db(self.db_path) as conn:
            row = conn.execute(query, (website_id, ad_hash)).fetchone()
            return dict(row) if row else None

    def get_advertisement_by_id(self, ad_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT a.*, w.name as website_name, w.website_key, s.name as section_name
            FROM advertisements a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            WHERE a.id = ?
        """
        with get_db(self.db_path) as conn:
            row = conn.execute(query, (ad_id,)).fetchone()
            return dict(row) if row else None

    def insert_advertisement(
        self,
        website_id: int,
        page_url: str,
        ad_hash: str,
        ad_type: str = "BANNER",
        position: str = "UNKNOWN",
        advertiser: Optional[str] = None,
        brand: Optional[str] = None,
        campaign: Optional[str] = None,
        image_url: Optional[str] = None,
        local_image_path: Optional[str] = None,
        target_url: Optional[str] = None,
        section_id: Optional[int] = None,
        detected_at: Optional[str] = None,
    ) -> int:
        now = detected_at or utc_now_iso()
        query = """
            INSERT INTO advertisements (
                website_id, section_id, page_url, advertiser, brand, campaign,
                ad_type, position, image_url, local_image_path, target_url,
                ad_hash, first_seen_at, last_seen_at, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
        """
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                query,
                (
                    website_id,
                    section_id,
                    page_url,
                    advertiser,
                    brand,
                    campaign,
                    ad_type,
                    position,
                    image_url,
                    local_image_path,
                    target_url,
                    ad_hash,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            ad_id = cur.lastrowid

            # Insert initial version (v1)
            conn.execute(
                """
                INSERT INTO advertisement_versions (
                    advertisement_id, version_number, advertiser, brand, campaign,
                    ad_type, position, image_url, local_image_path, target_url,
                    ad_hash, detected_at, change_type
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW')
                """,
                (
                    ad_id,
                    advertiser,
                    brand,
                    campaign,
                    ad_type,
                    position,
                    image_url,
                    local_image_path,
                    target_url,
                    ad_hash,
                    now,
                ),
            )
            return ad_id

    def update_advertisement_seen(
        self, ad_id: int, seen_at: Optional[str] = None, local_image_path: Optional[str] = None
    ) -> None:
        now = seen_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            if local_image_path:
                conn.execute(
                    """
                    UPDATE advertisements
                    SET last_seen_at = ?, status = 'ACTIVE', removed_at = NULL,
                        local_image_path = COALESCE(local_image_path, ?), updated_at = ?
                    WHERE id = ?
                    """,
                    (now, local_image_path, now, ad_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE advertisements
                    SET last_seen_at = ?, status = 'ACTIVE', removed_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, ad_id),
                )

    def enrich_advertisement_identity(
        self, ad_id: int, advertiser: Optional[str], brand: Optional[str],
        campaign: Optional[str], target_url: Optional[str]
    ) -> None:
        """Fill previously unavailable identity fields without erasing evidence."""
        with get_db(self.db_path) as conn:
            conn.execute(
                """UPDATE advertisements SET
                       advertiser = COALESCE(advertiser, ?),
                       brand = COALESCE(brand, ?),
                       campaign = COALESCE(campaign, ?),
                       target_url = COALESCE(target_url, ?)
                   WHERE id = ?""",
                (advertiser, brand, campaign, target_url, ad_id),
            )

    def enrich_advertisement_position(self, ad_id: int, position: Optional[str]) -> None:
        """Replace an unknown placement only when new structural evidence exists."""
        clean_position = str(position or "").strip()
        if not clean_position or clean_position.upper() == "UNKNOWN":
            return
        with get_db(self.db_path) as conn:
            conn.execute(
                """UPDATE advertisements
                   SET position = ?, updated_at = ?
                   WHERE id = ? AND (position IS NULL OR TRIM(position) = '' OR UPPER(position) = 'UNKNOWN')""",
                (clean_position, utc_now_iso(), ad_id),
            )

    def update_advertisement_creative(
        self,
        ad_id: int,
        new_ad_hash: str,
        image_url: Optional[str] = None,
        local_image_path: Optional[str] = None,
        target_url: Optional[str] = None,
        advertiser: Optional[str] = None,
        brand: Optional[str] = None,
        campaign: Optional[str] = None,
        ad_type: str = "BANNER",
        position: str = "UNKNOWN",
        detected_at: Optional[str] = None,
    ) -> None:
        now = detected_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            # Get latest version number
            row = conn.execute(
                "SELECT MAX(version_number) as max_v FROM advertisement_versions WHERE advertisement_id = ?",
                (ad_id,),
            ).fetchone()
            next_version = (row["max_v"] or 0) + 1

            # Update parent advertisement
            conn.execute(
                """
                UPDATE advertisements
                SET ad_hash = ?, image_url = ?, local_image_path = ?, target_url = ?,
                    advertiser = COALESCE(?, advertiser), brand = COALESCE(?, brand),
                    campaign = COALESCE(?, campaign), ad_type = ?, position = ?,
                    last_seen_at = ?, status = 'ACTIVE', removed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_ad_hash,
                    image_url,
                    local_image_path,
                    target_url,
                    advertiser,
                    brand,
                    campaign,
                    ad_type,
                    position,
                    now,
                    now,
                    ad_id,
                ),
            )

            # Insert new version record
            conn.execute(
                """
                INSERT INTO advertisement_versions (
                    advertisement_id, version_number, advertiser, brand, campaign,
                    ad_type, position, image_url, local_image_path, target_url,
                    ad_hash, detected_at, change_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CHANGED')
                """,
                (
                    ad_id,
                    next_version,
                    advertiser,
                    brand,
                    campaign,
                    ad_type,
                    position,
                    image_url,
                    local_image_path,
                    target_url,
                    new_ad_hash,
                    now,
                ),
            )

    def mark_advertisement_removed(
        self, ad_id: int, removed_at: Optional[str] = None
    ) -> None:
        now = removed_at or utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE advertisements
                SET status = 'REMOVED', removed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, ad_id),
            )

    def get_advertisements(
        self,
        website_key: Optional[str] = None,
        section_name: Optional[str] = None,
        status: Optional[str] = None,
        advertiser: Optional[str] = None,
        brand: Optional[str] = None,
        campaign: Optional[str] = None,
        ad_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
        identified_only: bool = False,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params: List[Any] = []

        if website_key:
            conditions.append("w.website_key = ?")
            params.append(website_key)
        if section_name and section_name.lower() != "all":
            conditions.append("s.name = ?")
            params.append(section_name)
        if status and status.upper() != "ALL":
            conditions.append("a.status = ?")
            params.append(status.upper())
        if identified_only:
            conditions.append(
                "(("
                "NULLIF(TRIM(a.brand), '') IS NOT NULL AND LOWER(TRIM(a.brand)) != 'not identified'"
                ") OR ("
                "NULLIF(TRIM(a.advertiser), '') IS NOT NULL AND LOWER(TRIM(a.advertiser)) != 'not identified'"
                "))"
            )
        if advertiser:
            conditions.append("a.advertiser LIKE ?")
            params.append(f"%{advertiser}%")
        if brand:
            conditions.append("a.brand LIKE ?")
            params.append(f"%{brand}%")
        if campaign:
            conditions.append("a.campaign LIKE ?")
            params.append(f"%{campaign}%")
        if ad_type and ad_type.upper() != "ALL":
            conditions.append("a.ad_type = ?")
            params.append(ad_type.upper())
        if search:
            search_clause = """(
                a.advertiser LIKE ? OR a.brand LIKE ? OR a.campaign LIKE ?
                OR a.position LIKE ? OR a.page_url LIKE ?
            )"""
            pattern = f"%{search}%"
            conditions.append(search_clause)
            params.extend([pattern, pattern, pattern, pattern, pattern])

        where_str = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                a.*,
                w.name as website_name,
                w.website_key,
                s.name as section_name
            FROM advertisements a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_str}
            ORDER BY a.last_seen_at DESC, a.id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, skip])
        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_advertisements(
        self,
        website_key: Optional[str] = None,
        section_name: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        advertiser: Optional[str] = None,
        brand: Optional[str] = None,
        campaign: Optional[str] = None,
        ad_type: Optional[str] = None,
        identified_only: bool = False,
    ) -> int:
        conditions = []
        params: List[Any] = []

        if website_key:
            conditions.append("w.website_key = ?")
            params.append(website_key)
        if section_name and section_name.lower() != "all":
            conditions.append("s.name = ?")
            params.append(section_name)
        if status and status.upper() != "ALL":
            conditions.append("a.status = ?")
            params.append(status.upper())
        if identified_only:
            conditions.append(
                "(("
                "NULLIF(TRIM(a.brand), '') IS NOT NULL AND LOWER(TRIM(a.brand)) != 'not identified'"
                ") OR ("
                "NULLIF(TRIM(a.advertiser), '') IS NOT NULL AND LOWER(TRIM(a.advertiser)) != 'not identified'"
                "))"
            )
        for field, value in (("advertiser", advertiser), ("brand", brand), ("campaign", campaign)):
            if value:
                conditions.append(f"a.{field} LIKE ?")
                params.append(f"%{value}%")
        if ad_type and ad_type.upper() != "ALL":
            conditions.append("a.ad_type = ?")
            params.append(ad_type.upper())
        if search:
            search_clause = """(
                a.advertiser LIKE ? OR a.brand LIKE ? OR a.campaign LIKE ?
                OR a.position LIKE ? OR a.page_url LIKE ?
            )"""
            pattern = f"%{search}%"
            conditions.append(search_clause)
            params.extend([pattern, pattern, pattern, pattern, pattern])

        where_str = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT COUNT(*) as total
            FROM advertisements a
            JOIN websites w ON a.website_id = w.id
            LEFT JOIN sections s ON a.section_id = s.id
            {where_str}
        """
        with get_db(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
            return row["total"] if row else 0

    def get_advertisement_versions(self, ad_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT v.*, a.page_url, w.name as website_name, w.website_key
            FROM advertisement_versions v
            JOIN advertisements a ON v.advertisement_id = a.id
            JOIN websites w ON a.website_id = w.id
            WHERE v.advertisement_id = ?
            ORDER BY v.version_number ASC, v.id ASC
        """
        with get_db(self.db_path) as conn:
            rows = conn.execute(query, (ad_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_advertisement_kpis(
        self, website_key: Optional[str] = None, identified_only: bool = False
    ) -> Dict[str, int]:
        conditions = []
        params = []
        if website_key:
            conditions.append("w.website_key = ?")
            params.append(website_key)
        if identified_only:
            conditions.append(
                "(("
                "NULLIF(TRIM(a.brand), '') IS NOT NULL AND LOWER(TRIM(a.brand)) != 'not identified'"
                ") OR ("
                "NULLIF(TRIM(a.advertiser), '') IS NOT NULL AND LOWER(TRIM(a.advertiser)) != 'not identified'"
                "))"
            )
        site_filter = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""
            SELECT
                COUNT(CASE WHEN a.status = 'ACTIVE' THEN 1 END) as active_ads,
                COUNT(CASE WHEN a.status = 'REMOVED' THEN 1 END) as removed_ads,
                COUNT(CASE WHEN a.status = 'CHANGED' THEN 1 END) as changed_ads,
                COUNT(DISTINCT a.advertiser) as unique_advertisers,
                COUNT(DISTINCT a.brand) as unique_brands,
                COUNT(*) as total_ads
            FROM advertisements a
            JOIN websites w ON a.website_id = w.id
            {site_filter}
        """
        with get_db(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
            if row:
                d = dict(row)
                return {
                    "total_ads": d.get("total_ads") or 0,
                    "active_ads": d.get("active_ads") or 0,
                    "removed_ads": d.get("removed_ads") or 0,
                    "changed_ads": d.get("changed_ads") or 0,
                    "unique_advertisers": d.get("unique_advertisers") or 0,
                    "unique_brands": d.get("unique_brands") or 0,
                }
            return {
                "total_ads": 0,
                "active_ads": 0,
                "removed_ads": 0,
                "changed_ads": 0,
                "unique_advertisers": 0,
                "unique_brands": 0,
            }


    # -------------------------------------------------------------------------
    # Users & Authentication
    # -------------------------------------------------------------------------
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        norm_email = str(email or "").strip().lower()
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = ?", (norm_email,)
            ).fetchone()
            return dict(row) if row else None

    def count_admins(self) -> int:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM users WHERE role = 'ADMIN'"
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def get_admin_user(self) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE role = 'ADMIN' LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: Optional[str] = None,
        role: str = "USER",
        status: str = "PENDING",
    ) -> Dict[str, Any]:
        norm_email = str(email or "").strip().lower()
        clean_role = str(role or "USER").upper()
        clean_status = str(status or "PENDING").upper()
        clean_name = str(full_name).strip() if full_name else None

        if clean_role not in ("ADMIN", "USER"):
            raise ValueError(f"Invalid role: {role}. Must be 'ADMIN' or 'USER'.")
        if clean_status not in ("PENDING", "APPROVED", "SUSPENDED"):
            raise ValueError(f"Invalid status: {status}. Must be 'PENDING', 'APPROVED', or 'SUSPENDED'.")

        import os
        allowed_admin_email = os.getenv("ADMIN_EMAIL", "rajxy71@gmail.com").strip().lower()

        if clean_role == "ADMIN":
            if norm_email != allowed_admin_email:
                raise ValueError(
                    f"Only the designated administrator email ({allowed_admin_email}) can hold the ADMIN role."
                )
            if self.count_admins() >= 1:
                existing_admin = self.get_admin_user()
                if existing_admin and existing_admin["email"].lower() == norm_email:
                    return existing_admin
                raise ValueError(
                    "Administrator account already exists. Exactly one administrator is allowed."
                )

        # Check existing user with this email
        existing = self.get_user_by_email(norm_email)
        if existing:
            raise ValueError(f"An account with email '{norm_email}' already exists.")

        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    email, password_hash, full_name, role, status, created_at, updated_at,
                    last_login_at, failed_login_attempts, locked_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
                """,
                (norm_email, password_hash, clean_name, clean_role, clean_status, now, now),
            )
            created = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(created)

    def update_user_status(self, user_id: int, status: str) -> Optional[Dict[str, Any]]:
        clean_status = str(status or "").upper()
        if clean_status not in ("PENDING", "APPROVED", "SUSPENDED"):
            raise ValueError(f"Invalid status: {status}")

        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # Guarantee: Administrator cannot be suspended or revoked
        if user["role"] == "ADMIN" and clean_status != "APPROVED":
            raise ValueError("Cannot revoke, suspend, or alter the administrator account.")

        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
                (clean_status, now, user_id),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(updated) if updated else None

    def update_user_login_success(self, user_id: int) -> None:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = 0,
                    locked_until = NULL,
                    last_login_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, user_id),
            )

    def update_user_failed_login(
        self, user_id: int, attempts: int, locked_until: Optional[str] = None
    ) -> None:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = ?,
                    locked_until = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (attempts, locked_until, now, user_id),
            )

    def get_user_permissions(self, user_id: int) -> List[str]:
        with get_db(self.db_path) as conn:
            user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
            if user and user["role"] == "ADMIN":
                from app.api.deps import ALL_PERMISSIONS
                return list(ALL_PERMISSIONS)
            rows = conn.execute(
                "SELECT permission_key FROM user_permissions WHERE user_id = ? ORDER BY permission_key",
                (user_id,),
            ).fetchall()
            return [r["permission_key"] for r in rows]

    def set_user_permissions(self, user_id: int, permissions: List[str]) -> None:
        now = utc_now_iso()
        clean_perms = set(str(p).strip() for p in permissions if str(p).strip())
        with get_db(self.db_path) as conn:
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            for p in clean_perms:
                conn.execute(
                    "INSERT OR IGNORE INTO user_permissions (user_id, permission_key, created_at) VALUES (?, ?, ?)",
                    (user_id, p, now),
                )

    def delete_user(self, user_id: int) -> bool:
        """Permanently deletes a normal user and all cascading auth records."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        if str(user.get("role", "")).upper() == "ADMIN":
            raise ValueError("Cannot delete the administrator account.")
        with get_db(self.db_path) as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0

    def update_user_password(self, user_id: int, password_hash: str) -> bool:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, failed_login_attempts = 0,
                    locked_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, now, user_id),
            )
            return cur.rowcount > 0

    def create_password_reset_token(
        self, user_id: int, token_hash: str, expires_at: str
    ) -> Dict[str, Any]:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            # A newly requested link invalidates older unused links.
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            cur = conn.execute(
                """
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at, created_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (user_id, token_hash, expires_at, now),
            )
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)

    def consume_password_reset_token(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Atomically marks a valid, unused reset token as consumed."""
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM password_reset_tokens
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = ? AND used_at IS NULL",
                (now, row["id"]),
            )
            return dict(row)

    def list_users(self) -> List[Dict[str, Any]]:
        """Returns safe user summaries with permissions and without password_hash."""
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, email, full_name, role, status, created_at, updated_at, last_login_at
                FROM users
                ORDER BY created_at DESC
                """
            ).fetchall()
            result = []
            for r in rows:
                u = dict(r)
                u["permissions"] = self.get_user_permissions(u["id"])
                result.append(u)
            return result

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------
    def create_session(self, user_id: int, token_hash: str, expires_at: str) -> Dict[str, Any]:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO user_sessions (
                    user_id, token_hash, expires_at, created_at, last_activity_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, token_hash, expires_at, now, now),
            )
            created = conn.execute(
                "SELECT * FROM user_sessions WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(created)

    def get_session_with_user(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT s.id as session_id, s.user_id, s.token_hash, s.expires_at,
                       s.created_at as session_created_at, s.last_activity_at,
                       u.email, u.full_name, u.role, u.status
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            res["permissions"] = self.get_user_permissions(res["user_id"])
            return res

    def touch_session(self, session_id: int) -> None:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            conn.execute(
                "UPDATE user_sessions SET last_activity_at = ? WHERE id = ?",
                (now, session_id),
            )

    def delete_session_by_token_hash(self, token_hash: str) -> bool:
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,)
            )
            return cur.rowcount > 0

    def delete_sessions_for_user(self, user_id: int) -> int:
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM user_sessions WHERE user_id = ?", (user_id,)
            )
            return cur.rowcount

    def clean_expired_sessions(self) -> int:
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM user_sessions WHERE expires_at < ?", (now,)
            )
            return cur.rowcount

    # -------------------------------------------------------------------------
    # Mailer Intelligence & Newsletter Data
    # -------------------------------------------------------------------------
    def get_mailer_email_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM mailer_emails WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return dict(row) if row else None

    def get_mailer_email_by_id(self, mailer_id: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM mailer_emails WHERE id = ?", (mailer_id,)
            ).fetchone()
            return dict(row) if row else None

    def save_mailer_email(
        self,
        source_name: str,
        sender_name: Optional[str],
        sender_email: Optional[str],
        email_subject: Optional[str],
        newsletter_heading: Optional[str],
        received_datetime: Optional[str],
        content_hash: str,
        raw_html_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_mailer_email_by_hash(content_hash)
        if existing:
            return existing

        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO mailer_emails
                    (source_name, sender_name, sender_email, email_subject,
                     newsletter_heading, received_datetime, content_hash, raw_html_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_name,
                    sender_name,
                    sender_email,
                    email_subject,
                    newsletter_heading,
                    received_datetime,
                    content_hash,
                    raw_html_path,
                    now,
                ),
            )
            created_row = conn.execute(
                "SELECT * FROM mailer_emails WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(created_row)

    def save_mailer_articles(
        self, mailer_id: int, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        now = utc_now_iso()
        results = []
        with get_db(self.db_path) as conn:
            # Delete existing articles for this mailer to prevent duplicate accumulation
            conn.execute("DELETE FROM mailer_articles WHERE mailer_id = ?", (mailer_id,))
            for i, art in enumerate(articles):
                cur = conn.execute(
                    """
                    INSERT INTO mailer_articles
                        (mailer_id, title, description, image_url, source_url, source_name, article_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mailer_id,
                        art.get("title", ""),
                        art.get("description", ""),
                        art.get("image_url", ""),
                        art.get("source_url", ""),
                        art.get("source_name", ""),
                        art.get("order", i + 1),
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM mailer_articles WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
                if row:
                    results.append(dict(row))
        return results

    def save_mailer_advertisements(
        self, mailer_id: int, ads: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        now = utc_now_iso()
        results = []
        with get_db(self.db_path) as conn:
            # Delete existing ads for this mailer to prevent duplicate accumulation
            conn.execute("DELETE FROM mailer_advertisements WHERE mailer_id = ?", (mailer_id,))
            for i, ad in enumerate(ads):
                cur = conn.execute(
                    """
                    INSERT INTO mailer_advertisements
                        (mailer_id, advertiser, title, image_url, target_url, advertisement_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mailer_id,
                        ad.get("advertiser", ""),
                        ad.get("title", ""),
                        ad.get("image_url", ""),
                        ad.get("target_url", ""),
                        ad.get("order", i + 1),
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM mailer_advertisements WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
                if row:
                    results.append(dict(row))
        return results

    def get_mailer_emails_list(
        self,
        source: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            query = """
                SELECT e.*,
                    (SELECT COUNT(*) FROM mailer_articles a WHERE a.mailer_id = e.id) AS article_count,
                    (SELECT COUNT(*) FROM mailer_advertisements ad WHERE ad.mailer_id = e.id) AS advertisement_count
                FROM mailer_emails e
                WHERE 1=1
            """
            params: List[Any] = []

            if source and source.strip() and source.lower() != "all":
                query += " AND LOWER(e.source_name) LIKE ?"
                params.append(f"%{source.strip().lower()}%")

            if start_date and start_date.strip():
                query += " AND e.received_datetime >= ?"
                params.append(start_date.strip())

            if end_date and end_date.strip():
                query += " AND e.received_datetime <= ?"
                params.append(end_date.strip() + "T23:59:59")

            if search and search.strip():
                s = f"%{search.strip().lower()}%"
                query += """ AND (
                    LOWER(e.newsletter_heading) LIKE ? OR
                    LOWER(e.email_subject) LIKE ? OR
                    LOWER(e.source_name) LIKE ? OR
                    LOWER(e.sender_email) LIKE ? OR
                    EXISTS (SELECT 1 FROM mailer_articles a WHERE a.mailer_id = e.id AND (LOWER(a.title) LIKE ? OR LOWER(a.description) LIKE ?)) OR
                    EXISTS (SELECT 1 FROM mailer_advertisements ad WHERE ad.mailer_id = e.id AND (LOWER(ad.advertiser) LIKE ? OR LOWER(ad.title) LIKE ?))
                )"""
                params.extend([s, s, s, s, s, s, s, s])

            query += " ORDER BY e.received_datetime DESC, e.id DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_mailer_email_detail(self, mailer_id: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            email_row = conn.execute(
                "SELECT * FROM mailer_emails WHERE id = ?", (mailer_id,)
            ).fetchone()
            if not email_row:
                return None

            result = dict(email_row)
            articles = conn.execute(
                "SELECT * FROM mailer_articles WHERE mailer_id = ? ORDER BY article_order ASC, id ASC",
                (mailer_id,),
            ).fetchall()
            ads = conn.execute(
                "SELECT * FROM mailer_advertisements WHERE mailer_id = ? ORDER BY advertisement_order ASC, id ASC",
                (mailer_id,),
            ).fetchall()

            result["articles"] = [dict(a) for a in articles]
            result["advertisements"] = [dict(ad) for ad in ads]
            result["article_count"] = len(result["articles"])
            result["advertisement_count"] = len(result["advertisements"])
            return result


# Global default repository instance
db_repo = Repository()

