# Storyboard Auto Queue v16 — diagnostic-informed build

This version uses the actual UI controls observed in the user's October 15 diagnostic log:

- ChatGPT Send is a **button with `aria-label="Send"` and `type="submit"`** when the prompt is ready.
- While image generation runs, ChatGPT may **not expose a Stop button** at all to DOM queries.
- A **`Play Snake while your image is generating`** control appeared during the observed generation.
- The previous **`generated-image-preview`** disappeared after submission and reappeared when the image finished.

The extension therefore observes composer-empty / generation indicator / generated-image-preview **transitions**, not counts of all `<img>` tags or `data-message-author-role` elements. It waits for a stable completed preview, then advances one imported Excel row.

## Install
1. Disable all previous versions on `chrome://extensions/`.
2. Extract this ZIP and Load unpacked the `storyboard-auto-queue-v16` folder.
3. Refresh ChatGPT and keep the generating tab open.
4. Import Excel/CSV/TXT and choose the first *unfinished* spreadsheet row.
5. Start. No manual first send is required if the detected Send control matches the log.

**Important:** This is a diagnostic-informed prototype, not an official ChatGPT API. If the UI changes or the lifecycle signals are ambiguous, it pauses without replaying an uncertain prompt. If an image is complete but the queue is stuck, use **Pause → Mark frame complete → Resume** once, and never Retry unless no result exists.

Import order is file row order, independent of scene numbering. Avoid switching tabs or navigating during generation.

## Tests performed
- JavaScript syntax verification
- ZIP/manifest validation
- Replay inspection of the diagnostic event timeline

Automated end-to-end image generation remains unverified in the user's Chrome browser.
