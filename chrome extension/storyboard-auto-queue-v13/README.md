# Storyboard Auto Queue v13

## Installation
1. Disable older Storyboard Auto Queue versions at chrome://extensions.
2. Load unpacked `storyboard-auto-queue-v13` folder.
3. Refresh your ChatGPT tab. Import Excel, CSV, or TXT.
4. Select the first **not yet generated** queue row if resuming work. Click Start / Continue.
5. The extension prepares **and attempts to send** that row automatically. After a new completed image it advances to the next row.

## Three composer states
- **IDLE**: voice/wave button, no send attempt.
- **SEND**: enabled up-arrow, stable at least 1.2 s before one click.
- **STOP**: square/stop active, never submit.

## Limitations
DOM-based automation is best effort. ChatGPT's controls can change. A missing/unrecognized arrow or image can pause the queue. No guaranteed unattended 50-image batch or bypass of usage limits. Keep the generating tab open. Test 2–3 rows first.

## Recovery
If an image is already finished but the queue is paused on that row, click **Mark frame complete**, then **Resume**. Never retry a submitted scene without inspecting the chat.
