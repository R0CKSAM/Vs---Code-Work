VETO SCOREBOARD MAKER - PORTABLE WINDOWS PACKAGE
================================================

FIRST USE
1. Install 64-bit Python 3.14 from python.org. Keep pip and Tcl/Tk selected.
2. Copy this whole VetoScoreboardMaker folder to the new Windows PC.
3. Double-click SETUP_AND_START.lnk.
4. Wait for setup to finish. The browser opens automatically.

NORMAL USE
- START_SCOREBOARD.lnk starts the server and opens the editor.
- STOP_SCOREBOARD.lnk stops the server.
- Local editor: http://127.0.0.1:8080/scoreboard
- Change the host, port, or allowed LAN networks in scoreboard_settings.ps1.

CODE UPDATES
1. On the development PC, run build_scoreboard_code_update.ps1.
2. Copy only VetoScoreboardCodeUpdate.zip into this portable folder.
3. Double-click APPLY_CODE_UPDATE.lnk.
4. The updater verifies all three runtime files, backs up the current code,
   replaces it, and restarts the scoreboard.
- Updates preserve scoreboard_settings.ps1, data/uploads, python_packages,
  wheels, FFmpeg, logs, and every local project/export.

LAN USE
1. Right-click ENABLE_LAN_ACCESS_RUN_AS_ADMIN.lnk, choose Run as administrator,
   and approve it once.
2. Open http://THIS-PC-IP:8080/scoreboard from another device.
3. The default firewall setting allows private 192.168.x.x networks only.

DEPENDENCIES
- Python 3.14 is the only prerequisite installed on Windows.
- Dependency wheels are bundled in wheels and FFmpeg is bundled in
  tools/ffmpeg/bin, so setup needs no internet after Python is installed.
- All scoreboard Python packages stay inside this folder's python_packages
  directory; setup does not create a virtual environment or Windows service.
- DeckLink SDI output also requires Blackmagic Desktop Video. Install the driver
  supplied by Blackmagic Design on every PC that has the DeckLink card.

DATA
- Uploaded images are kept in data/uploads inside this folder.
- Existing uploaded images from the source PC are included. Saved project JSON
  files can reconnect those images by their generated filename after transfer.
- Runtime logs are kept in logs.
- Save project writes to data/projects on the hosting PC. Open project lists
  the shared projects for every connected operator. Stale saves are rejected;
  reopen the latest version or choose Save a copy to preserve your changes.
- Open project also has Import JSON and Download JSON for manual transfers.
  PNG and MP4 exports still download to the operator's browser.
- Move the complete data folder (projects AND uploads) to migrate saved work.
  A JSON download alone does not contain image files.
- For code updates replace scoreboard_app.py, scoreboard_web.py and
  scoreboard_web.html together, or use the code-update ZIP. Keep data intact.
- Build with -IncludeUploads to include current projects and images in a
  portable package. If SCOREBOARD_WEB_UPLOAD_DIR overrides uploads, projects
  are stored in a sibling projects folder; copy that data location manually.
- Browser recovery drafts remain local; use Save project to share a version.
- Shared operator names identify edits; they are not account authentication.
