"""Collect visible ad creatives, including JavaScript-loaded iframe contents.

A single browser visit is an observation, not proof that unseen ads were removed.
"""
import logging

from bs4 import BeautifulSoup

from scraper.advertisements import AdvertisementDetector
from scraper.base.fetcher import PageFetcher
from scraper.ad_image_storage import save_ad_screenshot

logger = logging.getLogger("media-ad-collector")


def collect_advertisements(website_key, page_url):
    fetcher = PageFetcher()
    html = fetcher.fetch(page_url)
    detector = AdvertisementDetector(website_key)
    ads = detector.detect_advertisements_from_html(html or "", page_url)
    try:
        from playwright.sync_api import sync_playwright
        if not fetcher.can_fetch(page_url):
            return ads
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=fetcher.user_agent, viewport={"width": 1440, "height": 1000})
                page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                for _ in range(3):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(500)
                ads.extend(detector.detect_advertisements_from_html(page.content(), page_url))
                for frame in page.frames[1:]:
                    try:
                        root_frame = frame
                        while root_frame.parent_frame and root_frame.parent_frame != page.main_frame:
                            root_frame = root_frame.parent_frame
                        element = root_frame.frame_element()
                        outer = BeautifulSoup(element.evaluate("el => el.outerHTML"), "html.parser")
                        iframe = outer.find("iframe")
                        if not iframe or not ("google_ads" in str(iframe) or "doubleclick" in str(iframe) or "ad" in (iframe.get("id") or "").lower()):
                            continue
                        markup = BeautifulSoup(frame.content(), "html.parser")
                        for node in markup.select("img[src], img[data-src], a[href]"):
                            from urllib.parse import urljoin
                            for attr in ("src", "data-src", "href"):
                                if node.get(attr):
                                    node[attr] = urljoin(frame.url, node[attr])
                        iframe.name = "div"
                        iframe["class"] = ["ad-container"]
                        iframe.append(markup)
                        frame_ads = detector.detect_advertisements_from_html(str(iframe), page_url)
                        for ad in frame_ads:
                            if not ad.image_url and ad.target_url and element.is_visible():
                                bounds = element.bounding_box()
                                if bounds and bounds["width"] >= 80 and bounds["height"] >= 40:
                                    ad.local_image_path = save_ad_screenshot(
                                        element.screenshot(timeout=3000), website_key, ad.ad_hash)
                        ads.extend(frame_ads)
                    except Exception as exc:
                        logger.debug("Ad frame unavailable: %s", exc)
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("Browser ad collection unavailable; keeping HTML observations: %s", exc)
    # Empty slots, opaque frames, and creatives without verifiable identity are
    # retained in page evidence but are not promoted to monitored ad records.
    unique = {}
    for ad in ads:
        if (ad.image_url or ad.target_url) and (ad.brand or ad.advertiser):
            key = (ad.position, ad.image_url or ad.target_url)
            existing = unique.get(key)
            if existing is None or (ad.local_image_path and not existing.local_image_path):
                unique[key] = ad
    return list(unique.values())
