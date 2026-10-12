"""
app/scraper/sports package
Phase 4: FanCode Sports Scraper
"""

from app.scraper.sports.models import SportRecord
from app.scraper.sports.scraper import FanCodeSportsScraper

__all__ = [
    "FanCodeSportsScraper",
    "SportRecord",
]
