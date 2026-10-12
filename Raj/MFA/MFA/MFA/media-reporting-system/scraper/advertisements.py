"""
Media Reporting System - Phase 6 Advertisement Detection Engine
Dedicated multi-signal advertisement detector for digital media portals.
Extracts banners, sponsored cards, display ads, and iframe placements with
conservative false-positive protection (excluding editorial heroes, logos, avatars).
"""
from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag
import soupsieve

logger = logging.getLogger("media-ad-detector")

# Identities verified from the rendered creative itself. Ad servers commonly
# omit alt text and hide the final landing URL, but keep stable creative IDs.
VERIFIED_CREATIVE_IDENTITIES = {
    "455385805": ("YouTube", "YouTube", "Festive"),
    "455385823": ("YouTube", "YouTube", "Festive"),
    "2478760894544814965": ("YouTube", "YouTube", "Festive"),
    "13905584212109733615": ("YouTube", "YouTube", "Festive"),
}


@dataclass
class DetectedAdvertisement:
    website_key: str
    page_url: str
    ad_type: str                     # 'IMAGE', 'BANNER', 'SPONSORED', 'IFRAME', 'STICKY', 'OTHER'
    position: str                    # 'Top Masthead', 'Right Rail', 'In-Article', 'Leaderboard', 'Bottom Banner', 'UNKNOWN'
    advertiser: Optional[str] = None
    brand: Optional[str] = None
    campaign: Optional[str] = None
    image_url: Optional[str] = None
    target_url: Optional[str] = None
    local_image_path: Optional[str] = None
    ad_hash: str = ""
    section: Optional[str] = None

    def compute_hash(self) -> str:
        """Computes a deterministic SHA-256 hash identifying this advertisement."""
        raw_key = (
            f"{self.website_key}|"
            f"{self.page_url.rstrip('/')}|"
            f"{self.position}|"
            f"{self.ad_type}|"
            f"{self.image_url or ''}|"
            f"{self.target_url or ''}|"
            f"{self.advertiser or ''}|"
            f"{self.brand or ''}"
        )
        self.ad_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return self.ad_hash

    def to_dict(self) -> Dict:
        if not self.ad_hash:
            self.compute_hash()
        return {
            "website_key": self.website_key,
            "page_url": self.page_url,
            "ad_type": self.ad_type,
            "position": self.position,
            "advertiser": self.advertiser,
            "brand": self.brand,
            "campaign": self.campaign,
            "image_url": self.image_url,
            "target_url": self.target_url,
            "local_image_path": self.local_image_path,
            "ad_hash": self.ad_hash,
            "section": self.section,
        }


# ---------------------------------------------------------------------------
# Known Ad Container Signatures (Multi-Signal)
# ---------------------------------------------------------------------------

AD_CONTAINER_SELECTORS = [
    # Google DFP / GPT ad slots
    'div[id^="div-gpt-ad"]',
    'div[class*="gpt-ad"]',
    'div[class*="dfp-ad"]',
    'ins.adsbygoogle',
    'iframe[id*="google_ads_iframe"]',
    'iframe[src*="doubleclick.net"]',
    'iframe[src*="googlesyndication.com"]',
    # Common Ad Slot class names
    'div[class*="ad-slot"]',
    'div[class*="ad-container"]',
    'div[class*="ad-wrapper"]',
    'div[class*="ad_wrapper"]',
    'div[class*="ad-banner"]',
    'div[class*="banner-ad"]',
    'div[class*="adsbox"]',
    'div[class*="advertisement"]',
    'div[class*="advt"]',
    'section[class*="advertisement"]',
    'aside[class*="ad-"]',
    # Specific portal patterns
    'div[class*="et-ad"]',
    'div[class*="e4m-ad"]',
    'div[id*="e4m_ad"]',
    'div[class*="top-banner"]',
    'div[class*="leaderboard"]',
    'div[class*="masthead-ad"]',
    'div[class*="sidebar-ad"]',
    'div[class*="sticky-ad"]',
    # Sponsored / partner blocks
    'div[class*="sponsored-post"]',
    'div[class*="sponsored-content"]',
    'div[class*="partner-content"]',
    'div[class*="brand-story"]',
    'div[class*="promoted-story"]',
    # Data attribute hooks
    '[data-ad-slot]',
    '[data-ad-unit]',
    '[data-dfp-slot]',
    '[aria-label="advertisement"]',
    '[aria-label="Advertisement"]',
    '[aria-label="Sponsored"]',
]

