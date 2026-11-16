Sports export: all HTTP requests for the workbook date and exact mapped host(s).
sports_requests_enriched.parquet: one row per lake request, all original columns retained plus enrichment.
sports_audience_summary.parquet: the requested 12-column format. Rows group by all 11 descriptive dimensions.
raw_ts_requests counts .ts paths across ALL status codes, including retries/failures; no deduplication.
Zero-TS groups remain. No device/IP, UA, country or status filter was applied.
source_requests.parquet is the retained un-enriched extract. Lookup and mapping snapshots are retained.
Missing decoded values remain null/unknown; lookup status and provenance are in the detailed file.
Country/state/city are CDN log geography. ASN country describes the network, not viewer location.
ASN organization is an ISP/network label, and does not always identify a retail ISP.
UA bot labels are decoder signals, not proof of human or automated viewing.
No watch duration is inferred: requests alone do not prove watching or exact playback time.
An IP can occur in multiple summary rows; do not sum row-level IP counts for a unique audience.
All query-string fields remain in original queryStr even if not separately extracted.
Existing source files, workbooks and prior exports were not modified or removed.
