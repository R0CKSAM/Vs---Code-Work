"""
app/scraper/tours package
Phase 4: FanCode Tours Scraper
"""

from app.scraper.tours.models import TourRecord
from app.scraper.tours.scraper import FanCodeToursScraper

__all__ = [
    "FanCodeToursScraper",
    "TourRecord",
]
