# Storyboard Queue Diagnostics v1

This is a **read-only diagnostic extension**, separate from the unreliable auto-queue versions. It does not enter prompts, click Send, or read/store message contents. It records ChatGPT's visible composer states, nearby button attributes, conversation-turn counts and visible image/video element counts. It stores up to 220 state changes locally until exported or the next recording starts.

## Install
1. Disable all Storyboard Auto Queue versions at `chrome://extensions` to avoid interference.
2. Extract this ZIP. Load unpacked folder `storyboard-queue-diagnostics-v1`.
3. Refresh your ChatGPT tab.
4. Click **Start recording**.
5. Manually enter and send **one** test image prompt. Wait for image completion and 3 extra seconds.
6. Click **Stop recording**, then **Export JSON**.
7. Send the JSON to ChatGPT for analysis.

No message text or prompt content is intentionally saved. Button accessibility metadata (labels, test IDs, SVG classes), counts, and timestamps are included; review the JSON before sharing.

The log may still include page-UI labels that reveal account or interface details. The extension does not upload data anywhere; exporting produces a file locally.
