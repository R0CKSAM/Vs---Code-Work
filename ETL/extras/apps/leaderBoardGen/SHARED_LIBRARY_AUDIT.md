# Shared Library Workflow Verification

Verified 14 September 2026.

## Workflow

Creators and the live operator use the same hosted scoreboard URL. A completed
save wakes connected browsers through a revision notification. The operator's
library updates without navigation, without replacing their draft, and without
pushing anything On Air. The operator still selects a preset and explicitly
pushes it. Connections retry automatically and recover missed saves. A periodic
30-second refresh also picks up external file changes and provides recovery.

Browsers already open during this deployment need one refresh to load the new
JavaScript. Subsequent preset saves do not require browser reloads.

## Results

- 96 tests passed; one retired project-editor browser test skipped.
- Two independent browser contexts: creator save appeared in the operator's
  library in 0.130 seconds in the local test. This is not a guaranteed LAN SLA.
- Operator offline/reconnect recovered missed saves without navigation.
- Operator unsaved draft and software program frame remained unchanged.
- Simultaneous duplicate saves created exactly one preset.
- Simulated failed file replacement did not publish a new revision or leave a
  temporary preset. Existing saved data remained intact.
- New runtime instance preserved saved data and changed its notification revision.
- A malformed file did not hide valid presets or get deleted. Warnings were
  reported; further saves were blocked to avoid incomplete duplicate checks.
- Production after deployment: healthy, 19 presets readable, no library warnings,
  matching snapshot/notification revisions. SDI left stopped.

## Limits

One scoreboard host process owns the shared data directory. Concurrent unrelated
host processes writing the same directory are not supported by the in-process
save lock. Use backups and a UPS; atomic replacement cannot guarantee survival
of every disk, filesystem, power, or hardware failure. This test did not simulate
an actual power cut or benchmark a separate physical LAN client. Suspended
browser tabs may receive updates later; returning to the tab triggers refresh.

A server crash/restart does not automatically restart SDI or select a new
program. The operator must verify state and start output deliberately. Workflow
operator IDs are not a substitute for authenticated network access controls.

Regression tests: `ETL/tests/test_scoreboard_shared_live.py` plus the existing
scoreboard rendering, media, template-library, program, and popup test suites.
