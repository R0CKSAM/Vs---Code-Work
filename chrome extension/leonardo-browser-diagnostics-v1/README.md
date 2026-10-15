# Leonardo Browser Diagnostics v1

Independent, read-only diagnostic Chrome extension for https://app.leonardo.ai/.

## Install
1. Extract the ZIP.
2. Open chrome://extensions/ and turn on Developer mode.
3. Select Load unpacked and choose the extracted `leonardo-browser-diagnostics-v1` folder.
4. Refresh Leonardo AI.

## Collect one image generation cycle
1. Navigate to Leonardo's image-generation workspace, not only the Explore landing page.
2. Click Start recording in the extension.
3. Manually type/paste a sample prompt and press Generate. The extension does not perform any actions.
4. Let the image finish, then click Stop recording and Export JSON.
5. Review the JSON before sharing. Send it to ChatGPT for analysis.

## Privacy and limitations
- Records browser UI metadata such as labels, test IDs, field character counts, image counts and loading controls.
- Does NOT log prompt text, account details, generated image URLs, or the rendered images themselves.
- Logs are kept locally in Chrome extension storage until cleared; no remote upload.
- If Leonardo uses invisible/obfuscated controls or canvas, additional inspection may be required.
- Diagnostic only: has no permission to submit prompts or automate Leonardo actions.
