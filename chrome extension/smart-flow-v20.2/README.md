# v20.8.6 - timestamped upload aliases

Frame 16 stopped before Send because ChatGPT displayed a valid location upload as
`LOC_FESTIVAL(20261106-062938).png`. Its Anaya and prop uploads used numeric suffixes.
The shared filename matcher now canonicalizes numeric and YYYYMMDD-HHMMSS /
YYYYMMDD_HHMMSS timestamp suffixes, including repeated suffixes. Upload verification
and requested-reference lookup use the same canonicalization. The expected file
stem must still match; unrelated files remain blocked. Hidden stale composer
controls are ignored, and a true mismatch identifies the unexpected/expected names.

175 queue/recovery checks, 36 popup checks and 38 reference-matcher checks cover
this behavior, including the observed timestamp, stacked suffixes, hidden stale
labels and unrelated timestamped files. The update was installed in existing
Chrome. Frame 16 uploaded all three references, automatically approved and sent
its scene without resending completed Frames 9-15. See the latest production
check artifact for saving/advance verification.

# v20.8.5 - live upload filename verification

Live ChatGPT uploads were renamed to `LOC_FESTIVAL(7).png` and
`Aarohan technical crew reference board(2).png`. Composer labels also include
controls such as `Remove LOC_FESTIVAL(7).png`. The old literal filename guard
incorrectly rejected these successfully uploaded reference images.

Approval now recognizes numeric duplicate-name suffixes before the extension,
case differences and removal-control prefixes for the expected source files.
Unrelated filenames and unexpected extra images still block the run. Reference
matching also recognizes numbered upload-name variants. Version 20.8.4 added
control-label matching; 20.8.5 covers the inspected server-numbering behavior.
Regression checks cover expected and unrelated numbered filenames.

The live test restarted from S01_F009, preserving the existing PNG with Chrome's
unique-filename behavior. Both location and crew references uploaded, automatic
approval completed, and the current scene was sent without a confirmation click.
See the production audit artifacts for the final download/advance result.

# v20.8.3 - technical crew catalog and filenames with spaces

The user-supplied `Aarohan technical crew reference board.png` is verified as
Stagehand (left) and Young Volunteer (right). Both identities and Volunteer /
technical crew aliases map to that original image in the pack catalog. The pack
now has 15 images and 15 mapped named identities. Reload the pack folder once to
store the new image in Chrome. Existing source frames and image pixels are kept.
Filename matching now recognizes complete catalog filenames containing spaces;
it does not incorrectly report the final `board.png` token as a missing file.
The provided scene generation was left untouched while metadata was prepared.

# v20.8.2 - live ChatGPT search-unit layout

Live page inspection showed that current user and assistant turns use
`data-chatgpt-search-unit-key` and `data-chatgpt-search-message-ids`, without the
older `data-message-author-role` markers. Generated images can be separate tool
blocks with their own message IDs. Smart Flow now supports both layouts and
normalizes repeated message IDs, while still requiring each image owner to
follow the submitted current user turn. Historical previews remain rejected.

Live diagnostics verified the previously missing user/assistant IDs and current
prompt anchor. Resuming pending Frame 10 reported its missing crew references
within seconds, instead of waiting 18 minutes or crediting an older image.
The scene was not resent and no new image was saved. Queue progress was retained.
The user's supporting-cast image was restored to the composer and left unsent.

Tests reproduce the inspected search-unit structure for normal tool images,
reference follow-ups, missing-character text replies and upgraded pending frames
that had no old author-role baseline. Production remains blocked on the two
missing crew designs; Frame 9's duplicate output is still invalid.

# v20.8.1 - production audit: current-message image ownership

The live audit found `009_S01_F009.png` byte-identical to Frame 5 while Frame 9's
assistant response requested references. A previously unseen historical preview
could be accepted when conversation history hydrated after the baseline snapshot.
The audit paused the extension queue while preserving pending Frame 10.

