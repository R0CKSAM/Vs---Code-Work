"""
Media Reporting System - Database Schema DDL & Migrations
Defines ANSI SQL compatible schemas for SQLite & future PostgreSQL migration.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from database.connection import get_db

SCHEMA_SQL = """
-- 1. Websites table
CREATE TABLE IF NOT EXISTS websites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    website_key TEXT UNIQUE NOT NULL,
    base_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Sections table
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT uq_sections_website_name UNIQUE (website_id, name)
);

-- 3. Articles table (Current state)
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    headline TEXT NOT NULL,
    url TEXT NOT NULL,
    image_url TEXT,
    summary TEXT,
    published_at TEXT,
    publication_label TEXT,
    is_exclusive INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    removed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT uq_articles_website_url UNIQUE (website_id, url)
);

-- Indexes for articles
CREATE INDEX IF NOT EXISTS idx_articles_website_url ON articles(website_id, url);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_content_hash ON articles(content_hash);
CREATE INDEX IF NOT EXISTS idx_articles_last_seen_at ON articles(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_articles_last_changed_at ON articles(last_changed_at);

-- 4. Article Versions table (Historical snapshots)
CREATE TABLE IF NOT EXISTS article_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    headline TEXT NOT NULL,
    url TEXT NOT NULL,
    image_url TEXT,
    summary TEXT,
    section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    published_at TEXT,
    content_hash TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    change_type TEXT NOT NULL,
    CONSTRAINT chk_version_change_type CHECK (change_type IN ('NEW', 'UPDATED', 'UNCHANGED'))
);

-- Indexes for article_versions
CREATE INDEX IF NOT EXISTS idx_versions_article_id ON article_versions(article_id);
CREATE INDEX IF NOT EXISTS idx_versions_detected_at ON article_versions(detected_at);
CREATE INDEX IF NOT EXISTS idx_versions_change_type ON article_versions(change_type);

-- 5. Scrape Runs table (Audit logs)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    items_found INTEGER DEFAULT 0,
    new_items INTEGER DEFAULT 0,
    updated_items INTEGER DEFAULT 0,
    unchanged_items INTEGER DEFAULT 0,
    removed_items INTEGER DEFAULT 0,
    error_message TEXT,
    CONSTRAINT chk_scrape_run_status CHECK (status IN ('RUNNING', 'SUCCESS', 'COMPLETED', 'FAILED'))
);

-- Indexes for scrape_runs
CREATE INDEX IF NOT EXISTS idx_scrape_runs_website_id ON scrape_runs(website_id);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_started_at ON scrape_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_status ON scrape_runs(status);

-- 6. Advertisements table (Current state)
CREATE TABLE IF NOT EXISTS advertisements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    page_url TEXT NOT NULL,
    advertiser TEXT,
    brand TEXT,
    campaign TEXT,
    ad_type TEXT NOT NULL DEFAULT 'BANNER',
    position TEXT NOT NULL DEFAULT 'UNKNOWN',
    image_url TEXT,
    local_image_path TEXT,
    target_url TEXT,
    ad_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    removed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT uq_ads_website_ad_hash UNIQUE (website_id, ad_hash),
    CONSTRAINT chk_ad_status CHECK (status IN ('ACTIVE', 'REMOVED', 'CHANGED'))
);

-- Indexes for advertisements
CREATE INDEX IF NOT EXISTS idx_ads_website_id ON advertisements(website_id);
CREATE INDEX IF NOT EXISTS idx_ads_status ON advertisements(status);
CREATE INDEX IF NOT EXISTS idx_ads_ad_hash ON advertisements(ad_hash);
CREATE INDEX IF NOT EXISTS idx_ads_advertiser ON advertisements(advertiser);
CREATE INDEX IF NOT EXISTS idx_ads_brand ON advertisements(brand);
CREATE INDEX IF NOT EXISTS idx_ads_first_seen_at ON advertisements(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_ads_last_seen_at ON advertisements(last_seen_at);

-- 7. Advertisement Versions table (Historical snapshots)
CREATE TABLE IF NOT EXISTS advertisement_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advertisement_id INTEGER NOT NULL REFERENCES advertisements(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    advertiser TEXT,
    brand TEXT,
    campaign TEXT,
    ad_type TEXT NOT NULL DEFAULT 'BANNER',
    position TEXT NOT NULL DEFAULT 'UNKNOWN',
    image_url TEXT,
    local_image_path TEXT,
    target_url TEXT,
    ad_hash TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    change_type TEXT NOT NULL DEFAULT 'NEW',
    CONSTRAINT chk_ad_version_change_type CHECK (change_type IN ('NEW', 'CHANGED', 'REMOVED', 'UNCHANGED'))
);

-- Indexes for advertisement_versions
CREATE INDEX IF NOT EXISTS idx_ad_versions_advertisement_id ON advertisement_versions(advertisement_id);
CREATE INDEX IF NOT EXISTS idx_ad_versions_detected_at ON advertisement_versions(detected_at);
CREATE INDEX IF NOT EXISTS idx_ad_versions_change_type ON advertisement_versions(change_type);

-- 8. Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'USER',
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    CONSTRAINT chk_user_role CHECK (role IN ('ADMIN', 'USER')),
    CONSTRAINT chk_user_status CHECK (status IN ('PENDING', 'APPROVED', 'SUSPENDED'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_admin ON users(role) WHERE role = 'ADMIN';

-- 9. User Sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON user_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON user_sessions(expires_at);

-- 10. User Permissions table
CREATE TABLE IF NOT EXISTS user_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_user_permission UNIQUE (user_id, permission_key)
);

CREATE INDEX IF NOT EXISTS idx_permissions_user_id ON user_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_permissions_key ON user_permissions(permission_key);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Initializes the database schema and ensures all tables and indexes exist."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        if "publication_label" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN publication_label TEXT")
        if "is_exclusive" not in columns:
            conn.execute("ALTER TABLE articles ADD COLUMN is_exclusive INTEGER NOT NULL DEFAULT 0")

        user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "full_name" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")


# Alias for backwards and test compatibility
init_schema = init_db


def reset_db(db_path: Optional[Path] = None) -> None:
    """
    Development reset utility. Drops all existing tables and recreates the schema.
    """
    drop_sql = """
    DROP TABLE IF EXISTS user_permissions;
    DROP TABLE IF EXISTS user_sessions;
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS advertisement_versions;
    DROP TABLE IF EXISTS advertisements;
    DROP TABLE IF EXISTS article_versions;
    DROP TABLE IF EXISTS articles;
    DROP TABLE IF EXISTS sections;
    DROP TABLE IF EXISTS scrape_runs;
    DROP TABLE IF EXISTS websites;
    """
    with get_db(db_path) as conn:
        conn.executescript(drop_sql)
        conn.executescript(SCHEMA_SQL)
