"""
Media Reporting System - Mailer Ingestion & Processing Service
Orchestrates parser selection, duplicate detection, and database storage.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.repository import Repository, db_repo
from mailer.best_media_info_parser import BestMediaInfoParser
from mailer.models import ParsedMailer

logger = logging.getLogger("mailer-service")


class MailerService:
    """Service handling email ingestion, parsing, duplicate prevention, and queries."""

    def __init__(self, repo: Optional[Repository] = None):
        self.repo = repo or db_repo
        self.parsers = {
            "best_media_info": BestMediaInfoParser(),
        }
        self.default_parser = BestMediaInfoParser()

    def select_parser(self, html_content: str, metadata: Optional[Dict[str, Any]] = None):
        """Selects parser based on sender/source or content signals."""
        meta = metadata or {}
        sender = str(meta.get("sender_email") or meta.get("sender") or "").lower()
        source = str(meta.get("source_name") or "").lower()

        if "bestmediainfo" in sender or "best media info" in source or "bestmediainfo" in html_content.lower():
            return self.parsers["best_media_info"]

        # Default fallback
        return self.default_parser

    def process_email_html(
        self,
        html_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        raw_html_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses an HTML email, checks for duplicates, and persists structured data to DB.
        """
        parser = self.select_parser(html_content, metadata)
        parsed: ParsedMailer = parser.parse_email_html(html_content, metadata)

        # 1. Duplicate detection check
        existing = self.repo.get_mailer_email_by_hash(parsed.content_hash)
        if existing:
            detail = self.repo.get_mailer_email_detail(existing["id"])
            logger.info("Duplicate email detected with hash %s (ID: %s)", parsed.content_hash, existing["id"])
            return {
                "status": "duplicate",
                "is_duplicate": True,
                "message": "Newsletter already processed. Retained existing record.",
                "data": detail,
            }

        # 2. Save newsletter header
        saved_email = self.repo.save_mailer_email(
            source_name=parsed.source_name,
            sender_name=parsed.sender_name,
            sender_email=parsed.sender_email,
            email_subject=parsed.email_subject,
            newsletter_heading=parsed.newsletter_heading,
            received_datetime=parsed.received_datetime,
            content_hash=parsed.content_hash,
            raw_html_path=raw_html_path,
        )
        mailer_id = saved_email["id"]

        # 3. Save articles
        articles_dicts = [a.to_dict() for a in parsed.articles]
        saved_articles = self.repo.save_mailer_articles(mailer_id, articles_dicts)

        # 4. Save advertisements
        ads_dicts = [ad.to_dict() for ad in parsed.advertisements]
        saved_ads = self.repo.save_mailer_advertisements(mailer_id, ads_dicts)

        # 5. Return complete structured response
        detail = self.repo.get_mailer_email_detail(mailer_id)
        return {
            "status": "created",
            "is_duplicate": False,
            "message": f"Successfully processed newsletter with {len(saved_articles)} articles and {len(saved_ads)} advertisements.",
            "data": detail,
        }

    def process_file(
        self,
        file_path: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Reads an HTML file from disk and processes it."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Email HTML file not found: {path}")

        html_content = path.read_text(encoding="utf-8", errors="replace")
        return self.process_email_html(
            html_content=html_content,
            metadata=metadata,
            raw_html_path=str(path),
        )

    def list_newsletters(
        self,
        source: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self.repo.get_mailer_emails_list(
            source=source,
            search=search,
            start_date=start_date,
            end_date=end_date,
        )

    def get_newsletter_detail(self, mailer_id: int) -> Optional[Dict[str, Any]]:
        return self.repo.get_mailer_email_detail(mailer_id)


# Global default mailer service instance
mailer_service = MailerService()
