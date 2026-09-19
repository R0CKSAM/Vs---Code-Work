# Players Stats Importer

Python and the scoreboard's existing dependencies are sufficient. Run commands
from the folder containing scoreboard_app.py using that installation's Python.

## Preview First

```powershell
python .\import_davis_players.py
```

This creates a timestamped review folder under data/davis_import containing
index.html, individual PNG previews, review.csv, and review.json. No presets are
published. The included roster is the user's supplied 2026 round-2 list, NOT an
independently verified live nomination feed. It contains 63 players and 14
captains. Explicit captain rows are excluded; a playing captain must also have
an explicit player row with the official profile ID.

Profile requests are sequential, spaced by one second, limited to 20 seconds and
5 MB. Successful pages are cached for 24 hours. HTTP 401/403/429 stops further
profile requests for that run; no access-control workaround is attempted.
Re-running resumes from fresh successful cache entries. On 14 September the
official profile endpoint returned 403 to Python, so the initial batch was run
offline and carries roster-only names/countries with unverified stats blank.

```powershell
python .\import_davis_players.py --offline
python .\import_davis_players.py --offline --profile-dir C:\Profiles
```

Operator-supplied profile pages must be UTF-8 HTML named PROFILE_UUID.html.
The parser validates the H1 against the roster name and extracts a labelled Age
and available headshot URL. It does not guess W/L, debut, hand or nomination
status from rankings. Review headshots for suitability/permission and provide
a local cutout through image_file; remote images are not automatically fetched.

Country aliases are standardized in the new records. Existing presets are not
renamed. Exact normalized player names/countries are checked for duplicates;
abbreviations such as D.K. Suresh versus Dhakshineswar Suresh need human review.

## Review And Publish

### Using Your Existing Scraper

The importer accepts the CSV produced by daviscup_scraper.py, including its
FAVOURATE HAND column spelling:

```powershell
python .\import_davis_players.py --offline --scraper-csv "D:\Veto Logs Backup\images share\daviscup_players.csv"
```

Use this after the scraper has successfully created that CSV. The importer does
not run Selenium or change your original scraper. Only country/name matches in
the nominated roster are used; captains and other team-page players are excluded.
Duplicate identities are flagged rather than arbitrarily choosing one. Numeric
and hand fields are validated; rejected values appear in review_issues. Valid
CSV values remain unverified until operator review, with the source file recorded.
CSV files do not contain player photos; provide those separately via image_file.
An export containing plausible numbers is not proof of their correctness: check
the scraper's broad Total/Hand label matching against the official profile.

Inspect index.html/review.csv. In review.json, fill verified values under each
player's config, record their field_sources, optionally set image_file to a
local image path, and set approved to the JSON boolean true for reviewed rows.
Total W/L means Davis Cup total, not ATP or current-season results. Blank fields
may remain intentionally, but the reviewer must explicitly approve that card.

```powershell
python .\import_davis_players.py --publish .\data\davis_import\review-TIMESTAMP\review.json
```

Use --server http://HOST:8080 when the scoreboard runs elsewhere. The command
uploads approved local images and creates Players Stats presets through the
host API, triggering its normal no-reload library notifications. It never calls
live-output endpoints. Existing presets are skipped, not overwritten. A missing
save acknowledgement can be recovered by rerunning: duplicate checks skip the
already-created preset. Results are checkpointed in publish-results.json.

Unreadable hosted records block publishing until the host repairs them. Back up
the host data folder before bulk imports. Neither publication nor review changes
the existing library's country labels or other operators' drafts.

## Update an Existing Saved Template

Choose the saved player, edit the preview, then click Save template. Use
Update saved template with the host-managed editor ID/password to replace that
same preset. The confirmation does not push anything On Air. Save template with
a different name creates a separate preset without an editor password.

Updates retain the preset ID, notify connected browsers, and back up the previous
JSON in the storage folder's history directory. If another operator has saved
since you opened the preset, updating is rejected and your preview is retained.
Reopen the saved preset before retrying, or save your preview under another name.

For reviewed photo batches, fill_davis_photos.py accepts --review and --output.
It prompts for the host editor password (or reads SCOREBOARD_EDITOR_PASSWORD),
updates only empty player_path fields, and preserves every other saved setting.
Existing photos are always skipped. A new output directory is required per run;
results and before/after library snapshots are retained there. It never calls
live-output endpoints. Review the cutouts and confirm image-use rights first.