Every saved output must now belong to an identified assistant turn after the
current submitted user message. Missing owners, historical turns and a later
unrelated user prompt cannot produce a successful frame. Collapsed long prompts
are matched using their initial text plus the frame label. Reference follow-ups
reset the submitted-message anchor for the same pending frame.

A second safeguard hashes each download. Reusing the same image bytes for another
frame in the same queue blocks the download and frame advancement. Retrying a
save for the same frame remains supported. Old files are not deleted or replaced.
Frame 9's existing PNG must be treated as invalid and needs regeneration once its
missing supporting-character references are supplied.

The popup version now comes from Chrome's loaded manifest so editing files alone
does not misleadingly display a version that has not been reloaded. Regression
checks cover hydrated older images with unseen IDs, unowned previews, collapsed
prompts, changed user messages, historical reference questions and image hashes.

# v20.8.0 - complete reference catalog and requested-image recovery

The pack loader now stores every image in the selected `references` folder,
including files not listed for the imported scene. `Reference_Catalog.json` maps
character names and aliases to original image filenames. The known Aarohan pack
indexes 14 images and 13 named character identities, including all eight named
people on `CAST_SUPPORT.png`. The folder's `Reference_Mapping_Report.csv` lists
these matches. Image pixels and source prompts remain unchanged.

Cast names in a frame's CURRENT VISIBLE CAST / CROP field add matching reference
images before generation. If a new ChatGPT response asks for a known reference
instead of producing an image, Smart Flow attaches the matching local file,
uses the configured upload approval mode, and sends a follow-up asking to finish
only that pending scene. It does not resend the original scene prompt or advance
the frame before its image is generated and saved. Old assistant messages are
ignored; at most two reference follow-ups are allowed for a frame.

Reload Smart Flow and refresh ChatGPT after updating. Pause the queue and load the
complete pack folder again to index every file. Catalog reload is allowed with a
paused pending frame: its progress, prompt and current reference set are kept.
Resume checks a text-only reference request before the normal output timeout.
Adding a new named image such as `CHAR_STAGEHAND.png` makes its name searchable
on the next folder load. A custom catalog can add explicit aliases as version 1:
`{"version":1,"entries":[{"file":"CHAR_STAGEHAND.png","aliases":["Stagehand"]}]}`.

A catalog does not invent an identity. The currently inspected pack and ZIP have
no Stagehand or Young Volunteer reference; neither appears on CAST_SUPPORT.
These roles are recorded as unmapped instead of being assigned to another person.
Their request produces a clear missing-reference message, not an unrelated upload
or an 18-minute silent wait. Add their actual images and reload the folder to
recover that pending frame automatically. Unreviewed generated storyboard images
are not silently promoted to character references.

Tests cover all verified names, possessive aliases, filenames, missing roles,
reference-request recovery, same-frame download tracking, historical requests,
manual/automatic approval, pause/resume and the finite retry budget. Installed
Chrome acceptance uses real original OS files and extension storage with a local
conversation fixture. No new live generation is submitted by these tests.

# v20.7.1 - reference approval choice

Under Frame references, **Reference upload approval** now offers:
- **Automatic - wait 10 seconds, then continue** (default). You may approve early.
  After ten seconds, unrecognized thumbnail markup no longer requires a manual
  confirmation. Visible upload progress, partially loaded images, extra files,
  changed filenames and upload errors still block continuation.
- **Manual - wait for my approval**. Images upload, then the queue pauses until
  you confirm the attachments and Resume.

Keep **Automatically upload references** enabled for this workflow. Approval mode
can be changed while the queue is paused and has no pending frame. The countdown
is saved with the upload request and does not repeat that request after Resume.
It is a timed continuation choice, not proof that the server finished an upload.
Reload Smart Flow and refresh ChatGPT after updating.

Browser regression checks cover both choices, no send before ten seconds, early
approval, blocked progress, upload errors, and no duplicate uploads. The sections
below describe earlier releases.

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
