"""
Media Reporting System - Report Export Engine
Generates professional PDFs (ReportLab), Excel workbooks (openpyxl), and CSV files.
Saves outputs to storage/reports/ with safe filenames.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from backend.reporting.report_models import (
        ArticleReportItem,
        DailyReportResponse,
        WeeklyReportResponse,
        CustomReportResponse,
    )
except ImportError:
    from reporting.report_models import (
        ArticleReportItem,
        DailyReportResponse,
        WeeklyReportResponse,
        CustomReportResponse,
    )


class NumberedCanvas:
    """Canvas wrapper to compute dynamic page numbers (Page X of Y) for ReportLab."""

    def __init__(self, *args, **kwargs):
        pass


class ReportExporter:
    """Exports structured report data into PDF, Excel, and CSV formats."""

    def __init__(self, export_dir: Optional[Path] = None):
        if export_dir:
            self.export_dir = Path(export_dir)
        else:
            # D:\MFA\media-reporting-system\storage\reports
            _here = Path(__file__).resolve().parent
            _root = _here.parent.parent
            self.export_dir = _root / "storage" / "reports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # CSV Export
    # -------------------------------------------------------------------------
    def export_csv(
        self,
        report_data: Union[DailyReportResponse, WeeklyReportResponse, CustomReportResponse, List[ArticleReportItem]],
        filename: Optional[str] = None,
    ) -> Path:
        """Exports articles to CSV format."""
        if isinstance(report_data, (DailyReportResponse, WeeklyReportResponse)):
            articles = report_data.top_stories
        elif isinstance(report_data, CustomReportResponse):
            articles = report_data.articles
        elif isinstance(report_data, list):
            articles = report_data
        else:
            articles = []

        if not filename:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"report_{now_str}.csv"

        out_path = self.export_dir / filename

        with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Website",
                    "Section",
                    "Headline",
                    "URL",
                    "Published At",
                    "First Seen At",
                    "Last Seen At",
                    "Status",
                    "Content Hash",
                ]
            )
            for a in articles:
                item = a if isinstance(a, ArticleReportItem) else ArticleReportItem(**a)
                writer.writerow(
                    [
                        item.website_name,
                        item.section_name,
                        item.headline,
                        item.url,
                        item.published_at or "N/A",
                        item.first_seen_at,
                        item.last_seen_at,
                        item.status,
                        item.content_hash,
                    ]
                )

        return out_path

    # -------------------------------------------------------------------------
    # Excel Export (openpyxl)
    # -------------------------------------------------------------------------
    def export_excel(
        self,
        report_data: Union[DailyReportResponse, WeeklyReportResponse, CustomReportResponse],
        filename: Optional[str] = None,
    ) -> Path:
        """Exports full report dataset into styled multi-tab Excel workbook."""
        try:
            import openpyxl
            from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            # Fallback to CSV if openpyxl is not installed
            csv_name = (filename or "report").replace(".xlsx", "") + ".csv"
            return self.export_csv(report_data, filename=csv_name)

        if not filename:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"report_{now_str}.xlsx"

        out_path = self.export_dir / filename
        wb = openpyxl.Workbook()

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
        sub_font = Font(name="Calibri", size=10, italic=True, color="475569")
        bold_font = Font(name="Calibri", size=11, bold=True)
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        def style_header_row(ws, row_idx, max_col):
            for col in range(1, max_col + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")

        def auto_fit_columns(ws):
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 60)

        # Tab 1: Executive Summary
        ws_sum = wb.active
        ws_sum.title = "Executive Summary"

        ws_sum.cell(row=1, column=1, value="Media Intelligence Executive Summary").font = title_font
        generated_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        ws_sum.cell(row=2, column=1, value=f"Generated: {generated_time}").font = sub_font

        if isinstance(report_data, DailyReportResponse):
            ws_sum.cell(row=4, column=1, value="Reporting Date:").font = bold_font
            ws_sum.cell(row=4, column=2, value=report_data.executive_summary.reporting_date)
            ws_sum.cell(row=5, column=1, value="Total Monitored Articles:").font = bold_font
            ws_sum.cell(row=5, column=2, value=report_data.executive_summary.total_articles)
            ws_sum.cell(row=6, column=1, value="ET BrandEquity Articles:").font = bold_font
            ws_sum.cell(row=6, column=2, value=report_data.executive_summary.et_article_count)
            ws_sum.cell(row=7, column=1, value="Exchange4media Articles:").font = bold_font
            ws_sum.cell(row=7, column=2, value=report_data.executive_summary.e4m_article_count)
            ws_sum.cell(row=8, column=1, value="Sections Represented:").font = bold_font
            ws_sum.cell(row=8, column=2, value=report_data.executive_summary.sections_count)
            ws_sum.cell(row=9, column=1, value="New Articles:").font = bold_font
            ws_sum.cell(row=9, column=2, value=report_data.executive_summary.new_articles_count)
            ws_sum.cell(row=10, column=1, value="Updated Articles:").font = bold_font
            ws_sum.cell(row=10, column=2, value=report_data.executive_summary.updated_articles_count)
            ws_sum.cell(row=11, column=1, value="Removed Articles:").font = bold_font
            ws_sum.cell(row=11, column=2, value=report_data.executive_summary.removed_articles_count)
            ws_sum.cell(row=12, column=1, value="Monitoring State:").font = bold_font
            ws_sum.cell(row=12, column=2, value=report_data.executive_summary.monitoring_status)

        elif isinstance(report_data, WeeklyReportResponse):
            ws_sum.cell(row=4, column=1, value="Date Range:").font = bold_font
            ws_sum.cell(row=4, column=2, value=f"{report_data.date_range['start_date']} to {report_data.date_range['end_date']}")
            ws_sum.cell(row=5, column=1, value="Total Monitored Articles:").font = bold_font
            ws_sum.cell(row=5, column=2, value=report_data.total_articles)
            ws_sum.cell(row=6, column=1, value="ET BrandEquity:").font = bold_font
            ws_sum.cell(row=6, column=2, value=report_data.et_article_count)
            ws_sum.cell(row=7, column=1, value="Exchange4media:").font = bold_font
            ws_sum.cell(row=7, column=2, value=report_data.e4m_article_count)
            ws_sum.cell(row=8, column=1, value="New Articles:").font = bold_font
            ws_sum.cell(row=8, column=2, value=report_data.new_articles_count)
            ws_sum.cell(row=9, column=1, value="Updated Articles:").font = bold_font
            ws_sum.cell(row=9, column=2, value=report_data.updated_articles_count)
            ws_sum.cell(row=10, column=1, value="Removed Articles:").font = bold_font
            ws_sum.cell(row=10, column=2, value=report_data.removed_articles_count)

        elif isinstance(report_data, CustomReportResponse):
            ws_sum.cell(row=4, column=1, value="Total Matching Articles:").font = bold_font
            ws_sum.cell(row=4, column=2, value=report_data.total_matching)
            r = 5
            for k, v in report_data.filters.items():
                ws_sum.cell(row=r, column=1, value=f"Filter ({k}):").font = bold_font
                ws_sum.cell(row=r, column=2, value=str(v))
                r += 1

        auto_fit_columns(ws_sum)

        # Tab 2: Articles List
        def populate_article_sheet(sheet, items, sheet_title):
            sheet.title = sheet_title
            headers = ["Website", "Section", "Headline", "URL", "Published At", "First Seen At", "Status", "Content Hash"]
            sheet.append(headers)
            style_header_row(sheet, 1, len(headers))

            if not items:
                sheet.append(["No records available for this section."])
                return

            for a in items:
                item = a if isinstance(a, ArticleReportItem) else ArticleReportItem(**a)
                sheet.append(
                    [
                        item.website_name,
                        item.section_name,
                        item.headline,
                        item.url,
                        item.published_at or "N/A",
                        item.first_seen_at,
                        item.status,
                        item.content_hash,
                    ]
                )
            auto_fit_columns(sheet)

        if isinstance(report_data, (DailyReportResponse, WeeklyReportResponse)):
            populate_article_sheet(wb.create_sheet(), report_data.top_stories, "Top Stories")
            populate_article_sheet(wb.create_sheet(), report_data.new_articles, "New Articles")
            populate_article_sheet(wb.create_sheet(), report_data.updated_articles, "Updated Articles")
            populate_article_sheet(wb.create_sheet(), report_data.removed_articles, "Removed Articles")
        elif isinstance(report_data, CustomReportResponse):
            populate_article_sheet(wb.create_sheet(), report_data.articles, "Filtered Articles")

        # Tab: Sections Breakdown
        ws_sec = wb.create_sheet("Section Breakdown")
        sec_headers = ["Section", "Publication", "Article Count", "New Count", "Updated Count"]
        ws_sec.append(sec_headers)
        style_header_row(ws_sec, 1, len(sec_headers))
        for sb in report_data.section_breakdown:
            ws_sec.append([sb.section_name, sb.website_name, sb.article_count, sb.new_count, sb.updated_count])
        auto_fit_columns(ws_sec)

        wb.save(out_path)
        return out_path

    # -------------------------------------------------------------------------
    # PDF Export (ReportLab)
    # -------------------------------------------------------------------------
    def export_pdf(
        self,
        report_data: Union[DailyReportResponse, WeeklyReportResponse, CustomReportResponse],
        filename: Optional[str] = None,
    ) -> Path:
        """Generates a professional executive PDF report using ReportLab."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.pdfgen import canvas
            from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError:
            # Fallback to CSV if ReportLab is not available
            csv_name = (filename or "report").replace(".pdf", "") + ".csv"
            return self.export_csv(report_data, filename=csv_name)

        if not filename:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"report_{now_str}.pdf"

        out_path = self.export_dir / filename
        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
        )
        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#64748B"),
        )
        heading_style = ParagraphStyle(
            "ReportHeading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=10,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )
        table_cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
        )
        table_header_style = ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        )

        story = []

        # 1. Header Banner
        if isinstance(report_data, DailyReportResponse):
            report_title = "Daily Media Intelligence Brief"
            report_sub = f"Reporting Date: {report_data.executive_summary.reporting_date} | Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}"
        elif isinstance(report_data, WeeklyReportResponse):
            report_title = "Weekly Industry Roll-up"
            report_sub = f"Period: {report_data.date_range['start_date']} to {report_data.date_range['end_date']} | Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}"
        else:
            report_title = "Custom Media Intelligence Dossier"
            report_sub = f"Parametric Query | Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}"

        story.append(Paragraph(report_title, title_style))
        story.append(Paragraph(report_sub, subtitle_style))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))

        # 2. Executive Summary KPIs Table
        story.append(Paragraph("Executive Summary & Telemetry", heading_style))

        if isinstance(report_data, DailyReportResponse):
            kpi_data = [
                [
                    Paragraph("<b>Total Articles</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.total_articles), table_cell_style),
                    Paragraph("<b>ET BrandEquity</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.et_article_count), table_cell_style),
                ],
                [
                    Paragraph("<b>Exchange4media</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.e4m_article_count), table_cell_style),
                    Paragraph("<b>Sections Represented</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.sections_count), table_cell_style),
                ],
                [
                    Paragraph("<b>New Articles</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.new_articles_count), table_cell_style),
                    Paragraph("<b>Updated Articles</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.updated_articles_count), table_cell_style),
                ],
                [
                    Paragraph("<b>Removed Articles</b>", table_cell_style),
                    Paragraph(str(report_data.executive_summary.removed_articles_count), table_cell_style),
                    Paragraph("<b>Monitoring Cycles</b>", table_cell_style),
                    Paragraph(report_data.executive_summary.monitoring_status, table_cell_style),
                ],
            ]
        elif isinstance(report_data, WeeklyReportResponse):
            kpi_data = [
                [
                    Paragraph("<b>Total Volume</b>", table_cell_style),
                    Paragraph(str(report_data.total_articles), table_cell_style),
                    Paragraph("<b>ET BrandEquity</b>", table_cell_style),
                    Paragraph(str(report_data.et_article_count), table_cell_style),
                ],
                [
                    Paragraph("<b>Exchange4media</b>", table_cell_style),
                    Paragraph(str(report_data.e4m_article_count), table_cell_style),
                    Paragraph("<b>Sections Represented</b>", table_cell_style),
                    Paragraph(str(report_data.sections_count), table_cell_style),
                ],
                [
                    Paragraph("<b>New Articles</b>", table_cell_style),
                    Paragraph(str(report_data.new_articles_count), table_cell_style),
                    Paragraph("<b>Updated Articles</b>", table_cell_style),
                    Paragraph(str(report_data.updated_articles_count), table_cell_style),
                ],
            ]
        else:
            kpi_data = [
                [
                    Paragraph("<b>Total Matching Articles</b>", table_cell_style),
                    Paragraph(str(report_data.total_matching), table_cell_style),
                    Paragraph("<b>Status Filter</b>", table_cell_style),
                    Paragraph(str(report_data.filters.get("status", "ALL")), table_cell_style),
                ],
                [
                    Paragraph("<b>Publisher Filter</b>", table_cell_style),
                    Paragraph(str(report_data.filters.get("website", "all")), table_cell_style),
                    Paragraph("<b>Section Filter</b>", table_cell_style),
                    Paragraph(str(report_data.filters.get("section", "all")), table_cell_style),
                ],
            ]

        t_kpi = Table(kpi_data, colWidths=[130, 130, 130, 150])
        t_kpi.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t_kpi)
        story.append(Spacer(1, 10))

        # 3. Publisher Breakdown
        story.append(Paragraph("Publisher Coverage Distribution", heading_style))
        pub_table_data = [
            [
                Paragraph("<b>Publisher</b>", table_header_style),
                Paragraph("<b>Articles</b>", table_header_style),
                Paragraph("<b>Share (%)</b>", table_header_style),
                Paragraph("<b>New</b>", table_header_style),
                Paragraph("<b>Updated</b>", table_header_style),
                Paragraph("<b>Removed</b>", table_header_style),
            ]
        ]
        for pb in report_data.publisher_breakdown:
            pub_table_data.append(
                [
                    Paragraph(pb.website_name, table_cell_style),
                    Paragraph(str(pb.article_count), table_cell_style),
                    Paragraph(f"{pb.percentage}%", table_cell_style),
                    Paragraph(str(pb.new_count), table_cell_style),
                    Paragraph(str(pb.updated_count), table_cell_style),
                    Paragraph(str(pb.removed_count), table_cell_style),
                ]
            )
        t_pub = Table(pub_table_data, colWidths=[140, 75, 75, 75, 75, 100])
        t_pub.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t_pub)
        story.append(Spacer(1, 10))

        # 4. Weekly Daily Volume (if weekly report)
        if isinstance(report_data, WeeklyReportResponse) and report_data.daily_volume:
            story.append(Paragraph("Daily Volume Tracking", heading_style))
            vol_data = [
                [
                    Paragraph("<b>Date</b>", table_header_style),
                    Paragraph("<b>ET BrandEquity</b>", table_header_style),
                    Paragraph("<b>Exchange4media</b>", table_header_style),
                    Paragraph("<b>Daily Total</b>", table_header_style),
                ]
            ]
            for dv in report_data.daily_volume:
                vol_data.append(
                    [
                        Paragraph(dv.date, table_cell_style),
                        Paragraph(str(dv.et_count), table_cell_style),
                        Paragraph(str(dv.e4m_count), table_cell_style),
                        Paragraph(str(dv.total_count), table_cell_style),
                    ]
                )
            t_vol = Table(vol_data, colWidths=[130, 130, 130, 150])
            t_vol.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(t_vol)
            story.append(Spacer(1, 10))

        # 5. Top Stories / Article Roster
        articles_to_show = (
            report_data.top_stories
            if isinstance(report_data, (DailyReportResponse, WeeklyReportResponse))
            else report_data.articles[:25]
        )

        story.append(Paragraph("Latest Monitored Stories", heading_style))
        if not articles_to_show:
            story.append(Paragraph("<i>No articles recorded for this period.</i>", body_style))
        else:
            art_data = [
                [
                    Paragraph("<b>Publication</b>", table_header_style),
                    Paragraph("<b>Section</b>", table_header_style),
                    Paragraph("<b>Headline & Summary</b>", table_header_style),
                    Paragraph("<b>Status</b>", table_header_style),
                ]
            ]
            for a in articles_to_show[:20]:
                item = a if isinstance(a, ArticleReportItem) else ArticleReportItem(**a)
                art_data.append(
                    [
                        Paragraph(item.website_name, table_cell_style),
                        Paragraph(item.section_name, table_cell_style),
                        Paragraph(f"<b>{item.headline}</b>", table_cell_style),
                        Paragraph(item.status, table_cell_style),
                    ]
                )
            t_art = Table(art_data, colWidths=[100, 90, 280, 70])
            t_art.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(t_art)

        doc.build(story)
        return out_path


# Global default exporter
report_exporter = ReportExporter()
