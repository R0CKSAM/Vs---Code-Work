"""
Media Reporting System - Mailer Intelligence Engine
Processes HTML email newsletters into structured editorial and advertisement intelligence.
"""
from mailer.models import ParsedArticle, ParsedAdvertisement, ParsedMailer
from mailer.base_parser import MailerParser
from mailer.best_media_info_parser import BestMediaInfoParser
from mailer.gmail_fetcher import GmailMailerFetcher, gmail_fetcher
from mailer.service import mailer_service

__all__ = [
    "ParsedArticle",
    "ParsedAdvertisement",
    "ParsedMailer",
    "MailerParser",
    "BestMediaInfoParser",
    "GmailMailerFetcher",
    "gmail_fetcher",
    "mailer_service",
]
