"""Fail closed on an unfinished repair dependency or insufficient disk reserve."""
import argparse
import json
from pathlib import Path
import shutil
import time


def dependency_ready(path):
    if not path.exists():
        return True
    request = json.loads(path.read_text(encoding="utf-8-sig"))
    state = json.loads(Path(request["state_path"]).read_text(encoding="utf-8-sig"))
    status = state.get("status")
    if status in request["success_statuses"]:
        return True
    if status != "running":
        raise RuntimeError(f"Required repair is not complete: {status}. Inspect {request['state_path']}")
    return False


def check_capacity(data, archive, data_gib, archive_gib):
    readings = []
    for label, path, minimum in (("data", data, data_gib), ("archive", archive, archive_gib)):
        if minimum <= 0:
            raise ValueError("Disk reserves must be positive")
        free = shutil.disk_usage(path).free / 1024**3
        readings.append(dict(storage=label, path=str(path), free_gib=round(free, 2), reserve_gib=minimum))
        if free < minimum:
            raise RuntimeError(f"{label} has {free:.1f} GiB free; {minimum} GiB reserve required at {path}. No new day started.")
    return readings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency", type=Path)
    parser.add_argument("--wait-hours", type=float, default=24)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--data-reserve-gib", type=float, default=50)
    parser.add_argument("--archive-reserve-gib", type=float, default=100)
    args = parser.parse_args()
    if not 0 < args.wait_hours <= 48:
        parser.error("wait-hours must be in (0,48]")
    if args.dependency:
        deadline = time.monotonic() + args.wait_hours * 3600
        while not dependency_ready(args.dependency):
            if time.monotonic() >= deadline:
                raise RuntimeError("Required repair did not complete within the wait window")
            print(f"Waiting for verified repair: {args.dependency}", flush=True)
            time.sleep(60)
    if args.data or args.archive:
        if not args.data or not args.archive:
            parser.error("data and archive must be supplied together")
        print(json.dumps(check_capacity(args.data, args.archive, args.data_reserve_gib, args.archive_reserve_gib)), flush=True)


if __name__ == "__main__":
    main()
