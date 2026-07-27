#!/usr/bin/env python3
"""
livecheck.py — standalone "is this YouTube stream actually live?" checker.

Combines three independent signals so a fake has to fool all of them at once:

  1. FRAME-LOOP DETECTION
     Sample video frames over time, perceptually hash them, and look for
     near-duplicate frames recurring at a *consistent period*. A real live
     broadcast basically never repeats itself exactly; a looped file does,
     on a fixed cycle.

  2. YOUTUBE LIVE TELEMETRY
     Pull yt-dlp's metadata for the video repeatedly (no API key needed).
     A genuinely live stream has a concurrent_view_count that keeps moving
     and a live_status that stays 'is_live'. A stream that's technically
     "Live" on YouTube but actually replaying a finished broadcast tends to
     show a frozen or missing viewer count, or inconsistent live flags.

  3. ON-SCREEN CLOCK CHECK (optional, needs --clock-roi + pytesseract)
     If the broadcast has a visible clock/ticker (e.g. "EST 01:32"), crop
     that region each sample, OCR it, and check the time actually advances
     in step with wall-clock time. This is the strongest single tell when
     available — it's the broadcaster's own proof of liveness.

USAGE
    python livecheck.py "https://www.youtube.com/watch?v=XXXXXXXX"
    python livecheck.py URL --interval 15 --duration 20
    python livecheck.py URL --clock-roi 1130,600,180,40   # x,y,w,h in pixels

REQUIREMENTS
    pip install yt-dlp Pillow imagehash requests
    ffmpeg on PATH
    optional for clock check: pip install pytesseract  +  tesseract-ocr binary

OUTPUT
    A single verdict: LIVE / LIKELY LIVE / SUSPICIOUS / FAKE LIVE (looped),
    with the evidence that led there. Exit code 0 = looks live, 1 = fake,
    2 = inconclusive (not enough evidence either way).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image
import imagehash

try:
    import pytesseract
    HAVE_OCR = True
except ImportError:
    HAVE_OCR = False


# --------------------------------------------------------------------------
# ffmpeg / yt-dlp plumbing
# --------------------------------------------------------------------------

def resolve_ffmpeg() -> str:
    """Locate an ffmpeg executable without relying solely on shell PATH.

    Order: explicit LIVECHECK_FFMPEG env var -> PATH -> WinGet's versioned
    install folder (winget installs succeed even when the current shell's
    PATH hasn't been refreshed to see them yet).
    """
    configured = os.getenv("LIVECHECK_FFMPEG")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(
            f"LIVECHECK_FFMPEG points to a missing file: {candidate}"
        )

    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    matches = list(winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
    if matches:
        return str(max(matches, key=lambda p: p.stat().st_mtime))

    raise FileNotFoundError(
        "ffmpeg not found. It's installed via WinGet but not detected — "
        "close and reopen your terminal so PATH refreshes, or set "
        "LIVECHECK_FFMPEG to the full path of ffmpeg.exe (e.g. via "
        "'$env:LIVECHECK_FFMPEG=\"C:\\path\\to\\ffmpeg.exe\"' in PowerShell)."
    )


def yt_dlp_json(youtube_url: str) -> dict:
    """Fetch full metadata dict for the video via yt-dlp, no download."""
    result = subprocess.run(
        ["yt-dlp", "-J", "--no-warnings", youtube_url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def get_stream_url(youtube_url: str) -> str:
    result = subprocess.run(
        ["yt-dlp", "-g", "-f", "best[height<=480]", youtube_url],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().splitlines()[0]


def grab_frame(stream_url: str) -> Image.Image:
    result = subprocess.run(
        [
            resolve_ffmpeg(), "-y",
            "-i", stream_url,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "pipe:1",
        ],
        capture_output=True, check=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")


# --------------------------------------------------------------------------
# Signal 1: frame-loop detection
# --------------------------------------------------------------------------

@dataclass
class FrameRecord:
    timestamp: float
    hash: "imagehash.ImageHash"


@dataclass
class LoopMatch:
    frame_time: float
    matched_time: float
    period: float
    distance: int


class LoopDetector:
    def __init__(self, hash_size: int = 16, match_threshold: int = 6,
                 period_tolerance: float = 5.0):
        self.match_threshold = match_threshold
        self.period_tolerance = period_tolerance
        self.hash_size = hash_size
        self.frames: list[FrameRecord] = []
        self.matches: list[LoopMatch] = []

    def add_frame(self, image: Image.Image, timestamp: float) -> Optional[LoopMatch]:
        h = imagehash.phash(image, hash_size=self.hash_size)
        best_match, best_distance = None, None
        for prev in self.frames:
            d = h - prev.hash
            if d <= self.match_threshold and (best_distance is None or d < best_distance):
                best_match, best_distance = prev, d
        self.frames.append(FrameRecord(timestamp, h))
        if best_match is not None:
            m = LoopMatch(timestamp, best_match.timestamp,
                           timestamp - best_match.timestamp, best_distance)
            self.matches.append(m)
            return m
        return None

    def novelty_ratio(self) -> float:
        if not self.frames:
            return 1.0
        return 1 - (len(self.matches) / len(self.frames))

    def dominant_period(self):
        if len(self.matches) < 3:
            return None
        periods = sorted(m.period for m in self.matches)
        best_cluster: list[float] = []
        for p in periods:
            cluster = [q for q in periods if abs(q - p) <= self.period_tolerance]
            if len(cluster) > len(best_cluster):
                best_cluster = cluster
        if len(best_cluster) < 3:
            return None
        return (sum(best_cluster) / len(best_cluster), len(best_cluster))

    def verdict(self) -> dict:
        novelty = self.novelty_ratio()
        period_info = self.dominant_period()
        looping, reason = False, "no periodic repetition detected"
        if period_info is not None:
            period, count = period_info
            looping = True
            reason = f"{count} frame-matches recur at a consistent ~{period:.0f}s interval"
        elif novelty < 0.5 and len(self.frames) >= 10:
            looping = True
            reason = f"only {novelty:.0%} of sampled frames were visually novel"
        return {
            "signal": "frame_loop",
            "flagged_fake": looping,
            "novelty_ratio": round(novelty, 3),
            "frames_sampled": len(self.frames),
            "dominant_period_seconds": round(period_info[0], 1) if period_info else None,
            "reason": reason,
        }


# --------------------------------------------------------------------------
# Signal 2: YouTube live telemetry
# --------------------------------------------------------------------------

class TelemetryWatcher:
    """Polls yt-dlp metadata over the sampling window to check the live
    signals YouTube itself exposes actually behave like a live stream."""

    def __init__(self, youtube_url: str):
        self.url = youtube_url
        self.samples: list[dict] = []

    def poll(self, elapsed: float) -> None:
        try:
            info = yt_dlp_json(self.url)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return
        self.samples.append({
            "elapsed": elapsed,
            "live_status": info.get("live_status"),
            "concurrent_view_count": info.get("concurrent_view_count"),
            "is_live": info.get("is_live"),
        })

    def verdict(self) -> dict:
        if len(self.samples) < 2:
            return {
                "signal": "youtube_telemetry",
                "flagged_fake": False,
                "reason": "not enough metadata polls to judge (need >= 2)",
                "inconclusive": True,
            }

        statuses = {s["live_status"] for s in self.samples}
        is_live_flags = {s["is_live"] for s in self.samples}
        views = [s["concurrent_view_count"] for s in self.samples
                 if s["concurrent_view_count"] is not None]

        problems = []
        if statuses != {"is_live"}:
            problems.append(f"live_status was not consistently 'is_live' (saw: {statuses})")
        if is_live_flags != {True}:
            problems.append(f"is_live flag was not consistently True (saw: {is_live_flags})")
        if len(views) >= 2 and len(set(views)) == 1:
            problems.append(
                f"concurrent viewer count never changed across {len(views)} polls "
                f"(stuck at {views[0]}) — real live streams' viewer counts fluctuate"
            )
        if not views:
            problems.append("no concurrent_view_count reported at all")

        flagged = bool(problems)
        reason = "; ".join(problems) if problems else (
            "live_status stayed 'is_live' and viewer count moved across polls, "
            "consistent with a genuine live stream"
        )
        return {
            "signal": "youtube_telemetry",
            "flagged_fake": flagged,
            "reason": reason,
            "polls": len(self.samples),
            "viewer_counts_seen": views,
        }


# --------------------------------------------------------------------------
# Signal 3: optional on-screen clock OCR
# --------------------------------------------------------------------------

TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})(?::(\d{2}))?")


class ClockWatcher:
    def __init__(self, roi: tuple[int, int, int, int]):
        self.roi = roi  # x, y, w, h
        self.readings: list[tuple[float, float]] = []  # (elapsed, seconds_since_midnight)

    def sample(self, image: Image.Image, elapsed: float) -> None:
        if not HAVE_OCR:
            return
        x, y, w, h = self.roi
        crop = image.crop((x, y, x + w, y + h))
        # upscale + grayscale generally improves OCR on small overlay text
        crop = crop.convert("L").resize((w * 3, h * 3), Image.LANCZOS)
        text = pytesseract.image_to_string(
            crop, config="--psm 7 -c tessedit_char_whitelist=0123456789:."
        )
        m = TIME_RE.search(text)
        if not m:
            return
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        seconds = hh * 3600 + mm * 60 + ss
        self.readings.append((elapsed, seconds))

    def verdict(self) -> dict:
        if not HAVE_OCR:
            return {"signal": "clock_ocr", "flagged_fake": False,
                     "reason": "pytesseract not installed — skipped", "inconclusive": True}
        if len(self.readings) < 2:
            return {"signal": "clock_ocr", "flagged_fake": False,
                     "reason": "could not read a clock value from the ROI in >=2 samples",
                     "inconclusive": True}

        deltas = []
        for (e1, c1), (e2, c2) in zip(self.readings, self.readings[1:]):
            wall_delta = e2 - e1
            clock_delta = (c2 - c1) % 86400  # handle midnight wrap
            deltas.append(clock_delta - wall_delta)

        # A frozen/looped clock will show clock_delta far off wall_delta repeatedly.
        bad = [d for d in deltas if abs(d) > 20]  # >20s drift per interval = suspicious
        flagged = len(bad) >= max(2, len(deltas) // 2)
        reason = (
            f"on-screen clock did not track wall-clock time in {len(bad)}/{len(deltas)} "
            f"intervals (checked drift > 20s per step)"
            if flagged else
            f"on-screen clock advanced in step with wall-clock time across {len(deltas)} intervals"
        )
        return {
            "signal": "clock_ocr",
            "flagged_fake": flagged,
            "reason": reason,
            "readings": len(self.readings),
        }


# --------------------------------------------------------------------------
# Sampling loop tying it all together
# --------------------------------------------------------------------------

def run(youtube_url: str, interval: int, duration_min: float,
        hash_size: int, threshold: int, clock_roi: Optional[tuple], verbose: bool):

    loop_detector = LoopDetector(hash_size=hash_size, match_threshold=threshold)
    telemetry = TelemetryWatcher(youtube_url)
    clock = ClockWatcher(clock_roi) if clock_roi else None

    print(f"Checking: {youtube_url}")
    print(f"Sampling every {interval}s for {duration_min} min "
          f"(~{int(duration_min * 60 / interval)} samples)")
    if clock_roi:
        if not HAVE_OCR:
            print("  NOTE: --clock-roi given but pytesseract is not installed; "
                  "clock check will be skipped (pip install pytesseract).")
        else:
            print(f"  Clock ROI: {clock_roi}")
    print()

    start = time.monotonic()
    end = start + duration_min * 60
    stream_url = get_stream_url(youtube_url)
    telemetry.poll(0.0)

    sample_count = 0
    while time.monotonic() < end:
        if sample_count > 0 and sample_count % 10 == 0:
            stream_url = get_stream_url(youtube_url)

        elapsed = time.monotonic() - start
        try:
            frame = grab_frame(stream_url)
        except subprocess.CalledProcessError:
            stream_url = get_stream_url(youtube_url)
            frame = grab_frame(stream_url)

        match = loop_detector.add_frame(frame, elapsed)
        if clock is not None:
            clock.sample(frame, elapsed)
        telemetry.poll(elapsed)

        tag = f"FRAME MATCH (Δ{match.period:.0f}s, dist={match.distance})" if match else "new frame"
        print(f"  t={elapsed:6.0f}s  {tag}")

        sample_count += 1
        time.sleep(interval)

    loop_result = loop_detector.verdict()
    telemetry_result = telemetry.verdict()
    clock_result = clock.verdict() if clock is not None else {
        "signal": "clock_ocr", "flagged_fake": False,
        "reason": "no --clock-roi provided — skipped", "inconclusive": True,
    }

    return combine([loop_result, telemetry_result, clock_result])


def combine(results: list[dict]) -> dict:
    decisive = [r for r in results if not r.get("inconclusive")]
    fake_votes = [r for r in decisive if r["flagged_fake"]]
    live_votes = [r for r in decisive if not r["flagged_fake"]]

    if not decisive:
        verdict, exit_code = "INCONCLUSIVE", 2
    elif len(fake_votes) >= 2:
        verdict, exit_code = "FAKE LIVE (looped/pre-recorded)", 1
    elif len(fake_votes) == 1 and len(live_votes) == 0:
        verdict, exit_code = "SUSPICIOUS", 2
    elif len(fake_votes) == 1:
        verdict, exit_code = "SUSPICIOUS — one signal flagged, others clean", 2
    else:
        verdict, exit_code = "LIVE — no signals indicate looping/faking", 0

    return {"verdict": verdict, "exit_code": exit_code, "signals": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="YouTube stream URL")
    parser.add_argument("--interval", type=int, default=20, help="seconds between samples")
    parser.add_argument("--duration", type=float, default=20, help="minutes to sample for")
    parser.add_argument("--hash-size", type=int, default=16)
    parser.add_argument("--threshold", type=int, default=6, help="max Hamming distance for a frame match")
    parser.add_argument("--clock-roi", type=str, default=None,
                         help="x,y,w,h pixel box around an on-screen clock, e.g. 1130,600,180,40")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = parser.parse_args()

    clock_roi = None
    if args.clock_roi:
        try:
            clock_roi = tuple(int(v) for v in args.clock_roi.split(","))
            assert len(clock_roi) == 4
        except (ValueError, AssertionError):
            parser.error("--clock-roi must be x,y,w,h e.g. 1130,600,180,40")

    result = run(args.url, args.interval, args.duration, args.hash_size,
                 args.threshold, clock_roi, verbose=not args.json)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "=" * 60)
        print(f"VERDICT: {result['verdict']}")
        print("=" * 60)
        for sig in result["signals"]:
            flag = "⚠ FAKE SIGNAL " if sig.get("flagged_fake") else ("· skipped " if sig.get("inconclusive") else "✓ clean ")
            print(f"[{flag}] {sig['signal']}: {sig['reason']}")

    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()