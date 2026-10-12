"""
Media Reporting System - Advertisement Creative Asset Downloader & Storage
Safely downloads and archives ad creative image assets and screenshots under storage/advertisements/
Validates file sizes, content types, and prevents duplicate downloads.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("ad-storage")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_BASE = PROJECT_ROOT / "storage" / "advertisements"

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit


def download_ad_image(
    image_url: str,
    website_key: str,
    ad_hash: str,
    timeout_seconds: float = 8.0,
) -> Optional[str]:
    """
    Downloads an ad creative image and stores it locally under:
    storage/advertisements/<website_key>/<year>/<month>/<ad_hash[:16]>/
    Returns the relative path from project root or None.
    """
    if not image_url or not image_url.startswith("http"):
        return None

    now = datetime.now(timezone.utc)
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    short_hash = ad_hash[:16] if ad_hash else "unhashed"

    target_dir = STORAGE_BASE / website_key / year_str / month_str / short_hash
    target_dir.mkdir(parents=True, exist_ok=True)

    # Determine filename from URL path or fallback
    parsed = urllib.parse.urlparse(image_url)
    filename = os.path.basename(parsed.path) or "creative.jpg"
    clean_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not clean_filename or "." not in clean_filename:
        clean_filename = f"creative_{short_hash[:8]}.jpg"

    target_path = target_dir / clean_filename

    # If file already exists and is non-empty, reuse it
    if target_path.exists() and target_path.stat().st_size > 0:
        return str(target_path.relative_to(PROJECT_ROOT)).replace("\\", "/")

    partial_path = target_path.with_suffix(target_path.suffix + ".part")
    resp = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = requests.get(image_url, headers=headers, timeout=timeout_seconds, stream=True)
        if resp.status_code != 200:
            logger.warning("Failed to download ad creative from %s: HTTP %d", image_url, resp.status_code)
            return None

        # Validate content-type
        content_type = resp.headers.get("Content-Type", "").lower()
        if not any(t in content_type for t in ["image/", "application/octet-stream"]):
            logger.warning("Rejected non-image content type for %s: %s", image_url, content_type)
            return None

        # Write safely with size limit
        bytes_written = 0
        with open(partial_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    bytes_written += len(chunk)
                    if bytes_written > MAX_IMAGE_SIZE_BYTES:
                        logger.warning("Ad creative exceeded max size limit (%s)", image_url)
                        f.close()
                        partial_path.unlink(missing_ok=True)
                        return None
                    f.write(chunk)

        if bytes_written > 0:
            partial_path.replace(target_path)
            logger.info("Saved ad creative: %s (%d bytes)", target_path.name, bytes_written)
            return str(target_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        else:
            partial_path.unlink(missing_ok=True)
            return None

    except Exception as exc:
        logger.warning("Error downloading ad creative from %s: %s", image_url, exc)
        return None
    finally:
        partial_path.unlink(missing_ok=True)
        if resp is not None:
            resp.close()


def save_ad_screenshot(
    image_bytes: bytes,
    website_key: str,
    ad_hash: str,
    filename: str = "creative_render.png",
) -> Optional[str]:
    """
    Saves an in-memory rendered ad element screenshot to storage/advertisements/...
    Returns the relative path from project root or None.
    """
    if not image_bytes or len(image_bytes) == 0:
        return None

    now = datetime.now(timezone.utc)
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    short_hash = ad_hash[:16] if ad_hash else "unhashed"

    target_dir = STORAGE_BASE / website_key / year_str / month_str / short_hash
    target_dir.mkdir(parents=True, exist_ok=True)

    clean_filename = "".join(c for c in filename if c.isalnum() or c in "._-") or "render.png"
    target_path = target_dir / clean_filename

    try:
        with open(target_path, "wb") as f:
            f.write(image_bytes)
        logger.info("Saved ad render screenshot: %s (%d bytes)", target_path.name, len(image_bytes))
        return str(target_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except Exception as exc:
        logger.warning("Error saving ad render screenshot: %s", exc)
        return None
