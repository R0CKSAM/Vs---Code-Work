"""
Media Reporting System - Storyboard18 Scraper Package
"""
from .config import STORYBOARD18, STORYBOARD18_SECTION_SLUG_MAP, WebsiteConfig
from .scraper import Storyboard18Scraper

__all__ = ["Storyboard18Scraper", "STORYBOARD18", "STORYBOARD18_SECTION_SLUG_MAP", "WebsiteConfig"]
