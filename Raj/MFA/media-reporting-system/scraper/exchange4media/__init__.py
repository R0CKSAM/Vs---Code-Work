"""
Exchange4media Scraper Package
"""
from scraper.exchange4media.config import E4M_SECTION_SLUG_MAP, EXCHANGE4MEDIA
from scraper.exchange4media.scraper import Exchange4mediaScraper

__all__ = ["Exchange4mediaScraper", "EXCHANGE4MEDIA", "E4M_SECTION_SLUG_MAP"]
