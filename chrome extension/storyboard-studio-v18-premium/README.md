# Storyboard Studio v18

## v18.0.3 — choose the starting frame on the main screen

The main screen now has **Start / resume from frame**, an imported-position number input, and a preview of the actual frame label. The number defaults to the current frame and supports the full imported queue (for example, 1–110).

- **Start generating** starts the chosen frame. Starting a pending frame offers a fresh attempt after confirmation.
- **Resume** continues the current pending frame when its position is unchanged, or switches to the chosen position after confirmation.
- **Set frame** chooses the next position without starting generation. It can also replace a stuck pending frame after confirmation.

Changing position keeps existing downloads and history. It is blocked while the queue or ChatGPT is generating. A different composer draft is preserved. Selecting a previously generated frame can generate another image; filename conflicts still use Chrome's unique-name behavior.

Positions follow the imported order. If the imported labels are not sequential, use the label preview to confirm the intended frame. Reopening the popup defaults to the stored current position; periodic refresh does not overwrite a number being edited. Reload the same extension folder and refresh the ChatGPT tab to use v18.0.3.

## v18.0.2 — distinguish refreshed images from new output

Prompt recovery now associates existing previews with their assistant-message containers and compares stable image asset addresses rather than treating renewed image signatures as new generations. Loading older conversation history no longer blocks recovery when the last user message is unchanged. Legacy prepared frames can refresh their old image baseline when the preceding frame is identifiable.

New or unrecognized output, an attempted Send, or a changed latest user message still prevents automatic repasting. The error text now distinguishes those conditions. Verification passes 82 checks across 26 browser scenarios, including image-link refresh, history hydration and the duplicate-send safeguards.

Reload the same installed extension folder, refresh the existing ChatGPT tab, verify the popup shows **v18.0.2**, then Resume. Keep the current queue and progress; do not Reset or re-import. If a pause remains, export a fresh diagnostic log from v18.0.2 so the current reason is available.

## v18.0.1 — recover a cleared, unsent prompt

When ChatGPT clears or remounts the composer before Storyboard Studio has clicked Send, the queue now checks the visible conversation and generation state, waits briefly, and restores an empty prompt automatically. This is limited to three restores per pending frame. The current row and completed progress are retained.

Different nonempty drafts are preserved. Already-submitted prompts, active generation, new output, or changed conversation evidence are not blindly repasted. An uncertain submission still requires review. Existing v18 prepared frames can recover when the preceding conversation is visible and unchanged.

To apply the fix to an existing paused queue:

1. In `chrome://extensions`, reload **the same installed Storyboard Studio folder**.
2. Refresh the existing ChatGPT conversation tab.
3. Open Storyboard Studio and select **Resume**. For the reported case, progress should remain **37 / 110**, with **Frame 038** current.

Do not Reset or re-import the storyboard to apply this update. If the frame was already sent, inspect the conversation before using the explicit Retry option. Image downloads retain `conflictAction: 'uniquify'` and do not overwrite an existing filename.

Verification: browser tests exercise actual `content.js` with synthetic textarea and contenteditable composers, including clearing/remounts, manual sends, active generation, different drafts, retry limits, pause/queue replacement, and legacy prepared-state recovery. No live image generation is needed for these tests.

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
