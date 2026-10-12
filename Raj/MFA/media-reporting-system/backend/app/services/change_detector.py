"""
Media Reporting System - Change Detection & Article Lifecycle Engine
Tracks article lifecycles (NEW, UPDATED, UNCHANGED, REMOVED) and preserves historical versions.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database.repository import Repository, db_repo, utc_now_iso

logger = logging.getLogger("change-detector")

# Thresholds to protect against false mass-removals during partial network glitches
MIN_ARTICLES_FOR_SAFE_REMOVAL = 5

DEFAULT_WEBSITE_METADATA = {
    "et_brand_equity": {
        "name": "ET BrandEquity",
        "url": "https://brandequity.economictimes.indiatimes.com/",
    },
    "exchange4media": {
        "name": "Exchange4media",
        "url": "https://www.exchange4media.com/",
    },
    "campaign_india": {
        "name": "Campaign India",
        "url": "https://www.campaignindia.in/news",
    },
    "bestmediainfo": {
        "name": "BestMediaInfo",
        "url": "https://bestmediainfo.com/",
    },
    "social_samosa": {
        "name": "Social Samosa",
        "url": "https://www.socialsamosa.com/",
    },
    "adgully": {
        "name": "Adgully",
        "url": "https://www.adgully.com/",
    },
    "mediabrief": {
        "name": "MediaBrief",
        "url": "https://mediabrief.com/",
    },
    "storyboard18": {
        "name": "Storyboard18",
        "url": "https://www.storyboard18.com/",
    },
    "indiantelevision": {
        "name": "Indian Television",
        "url": "https://indiantelevision.com/",
    },
}


def normalize_field(val: Optional[str]) -> str:
    """Trims whitespace and normalizes empty or None values to empty string."""
    if not val:
        return ""
    return str(val).strip()


def compute_content_hash(
    headline: str,
    summary: Optional[str] = None,
    image_url: Optional[str] = None,
    section: Optional[str] = None,
    published_at: Optional[str] = None,
) -> str:
    """
    Computes a deterministic SHA-256 hash of meaningful article content.
    Explicitly excludes volatile fields like scraped_at and last_seen_at.
    """
    norm_headline = normalize_field(headline)
    norm_summary = normalize_field(summary)
    norm_image = normalize_field(image_url)
    norm_section = normalize_field(section)
    norm_published = normalize_field(published_at)

    components = [
        norm_headline,
        norm_summary,
        norm_image,
        norm_section,
        norm_published,
    ]
    raw_str = "|".join(components)
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


class ChangeDetector:
    """
    Core engine responsible for processing incoming article batches,
    classifying them into NEW, UPDATED, UNCHANGED, and REMOVED,
    and auditing historical versions.
    """

    def __init__(self, repo_or_db_path: Optional[Any] = None):
        if repo_or_db_path is None:
            self.repo = db_repo
        elif isinstance(repo_or_db_path, Repository):
            self.repo = repo_or_db_path
        else:
            self.repo = Repository(repo_or_db_path)

    def ensure_website(self, website_key: str) -> Dict[str, Any]:
        """Ensures the website is registered in the database."""
        meta = DEFAULT_WEBSITE_METADATA.get(
            website_key,
            {
                "name": website_key.replace("_", " ").title(),
                "url": f"https://{website_key}.com",
            },
        )
        return self.repo.get_or_create_website(
            name=meta["name"],
            website_key=website_key,
            base_url=meta["url"],
        )

    def process_scraped_articles(
        self,
        website_key: str,
        articles: Optional[List[Dict[str, Any]]] = None,
        scraped_items: Optional[List[Dict[str, Any]]] = None,
        *,
        is_successful: bool = True,
        scrape_success: Optional[bool] = None,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        detected_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes a scrape result batch for a single website with full change detection
        and false-removal protection safeguards.
        """
        now = detected_at or utc_now_iso()
        site_record = self.ensure_website(website_key)
        website_id = site_record["id"]

        # Publisher homepages and section pages are rolling discovery feeds.
        # Absence from a later listing crawl is not evidence that the original
        # article was deleted. Restore records affected by the former policy.
        restored_items = self.repo.reactivate_articles_for_website(website_id)
        if restored_items:
            logger.info(
                "Restored %d published article(s) for %s after listing rotation",
                restored_items,
                website_key,
            )

        items = articles if articles is not None else (scraped_items or [])
        success = scrape_success if scrape_success is not None else is_successful

        run_id = self.repo.start_scrape_run(website_id)

        # ---------------------------------------------------------------------
        # Safeguard 1: Scraper Failure Protection
        # ---------------------------------------------------------------------
        if not success:
            logger.warning(
                "Scrape failed for website '%s': %s. Aborting change detection; preserving active records.",
                website_key,
                error_message,
            )
            self.repo.finish_scrape_run(
                run_id=run_id,
                status="FAILED",
                items_found=0,
                new_items=0,
                updated_items=0,
                unchanged_items=0,
                removed_items=0,
                error_message=error_message or "Scraper execution failed",
            )
            return {
                "run_id": run_id,
                "status": "FAILED",
                "website_key": website_key,
                "items_found": 0,
                "new_items": 0,
                "updated_items": 0,
                "unchanged_items": 0,
                "removed_items": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
                "removed": 0,
                "error_message": error_message,
            }

        # ---------------------------------------------------------------------
        # Safeguard 2: Unexpected Zero Items Protection
        # ---------------------------------------------------------------------
        if len(items) == 0:
            msg = "Scraper returned 0 articles unexpectedly. Flagged for review; 0 articles marked removed."
            logger.warning(msg)
            self.repo.finish_scrape_run(
                run_id=run_id,
                status="SUCCESS",
                items_found=0,
                new_items=0,
                updated_items=0,
                unchanged_items=0,
                removed_items=0,
                error_message=msg,
            )
            return {
                "run_id": run_id,
                "status": "SUCCESS",
                "website_key": website_key,
                "items_found": 0,
                "new_items": 0,
                "updated_items": 0,
                "unchanged_items": 0,
                "removed_items": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
                "removed": 0,
                "warning": msg,
            }


        new_items = 0
        updated_items = 0
        unchanged_items = 0
        removed_items = 0

        # ---------------------------------------------------------------------
        # Process Incoming Articles (NEW, UNCHANGED, UPDATED)
        # ---------------------------------------------------------------------
        fetcher = None
        for raw_art in items:
            url = normalize_field(raw_art.get("url"))
            headline = normalize_field(raw_art.get("headline"))
            if not url or not headline:
                continue

            summary = raw_art.get("summary") or None
            image_url = raw_art.get("image_url") or None
            section_name = raw_art.get("section") or "Overall"
            published_at = raw_art.get("published_at") or None
            existing = self.repo.get_article_by_url(website_id, url)
            # A publisher-provided relative label is publication metadata. If
            # no exact timestamp has ever been captured, convert it once using
            # the scrape moment as the reference. Never substitute first_seen
            # or last_seen by themselves for a publication timestamp.
            if not published_at and not (existing and existing.get("published_at")):
                publication_label = raw_art.get("publication_label")
                if publication_label:
                    try:
                        from scraper.utils.date_parser import parse_relative_date_to_iso

                        published_at = parse_relative_date_to_iso(
                            publication_label,
                            reference_iso=raw_art.get("scraped_at"),
                        )
                    except (TypeError, ValueError):
                        published_at = None
            # Listing cards often omit metadata present on an earlier article-page fetch.
            # Missing extraction is not evidence that the publisher deleted a field.
            if existing:
                summary = summary or existing.get("summary")
                image_url = image_url or existing.get("image_url")
                published_at = existing.get("published_at") or published_at

            # Resolve section foreign key
            sec_record = self.repo.get_or_create_section(
                website_id=website_id,
                name=section_name,
            )
            section_id = sec_record["id"]

            content_hash = compute_content_hash(
                headline=headline,
                summary=summary,
                image_url=image_url,
                section=section_name,
                published_at=published_at,
            )

            existing = self.repo.get_article_by_url(website_id, url)

            if not existing:
                # -------------------------------------------------------------
                # 1. NEW Article
                # -------------------------------------------------------------
                # If published_at, summary or image is missing, enrich from detail page
                if not published_at or not summary or not image_url:
                    try:
                        from scraper.base.fetcher import PageFetcher
                        from scraper.base.enrichment import enrich_article_dict
                        if fetcher is None:
                            fetcher = PageFetcher()
                        enriched = enrich_article_dict(raw_art, fetcher)
                        published_at = enriched.get("published_at") or published_at
                        headline = enriched.get("headline") or headline
                        summary = enriched.get("summary") or summary
                        image_url = enriched.get("image_url") or image_url
                        content_hash = compute_content_hash(
                            headline=headline,
                            summary=summary,
                            image_url=image_url,
                            section=section_name,
                            published_at=published_at,
                        )
                    except Exception:
                        pass
                # Keep published_at None if unavailable from publisher
                art_row = self.repo.insert_article(
                    website_id=website_id,
                    section_id=section_id,
                    headline=headline,
                    url=url,
                    image_url=image_url,
                    summary=summary,
                    published_at=published_at,
                    content_hash=content_hash,
                    detected_at=now,
                )
                self.repo.insert_article_version(
                    article_id=art_row["id"],
                    headline=headline,
                    url=url,
                    image_url=image_url,
                    summary=summary,
                    section_id=section_id,
                    published_at=published_at,
                    content_hash=content_hash,
                    change_type="NEW",
                    detected_at=now,
                )
                new_items += 1

            elif existing["content_hash"] == content_hash:
                # -------------------------------------------------------------
                # 2. UNCHANGED Article
                # -------------------------------------------------------------
                self.repo.touch_article_seen(existing["id"], detected_at=now)
                unchanged_items += 1

            else:
                # -------------------------------------------------------------
                # 3. UPDATED Article (Content modified)
                # -------------------------------------------------------------
                self.repo.update_article_content(
                    article_id=existing["id"],
                    headline=headline,
                    image_url=image_url,
                    summary=summary,
                    section_id=section_id,
                    published_at=published_at,
                    content_hash=content_hash,
                    detected_at=now,
                )
                self.repo.insert_article_version(
                    article_id=existing["id"],
                    headline=headline,
                    url=url,
                    image_url=image_url,
                    summary=summary,
                    section_id=section_id,
                    published_at=published_at,
                    content_hash=content_hash,
                    change_type="UPDATED",
                    detected_at=now,
                )
                updated_items += 1

            if existing:
                # If existing DB record lacks publication date, enrich and update it
                if not existing.get("published_at"):
                    target_pub = published_at or raw_art.get("published_at")
                    if not target_pub:
                        try:
                            from scraper.base.fetcher import PageFetcher
                            from scraper.base.enrichment import enrich_article_dict
                            if fetcher is None:
                                fetcher = PageFetcher()
                            enriched = enrich_article_dict(raw_art, fetcher)
                            target_pub = enriched.get("published_at")
                        except Exception:
                            pass
                    if target_pub:
                        self.repo.update_article_published_at(existing["id"], target_pub, detected_at=now)

            self.repo.update_article_labels(
                (existing or art_row)["id"],
                raw_art.get("publication_label"),
                bool(raw_art.get("is_exclusive")),
            )

        # Listing absence never marks an article removed. A future removal
        # workflow must verify the canonical article URL itself (404/410) before
        # changing lifecycle status.

        # Update snapshot JSON file in scraper_output/ for file-fallback compatibility
        try:
            from app.services.generic_source_service import find_source_scraper_output_file
            out_file = find_source_scraper_output_file(website_key)
            db_articles = self.repo.get_articles(website_key=website_key, status="all", limit=None)
            if db_articles:
                payload = {
                    "generated_at": now,
                    "website": website_key,
                    "count": len(db_articles),
                    "articles": [
                        {
                            "website": a.get("website_name") or website_key,
                            "website_key": website_key,
                            "section": a.get("section_name") or "Overall",
                            "headline": a["headline"],
                            "url": a["url"],
                            "image_url": a.get("image_url"),
                            "summary": a.get("summary"),
                            "published_at": a.get("published_at"),
                            "scraped_at": a.get("first_seen_at") or a.get("created_at") or a.get("last_seen_at"),
                            "first_seen_at": a.get("first_seen_at") or a.get("created_at"),
                            "last_seen_at": a.get("last_seen_at"),
                            "content_hash": a["content_hash"],
                            "publication_label": a.get("publication_label"),
                            "is_exclusive": bool(a.get("is_exclusive")),
                        }
                        for a in db_articles
                    ],
                }
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as snap_exc:
            logger.debug("Snapshot update notice for %s: %s", website_key, snap_exc)

        self.repo.finish_scrape_run(
            run_id=run_id,
            status="SUCCESS",
            items_found=len(items),
            new_items=new_items,
            updated_items=updated_items,
            unchanged_items=unchanged_items,
            removed_items=removed_items,
        )

        return {
            "run_id": run_id,
            "status": "SUCCESS",
            "website_key": website_key,
            "items_found": len(items),
            "new_items": new_items,
            "updated_items": updated_items,
            "unchanged_items": unchanged_items,
            "removed_items": removed_items,
            "new": new_items,
            "updated": updated_items,
            "unchanged": unchanged_items,
            "removed": removed_items,
        }

    # Alias for method invocation
    process_scrape_result = process_scraped_articles


# Global change detector instance
change_detector = ChangeDetector()