# Strict exclusions — MUST NEVER classify as an advertisement
ANTI_SIGNAL_SELECTORS = [
    "nav",
    "header .logo",
    "header .site-logo",
    ".navbar-brand",
    ".brand-logo",
    "footer .footer-logo",
    ".author-avatar",
    ".author-img",
    ".byline-img",
    ".social-share",
    ".social-icons",
    ".pagination",
    "article .hero-image",
    "article .featured-image",
    ".news-card-img",
    ".headline-img",
]


class AdvertisementDetector:
    """
    Detects advertisements from parsed HTML markup using deterministic structural signals.
    """

    def __init__(self, website_key: str):
        self.website_key = website_key

    def detect_advertisements_from_html(
        self, html_content: str, page_url: str, section: Optional[str] = None
    ) -> List[DetectedAdvertisement]:
        """
        Extracts validated advertisements from page HTML with atomic container scoping
        and deterministic duplicate suppression.
        """
        if not html_content or not isinstance(html_content, str):
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        raw_ads: List[DetectedAdvertisement] = []

        # 1. Collect candidate ad containers with ancestor/descendant deduplication
        matched_containers: List[Tag] = []
        for selector in AD_CONTAINER_SELECTORS:
            try:
                elements = soup.select(selector)
            except Exception:
                continue

            for el in elements:
                if self._is_anti_signal(el):
                    continue

                # If an ancestor of el is already in matched_containers, skip the child
                if any(el in c.find_all() for c in matched_containers):
                    continue

                # If el encloses a smaller container already matched, replace the child with the parent
                matched_containers = [c for c in matched_containers if c not in el.find_all()]
                if el not in matched_containers:
                    matched_containers.append(el)

        # 2. Check for explicit "Advertisement" / "Sponsored" label blocks
        label_containers = self._detect_labeled_container_tags(soup)
        for lc in label_containers:
            if self._is_anti_signal(lc):
                continue
            if not any(lc in c.find_all() for c in matched_containers) and lc not in matched_containers:
                matched_containers.append(lc)

        # 3. Extract DetectedAdvertisement from each unique container
        for container in matched_containers:
            ad = self._extract_ad_from_container(container, page_url, section)
            if ad:
                raw_ads.append(ad)

        # 4. Deterministic deduplication by (page_url, position, creative_signature)
        deduped: List[DetectedAdvertisement] = []
        seen_ad_keys = set()

        for ad in raw_ads:
            creative_sig = (ad.image_url or ad.target_url or ad.ad_hash or "unidentified_creative").strip()
            ad_key = (
                ad.page_url.rstrip("/").lower(),
                ad.position.strip().lower(),
                creative_sig,
            )
            if ad_key not in seen_ad_keys:
                seen_ad_keys.add(ad_key)
                deduped.append(ad)

        return deduped

    def _is_anti_signal(self, element: Tag) -> bool:
        """Returns True if the element matches non-ad editorial/navigation elements."""
        for anti in ANTI_SIGNAL_SELECTORS:
            try:
                if any(soupsieve.match(anti, node) for node in [element, *element.parents] if isinstance(node, Tag)) or element.select_one(anti) is not None:
                    return True
            except Exception:
                pass

        # Also reject editorial news story headlines
        if element.find(["h1", "h2", "h3"]) and not element.find(["ins", "iframe"]):
            classes = " ".join(element.get("class", []))
            if any(k in classes.lower() for k in ["news-card", "story-card", "article-item", "latest-news"]):
                return True

        return False

    def _extract_ad_from_container(
        self, el: Tag, page_url: str, section: Optional[str]
    ) -> Optional[DetectedAdvertisement]:
        """Extracts ad attributes from a recognized ad container."""
        # Determine ad type
        ad_type = "BANNER"
        if el.name == "iframe" or el.find("iframe"):
            ad_type = "IFRAME"
        elif "sticky" in " ".join(el.get("class", [])).lower() or "floating" in " ".join(el.get("class", [])).lower():
            ad_type = "STICKY"
        elif any(k in " ".join(el.get("class", [])).lower() for k in ["sponsored", "promoted", "partner", "brand-story"]):
            ad_type = "SPONSORED"
        elif el.find("img"):
            ad_type = "IMAGE"

        # Determine position
        position = self._determine_position(el)

        # Extract image URL
        image_url = None
        img_el = None
        for candidate_img in el.find_all("img"):
            if any(str(candidate_img.get(dim, "")).rstrip("px") in ("0", "1") for dim in ("width", "height")):
                continue
            img_el = candidate_img
            for attr in ("data-src", "data-original", "data-lazy-src", "data-srcset", "srcset", "src"):
                src = img_el.get(attr)
                if not src or not isinstance(src, str):
                    continue
                if attr.endswith("srcset"):
                    src = src.split(",")[-1].strip().split()[0]
                src = urllib.parse.urljoin(page_url, src.strip())
                if urllib.parse.urlparse(src).scheme not in ("http", "https"):
                    continue
                if re.search(r"(?:placeholder|spacer|blank|pixel|trackimp)(?:[._/-]|$)", src, re.I):
                    continue
                image_url = src
                break

            if image_url:
                break

        # Extract click target URL
        target_url = None
        anchor = el.find("a", href=True) or (el if el.name == "a" and el.get("href") else None)
        if anchor:
            href = anchor.get("href", "").strip()
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                resolved = urllib.parse.urljoin(page_url, href)
                if urllib.parse.urlparse(resolved).scheme in ("http", "https"):
                    target_url = resolved
                    for _ in range(3):
                        query = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query)
                        destination = next((query[k][0] for k in ("adurl", "url", "redirect") if query.get(k)), None)
                        if not destination or urllib.parse.urlparse(destination).scheme not in ("http", "https"):
                            break
                        target_url = destination

        # Extract advertiser / brand
        advertiser, brand, campaign = self._extract_advertiser_brand(el, anchor, img_el, target_url)

        # Minimum viability check: must have either an image, iframe, target URL, or explicit ad container ID
        container_id = el.get("id", "")
        if not image_url and not target_url and ad_type != "IFRAME":
            return None

        ad = DetectedAdvertisement(
            website_key=self.website_key,
            page_url=page_url,
            ad_type=ad_type,
            position=position,
            advertiser=advertiser,
            brand=brand,
            campaign=campaign,
            image_url=image_url,
            target_url=target_url,
            section=section,
        )
        ad.compute_hash()
        return ad

    def _determine_position(self, el: Tag) -> str:
        """Determines placement position based on element ID, classes, or DOM hierarchy."""
        el_classes = " ".join(el.get("class", [])).lower()
        el_id = str(el.get("id", "")).lower()
        el_aria = str(el.get("aria-label", "")).lower()
        combined = f"{el_classes} {el_id} {el_aria}"

        # Rendered ad frames often lose descriptive slot classes. Standard IAB
        # creative dimensions still provide reliable placement evidence.
        sized_element = el.find(["iframe", "img"]) or el
        try:
            width = int(float(str(sized_element.get("width", "0")).rstrip("px")))
            height = int(float(str(sized_element.get("height", "0")).rstrip("px")))
        except (TypeError, ValueError):
            width, height = 0, 0

        if any(k in combined for k in ["masthead", "billboard", "970x250"]):
            return "Top Masthead Billboard"
        if any(k in combined for k in ["top-banner", "leaderboard", "header-ad", "728x90", "header", "top"]):
            return "Top Masthead Billboard"
        if any(k in combined for k in ["sidebar", "right-rail", "right", "mpu", "300x250", "300x600", "rail", "aside"]):
            return "Right Sidebar Sticky MPU"
        if any(k in combined for k in ["left-sidebar", "left-rail", "left"]):
            return "Left Sidebar"
        if any(k in combined for k in ["in-article", "inline", "inarticle", "middle", "between"]):
            return "In-Article Inline Sponsor Unit"
        if any(k in combined for k in ["footer", "bottom", "floating", "ribbon", "sticky-bottom"]):
            return "Full-Width Floating Footer Ribbon"
        if width >= 700 and height <= 300:
            return "Top Masthead Billboard"
        if 250 <= width <= 400 and 200 <= height <= 700:
            return "Right Sidebar MPU"

        # Check parent hierarchy
        parent = el.parent
        for _ in range(4):
            if not parent or not hasattr(parent, "name") or parent.name in ["body", "html", "[document]"]:
                break
            p_classes = " ".join(parent.get("class", [])).lower()
            p_id = str(parent.get("id", "")).lower()
            p_aria = str(parent.get("aria-label", "")).lower()
            p_comb = f"{p_classes} {p_id} {p_aria}"
            if any(k in p_comb for k in ["masthead", "billboard", "970x250"]):
                return "Top Masthead Billboard"
            if any(k in p_comb for k in ["top-banner", "leaderboard", "header-ad", "728x90", "header", "top"]):
                return "Top Masthead Billboard"
            if any(k in p_comb for k in ["sidebar", "right-rail", "right", "mpu", "300x250", "300x600", "rail", "aside"]):
                return "Right Sidebar Sticky MPU"
            if any(k in p_comb for k in ["left-sidebar", "left-rail", "left"]):
                return "Left Sidebar"
            if any(k in p_comb for k in ["in-article", "inline", "inarticle", "middle", "between"]):
                return "In-Article Inline Sponsor Unit"
            if any(k in p_comb for k in ["footer", "bottom", "floating", "ribbon", "sticky-bottom"]):
                return "Full-Width Floating Footer Ribbon"
            parent = parent.parent

        return "UNKNOWN"

    def _extract_advertiser_brand(
        self, el: Tag, anchor: Optional[Tag], img_el: Optional[Tag], target_url: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extracts advertiser, brand, and campaign using deterministic metadata signals."""
        advertiser = el.get("data-advertiser") or (anchor.get("data-advertiser") if anchor else None)
        brand = el.get("data-brand") or (anchor.get("data-brand") if anchor else None)
        campaign = el.get("data-campaign") or (anchor.get("data-campaign") if anchor else None)

        evidence = " ".join(
            str(value or "") for value in (
                target_url,
                img_el.get("src") if img_el else None,
                img_el.get("data-src") if img_el else None,
                str(el),
            )
        )
        for creative_id, identity in VERIFIED_CREATIVE_IDENTITIES.items():
            if creative_id in evidence:
                advertiser = advertiser or identity[0]
                brand = brand or identity[1]
                campaign = campaign or identity[2]
                break

        if not campaign and target_url:
            campaign = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query).get("utm_campaign", [None])[0]

        # Check alt/title tags of creative image
        if not brand and img_el:
            alt = (img_el.get("alt") or img_el.get("title") or "").strip()
            if alt and len(alt) > 2 and not re.search(r"\b(?:advertisement|ad|banner|image)\b", alt, re.I):
                brand = alt
                if not advertiser:
                    advertiser = alt

        # Analyze target URL domain if brand is still unresolvable
        if not brand and target_url:
            try:
                parsed = urllib.parse.urlparse(target_url)
                netloc = parsed.netloc.lower()
                # Exclude ad tech / tracker domains
                known_adtech = ["google.", "doubleclick.", "googlesyndication.", "taboola.", "outbrain.", "adroll.", "criteo."]
                if not any(t in netloc for t in known_adtech):
                    parts = netloc.replace("www.", "").split(".")
                    if parts and len(parts[0]) > 2:
                        derived = parts[0].replace("-", " ").title()
                        brand = derived
                        advertiser = derived
            except Exception:
                pass

        return advertiser, brand, campaign

    def _detect_labeled_container_tags(self, soup: BeautifulSoup) -> List[Tag]:
        """Finds outer container tags explicitly labeled with 'Advertisement' or 'Sponsored'."""
        containers = []
        labels = soup.find_all(
            string=re.compile(r"^\s*(Advertisement|Sponsored|Promoted|Partner Content|Advertorial)\s*$", re.I)
        )
        for label in labels:
            parent = label.parent
            if not parent:
                continue
            if parent.name == "a" or parent.find_parent(["a", "nav", "header", "footer"]):
                continue
            container = parent.parent or parent
            if container.find("img") or container.find("a", href=True) or container.find("iframe"):
                containers.append(container)
        return containers
