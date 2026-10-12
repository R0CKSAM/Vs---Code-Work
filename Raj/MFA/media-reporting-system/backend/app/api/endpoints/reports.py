"""
Media Reporting System - Professional Reporting & Export Endpoints
Exposes real database-backed daily, weekly, and custom report synthesis,
as well as on-demand PDF, Excel, and CSV export file downloads.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.api.deps import require_permission
from fastapi.responses import FileResponse

try:
    from backend.reporting.report_models import (
        CustomReportResponse,
        DailyReportResponse,
        WeeklyReportResponse,
    )
    from backend.reporting.report_service import report_service
    from backend.reporting.report_export import report_exporter
except ImportError:
    from reporting.report_models import (
        CustomReportResponse,
        DailyReportResponse,
        WeeklyReportResponse,
    )
    from reporting.report_service import report_service
    from reporting.report_export import report_exporter

router = APIRouter(prefix="/reports", tags=["Reports & Intelligence Dossiers"])

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_str(date_str: Optional[str], param_name: str = "date") -> Optional[str]:
    """Validates date format YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    if not DATE_REGEX.match(date_str):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format for '{param_name}'. Expected YYYY-MM-DD, got '{date_str}'",
        )
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid calendar date for '{param_name}': {e}",
        )
    return date_str


def validate_date_range(start_date: Optional[str], end_date: Optional[str]):
    """Validates that start_date <= end_date."""
    s = validate_date_str(start_date, "start_date")
    e = validate_date_str(end_date, "end_date")
    if s and e and s > e:
        raise HTTPException(
            status_code=400,
            detail=f"start_date ({s}) cannot be after end_date ({e}).",
        )
    return s, e


# -----------------------------------------------------------------------------
# 1. Daily Report Endpoint
# -----------------------------------------------------------------------------
@router.get("/daily", response_model=DailyReportResponse)
async def get_daily_report(
    date: Optional[str] = Query(None, description="Report date in YYYY-MM-DD format (default: today)")
):
    """
    Returns the comprehensive daily media intelligence executive summary
    and publisher/section breakdown for the specified date.
    """
    d = validate_date_str(date, "date")
    return report_service.generate_daily_report(d)


# -----------------------------------------------------------------------------
# 2. Weekly Report Endpoint
# -----------------------------------------------------------------------------
@router.get("/weekly", response_model=WeeklyReportResponse)
async def get_weekly_report(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Returns the weekly industry roll-up report with daily volume tracking
    and multi-day coverage distribution.
    """
    s, e = validate_date_range(start_date, end_date)
    return report_service.generate_weekly_report(s, e)


# -----------------------------------------------------------------------------
# 3. Custom Report Endpoint
# -----------------------------------------------------------------------------
@router.get("/custom", response_model=CustomReportResponse)
async def get_custom_report(
    start_date: Optional[str] = Query(None, description="Filter start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter end date (YYYY-MM-DD)"),
    website: Optional[str] = Query(None, description="Filter by publication key or 'all'"),
    section: Optional[str] = Query(None, description="Filter by section name or 'all'"),
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE, UPDATED, REMOVED, ALL)"),
    search: Optional[str] = Query(None, description="Keyword search in headlines/summaries"),
    limit: int = Query(500, ge=1, le=2000, description="Max matching records to return"),
):
    """
    Performs parametric multi-criteria filtering against stored database articles.
    """
    s, e = validate_date_range(start_date, end_date)
    return report_service.generate_custom_report(
        start_date=s,
        end_date=e,
        website=website,
        section=section,
        status=status,
        search=search,
        limit=limit,
    )


# -----------------------------------------------------------------------------
# 4. Export Endpoints (PDF, Excel, CSV)
# -----------------------------------------------------------------------------
@router.get("/export", dependencies=[Depends(require_permission("reports.export"))])
async def export_report(
    report_type: str = Query("daily", description="Report type: daily, weekly, custom"),
    format: str = Query("pdf", description="Export format: pdf, excel, csv"),
    date: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    website: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """
    Generates and returns downloadable PDF, Excel, or CSV report files.
    """
    fmt = format.lower()
    rtype = report_type.lower()

    if fmt not in ("pdf", "excel", "csv", "xlsx"):
        raise HTTPException(400, f"Unsupported export format '{format}'. Supported: pdf, excel, csv")

    # Generate data model
    if rtype == "daily":
        d = validate_date_str(date, "date")
        data = report_service.generate_daily_report(d)
        target_date = data.executive_summary.reporting_date
        base_name = f"daily_report_{target_date}"
    elif rtype == "weekly":
        s, e = validate_date_range(start_date, end_date)
        data = report_service.generate_weekly_report(s, e)
        base_name = f"weekly_report_{data.date_range['start_date']}_to_{data.date_range['end_date']}"
    elif rtype == "custom":
        s, e = validate_date_range(start_date, end_date)
        data = report_service.generate_custom_report(
            start_date=s,
            end_date=e,
            website=website,
            section=section,
            status=status,
            search=search,
        )
        base_name = f"custom_dossier_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    else:
        raise HTTPException(400, f"Unsupported report type '{report_type}'. Supported: daily, weekly, custom")

    # Dispatch to exporter
    if fmt == "pdf":
        file_path = report_exporter.export_pdf(data, filename=f"{base_name}.pdf")
        media_type = "application/pdf"
    elif fmt in ("excel", "xlsx"):
        file_path = report_exporter.export_excel(data, filename=f"{base_name}.xlsx")
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif fmt == "csv":
        file_path = report_exporter.export_csv(data, filename=f"{base_name}.csv")
        media_type = "text/csv"

    if not file_path.exists():
        raise HTTPException(500, "Report file generation failed.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )
