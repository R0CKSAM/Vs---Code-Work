# Media Reporting System - Local Storage Engine

This directory provides localized binary and media asset persistence for tracked publications.

## Phase 0 Status

> **IMPORTANT**: In **Phase 0 — Foundation**, NO file saving or media downloading logic is active. The subdirectories exist as designated locations for future asset ingestion.

---

## Planned Storage Structure

- `screenshots/`: Full-page and above-the-fold viewport captures of monitored websites captured during crawl cycles (using Playwright).
- `advertisements/`: Isolated banner advertisements, video frame grabs, and masthead creatives stored for verification and historical comparison.
- `article_images/`: Editorial thumbnail images extracted from news stories.

All storage in future phases will use local relative file paths with support for open-source S3-compatible object storage (e.g. MinIO) when scaling.
