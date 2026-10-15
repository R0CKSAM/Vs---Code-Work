# Storyboard Studio v18

Premium UI built on the proven v16 queue logic.

## New features
- Optional automatic image downloads (OFF by default) to Downloads/Storyboard Studio. Only downloads when a unique visible image element can be identified. Otherwise records a skip; does not guess. The browser may need to permit downloads.
- Per-frame completion/needs-review history with CSV export.
- Desktop completion notification (ON by default).
- Safe local diagnostic log export and support message: Please contact Smarth for support.

## Install
Extract ZIP, open chrome://extensions, disable old versions, enable Developer mode, Load unpacked, choose this folder, refresh ChatGPT.

## Important
Browser UI selectors are not a supported ChatGPT automation API. Test 2–3 frames before running a large queue. Image auto-save is best effort and never marks a generation as failed merely because download was not possible. Each queue is ordered by imported Excel row, not frame numbering.
