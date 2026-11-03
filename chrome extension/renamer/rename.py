import re
from pathlib import Path

FOLDER = Path(r"C:\Users\Intern\Downloads\Storyboard Studio")
DRY_RUN = False   # True = only preview; set to False to actually rename

pattern = re.compile(r"(frame_\d+.*)$", re.IGNORECASE)  # keep from "Frame_" onwards

for f in sorted(FOLDER.iterdir()):
    if not f.is_file():
        continue
    m = pattern.search(f.name)
    if not m or m.group(1) == f.name:
        continue                      # no "Frame_xx" found, or nothing to remove
    new = f.with_name(m.group(1))
    if new.exists():
        print(f"SKIP (name already exists): {f.name} -> {new.name}")
        continue
    print(f"{f.name}  ->  {new.name}")
    if not DRY_RUN:
        f.rename(new)