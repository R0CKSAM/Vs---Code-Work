"""
crawler.py – FanCode Discovery Crawler.

Performs a controlled, polite breadth-first crawl of FanCode starting
from the homepage.  For each page visited it:

  1. Navigates with Playwright (real browser, JS rendered)
  2. Extracts internal links
  3. Classifies the page
  4. Captures network metadata via NetworkMonitor
  5. Records a DiscoveredPage result

Hard limits are enforced from Settings to prevent runaway crawls:
  - DISCOVERY_MAX_PAGES
  - DISCOVERY_MAX_DEPTH
  - DISCOVERY_MAX_LINKS_PER_PAGE
  - DISCOVERY_TIMEOUT_SECONDS
  - REQUEST_DELAY_SECONDS   (polite inter-page delay)

The crawler does NOT:
  - Submit forms
  - Click buttons
  - Attempt login
  - Bypass CAPTCHA or bot protection
  - Follow external links
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

from playwright.sync_api import Browser, BrowserContext, Page, TimeoutError as PWTimeout

from app.config.settings import settings
from app.scraper.discovery.models import (
    DiscoveredPage,
    DiscoveryResult,
    PageType,
)
from app.scraper.discovery.network_monitor import NetworkMonitor
from app.scraper.discovery.page_classifier import classify_page
from app.scraper.discovery.url_normalizer import (
    deduplicate,
    is_internal,
    normalize,
)

logger = logging.getLogger(__name__)

# Images we want to sample (not exhaustively — first N)
MAX_IMAGES_PER_PAGE = 10


class FanCodeCrawler:
    """
    Breadth-first discovery crawler for https://www.fancode.com/

    Parameters
    ----------
    browser : Browser
        An already-launched Playwright Browser instance.
    max_pages : int
        Hard page-visit cap. Overrides settings default when provided.
    max_depth : int
        Maximum crawl depth from the seed URL.
    max_links_per_page : int
        Maximum internal links extracted per page.
    timeout_seconds : int
        Wall-clock timeout for the entire crawl.
    delay_seconds : float
        Polite delay between page visits.
    seed_url : str
        Starting URL (defaults to settings.BASE_URL).
    """

    def __init__(
        self,
        browser: Browser,
        max_pages: int = 0,
        max_depth: int = 0,
        max_links_per_page: int = 0,
        timeout_seconds: int = 0,
        delay_seconds: float = 0.0,
        seed_url: str = "",
    ) -> None:
        self._browser = browser
        self._max_pages = max_pages or settings.DISCOVERY_MAX_PAGES
        self._max_depth = max_depth or settings.DISCOVERY_MAX_DEPTH
        self._max_links = max_links_per_page or settings.DISCOVERY_MAX_LINKS_PER_PAGE
        self._timeout_s = timeout_seconds or settings.DISCOVERY_TIMEOUT_SECONDS
        self._delay_s = delay_seconds if delay_seconds > 0 else settings.REQUEST_DELAY_SECONDS
        self._seed = seed_url or settings.BASE_URL

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run(self) -> DiscoveryResult:
        """
        Execute the full discovery crawl and return a DiscoveryResult.

        Creates a single BrowserContext for the entire crawl (shared
        cookie jar, but effectively clean because FanCode does not
        require authentication for public pages).
        """
        result = DiscoveryResult(base_url=self._seed)
        logger.info(
            "Discovery crawl started | seed=%s max_pages=%d max_depth=%d",
            self._seed, self._max_pages, self._max_depth,
        )

        ctx = self._browser.new_context(
            viewport={
                "width": settings.BROWSER_VIEWPORT_WIDTH,
                "height": settings.BROWSER_VIEWPORT_HEIGHT,
            },
            locale="en-US",
            timezone_id="UTC",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        ctx.set_default_timeout(settings.DISCOVERY_PAGE_TIMEOUT_MS)
        ctx.set_default_navigation_timeout(settings.DISCOVERY_PAGE_TIMEOUT_MS)

        try:
            self._crawl(ctx, result)
        finally:
            ctx.close()

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Discovery crawl finished | pages=%d json_endpoints=%d terminated_early=%s",
            result.page_count,
            len(result.json_endpoints),
            result.terminated_early,
        )
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Internal crawl loop
    # ──────────────────────────────────────────────────────────────────────────

    def _crawl(self, ctx: BrowserContext, result: DiscoveryResult) -> None:
        """BFS crawl loop with hard limits."""
        queue: deque[tuple[str, int]] = deque()  # (url, depth)
        visited: Set[str] = set()
        deadline = time.monotonic() + self._timeout_s

        # Seed
        seed_norm = normalize(self._seed, self._seed) or self._seed
        queue.append((seed_norm, 0))

        while queue:
            # ── Termination checks ────────────────────────────────────────
            if result.page_count >= self._max_pages:
                result.terminated_early = True
                result.termination_reason = f"max_pages={self._max_pages} reached"
                logger.info("Crawl limit: %s", result.termination_reason)
                break

            if time.monotonic() > deadline:
                result.terminated_early = True
                result.termination_reason = f"timeout={self._timeout_s}s reached"
                logger.info("Crawl limit: %s", result.termination_reason)
                break

            url, depth = queue.popleft()

            if url in visited:
                continue
            if depth > self._max_depth:
                continue
            if not is_internal(url):
                continue

            visited.add(url)

            # ── Visit page ────────────────────────────────────────────────
            page_data = self._visit_page(ctx, url, depth)
            result.pages.append(page_data)
            result.all_network_events.extend(page_data.network_events)

            logger.info(
                "[depth=%d] %s | type=%s | links=%d | net=%d",
                depth,
                url,
                page_data.page_type.value,
                len(page_data.internal_links),
                len(page_data.network_events),
            )

            # ── Enqueue discovered links (next depth) ─────────────────────
            if depth < self._max_depth:
                for link in page_data.internal_links:
                    if link not in visited:
                        queue.append((link, depth + 1))

            # ── Polite delay ──────────────────────────────────────────────
            if queue and self._delay_s > 0:
                time.sleep(self._delay_s)

    def _visit_page(
        self, ctx: BrowserContext, url: str, depth: int
    ) -> DiscoveredPage:
        """Navigate to a single URL and collect all metadata."""
        page = ctx.new_page()
        monitor = NetworkMonitor(page, page_url=url)
        monitor.attach()

        http_status: Optional[int] = None
        canonical: Optional[str] = None
        title = ""
        internal_links: List[str] = []
        image_urls: List[str] = []
        error: Optional[str] = None

        try:
            resp = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.DISCOVERY_PAGE_TIMEOUT_MS,
            )
            if resp:
                http_status = resp.status

            # Extra settle time for JS-rendered content
            if settings.DISCOVERY_WAIT_AFTER_LOAD_MS > 0:
                page.wait_for_timeout(settings.DISCOVERY_WAIT_AFTER_LOAD_MS)

            title = page.title() or ""

            # Canonical URL
            canonical = self._extract_canonical(page) or url

            # Internal links
            internal_links = self._extract_internal_links(page, url)

            # Image URLs (sampled)
            image_urls = self._extract_image_urls(page)

        except PWTimeout:
            error = f"Navigation timeout after {settings.DISCOVERY_PAGE_TIMEOUT_MS}ms"
            logger.warning("Timeout on %s", url)
        except Exception as exc:
            error = str(exc)
            logger.warning("Error visiting %s: %s", url, exc)
        finally:
            monitor.detach()
            events = monitor.get_events()
            try:
                page.close()
            except Exception:
                pass

        page_type = classify_page(url, title)

        return DiscoveredPage(
            url=url,
            canonical_url=canonical,
            title=title,
            page_type=page_type,
            depth=depth,
            http_status=http_status,
            internal_links=internal_links,
            image_urls=image_urls,
            network_events=events,
            error=error,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Extraction helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_canonical(self, page: Page) -> Optional[str]:
        """Extract the <link rel="canonical"> href if present."""
        try:
            el = page.locator('link[rel="canonical"]')
            if el.count():
                href = el.first.get_attribute("href")
                if href:
                    return normalize(href, page.url)
        except Exception:
            pass
        return None

    def _extract_internal_links(self, page: Page, page_url: str) -> List[str]:
        """
        Extract and normalize all internal <a href> links.
        Capped at DISCOVERY_MAX_LINKS_PER_PAGE.
        """
        raw_links: List[str] = []
        try:
            anchors = page.locator("a[href]").all()
            for anchor in anchors[:self._max_links * 2]:  # over-fetch, filter below
                try:
                    href = anchor.get_attribute("href")
                    if href:
                        raw_links.append(href)
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Link extraction error on %s: %s", page_url, exc)

        normalized: List[str] = []
        for raw in raw_links:
            norm = normalize(raw, page_url)
            if norm and is_internal(norm):
                normalized.append(norm)

        return deduplicate(normalized)[: self._max_links]

    def _extract_image_urls(self, page: Page) -> List[str]:
        """Extract a sample of image src URLs for pattern analysis."""
        urls: List[str] = []
        try:
            imgs = page.locator("img[src]").all()
            for img in imgs[:MAX_IMAGES_PER_PAGE]:
                try:
                    src = img.get_attribute("src")
                    if src and src.startswith("http"):
                        urls.append(src)
                except Exception:
                    continue
        except Exception:
            pass
        return urls


# ──────────────────────────────────────────────────────────────────────────────
# Artifact persistence
# ──────────────────────────────────────────────────────────────────────────────

def save_discovery_result(result: DiscoveryResult, output_dir: str = "") -> Path:
    """
    Persist the DiscoveryResult as JSON to the output directory.

    Returns the path of the written file.
    """
    out = Path(output_dir or settings.DISCOVERY_OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = out / f"discovery_{ts}.json"

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info("Discovery result saved to %s", file_path)
    return file_path


def persist_discovery_to_db(result: DiscoveryResult) -> int:
    """
    Persist discovered pages from a DiscoveryResult to the database.
    Does not modify or break the file-based artifact workflow.
    Returns the count of pages persisted/updated.
    """
    from app.database.connection import get_session, init_db
    from app.database.repositories import PagesRepository, ScrapeRunsRepository

    init_db()
    with get_session() as session:
        pages_repo = PagesRepository(session)
        runs_repo = ScrapeRunsRepository(session)

        count = 0
        for p in result.pages:
            pages_repo.upsert(
                url=p.url,
                canonical_url=p.canonical_url or p.url,
                page_type=p.page_type.value,
                title=p.title,
                http_status=p.http_status,
                metadata_json={
                    "depth": p.depth,
                    "links_count": len(p.internal_links),
                    "network_events_count": len(p.network_events),
                },
            )
            count += 1

        run = runs_repo.create_run(
            run_type="discovery",
            metadata_json={"seed_url": result.base_url},
        )
        runs_repo.finish_run(
            run_id=run.id,
            status="success" if not result.terminated_early else "partial",
            pages_discovered=len(result.pages),
            records_processed=count,
            records_created=count,
        )

    logger.info("Persisted %d discovered pages to database.", count)
    return count


# Backward-compatibility alias
FanCodeDiscoveryCrawler = FanCodeCrawler

