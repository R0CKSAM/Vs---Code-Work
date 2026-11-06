# Smart Flow v20.7.0 - automatic mapped references and scenes

Reload this extension folder in Chrome Extensions and refresh ChatGPT after the
current generation finishes. Import `S01_First_5_Test.csv`, then choose **Load
Aarohan reference pack folder** and select the entire pack. Leave **Automatically
upload references** enabled and choose **Start generating**. No Attach or Confirm
click is required for successfully detected uploads in this mode.

Smart Flow selects each frame's character, location and prop images from
`Attachment_Manifest.csv`, uploads the exact original files when the mapping
changes, and waits for loaded composer thumbnails, no upload indicators and a
stable attachment set. It then prepares the scene prompt and clicks the enabled
Send button once. Every mapped scene names the references to use and instructs
ChatGPT to render that scene rather than a reference board. Consecutive frames
with identical mappings reuse their references in the same conversation.

Enable **Save completed images automatically** to wait for each completed Chrome
download before the next frame. Missing files, upload errors, extra attachments,
manual drafts, changed conversations and unverifiable uploads pause the queue.
Resume observes an existing upload rather than requesting it again. Detection
requires composer image thumbnails; unsupported site layouts pause for manual
review instead of assuming an upload succeeded. After reviewing the attachments,
the manual confirmation button can override automatic upload verification.

**Continue with listed reference gaps** is off by default. Enable it if you want
to use the pack's available mapped images even where its manifest flags a missing
exact setup. It never substitutes another image or permits missing image files.
With this setting off, use the manual Attach button to review a flagged frame.
Disable automatic references to retain the v20.6 manual attachment workflow.
The older five-character workbook and Repeat modes retain their existing setup.

Original pack CSVs import directly as `Frame ID, Prompt`; original text, row order
and tracking IDs are preserved. After the five-frame trial, use a scene CSV or
`Aarohan_Mapped_Prompts.csv` for all 1,444 frames and load the pack folder again.
No source CSV, manifest or reference PNG is modified.

Validation uses the actual pack and isolated Chrome with a local conversation
fixture. It covers automatic reference changes, delayed and failed uploads,
missing/extra files, timeout, gap preferences, pause during dispatch, downloads
and no duplicate requests. The original OS image files and real extension storage
are used; directory-relative metadata is emulated because headless CDP does not
operate the folder picker. No live image generation is performed. Live ChatGPT
layout compatibility and artistic consistency require the user's trial.

The following sections describe earlier releases.

## v20.5.0 - attach character references before generation

Reload this same `smart-flow-v20.2` folder in Chrome Extensions, then refresh ChatGPT. Under **Character references**, select **Use Aarohan references (5)** to load exact local copies of Anaya, Arjun, Mehak, Trisha and Veer from the user's `Downloads/Storyboard Studio` folder. **Choose other images** supports 1-8 PNG/JPG/WebP files (10 MB each, 40 MB combined). Full-resolution images remain in extension-local storage until **Attach all to ChatGPT** is selected. `unlimitedStorage` accommodates these original-size images without the normal 10 MB local-storage cap. This copy includes the user's five reference assets; remove/replace those assets before distributing a generic release.

**Attach all to ChatGPT** fills the site's image file input, or pastes files into the composer if the input is not mounted. This requests uploads; it does not submit a message. Check every reference thumbnail in ChatGPT and wait for upload indicators to finish. Select **All attachments are uploaded and ready**, then **Start generating**. The first storyboard prompt and images are sent together, with a named character guide. Later frames reuse that conversation's images. Reference images are not image-generation outputs and are not downloaded again.

The character-batch workbook marked `REFERENCE SET REQUIRED:` requires all five core characters and explicit upload confirmation. Confirmation belongs to a particular reference set, tab and conversation. Switching to another conversation requires attaching/confirming there. Repeated Attach requests are blocked to avoid duplicate uploads. A new chat's initial `/` to `/c/<id>` transition is adopted only when the exact first submitted prompt is observed. Manual composer drafts and pending frames are preserved. Reference selection does not change original story numbering or batch order.

If ChatGPT does not show all attachments after the request, attach the same files using ChatGPT's own upload control before confirming. Smart Flow cannot certify upload completion from a synthetic event; the employee's visible review is required. Keep the attachments in the composer until the first frame sends. Repeat mode still sends its exact configured text, even with references selected.

Workbook: `Y:\Veto Logs Backup\Aarohan\Smart Flow Uploads\Aarohan_1.1_1.2_Character_Batches_Smart_Flow_WITH_REFERENCES.xlsx`. It contains 227 unique images across 41 cast batches; original frame 228 is an editorial-only transition retained in the chronology map. Queue position 1 is original Frame 032. All generation prompts use the 3D-anime master, and original animation tabs are preserved as references.

Verification: 79 queue checks across 34 scenarios, 36 popup checks, 14 background checks, 27 real installed-extension reference checks, and 17 workbook checks. The installed test uses the actual five PNGs and workbook with actual Chrome storage/file inputs/downloads, but a local simulated ChatGPT page. No live reference upload or image generation was performed in the user's normal profile. Live page compatibility and generated identity/style fidelity still require user review.

# Smart Flow v20 — Aurora UI Edition

## v20.4.0 — upload/start reliability and interface audit

