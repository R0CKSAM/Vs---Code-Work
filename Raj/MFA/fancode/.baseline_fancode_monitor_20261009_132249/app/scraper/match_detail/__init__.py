"""
app/scraper/match_detail package
Phase 5: Match Detail Scraper & Enrichment
"""

from app.scraper.match_detail.models import MatchDetail, RawMatchDetail
from app.scraper.match_detail.scraper import FanCodeMatchDetailScraper

__all__ = [
    "FanCodeMatchDetailScraper",
    "MatchDetail",
    "RawMatchDetail",
]
