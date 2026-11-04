Source: published VOD dashboard daily payloads. Last seven completed days: 28 October?3 November 2026 IST.
One row per date/video key (content_code), all included STREAM VOD hosts/channels.
CLI IP and device columns are distinct nonempty identity counts, matching dashboard semantics, not literal IP/device lists.
Watch time is in minutes: dashboard request_watch_hours x 60, all statuses. This estimates six seconds per TS request; retries/errors can overstate viewing.
Mobile and CTV use the payload decoded_form_factor classifications. Desktop, tablet, unknown and other classes remain in total watch time but are not assigned to Mobile/CTV.
No retroactive UA reclassification is performed; export matches the published dashboard snapshot.
Do not sum distinct counts to calculate unique viewers across video keys/dates.
