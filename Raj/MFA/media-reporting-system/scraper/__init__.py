"""
Media Reporting System - Scraper Package
Houses the scraping pipeline for:
- Phase 2: ET BrandEquity (brandequity.economictimes.indiatimes.com)
- Phase 3: Exchange4media (exchange4media.com)
"""
from scraper.base.article import Article
from scraper.base.fetcher import PageFetcher
from scraper.et_brand_equity import ETBrandEquityScraper, ET_BRAND_EQUITY
from scraper.exchange4media import Exchange4mediaScraper, EXCHANGE4MEDIA
from scraper.campaign_india import CampaignIndiaScraper, CAMPAIGN_INDIA
from scraper.bestmediainfo import BestMediaInfoScraper, BESTMEDIAINFO
from scraper.social_samosa import SocialSamosaScraper, SOCIAL_SAMOSA
from scraper.adgully import AdgullyScraper, ADGULLY
from scraper.mediabrief import MediaBriefScraper, MEDIABRIEF
from scraper.storyboard18 import Storyboard18Scraper, STORYBOARD18
from scraper.indiantelevision import IndianTelevisionScraper, INDIAN_TELEVISION

__all__ = [
    "Article",
    "PageFetcher",
    "ETBrandEquityScraper",
    "ET_BRAND_EQUITY",
    "Exchange4mediaScraper",
    "EXCHANGE4MEDIA",
    "CampaignIndiaScraper",
    "CAMPAIGN_INDIA",
    "BestMediaInfoScraper",
    "BESTMEDIAINFO",
    "SocialSamosaScraper",
    "SOCIAL_SAMOSA",
    "AdgullyScraper",
    "ADGULLY",
    "MediaBriefScraper",
    "MEDIABRIEF",
    "Storyboard18Scraper",
    "STORYBOARD18",
    "IndianTelevisionScraper",
    "INDIAN_TELEVISION",
]

