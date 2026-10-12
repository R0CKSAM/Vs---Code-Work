"""
Media Reporting System - Mailer Intelligence API Endpoints
Provides endpoints for listing, inspecting, uploading, and exporting newsletter intelligence.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from mailer.export import mailer_exporter
from mailer.gmail_fetcher import gmail_fetcher
from mailer.service import mailer_service
from backend.app.core.config import settings

logger = logging.getLogger("mailer-api")

router = APIRouter(prefix="/mailer", tags=["Mailer Intelligence"])


class RawHtmlRequest(BaseModel):
    html_content: str = Field(..., description="Raw HTML string of the newsletter")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional email metadata")


class GmailSyncRequest(BaseModel):
    app_password: Optional[str] = Field(default=None, description="Optional Gmail app password (uses server config if omitted)")
    email: Optional[str] = Field(default=None, description="Optional Gmail address")
    search_query: Optional[str] = Field(default=None, description="Custom IMAP search filter")
    max_emails: int = Field(default=25, ge=1, le=100, description="Max emails to check")


@router.get("/gmail-status", summary="Get Gmail configuration status")
async def get_gmail_status() -> Dict[str, Any]:
    configured = bool(settings.GMAIL_EMAIL and settings.GMAIL_APP_PASSWORD)
    return {
        "email": settings.GMAIL_EMAIL,
        "is_configured": configured,
        "imap_server": settings.GMAIL_IMAP_SERVER,
        "imap_port": settings.GMAIL_IMAP_PORT,
    }


@router.post("/sync-gmail", summary="Fetch newsletters directly from Gmail via IMAP")
async def sync_gmail(req: Optional[GmailSyncRequest] = None) -> Dict[str, Any]:
    email_addr = (req.email.strip() if req and req.email else settings.GMAIL_EMAIL) or "rajxy101@gmail.com"
    app_pwd = (req.app_password.strip() if req and req.app_password else settings.GMAIL_APP_PASSWORD)
    max_items = req.max_emails if req else 25
    query = req.search_query if req else None

    if not app_pwd:
        raise HTTPException(
            status_code=400,
            detail="Google App Password is required. Please provide it in the sync dialog or set GMAIL_APP_PASSWORD in your environment.",
        )

    fetcher = gmail_fetcher
    if email_addr != fetcher.email_address or app_pwd != fetcher.app_password:
        from mailer.gmail_fetcher import GmailMailerFetcher
        fetcher = GmailMailerFetcher(email_address=email_addr, app_password=app_pwd)

    try:
        result = fetcher.fetch_and_ingest(
            search_query=query,
            max_emails=max_items,
        )
        return result
    except Exception as exc:
        logger.error("Gmail sync failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/list", summary="List all processed newsletters with counts")
async def list_mailers(
    source: Optional[str] = Query(None, description="Filter by publisher/source name"),
    search: Optional[str] = Query(None, description="Search query across headings, articles, ads"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
) -> List[Dict[str, Any]]:
    return mailer_service.list_newsletters(
        source=source,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{mailer_id}", summary="Get detailed newsletter intelligence")
async def get_mailer_detail(mailer_id: int) -> Dict[str, Any]:
    detail = mailer_service.get_newsletter_detail(mailer_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Newsletter not found")
    return detail


@router.post("/upload", summary="Upload and parse an HTML newsletter file")
async def upload_mailer_html(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith((".html", ".htm")):
        raise HTTPException(status_code=400, detail="Only .html or .htm files are supported")

    content_bytes = await file.read()
    html_content = content_bytes.decode("utf-8", errors="replace")

    meta = {
        "filename": file.filename,
    }
    result = mailer_service.process_email_html(html_content, metadata=meta)
    return result


@router.post("/parse-raw", summary="Parse raw HTML newsletter content")
async def parse_raw_mailer(req: RawHtmlRequest) -> Dict[str, Any]:
    result = mailer_service.process_email_html(req.html_content, metadata=req.metadata)
    return result


@router.post("/seed-sample", summary="Seed the Best Media Info test newsletter into the database")
async def seed_sample_mailer() -> Dict[str, Any]:
    fixture_path = (
        Path(__file__).resolve().parents[4]
        / "mailer"
        / "tests"
        / "fixtures"
        / "best_media_info_sample.html"
    )
    if not fixture_path.exists():
        # Fallback check
        _alt = Path("D:/MFA/media-reporting-system/mailer/tests/fixtures/best_media_info_sample.html")
        if _alt.exists():
            fixture_path = _alt
        else:
            raise HTTPException(status_code=500, detail="Sample fixture not found on disk")

    meta = {
        "sender_name": "Best Media Info",
        "sender_email": "bmi@bestmediainfo.in",
        "date": "2026-10-06T11:34:00",
    }
    result = mailer_service.process_file(fixture_path, metadata=meta)
    return result


@router.get("/{mailer_id}/export", summary="Export mailer articles and advertisements to Excel or CSV")
async def export_mailer(
    mailer_id: int,
    format: str = Query("excel", description="Export format: excel or csv"),
):
    detail = mailer_service.get_newsletter_detail(mailer_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Newsletter not found")

    fmt = format.lower()
    base_name = f"mailer_{mailer_id}_{detail.get('source_name', 'newsletter').replace(' ', '_').lower()}"

    if fmt in ("excel", "xlsx"):
        file_path = mailer_exporter.export_excel(detail, filename=f"{base_name}.xlsx")
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt == "csv":
        file_path = mailer_exporter.export_csv(detail, filename=f"{base_name}.csv")
        media_type = "text/csv"
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'excel' or 'csv'")

    if not file_path.exists():
        raise HTTPException(status_code=500, detail="Export generation failed")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )
