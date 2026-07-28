#!/usr/bin/env python3
"""
livecheck.py — Simple YouTube Clock Extractor

Scans a live stream for an on-screen clock. 
Outputs exactly what it sees: The Time, the Title, and the Link.
If no time is visible, it outputs "None".
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from typing import Optional

import cv2

try:
    import pytesseract
    HAVE_OCR = True
except ImportError:
    HAVE_OCR = False
    print("Warning: pytesseract is not installed. OCR will not work.")

# STRICT REGEX: Must have a colon (HH:MM or HH:MM:SS) to avoid matching website URLs or decimals
CLOCK_RE = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*(?:AM|PM|EST|PST|IST|UTC|GMT)?\b",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# YouTube Extractors
# --------------------------------------------------------------------------

def get_stream_info(youtube_url: str) -> dict:
    """Extract direct HLS stream URL and Title using yt-dlp."""
    cmd = ["yt-dlp", "-J", "--no-warnings", "-f", "best[height<=720]/best", youtube_url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to fetch stream info for {youtube_url}")
    
    info = json.loads(res.stdout)
    return {
        "title": info.get("title", "Unknown Title"),
        "stream_url": info.get("url")
    }

def discover_live_videos(channel_source: str, limit: int = 10) -> list[dict]:
    """Scan channel streams tab and return active live streams."""
    raw = channel_source.strip()
    if raw.startswith("@"):
        raw = f"https://www.youtube.com/{raw}"
    elif not raw.startswith("http"):
        raw = f"https://www.youtube.com/@{raw.lstrip('@')}"

    tab_url = raw.rstrip("/") + "/streams"

    cmd = [
        "yt-dlp", "-J", "--flat-playlist", "--no-warnings",
        "--playlist-end", str(limit), tab_url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Could not read channel streams tab: {res.stderr[:200]}")

    info = json.loads(res.stdout)
    live = []
    seen = set()

    for entry in info.get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        vid = str(entry["id"])
        if vid in seen:
            continue

        status = entry.get("live_status")
        if status in {"was_live", "post_live", "not_live"} or entry.get("duration") is not None:
            continue

        seen.add(vid)
        live.append({
            "id": vid,
            "title": entry.get("title") or vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return live

# --------------------------------------------------------------------------
# OCR Scanner
# --------------------------------------------------------------------------

class FastClockDetector:
    def __init__(self):
        self.roi: Optional[tuple[int, int, int, int]] = None
        self.readings: list[str] = []
        self.consecutive_failures: int = 0

    def detect_roi(self, cv_frame) -> Optional[tuple[int, int, int, int]]:
        if not HAVE_OCR:
            return None

        h, w = cv_frame.shape[:2]
        
        target_w = 1280.0
        scale = target_w / max(w, h) if max(w, h) > target_w else 1.0
        
        if scale != 1.0:
            resized = cv2.resize(cv_frame, (int(w * scale), int(h * scale)))
        else:
            resized = cv_frame

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        data = pytesseract.image_to_data(
            gray, config="--psm 11", output_type=pytesseract.Output.DICT
        )

        for i, text in enumerate(data.get("text", [])):
            text = text.strip()
            if not text or not CLOCK_RE.search(text):
                continue

            conf = float(data["conf"][i]) if data.get("conf") else -1
            if conf < 25:
                continue

            rx = int(data["left"][i] / scale)
            ry = int(data["top"][i] / scale)
            rw = int(data["width"][i] / scale)
            rh = int(data["height"][i] / scale)

            pad_x = max(20, rw // 3)
            pad_y = max(12, rh // 2)
            
            x1 = max(0, rx - pad_x)
            y1 = max(0, ry - pad_y)
            w1 = min(w - x1, rw + 2 * pad_x)
            h1 = min(h - y1, rh + 2 * pad_y)

            return (x1, y1, w1, h1)

        return None

    def sample(self, cv_frame) -> Optional[str]:
        if not HAVE_OCR:
            return None

        if self.roi is None:
            self.roi = self.detect_roi(cv_frame)
            if self.roi is None:
                return None

        x, y, w, h = self.roi
        crop = cv_frame[y : y + h, x : x + w]
        if crop.size == 0:
            self.roi = None
            return None

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        gray = cv2.resize(gray, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

        text = pytesseract.image_to_string(
            gray, config="--psm 6 -c tessedit_char_whitelist=0123456789:"
        ).strip()

        match = CLOCK_RE.search(text)
        if not match:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 2:
                self.roi = None
                self.consecutive_failures = 0
            return None

        self.consecutive_failures = 0
        hh = match.group(1)
        mm = match.group(2)
        ss = match.group(3)
        
        display_str = f"{hh}:{mm}:{ss}" if ss else f"{hh}:{mm}"
        self.readings.append(display_str)
        return display_str

# --------------------------------------------------------------------------
# Stream Inspector
# --------------------------------------------------------------------------

def analyze_stream(
    youtube_url: str,
    title: str = "",
    target_clock_readings: int = 3, 
    max_timeout_sec: int = 90, 
    interval_sec: int = 3
) -> dict:
    
    # If title is missing (single video mode), fetch it
    if not title:
        try:
            info = get_stream_info(youtube_url)
            title = info["title"]
            stream_url = info["stream_url"]
        except Exception as err:
            return {"url": youtube_url, "time": "ERROR", "title": str(err)}
    else:
        try:
            # Title was passed via channel scanner, just get stream URL
            cmd = ["yt-dlp", "-g", "-f", "best[height<=720]/best", youtube_url]
            res = subprocess.run(cmd, capture_output=True, text=True)
            stream_url = res.stdout.strip().splitlines()[0]
        except Exception:
            return {"url": youtube_url, "time": "ERROR", "title": title}

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        return {"url": youtube_url, "time": "ERROR", "title": title}

    clock_detector = FastClockDetector()
    start_time = time.monotonic()
    max_end_time = start_time + max_timeout_sec

    print(f"Sampling stream (waiting for {target_clock_readings} valid reads or {max_timeout_sec}s timeout)...")

    while time.monotonic() < max_end_time:
        ret, frame = cap.read()
        if not ret:
            cap.open(stream_url)
            time.sleep(1)
            continue

        elapsed = time.monotonic() - start_time
        clock_time_str = clock_detector.sample(frame)
        valid_count = len(clock_detector.readings)

        if clock_time_str:
            print(f"  [t={elapsed:4.1f}s] Found Time: {clock_time_str} [{valid_count}/{target_clock_readings}]")
        else:
            print(f"  [t={elapsed:4.1f}s] Scanning frame (No clock visible)...")

        if valid_count >= target_clock_readings:
            break

        time.sleep(interval_sec)

    cap.release()

    final_time = clock_detector.readings[-1] if clock_detector.readings else "None"

    return {
        "url": youtube_url,
        "time": final_time,
        "title": title
    }

# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simple YouTube Clock Extractor")
    parser.add_argument("target", help="YouTube video URL or channel handle (e.g. @IndiaTV)")
    parser.add_argument("--timeout", type=int, default=90, help="Max wait time per video")
    parser.add_argument("--samples", type=int, default=3, help="Required clock readings to confirm time")
    parser.add_argument("--interval", type=int, default=3, help="Seconds between frames")
    parser.add_argument("--limit", type=int, default=10, help="Max streams to check in channel mode")
    args = parser.parse_args()

    target = args.target.strip()
    is_channel = not ("watch?v=" in target or "youtu.be/" in target)
    results = []

    if not is_channel:
        print(f"\n--- Checking Video: {target} ---")
        res = analyze_stream(
            target, 
            target_clock_readings=args.samples, 
            max_timeout_sec=args.timeout, 
            interval_sec=args.interval
        )
        results.append(res)
    else:
        print(f"\nScanning channel streams: {target}")
        try:
            live_videos = discover_live_videos(target, limit=args.limit)
        except Exception as exc:
            print(f"Error reading channel: {exc}")
            sys.exit(2)

        if not live_videos:
            print("No active live streams found on this channel.")
            sys.exit(0)

        for idx, vid in enumerate(live_videos, 1):
            print(f"\n[{idx}/{len(live_videos)}] Inspecting: {vid['title']}")
            res = analyze_stream(
                vid["url"], 
                title=vid["title"],
                target_clock_readings=args.samples, 
                max_timeout_sec=args.timeout, 
                interval_sec=args.interval
            )
            results.append(res)

    print("\n" + "=" * 100)
    print(f"{'TIME':<10} | {'TITLE':<45} | {'URL'}")
    print("=" * 100)
    for r in results:
        # truncate title neatly for the table
        title_str = (r['title'][:42] + '...') if len(r['title']) > 45 else r['title']
        print(f"{r['time']:<10} | {title_str:<45} | {r['url']}")
    print("=" * 100 + "\n")

if __name__ == "__main__":
    main()