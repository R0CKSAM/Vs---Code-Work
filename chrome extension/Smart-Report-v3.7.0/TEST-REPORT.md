# Smart Report 3.7.0 — Test report

## Passed automated checks

- JavaScript syntax checks for all packaged .js files.
- Real Chromium rendering of a synthetic dashboard with a nested scroll container, sticky toolbar, collapsed rows, lazy canvas painting and an artificial empty lower area.
- Complete stitched screenshot: 1600 × 3489 pixels, 5 parts, 12 chart panels. Three initially collapsed rows were opened.
- Same output dimensions after changing the fixture window from 1040 × 720 to 820 × 640.
- Ordinary document scrolling as well as nested dashboard scrolling.
- Deliberately transparent chart canvases caused a capture error naming the blank panels; Microsoft submission mock was not called for that failed report.
- Explicit No data panels retained as No data.
- Preview left accepted/failed email counters unchanged.
- Screenshot approval gate, actual packaged popup and preview page interactions.
- One mocked HTTP 202 incremented acceptance once. A later failed capture incremented failure once without another submission.
- Last completed result remained visible while the current report displayed Preparing screenshot.
- Different real variable filters were rejected; only the configured diagnostic parameter was ignored for tab matching.

## Important limits of these tests

The renderer and CDP screenshot commands were real, but Chrome-extension API calls and Microsoft Graph were mocked in a browser harness. Installing an unpacked extension in this runtime was blocked by its browser policy, so no installed-extension end-to-end pass is claimed. No browser policy was disabled or changed.

No corporate Grafana login, live data source, Microsoft OAuth flow, Outlook submission or recipient delivery was tested. The capture checks validate rendering signals, not the correctness of business data. Some Grafana versions/plugins may require further selector adjustments; the intended behavior is to stop with an error rather than send an empty chart.

The user must review a live preview and a test email attachment before starting automated reports.
