Storyboard Auto Queue v2 — cautious experimental prototype

Installation:
1) Unzip the archive.
2) Chrome > chrome://extensions > Developer mode > Load unpacked.
3) Select the storyboard-auto-queue-v2 folder.
4) Open or refresh https://chatgpt.com/, keep the chat tab open.
5) Load the TXT file (or paste one Frame ## || scene per line), enter a master style.
6) Test 2–3 prompts first; click Start.

What changed:
- Uses a specific send-button selector, not any button containing an SVG.
- Confirms a new user message was created before treating submission as successful.
- Stores a pending frame; does NOT increment completed count on submission.
- Requires a new assistant image and a settled completion window before advancing.
- Pauses after seven minutes or any detection error; no blind auto-retries.
- Pause/Resume and persistent queue; completed progress survives popup closing.

Limitations:
- ChatGPT DOM and images are not a guaranteed automation API.
- On interface changes, selectors must be adapted.
- Image detection may fail for some image viewer/card implementations or repeated image src.
- Keep the tab open; avoid manually sending messages while queue runs.
- Pausing while a prompt is already pending does not cancel ChatGPT generation.
- On interruption or refresh, visually inspect the most recent frame before resuming.
- No automatic image downloads; does not bypass usage limits.

V2.1 SEND FIX: Waits up to 8s for an enabled specifically identified Send button, then tries form.requestSubmit if available. Does NOT use synthetic Enter keys. If confirmation fails, it pauses. If you manually click Send after a failed attempt, verify the frame before resuming.
