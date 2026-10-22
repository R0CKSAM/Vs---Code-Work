# Smart Report v3.9.1 — Branding & UI release

This package is based on Smart Report v3.9.0 Production Candidate.

## Branding
- Original approved Smart Report chart-and-envelope artwork retained as `assets/brand-logo.png`.
- Square artwork cropped for toolbar icons at 16, 32, 48, and 128 px.
- Header icon, wordmark, login wordmark and screenshot review tab all integrated.
- Palette: deep navy (#092436), mint (#3ad6b9), off-white (#f6faf9), dark ink (#172f3e).

## Interaction colors
- Start / Continue: teal
- Pause: amber; Resume: blue (one existing button, controlled by mode)
- Stop / destructive: muted red
- Test delivery: blue
- Errors: light-red panel with accessible text
- Success: deep green

## Overflow protections
- Fixed intrinsic 540px Chrome popup root preserved; prevents scrollbar-only regression.
- Long addresses, recipients, subject, errors and history wrapped/scrollable.
- Provider cards and buttons use flex min-width:0 and bounded widths.
- Accordions have right-aligned CSS chevrons and motion reduced on request.
- Preview tab is responsive.

## Technical integrity
- Manifest key and OAuth client settings unchanged to preserve identity.
- Background scheduler, capture engine, Microsoft & Google sending APIs unchanged.
- Popup JS change: sets `data-control-mode` on existing Pause/Resume control for styling only.

## Installation
1. Back up your working v3.9.0 folder.
2. Copy these files into the exact existing unpacked extension folder so the installed extension ID remains stable. Do not remove `manifest.key`.
3. In `chrome://extensions/`, press Reload on Smart Report.
4. Verify the popup and both providers; use a single test before resuming a schedule.

Static/UI tests cannot guarantee successful live background-tab capture or Microsoft/Google delivery. Validate in Chrome.

## Validation completed for this release
- Existing 62 reporting regression checks: 62/62 pass.
- Original popup assertions: 69/69 pass.
- New rendered-brand stress tests: 26/26 pass across welcome, overview, paused/running, expanded delivery, dashboard URL, long error/history, and dropdown states.
- No horizontal overflow detected in those simulated views.
- All JavaScript syntax checks passed; ZIP CRC integrity passed.
- Full end-to-end mail delivery in the live user's Chrome account was **not** retested by this offline build.
