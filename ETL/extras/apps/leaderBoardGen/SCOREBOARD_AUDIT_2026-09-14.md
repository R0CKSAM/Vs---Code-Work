# Scoreboard Verification - 14 September 2026

## Result

88 automated tests passed, one retired project-editor browser test skipped.
The current template-library browser workflow is covered by replacement tests.
Scoreboard alone was restarted on port 8080. Health and writable upload storage
passed; the program-preview endpoint returned HTTP 200 with a revision header.
SDI was left stopped. War Room and Recorder were not restarted.

## Verified Coverage

- Eight templates, supported HD/UHD canvas sizes, country codes and long text.
- Saved assets surviving relocation, duplicate protection, stale revisions,
  host credential checks and expired editing grants in legacy backend methods.
- Current browser template library, custom uploads and text-box positioning.
- Real FFmpeg video decoding, looping, overlay rendering and MP4 export.
- Preview edits and template changes leave program output unchanged until Push.
- Clear sends black while keeping output active; Stop ends output.
- Program revision checks reject stale actions; output ownership is enforced.
- Desktop and mobile screenshots inspected for overlapping controls.
- Actual DeckLink output 1 ran red, green, blue and black for eight seconds at
  HD 1080i50 without a pipeline error, then stopped through finally cleanup.

## Fixes During Verification

- Paced decoded video frames: burst delivery could make looping video appear
  frozen in the latest-frame output buffer.
- Removed client-supplied internal render scaling at the web boundary to prevent
  arbitrary multipliers bypassing supported canvas sizes.
- Updated legacy test expectations to host-managed credentials without weakening
  production authentication.

## Limits And Follow-Up

This is functional regression and a short hardware smoke test, not certification
that nothing can break in every circumstance or a completed security audit.

- The On Air monitor copies the software output buffer. No physical SDI return
  capture was available; cable/display output needs independent confirmation.
- Long-duration soak, power loss, disk-full, GPU/driver failures and sustained
  multi-user load have not been exhaustively exercised.
- Corrupt individual library JSON can disrupt listing; isolate bad records and
  surface warnings without deleting source files in a subsequent hardening pass.
- Uploaded video demuxing still auto-detects formats. Review explicit demuxer
  selection and resource limits before accepting untrusted public uploads.
- Operator IDs are workflow ownership controls, not a replacement for authenticated
  accounts. Keep access within the authorized LAN/proxy boundary.

## Reproduction

From the workspace root:

```powershell
.\venv\Scripts\python.exe -m pytest ETL/tests/test_scoreboard_app.py ETL/tests/test_scoreboard_program.py ETL/tests/test_custom_media.py ETL/tests/test_scoreboard_library.py ETL/tests/test_broadcast_canvas.py ETL/tests/test_qualifier_rounds.py -q
```

The explicit hardware script is `ETL/tests/manual_scoreboard_sdi_check.py`.
It requires `--confirm-output-1`, refuses active scoreboard SDI, and sends test
colors to output 1. Run it only with operator approval and a free output.

Portable code update rebuilt at `ETL/output/portable/VetoScoreboardCodeUpdate.zip`.
