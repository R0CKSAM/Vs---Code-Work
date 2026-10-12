"""
Media Reporting System - Phase 6 Advertisement Change Detection & Persistence Engine
Processes detected advertisements against database state:
  - Tracks NEW, UNCHANGED, CHANGED, and REMOVED advertisement lifecycles.
  - Maintains first_seen_at and updates last_seen_at.
  - Archives creative version history in advertisement_versions.
  - Applies failed-scrape safeguards to protect active advertisement records.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from database.repository import Repository, db_repo
from scraper.ad_image_storage import download_ad_image
from scraper.advertisements import DetectedAdvertisement

logger = logging.getLogger("ad-change-detector")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvertisementChangeDetector:
    """
    Coordinates advertisement change detection, asset archiving, and database persistence.
    """

    def __init__(self, repo_or_db_path: Optional[Union[Repository, Path, str]] = None):
        if isinstance(repo_or_db_path, Repository):
            self.repo = repo_or_db_path
        elif repo_or_db_path is not None:
            self.repo = Repository(repo_or_db_path)
        else:
            self.repo = db_repo

    def process_detected_advertisements(
        self,
        website_key: str,
        detected_ads: List[Union[DetectedAdvertisement, Dict[str, Any]]],
        scrape_success: bool = True,
        download_images: bool = True,
        detected_at: Optional[str] = None,
        allow_removals: bool = True,
    ) -> Dict[str, Any]:
        """
        Processes a batch of detected advertisements for a website.
        Returns a breakdown of new, updated/changed, unchanged, and removed ads.
        """
        now = detected_at or _now_iso()

        # Resolve website
        site_record = self.repo.get_website_by_key(website_key)
        if not site_record:
            site_record = self.repo.get_or_create_website(
                name=website_key.replace("_", " ").title(),
                website_key=website_key,
                base_url="",
            )
        website_id = site_record["id"]

        # Normalized detected ads dict list
        norm_ads: List[Dict[str, Any]] = []
        for ad in detected_ads:
            if isinstance(ad, DetectedAdvertisement):
                norm_ads.append(ad.to_dict())
            elif isinstance(ad, dict):
                norm_ads.append(ad)

        new_count = 0
        changed_count = 0
        unchanged_count = 0
        removed_count = 0

        # Fetch current active advertisements from DB
        all_records = self.repo.get_advertisements(website_key=website_key, limit=-1)
        current_active = [a for a in all_records if a["status"] != "REMOVED"]
        active_by_hash = {a["ad_hash"]: a for a in all_records}
        placement_records = defaultdict(list)
        for a in current_active:
            placement_records[f"{a['page_url']}|{a['position']}"].append(a)
        placement_counts = Counter(f"{a.get('page_url', '')}|{a.get('position') or 'UNKNOWN'}" for a in norm_ads)
        # A broad position such as UNKNOWN may contain several independent slots.
        active_by_position_url = {
            key: records[0] for key, records in placement_records.items()
            if len(records) == 1 and placement_counts[key] == 1
        }

        seen_ad_ids = set()
        seen_hashes = set()

        for ad_data in norm_ads:
            ad_hash = ad_data.get("ad_hash") or ""
            if not ad_hash or ad_hash in seen_hashes:
                continue
            seen_hashes.add(ad_hash)
            page_url = ad_data.get("page_url") or ""
            position = ad_data.get("position") or "UNKNOWN"
            ad_type = ad_data.get("ad_type") or "BANNER"
            image_url = ad_data.get("image_url")
            target_url = ad_data.get("target_url")
            advertiser = ad_data.get("advertiser")
            brand = ad_data.get("brand")
            campaign = ad_data.get("campaign")
            section_name = ad_data.get("section")

            # Resolve section if provided
            section_id = None
            if section_name:
                sec = self.repo.get_or_create_section(website_id, section_name)
                section_id = sec["id"]

            pos_url_key = f"{page_url}|{position}"

            # Case 1: Identical ad hash already exists
            if ad_hash in active_by_hash:
                existing = active_by_hash[ad_hash]
                seen_ad_ids.add(existing["id"])
                unchanged_count += 1
                local_path = ad_data.get("local_image_path")
                if download_images and image_url and not existing.get("local_image_path") and not local_path:
                    local_path = download_ad_image(image_url, website_key, ad_hash)
                self.repo.update_advertisement_seen(existing["id"], seen_at=now, local_image_path=local_path)
                self.repo.enrich_advertisement_identity(
                    existing["id"], advertiser, brand, campaign, target_url
                )
                self.repo.enrich_advertisement_position(existing["id"], position)
                continue

            # Case 2: Same position on page exists, but creative/hash changed
            if pos_url_key in active_by_position_url:
                existing = active_by_position_url[pos_url_key]
                seen_ad_ids.add(existing["id"])
                changed_count += 1

                # Download new creative image if available
                local_path = ad_data.get("local_image_path")
                if download_images and image_url and not local_path:
                    local_path = download_ad_image(image_url, website_key, ad_hash)

                self.repo.update_advertisement_creative(
                    ad_id=existing["id"],
                    new_ad_hash=ad_hash,
                    image_url=image_url,
                    local_image_path=local_path,
                    target_url=target_url,
                    advertiser=advertiser,
                    brand=brand,
                    campaign=campaign,
                    ad_type=ad_type,
                    position=position,
                    detected_at=now,
                )
                continue

            # Case 3: Completely NEW advertisement
            local_path = ad_data.get("local_image_path")
            if download_images and image_url and not local_path:
                local_path = download_ad_image(image_url, website_key, ad_hash)

            ad_id = self.repo.insert_advertisement(
                website_id=website_id,
                page_url=page_url,
                ad_hash=ad_hash,
                ad_type=ad_type,
                position=position,
                advertiser=advertiser,
                brand=brand,
                campaign=campaign,
                image_url=image_url,
                local_image_path=local_path,
                target_url=target_url,
                section_id=section_id,
                detected_at=now,
            )
            seen_ad_ids.add(ad_id)
            new_count += 1

        # Case 4: Mark removed advertisements
        # SAFEGUARD: Only mark removed if scrape was successful and removals are allowed
        if scrape_success and allow_removals:
            for existing in current_active:
                if existing["id"] not in seen_ad_ids:
                    self.repo.mark_advertisement_removed(existing["id"], removed_at=now)
                    removed_count += 1
        elif not scrape_success:
            logger.warning(
                "Incomplete ad observation for %s: preserving %d previously observed advertisements due to scrape failure.",
                website_key,
                len(current_active),
            )
        else:
            logger.debug(
                "Preserving %d previously observed advertisements for %s (removal safeguard active).",
                len(current_active),
                website_key,
            )

        logger.info(
            "[ADS] %s processed %d detected ads: new=%d changed=%d unchanged=%d removed=%d",
            website_key,
            len(norm_ads),
            new_count,
            changed_count,
            unchanged_count,
            removed_count,
        )

        return {
            "website_key": website_key,
            "detected_count": len(norm_ads),
            "new": new_count,
            "changed": changed_count,
            "unchanged": unchanged_count,
            "removed": removed_count,
        }


# Global default ad change detector instance
ad_change_detector = AdvertisementChangeDetector()
