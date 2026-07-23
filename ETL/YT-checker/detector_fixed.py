"""
YouTube Live vs Prerecorded Detector (CORRECTED)

Detects whether a YouTube stream is genuinely LIVE or PRERECORDED (fake live) by:
1. Pre-flight check: verify video is actually currently live
2. Frame repetition analysis: detect if frames recur on a consistent cycle
3. Clock/Timestamp detection: read on-screen time and verify it advances

Usage:
    python detector_fixed.py "https://www.youtube.com/watch?v=XXXXXXXX" --duration 30 --interval 15

Setup:
    pip install yt-dlp pillow imagehash opencv-python pytesseract numpy
    Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Try importing all dependencies (fail gracefully with good error messages)
MISSING_DEPS = []
BROKEN_DEPS = []

# Check PIL/Pillow
try:
    from PIL import Image
except ImportError:
    MISSING_DEPS.append("pillow")
    Image = None

# Check imagehash
try:
    import imagehash
except ImportError:
    MISSING_DEPS.append("imagehash")
    imagehash = None

# Check numpy
try:
    import numpy as np
except ImportError:
    MISSING_DEPS.append("numpy")
    np = None

# Check cv2 (opencv-python)
try:
    import cv2
except ImportError:
    MISSING_DEPS.append("opencv-python")
    cv2 = None

# Check pytesseract (optional but recommended)
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    MISSING_DEPS.append("pytesseract (optional but recommended)")
    TESSERACT_AVAILABLE = False
    pytesseract = None


# ============ DEPENDENCY CHECKING ============

def check_dependencies() -> bool:
    """
    Verify all required dependencies are installed and working.
    Returns True if all good, False if critical deps missing.
    """
    print("=" * 70)
    print("🔍 DEPENDENCY CHECK")
    print("=" * 70)
    
    all_ok = True
    
    # Python packages
    print("\n📦 Python Packages:")
    python_deps = {
        "Pillow": Image is not None,
        "imagehash": imagehash is not None,
        "numpy": np is not None,
        "opencv-python": cv2 is not None,
        "pytesseract": pytesseract is not None,
    }
    
    for pkg, available in python_deps.items():
        status = "✓" if available else "✗"
        required = "" if pkg == "pytesseract" else " (required)"
        print(f"  {status} {pkg}{required}")
        if not available and pkg != "pytesseract":
            all_ok = False
    
    # External binaries
    print("\n🔧 External Tools:")
    
    # Check yt-dlp
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=5, check=True
        )
        version = result.stdout.strip().split()[0]
        print(f"  ✓ yt-dlp (version: {version})")
    except Exception as e:
        print(f"  ✗ yt-dlp (not found)")
        print(f"     Install: pip install yt-dlp")
        all_ok = False
    
    # Check ffmpeg
    try:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            # Try winget location on Windows
            winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
            matches = list(winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
            if matches:
                ffmpeg_path = str(max(matches, key=lambda p: p.stat().st_mtime))
        
        if ffmpeg_path:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True, text=True, timeout=5
            )
            version_line = result.stdout.split('\n')[0]
            print(f"  ✓ ffmpeg ({ffmpeg_path})")
        else:
            raise FileNotFoundError("ffmpeg not found on PATH")
    except Exception as e:
        print(f"  ✗ ffmpeg (not found)")
        print(f"     Windows: winget install -e --id Gyan.FFmpeg")
        print(f"     macOS:   brew install ffmpeg")
        print(f"     Linux:   sudo apt install ffmpeg")
        all_ok = False
    
    # Check Tesseract binary (if pytesseract is installed)
    if pytesseract:
        print("\n🎯 OCR Support (Tesseract):")
        try:
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=5, check=True
            )
            version = result.stdout.split('\n')[0]
            print(f"  ✓ Tesseract ({version})")
        except Exception as e:
            print(f"  ✗ Tesseract binary not found")
            print(f"     Clock detection (OCR) will NOT work")
            print(f"     Install from: https://github.com/UB-Mannheim/tesseract/wiki")
            print(f"     Windows: Download .exe installer")
            print(f"     macOS:   brew install tesseract")
            print(f"     Linux:   sudo apt install tesseract-ocr")
            TESSERACT_AVAILABLE = False
    else:
        print("\n🎯 OCR Support (Tesseract):")
        print(f"  ⚠️  pytesseract not installed (clock detection disabled)")
        print(f"     Install: pip install pytesseract")
    
    # Summary
    print("\n" + "=" * 70)
    if all_ok:
        print("✅ All critical dependencies OK")
        if not TESSERACT_AVAILABLE:
            print("   (OCR/clock detection disabled, but frame analysis still works)")
    else:
        print("❌ MISSING CRITICAL DEPENDENCIES")
        print("   Cannot proceed. Install missing packages above.")
    print("=" * 70 + "\n")
    
    return all_ok


class YouTubeStreamDetector:
    """Corrected live vs prerecorded detector."""

    def __init__(self, hash_threshold: int = 5, period_tolerance: float = 5.0, min_period_matches: int = 3):
        """
        Args:
            hash_threshold: Perceptual hash Hamming distance (0-64, lower=stricter). 
                           5-8 for tight match, 8-12 for loose. Default 5.
            period_tolerance: Seconds of slack when checking if matches cluster around same period.
            min_period_matches: How many matches at the same period needed to flag a loop.
        """
        self.hash_threshold = hash_threshold
        self.period_tolerance = period_tolerance
        self.min_period_matches = min_period_matches
        
        self.frames: List[Tuple[float, imagehash.ImageHash, Image.Image]] = []
        self.matches: List[Dict] = []  # {elapsed, matched_at, period, distance}
        self.detected_timestamps: List[Tuple[float, str]] = []

    # ============ FFmpeg & Stream Resolution ============

    def resolve_ffmpeg(self) -> str:
        """Locate FFmpeg executable."""
        if configured := os.getenv("YT_DETECTOR_FFMPEG"):
            candidate = Path(configured).expanduser()
            if candidate.is_file():
                return str(candidate)
            raise FileNotFoundError(f"FFmpeg not found at: {candidate}")

        if on_path := shutil.which("ffmpeg"):
            return on_path

        # Windows: check winget install location
        winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            matches = list(winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
            if matches:
                return str(max(matches, key=lambda p: p.stat().st_mtime))

        raise FileNotFoundError("FFmpeg not found. Install: winget install -e --id Gyan.FFmpeg")

    def check_is_live(self, youtube_url: str) -> Tuple[bool, str, str]:
        """Check if video is currently live using yt-dlp metadata."""
        try:
            result = subprocess.run(
                ["yt-dlp", "-j", "--no-warnings", "-q", youtube_url],
                capture_output=True, text=True, check=True, timeout=10,
            )
            info = json.loads(result.stdout)
            live_status = info.get("live_status")
            title = info.get("title", "Unknown")
            is_live = live_status == "is_live"
            return is_live, live_status, title
        except Exception as e:
            raise RuntimeError(f"Failed to check video status: {e}")

    def get_stream_url(self, youtube_url: str) -> str:
        """Resolve YouTube URL to playable stream."""
        result = subprocess.run(
            ["yt-dlp", "-g", "-f", "best[height<=480]", youtube_url],
            capture_output=True, text=True, check=True, timeout=15,
        )
        return result.stdout.strip().splitlines()[0]

    def grab_frame(self, stream_url: str) -> Image.Image:
        """Grab single frame from stream."""
        ffmpeg = self.resolve_ffmpeg()
        result = subprocess.run(
            [ffmpeg, "-y", "-i", stream_url, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
            capture_output=True, check=True, timeout=30,
        )
        return Image.open(io.BytesIO(result.stdout))

    # ============ Frame Analysis (CORRECTED) ============

    def analyze_frame_repetition(self) -> Tuple[str, str]:
        """
        CORRECTED: Detect if frames repeat on a consistent cycle (true loop signature).
        
        A genuine loop has the same frames recurring at approximately the same
        period. We look for a *cluster* of matches all happening at roughly
        the same interval apart.
        """
        if len(self.frames) < 3:
            return "INSUFFICIENT_FRAMES", f"Only {len(self.frames)} frames (need 3+)"

        # Compare every frame against every earlier frame
        for idx in range(len(self.frames)):
            current_time, current_hash, _ = self.frames[idx]
            
            for prev_idx in range(idx):
                prev_time, prev_hash, _ = self.frames[prev_idx]
                distance = current_hash - prev_hash
                
                # Only record if hashes are actually similar
                if distance <= self.hash_threshold:
                    period = current_time - prev_time
                    self.matches.append({
                        "elapsed": current_time,
                        "matched_at": prev_time,
                        "period": period,
                        "distance": distance,
                    })

        if not self.matches:
            return "LIKELY_REAL", "No repeated frames detected (content appears fresh)"

        # Look for clustering of matches around the same period
        periods = [m["period"] for m in self.matches]
        period_clusters = defaultdict(list)
        
        for period in periods:
            # Find which cluster this period belongs to
            found = False
            for cluster_period in period_clusters:
                if abs(period - cluster_period) <= self.period_tolerance:
                    period_clusters[cluster_period].append(period)
                    found = True
                    break
            if not found:
                period_clusters[period] = [period]

        # Find the largest cluster
        best_cluster_period = max(period_clusters.keys(), key=lambda p: len(period_clusters[p]))
        best_cluster_size = len(period_clusters[best_cluster_period])

        if best_cluster_size >= self.min_period_matches:
            avg_period = sum(period_clusters[best_cluster_period]) / len(period_clusters[best_cluster_period])
            reason = f"Frames recur every ~{avg_period:.0f}s ({best_cluster_size} matches) — LOOP DETECTED"
            return "LIKELY_FAKE", reason
        else:
            reason = f"Weak periodicity: {best_cluster_size} matches (need {self.min_period_matches})"
            return "UNCERTAIN", reason

    # ============ Clock/Timestamp Detection (CORRECTED) ============

    def detect_clock_in_frame(self, image: Image.Image) -> Optional[str]:
        """
        CORRECTED: Extract timestamp from frame using OCR.
        
        Scans full image for time patterns instead of hardcoding regions.
        Returns None if pytesseract/Tesseract not available.
        """
        if not TESSERACT_AVAILABLE or pytesseract is None or cv2 is None or np is None:
            return None

        try:
            # Convert to grayscale
            gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            
            # Enhance contrast for OCR
            gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # Extract all text (don't restrict to specific regions)
            text = pytesseract.image_to_string(
                gray,
                config='--psm 11 -c tessedit_char_whitelist=0123456789:/-'
            )
            
            # Look for time pattern HH:MM(:SS) or variations
            # Patterns: "14:30", "2:45:30", "14:30:45", "14/30", etc.
            time_pattern = r'([0-1]?[0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?'
            matches = re.findall(time_pattern, text)
            
            if matches:
                # Return the first match (likely the most prominent)
                h, m, s = matches[0]
                if s:
                    return f"{h}:{m}:{s}"
                else:
                    return f"{h}:{m}"
            
            return None
        except Exception:
            return None

    def analyze_timestamp_progression(self) -> Tuple[str, str]:
        """
        CORRECTED: Check if detected timestamps actually advance over real time.
        
        Real live: on-screen time advances roughly matching elapsed seconds.
        Fake loop: time either doesn't advance or repeats.
        """
        if not self.detected_timestamps:
            return "NO_CLOCK", "No visible timestamp detected"

        if len(self.detected_timestamps) < 2:
            return "INSUFFICIENT_CLOCKS", f"Only {len(self.detected_timestamps)} timestamp(s) detected"

        # Parse timestamps
        parsed = []
        for elapsed, ts_str in self.detected_timestamps:
            try:
                parts = ts_str.split(':')
                h = int(parts[0])
                m = int(parts[1])
                s = int(parts[2]) if len(parts) > 2 else 0
                total_seconds = h * 3600 + m * 60 + s
                parsed.append((elapsed, total_seconds))
            except (ValueError, IndexError):
                continue

        if len(parsed) < 2:
            return "INVALID_FORMAT", "Could not parse timestamp format"

        # Check progression
        advances = 0
        reversals = 0
        static_periods = 0
        
        for i in range(1, len(parsed)):
            elapsed_diff = parsed[i][0] - parsed[i-1][0]
            time_diff = parsed[i][1] - parsed[i-1][1]
            
            if elapsed_diff <= 0:
                continue
            
            # Allow ±3 seconds drift
            if 0 < time_diff <= elapsed_diff + 3:
                advances += 1
            elif time_diff < 0:
                reversals += 1
            elif time_diff == 0:
                static_periods += 1

        total = len(parsed) - 1
        advance_ratio = advances / total if total > 0 else 0

        if reversals > 0:
            reason = f"Time reversed {reversals} times — clock looping"
            return "CLOCK_LOOPS", reason
        elif advance_ratio > 0.7:
            reason = f"Clock advances naturally ({advances}/{total} samples)"
            return "CLOCK_REAL", reason
        elif advance_ratio > 0.3:
            reason = f"Partial advancement ({advances}/{total} samples, {static_periods} static)"
            return "CLOCK_UNCERTAIN", reason
        else:
            reason = f"Clock mostly static ({static_periods}/{total} samples)"
            return "CLOCK_STATIC", reason

    # ============ Main Analysis ============

    def sample_stream(self, youtube_url: str, interval_seconds: int, duration_minutes: float) -> None:
        """Sample stream and analyze."""
        
        # Pre-flight check
        print("=" * 70)
        print("🔍 PRE-FLIGHT CHECK")
        print("=" * 70)
        try:
            is_live, live_status, title = self.check_is_live(youtube_url)
            print(f"Title: {title}")
            print(f"Status: {live_status}")
            
            if not is_live:
                print("\n❌ NOT CURRENTLY LIVE")
                if live_status == "was_live" or live_status == "post_live":
                    print("   This stream has ended.")
                elif live_status == "is_upcoming":
                    print("   This stream hasn't started yet.")
                elif live_status == "not_live":
                    print("   This is not a live stream.")
                else:
                    print(f"   Status: {live_status}")
                return
            
            print("✓ Currently live!\n")
        except Exception as e:
            print(f"❌ Failed to check: {e}")
            return

        # Stream sampling
        print("=" * 70)
        print("📊 SAMPLING")
        print("=" * 70)
        print(f"Duration: {duration_minutes} min, Interval: {interval_seconds}s")
        print(f"Expected samples: {int(duration_minutes * 60 / interval_seconds)}\n")

        try:
            print("📡 Resolving stream URL...")
            stream_url = self.get_stream_url(youtube_url)
        except Exception as e:
            print(f"❌ Failed to resolve: {e}")
            return

        start_time = time.monotonic()
        end_time = start_time + duration_minutes * 60
        sample_count = 0

        while time.monotonic() < end_time:
            elapsed = time.monotonic() - start_time
            try:
                print(f"Sample {sample_count + 1:2d} ({elapsed:6.1f}s)... ", end="", flush=True)
                frame = self.grab_frame(stream_url)
                frame_hash = imagehash.phash(frame, hash_size=16)
                self.frames.append((elapsed, frame_hash, frame))
                
                # Try to detect timestamp
                timestamp = self.detect_clock_in_frame(frame)
                if timestamp:
                    self.detected_timestamps.append((elapsed, timestamp))
                    print(f"✓ Clock: {timestamp}")
                else:
                    print("✓ (no clock visible)")

            except subprocess.CalledProcessError:
                print("⚠️  Refreshing URL...", flush=True)
                try:
                    stream_url = self.get_stream_url(youtube_url)
                    frame = self.grab_frame(stream_url)
                    frame_hash = imagehash.phash(frame, hash_size=16)
                    self.frames.append((elapsed, frame_hash, frame))
                    
                    timestamp = self.detect_clock_in_frame(frame)
                    if timestamp:
                        self.detected_timestamps.append((elapsed, timestamp))
                        print(f"Sample {sample_count + 1:2d} ({elapsed:6.1f}s)... ✓ Clock: {timestamp}")
                    else:
                        print(f"Sample {sample_count + 1:2d} ({elapsed:6.1f}s)... ✓")
                except Exception as e:
                    print(f"❌ {e}")
                    continue

            sample_count += 1
            time.sleep(interval_seconds)

        print()
        self.report()

    def report(self) -> None:
        """Generate comprehensive verdict."""
        if len(self.frames) < 2:
            print("❌ Not enough frames for analysis")
            return

        print("\n" + "=" * 70)
        print("📊 ANALYSIS RESULTS")
        print("=" * 70)
        print(f"Total frames: {len(self.frames)}")
        print(f"Timestamps detected: {len(self.detected_timestamps)}")
        print(f"Frame matches found: {len(self.matches)}")
        print()

        # Frame analysis
        frame_verdict, frame_reason = self.analyze_frame_repetition()
        print(f"🎬 FRAME ANALYSIS: {frame_verdict}")
        print(f"   {frame_reason}")
        print()

        # Clock analysis
        if self.detected_timestamps:
            clock_verdict, clock_reason = self.analyze_timestamp_progression()
            print(f"🕐 CLOCK ANALYSIS: {clock_verdict}")
            print(f"   {clock_reason}")
            print(f"   Samples: {[ts for _, ts in self.detected_timestamps[:10]]}")
        else:
            clock_verdict = "NO_CLOCK"
            print(f"🕐 CLOCK ANALYSIS: NO_CLOCK")
            print(f"   No visible timestamp found")
        print()

        # Final verdict
        print("=" * 70)
        print("🎯 FINAL VERDICT")
        print("=" * 70)

        if frame_verdict == "LIKELY_FAKE":
            if clock_verdict in ["CLOCK_LOOPS", "CLOCK_STATIC"]:
                print("🔴 VERY LIKELY PRERECORDED (FAKE LIVE)")
                print("   Evidence: Frames loop + time doesn't advance")
                print("   Confidence: HIGH")
            elif clock_verdict in ["CLOCK_REAL", "CLOCK_UNCERTAIN"]:
                print("🟡 CONFLICTING SIGNALS - Manual review needed")
                print("   Frames loop BUT clock advances (rare, manual manipulation?)")
            else:
                print("🔴 PROBABLY PRERECORDED (FAKE LIVE)")
                print("   Evidence: Frames loop consistently")
                print("   Confidence: MEDIUM (no clock to verify)")

        elif frame_verdict == "LIKELY_REAL":
            if clock_verdict in ["CLOCK_REAL", "CLOCK_UNCERTAIN"]:
                print("🟢 VERY LIKELY GENUINE LIVE")
                print("   Evidence: Fresh frames + advancing clock")
                print("   Confidence: HIGH")
            elif clock_verdict == "NO_CLOCK":
                print("🟡 LIKELY GENUINE LIVE (unverified)")
                print("   Evidence: No frame repetition detected")
                print("   Note: Add visible clock for higher confidence")
            else:
                print("🟡 PROBABLY LIVE")
                print("   Evidence: Frames appear fresh")
                print("   Note: Clock not advancing (may be disabled)")

        else:  # UNCERTAIN
            print("🟡 UNCERTAIN")
            print("   Signals are weak or contradictory")
            print("   Recommendation: Extend sampling duration")

        print()
        print("Other signals to check manually:")
        print("  • Chat responsiveness - Do mods respond to current messages?")
        print("  • Guest appearances - Are new people/guests appearing?")
        print("  • Background changes - Lighting, props, setup changes?")
        print("=" * 70)


def main():
    # Check dependencies FIRST before parsing args
    if not check_dependencies():
        print("\n❌ Please install missing dependencies and try again.")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description="Detect if YouTube stream is live or prerecorded (fake live)"
    )
    parser.add_argument("url", help="YouTube stream URL")
    parser.add_argument("--interval", type=int, default=15, help="Seconds between samples (default: 15)")
    parser.add_argument("--duration", type=float, default=30, help="Minutes to sample (default: 30)")
    parser.add_argument("--threshold", type=int, default=5, help="Frame hash threshold 0-64 (default: 5)")
    parser.add_argument("--period-tolerance", type=float, default=5.0,
                       help="Seconds of slack for period matching (default: 5)")
    parser.add_argument("--min-matches", type=int, default=3, help="Matches to flag loop (default: 3)")

    args = parser.parse_args()

    detector = YouTubeStreamDetector(
        hash_threshold=args.threshold,
        period_tolerance=args.period_tolerance,
        min_period_matches=args.min_matches,
    )
    detector.sample_stream(args.url, args.interval, args.duration)


if __name__ == "__main__":
    main()
