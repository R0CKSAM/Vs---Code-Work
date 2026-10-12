"""
Media Reporting System - Mailer Data Models
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParsedArticle:
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    order: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedAdvertisement:
    advertiser: Optional[str] = None
    title: Optional[str] = None
    image_url: Optional[str] = None
    target_url: Optional[str] = None
    order: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedMailer:
    source_name: str
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    email_subject: Optional[str] = None
    received_datetime: Optional[str] = None
    newsletter_heading: Optional[str] = None
    articles: List[ParsedArticle] = field(default_factory=list)
    advertisements: List[ParsedAdvertisement] = field(default_factory=list)
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "sender_name": self.sender_name,
            "sender_email": self.sender_email,
            "email_subject": self.email_subject,
            "received_datetime": self.received_datetime,
            "newsletter_heading": self.newsletter_heading,
            "content_hash": self.content_hash,
            "articles": [a.to_dict() for a in self.articles],
            "advertisements": [ad.to_dict() for ad in self.advertisements],
            "article_count": len(self.articles),
            "advertisement_count": len(self.advertisements),
        }
