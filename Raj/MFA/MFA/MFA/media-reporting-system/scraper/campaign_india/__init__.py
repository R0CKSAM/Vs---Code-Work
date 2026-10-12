"""
Media Reporting System - Campaign India Scraper Package
"""
from .config import CAMPAIGN_INDIA, CAMPAIGN_INDIA_SECTION_SLUG_MAP, WebsiteConfig
from .scraper import CampaignIndiaScraper

__all__ = ["CampaignIndiaScraper", "CAMPAIGN_INDIA", "CAMPAIGN_INDIA_SECTION_SLUG_MAP", "WebsiteConfig"]