The exact `1.1_Smart_Flow_UPLOAD.xlsx` exposed an import-completion bug: controls were refreshed while the import lock was still held, temporarily leaving Start disabled. Import now releases the lock and refreshes immediately. The workbook's 110 frames and 3D-anime/hall-entry instructions are preserved.

- **Check connection** verifies the active ChatGPT tab, message box and installed content-script version without sending a prompt. Start/Resume run the same check. After upgrading, refresh ChatGPT so its script matches the popup.
- **Start / resume from frame** is on the main screen. The position defaults to the current imported frame; typed choices survive UI refresh. Set frame changes position without starting, with confirmation for a pending frame or a jump. Different user drafts and other tabs' pending frames are preserved. Imported position is distinct from arbitrary spreadsheet frame labels.
- Start, Pause, Resume and Stop stay visible at the bottom. Ready-state instructions explain the next action; completed upload details collapse so they do not hide the work controls. Progress count and percentage are separated. Repeat settings sit below the normal storyboard flow. Only paused/stopped queues offer Resume.
- Cleared unsent prompts can restore after a stable check, up to three attempts. A different draft, changed conversation, new output or uncertain Send pauses rather than submitting a duplicate. Both textarea and rich-text composers are covered. A temporary composer remount can wait up to ten seconds.
- Storyboard autosave now waits for Chrome to report a finished download, just like repeat mode. An interrupted save pauses; Resume retries saving the same image. Signatures on existing images and older hydrated image history do not count as a new result.
- Error logs now report the manifest version and queue mode instead of hardcoded v19. Pending work stays tied to its ChatGPT conversation.

Reload the same extension folder in `chrome://extensions`, refresh the ChatGPT conversation, and reopen Smart Flow. Existing queues remain in storage. If the revised 3D workbook is already imported, it does not need importing again just to upgrade the extension.

See [the audit and limitations](AUDIT-2026-10-29.md). Actual installed-extension acceptance artifacts and screenshots are saved in `D:\Vs - Code Work\Smart-Flow-Audit-20261029`.

## v20.3.0 — repeat a custom message

Open **Repeat a message** at the top of the popup. The default message is **Next**; replace it with your own text and choose **Number of images** (1–1,000, default 10). Click **Prepare repeat run**, then **Start generating**. No spreadsheet is needed. Preparing a repeat run asks before replacing an existing queue and its progress; downloaded files are kept.

Set up the sequence, image instructions and reference images in the same ChatGPT conversation first. Repeat mode sends the message exactly as entered, with no master style, frame label or image-format suffix added. Each cycle waits for a new generated image, starts saving it, and waits for Chrome to report the download complete before advancing. Filename conflicts still use Chrome's `uniquify` behavior.

**Pause**, **Resume** and **Stop** use the normal controls. If saving fails, the run pauses on that image; **Resume** checks an existing download or retries saving the same generated image without sending another prompt. Manual completion cannot skip the required save. Text-only replies or no new image after the generator becomes idle pause the loop. Existing user drafts are preserved. The repeat count is finite and persists across popup reopening.

To return to storyboard automation, upload an Excel/CSV/TXT file. It resets the mode to the normal storyboard prompt builder. The repeat settings remain available for later use. To apply this update, reload the same extension folder in `chrome://extensions`, then refresh the ChatGPT tab.

Verification: `tests/test-repeat-mode.py` passes 39 queue checks across 16 scenarios plus 29 checks against the actual popup. `tests/repeat-background-checks.mjs` passes 14 checks against the actual download/status message handlers, including ownership and filename conflicts. These use synthetic generation and download APIs; no live ChatGPT image request or image credits were used. Existing upload validation passes 48 checks for Smart Flow and 48 for Storyboard Studio.

## v20.2.1 — clear upload validation

Excel and CSV uploads are validated before replacing the queue. Incompatible uploads show a persistent notice with the problem, affected rows where applicable, and instructions to use **Download example Excel**. Existing progress and pending frames are kept on validation failure.

The first worksheet needs a **Scene Prompt** header and one nonempty scene per data row. **Frame** and **Master Prompt** are optional; missing columns are disclosed. Use a single shared master prompt and put frame-specific instructions in Scene Prompt. Incomplete rows, conflicting masters, duplicate storyboard headers and formulas in storyboard columns are rejected. Successful uploads disclose unused sheets/columns. Reload the existing extension folder to apply the update.

Compact premium redesign based on the provided Smart Flow reference.

- Preserves v19 automation scripts (`content.js`, `background.js`, `popup.js`, `importer.js`) unchanged.
- Adds a luminous navy gradient progress card, subtle mint glow, refined upload highlight, and color-coded controls: teal Start, amber Pause, blue Resume, red Stop.
- Keeps Excel/CSV/TXT import, sample workbook, history, diagnostics, and logo customization.

## Installation
Chrome > chrome://extensions > disable previous Smart Flow > enable Developer mode > Load unpacked > select the `smart-flow-v20` folder. Refresh ChatGPT.

Note: UI code passed structural checks; full image-generation automation has not been live-tested in this update.


## v20.2 Layout audit
UI-only CSS hardening: bounded multi-line current frame display, overflow-safe filenames/labels, restricted advanced prompt editors, wrapping support/error text, history scrolling, responsive control sizing, and accessible dropdown alignment. Automation/background/import scripts unchanged.
