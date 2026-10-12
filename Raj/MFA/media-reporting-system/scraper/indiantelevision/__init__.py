"""
Media Reporting System - Indian Television Scraper Package
"""
from .config import INDIAN_TELEVISION, INDIAN_TELEVISION_SECTION_SLUG_MAP, WebsiteConfig
from .scraper import IndianTelevisionScraper

__all__ = ["IndianTelevisionScraper", "INDIAN_TELEVISION", "INDIAN_TELEVISION_SECTION_SLUG_MAP", "WebsiteConfig"]
