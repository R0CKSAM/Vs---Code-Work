"""
Media Reporting System - Social Samosa Scraper Package
"""
from .config import SOCIAL_SAMOSA, SOCIAL_SAMOSA_SECTION_SLUG_MAP, WebsiteConfig
from .scraper import SocialSamosaScraper

__all__ = ["SocialSamosaScraper", "SOCIAL_SAMOSA", "SOCIAL_SAMOSA_SECTION_SLUG_MAP", "WebsiteConfig"]
