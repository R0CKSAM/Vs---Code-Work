INDUPAPER DATE DOWNLOADER 1.2.0

Open the newspaper you want on InduPaper, then open the extension.
Choose City and Sub City/edition where provided, then your From and Through dates.
Choose Download date range. One date is processed at a time.

FIXES
- Skip date records the omission and continues automatically.
- Temporary network, HTTP 429 and server failures retry at most three times, after 15/45/120 seconds.
- Missing editions and access errors pause for review. Skip explicitly to continue without that date.
- A retry countdown, saved count and skipped count are shown in the popup.
- Manual pauses and canceled downloads stay paused.
- Chrome restart/update recovery restores a unique newspaper tab and checks download history before generating another PDF.
- Existing completed downloads are adopted; interrupted transfers are resumed where Chrome allows it.
- An uncertain PDF-save outcome pauses for inspection instead of automatically sending again.
- Downloads without progress for ten minutes pause for inspection.
- Saved batches persist when the browser closes. Chrome must be open for downloading.

FILES
Chrome Downloads\InduPaper\NEWSPAPER\EDITION
Old Times of India batches retain their original location/names.
Existing files are preserved using numbered filenames.
For unattended saving, turn off Ask where to save each file in Chrome Downloads settings.
PDF page rendering/quality comes from the newspaper site's PDF generator.

INSTALL / UPDATE
Open chrome://extensions, enable Developer mode and Load unpacked (this folder).
For an existing installation, click Reload on InduPaper Date Downloader.
A version mismatch displays Update pending and disables batch controls until Reload.

SUPPORT
HT and TOI form flows are tested. Other pages with matching date/edition/PDF controls are detected dynamically.
Different button code or filenames may need an adapter. No login/CAPTCHA/access controls are bypassed.
If several restored tabs show the same newspaper, close the extra copies before Resume.

VALIDATION
Node 22+: node tests/worker-checks.cjs (retry/recovery/skip/state tests).
Node 22+ and Chrome on Windows: node tests/browser-checks.cjs (isolated form/PDF/popup fixtures).
Live HT Delhi PDFs and edition-specific filenames were verified on this PC.
No PC reboot or account sign-in was required for automated recovery tests.
