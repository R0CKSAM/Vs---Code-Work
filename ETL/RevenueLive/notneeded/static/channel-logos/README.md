# Channel logos

Local, raster-only assets used in Channel metrics and Views distribution.
`manifest.json` records the exact catalog channel ID, original asset URL and
SHA-256 for each file. Channel names match explicitly, not through fuzzy search.

Catalog: https://github.com/iptv-org/api
Assets are channel trademarks from their respective owners; catalog availability
does not grant ownership or a new license. Use here is channel identification.

Refresh utility: `design/fetch_channel_logos.py` (requires Pillow).
Visually review refreshed assets before release. Some catalog entries retain old
branding; Epic subchannels were deliberately not mapped to former brand logos.
News Nation regional variants and ambiguous creator channels use initials until
their exact artwork is confirmed. Do not reuse the national logo automatically.

9X Tashan uses a white mark, displayed on a dark backing without altering artwork.
Missing manifests, unmapped names and image loading errors fall back to initials.
Dashboard viewers never need to contact a third-party image host.
