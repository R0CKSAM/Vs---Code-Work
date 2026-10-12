"""
Media Reporting System - Adgully Scraper Package
"""
from .config import ADGULLY, ADGULLY_SECTION_SLUG_MAP, WebsiteConfig
from .scraper import AdgullyScraper

__all__ = ["AdgullyScraper", "ADGULLY", "ADGULLY_SECTION_SLUG_MAP", "WebsiteConfig"]
