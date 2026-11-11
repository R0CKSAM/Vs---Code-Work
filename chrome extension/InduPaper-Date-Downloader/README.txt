INSTALL
1. Open chrome://extensions in Chrome.
2. Turn on Developer mode (top right).
3. Click Load unpacked and select this InduPaper-Date-Downloader folder.
4. Open https://www.indupaper.com/times-of-india.html and wait for city options.
5. Open this extension from Chrome's puzzle icon; pin it if desired.
6. Choose city, From and Through dates, then Download date range.

Uses the site's existing PDF generator; does not bypass login, CAPTCHA or access restrictions.
One date is processed at a time, with a five-second gap after a confirmed completed download.
Keep Chrome and the original newspaper tab open. The popup can be closed.
Files go to Chrome Downloads\InduPaper\CITY. Turn off Ask where to save each file for unattended use.
The site names files toi-CITY-YYYY-MM-DD.pdf. Chrome normally adds numbers for existing names.
Pause finishes the current operation first. Resume/retry can duplicate a file if its prior outcome is uncertain; check Downloads.
Missing dates/site errors pause the queue. Skip date explicitly records a skipped date.
The watchdog pauses after ten minutes without completion. Browser restart/tab closure may require a retry.
Supports this Times of India page only; PDFs retain the site's own rendering and image quality.

Implementation checked against the live page and TOI.js on 2026-11-11.
No live batch has been started automatically: choose your own dates and city.

