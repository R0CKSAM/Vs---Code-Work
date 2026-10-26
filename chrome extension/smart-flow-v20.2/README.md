# Smart Flow v20 — Aurora UI Edition

Compact premium redesign based on the provided Smart Flow reference.

- Preserves v19 automation scripts (`content.js`, `background.js`, `popup.js`, `importer.js`) unchanged.
- Adds a luminous navy gradient progress card, subtle mint glow, refined upload highlight, and color-coded controls: teal Start, amber Pause, blue Resume, red Stop.
- Keeps Excel/CSV/TXT import, sample workbook, history, diagnostics, and logo customization.

## Installation
Chrome > chrome://extensions > disable previous Smart Flow > enable Developer mode > Load unpacked > select the `smart-flow-v20` folder. Refresh ChatGPT.

Note: UI code passed structural checks; full image-generation automation has not been live-tested in this update.


## v20.2 Layout audit
UI-only CSS hardening: bounded multi-line current frame display, overflow-safe filenames/labels, restricted advanced prompt editors, wrapping support/error text, history scrolling, responsive control sizing, and accessible dropdown alignment. Automation/background/import scripts unchanged.
