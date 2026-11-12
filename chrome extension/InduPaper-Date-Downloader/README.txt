INSTALL / UPDATE
Open chrome://extensions and click Reload on InduPaper Date Downloader (version 1.1.1).
For a new installation: Developer mode > Load unpacked > select this folder.
Return to your chosen InduPaper newspaper page and reopen the extension.

USE
The newspaper title, date control, and city/edition selectors are detected from the page.
Hindustan Times includes City and Sub City. Changing City refreshes available Sub City options.
Choose the edition, From date and Through date, then Download date range.
The chosen edition is reapplied for each date. The batch stays bound to its original newspaper tab.
Files save under Chrome Downloads\InduPaper\NEWSPAPER\EDITION.
Old Times of India batches keep their original naming/location and can still resume.

The extension uses the site's existing PDF generator. No access restrictions are bypassed.
Pages need one date form with a PDF button whose handler is available to the browser.
HT and TOI forms were checked with 21 real-browser checks; other matching forms are detected dynamically.
Live HT validation on 2026-11-12: Delhi / Delhi, 2026-09-01 saved as 24 pages (59.2 MB); queue advanced automatically to 2026-09-02. Unsupported pages show a clear message.
Some other newspaper pages may use different button code or filenames and need an adapter.

Downloads proceed sequentially with a five-second gap after completion.
Keep Chrome and the original newspaper tab open. The popup can close.
For unattended use, turn off Ask where to save each file in Chrome Downloads settings.
Existing filenames get numbered suffixes. PDFs retain the site's rendering/image quality.
Pause finishes the current operation first. Check downloads before retrying an uncertain result.
Missing dates/site errors pause the queue. Skip date explicitly records a skipped date.
A ten-minute watchdog pauses long-running attempts for inspection.


1.1.1: only newspaper API HTTP failures pause a batch; unrelated opaque ad responses are ignored. A page error cannot override an already tracked PDF download.

