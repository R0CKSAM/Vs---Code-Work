"""
models.py – SQLAlchemy 2.x ORM models for FanCode Monitor Phase 2.

Entities:
- Sport: Top-level sports (Cricket, Football, Kabaddi, etc.)
- Tour: Series, tournaments, or tours belonging to a sport
- Match: Individual matches/fixtures belonging to a tour and sport
- Video: Highlights, replays, or clips associated with sports/tours/matches
- Page: Discovered FanCode URLs with metadata and canonical identity
- ChangeEvent: Log of detected entity changes (foundation for Phase 8)
- ScrapeRun: Audit log of discovery/scraper runs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.connection import Base, utc_now


class Sport(Base):
    """Sports category (e.g. Cricket, Football)."""
    __tablename__ = "sports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    tours: Mapped[List["Tour"]] = relationship("Tour", back_populates="sport", cascade="all, delete-orphan")
    matches: Mapped[List["Match"]] = relationship("Match", back_populates="sport")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="sport")


class Tour(Base):
    """Tournament / Tour / Series entity."""
    __tablename__ = "tours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    sport_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sports.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    sport: Mapped[Optional["Sport"]] = relationship("Sport", back_populates="tours")
    matches: Mapped[List["Match"]] = relationship("Match", back_populates="tour", cascade="all, delete-orphan")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="tour")


class Match(Base):
    """Match / fixture entity."""
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    tour_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tours.id", ondelete="SET NULL"), nullable=True, index=True)
    sport_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sports.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    match_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    start_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    venue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    team_a_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    team_a_external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    team_b_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    team_b_external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    team_a_logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    team_b_logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    score_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    tour: Mapped[Optional["Tour"]] = relationship("Tour", back_populates="matches")
    sport: Mapped[Optional["Sport"]] = relationship("Sport", back_populates="matches")
    videos: Mapped[List["Video"]] = relationship("Video", back_populates="match")


class Video(Base):
    """Video content (highlights, replays, live streams)."""
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sport_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sports.id", ondelete="SET NULL"), nullable=True, index=True)
    tour_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tours.id", ondelete="SET NULL"), nullable=True, index=True)
    match_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True)

    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    video_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    sport: Mapped[Optional["Sport"]] = relationship("Sport", back_populates="videos")
    tour: Mapped[Optional["Tour"]] = relationship("Tour", back_populates="videos")
    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="videos")


class Page(Base):
    """Discovered FanCode page records."""
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True, index=True)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN", index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_json: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ChangeEvent(Base):
    """Audit log of detected entity changes (foundation for Phase 8)."""
    __tablename__ = "change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. "match", "tour"
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "NEW", "UPDATED", "STATUS_CHANGED", "REMOVED"
    field_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), default="INFO", nullable=True)  # "INFO", "IMPORTANT", "CRITICAL"
    scrape_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)



class ScrapeRun(Base):
    """Audit log of discovery and scraping operations."""
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "discovery", "schedule", etc.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False, index=True)  # "running", "success", "failed"

    pages_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class NotificationBatch(Base):
    """Audit log of notification batch / digest creation and delivery."""
    __tablename__ = "notification_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, SENT, FAILED, DRY_RUN
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    deliveries: Mapped[List["NotificationDelivery"]] = relationship("NotificationDelivery", back_populates="batch", cascade="all, delete-orphan")
    event_links: Mapped[List["NotificationEventLink"]] = relationship("NotificationEventLink", back_populates="batch", cascade="all, delete-orphan")


class NotificationDelivery(Base):
    """Individual recipient delivery attempt and audit record."""
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("notification_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, SENT, FAILED, SKIPPED
    provider: Mapped[str] = mapped_column(String(50), default="console", nullable=False)  # console, test, smtp
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    batch: Mapped["NotificationBatch"] = relationship("NotificationBatch", back_populates="deliveries")


class NotificationEventLink(Base):
    """Association linking notification batches to specific ChangeEvent records."""
    __tablename__ = "notification_event_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("notification_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    change_event_id: Mapped[int] = mapped_column(Integer, ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    batch: Mapped["NotificationBatch"] = relationship("NotificationBatch", back_populates="event_links")
    change_event: Mapped["ChangeEvent"] = relationship("ChangeEvent")

