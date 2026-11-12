INDUPAPER DATE DOWNLOADER 1.3.2

UNATTENDED USE
Open your chosen InduPaper newspaper page, open the extension, select edition and dates, and leave Unattended mode checked.
Temporary errors retry three times after 15, 45 and 120 seconds. If a date still fails, it is recorded as missed and the next date starts automatically.
Missing-date responses are recorded without an endless retry loop. The batch finishes even when every requested date is unavailable.
A date is marked saved only after Chrome confirms a completed download.

A final CSV batch report is saved beside the PDFs, listing saved, missed and skipped dates, reasons and attempt counts.
Download report creates a clearly named PARTIAL report while a batch is running.
Retry missed dates starts a focused batch containing only missed/skipped dates; saved dates are not repeated.
Uncheck Unattended mode to pause on date errors instead.

POWER / RECOVERY
Uses Chrome's power API to prevent automatic idle sleep during an active batch; the screen can still turn off.
The keep-awake request is released when done or manually paused. Chrome must remain running.
A deliberate PC sleep, shutdown or closing Chrome can stop execution; saved state recovers when Chrome runs again.
Chrome restart recovery checks download history, adopts completed files and resumes interrupted transfers where possible.
Manual pauses and user-canceled transfers stay paused.
Access/login errors, a changed/ambiguous newspaper tab, or an uncertain PDF-save result still require review; no access restriction is bypassed.

FILES
Chrome Downloads\InduPaper\NEWSPAPER\EDITION
Existing names receive numbered suffixes. Turn off Ask where to save each file in Chrome Downloads settings for unattended use.
PDF page rendering/quality comes from the site's PDF generator. The extension cannot create editions the website does not provide.
HT/TOI form flows are tested; other matching newspaper forms are detected dynamically.

INSTALL / UPDATE
chrome://extensions > Developer mode > Load unpacked (this folder).
For updates, Reload InduPaper Date Downloader. The UI checks its loaded version.
The power permission is used only for active-batch keep-awake behavior.

TESTS (Node 22+, Windows Chrome for browser tests)
node tests/worker-checks.cjs
node tests/browser-checks.cjs
The queue tests include an entire 31-day HTTP-500 failure simulation that finishes with a missed-date report and never waits for manual Resume.
Power API reference: https://developer.chrome.com/docs/extensions/reference/api/power
