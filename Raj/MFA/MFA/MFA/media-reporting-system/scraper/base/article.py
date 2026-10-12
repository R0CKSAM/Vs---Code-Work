"""
Media Reporting System - Article Data Model
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Article:
    """
    Standard normalized Article representation across all monitored media publishers.
    """
    website: str
    website_key: str
    section: str
    headline: str
    url: str
    image_url: Optional[str] = None
    summary: Optional[str] = None
    published_at: Optional[str] = None
    scraped_at: str = ""
    content_hash: str = ""
    publication_label: Optional[str] = None
    is_exclusive: bool = False

    def finalize(self) -> Article:
        """
        Finalizes the article record by populating scraped_at (if not already set)
        and computing a deterministic SHA-256 content hash.
        
        The content hash strictly excludes `scraped_at` so identical article content
        produces identical checksums across repeat scrape cycles.
        """
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()

        hash_source = "||".join(
            [
                self.website_key or "",
                self.section or "",
                self.headline or "",
                self.url or "",
                self.image_url or "",
                self.summary or "",
            ]
        )

        self.content_hash = hashlib.sha256(
            hash_source.encode("utf-8")
        ).hexdigest()

        return self
