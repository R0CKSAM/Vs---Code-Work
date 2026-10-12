# Media Reporting System - Reports Engine

This directory is allocated for automated media dossiers, clipping summaries, and analytical spreadsheets.

## Phase 0 Status

> **IMPORTANT**: In **Phase 0 — Foundation**, NO report rendering or document generation is implemented.

---

## Planned Architecture (Phase 8)

In **Phase 8 — Automated Reports**, the reporting engine will produce:
1. **Executive Daily Briefings (PDF)**:
   - Generated using open-source tools: Jinja2 HTML templates rendered via WeasyPrint or ReportLab.
   - Summarizing top breaking stories across monitored media portals.
2. **Advertiser Activity Spreadsheets (Excel / XLSX)**:
   - Generated using open-source `openpyxl`.
   - Tabulating brand campaigns, placements, frequency of appearances, and estimated impressions.
3. **Custom Parameter Reports**:
   - Filtered by sector, publication, keyword, or date range.

---

## Directory Structure

```
reports/
├── templates/           # Jinja2 HTML / CSS templates for PDF generation
├── generated/           # Output directory for rendered PDF and Excel reports
└── README.md
```
