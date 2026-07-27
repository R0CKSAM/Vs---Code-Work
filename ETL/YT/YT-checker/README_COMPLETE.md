# YouTube Live vs Prerecorded Detector - Complete Guide

## What Is This?

A Python tool that analyzes YouTube streams to determine if they're **genuinely broadcasting live** or **looping pre-recorded video** (fake live).

**Why does this matter?**
- News channels sometimes loop content instead of broadcasting fresh news
- 24/7 streams may replay prerecorded segments
- Scammers use fake-live streams to impersonate legitimate channels
- Producers need to verify competitor streams are actually live

---

## How It Works (High Level)

The detector looks for three things:

### 1. 🎬 Frame Repetition (Primary Signal)
```
Real live:      Every frame is different
                Frame 1 ≠ Frame 2 ≠ Frame 3 ≠ Frame 4...

Fake live:      Frames repeat every N seconds (loop detected!)
                Frame 1 = Frame 1 (seen 120s ago)
                Frame 2 = Frame 2 (seen 120s ago)
                Frame 3 = Frame 3 (seen 120s ago)
```

**How it detects this:**
- Uses **perceptual hashing** to fingerprint each frame
- Compares current frame against all previous frames
- Looks for matches recurring at consistent time intervals
- Example: If 5+ frames match at ~120s period → loop detected!

### 2. 🕐 Clock Progression (Verification)
```
Real live:      On-screen clock advances as time passes
                14:00 → 14:15 → 14:30 → 14:45

Fake live:      Clock stays static or repeats
                14:00 → 14:00 → 14:00 (static)
                OR
                14:00 → 14:15 → 14:00 (reset/reversal)
```

**How it detects this:**
- Uses **OCR (Tesseract)** to read timestamps from frames
- Tracks whether time advances naturally
- Any reversal = loop confirmed!

### 3. ✅ Pre-Flight Check (Efficiency)
```
Before sampling:
  "Is this video currently live?"
  
If NOT:
  ❌ Don't waste 30 minutes sampling
  ✅ Report immediately: "Stream has ended"
```

---

## File Structure

```
live_stream_detector/
├── detector_fixed.py          ← Main detection script
├── FUNDAMENTALS.md            ← How it all works (detailed)
├── INSTALL.md                 ← Dependency installation guide
├── QUICKSTART.md              ← Commands and examples
├── CORRECTIONS.md             ← What was wrong with original
├── requirements.txt           ← Python packages
└── README_COMPLETE.md         ← This file
```

---

## Quick Start

### 1. Install Dependencies
```bash
pip install yt-dlp pillow imagehash opencv-python pytesseract numpy
```

Then install system tools:
- **Windows**: `winget install -e --id Gyan.FFmpeg`
- **macOS**: `brew install ffmpeg tesseract`
- **Linux**: `sudo apt install ffmpeg tesseract-ocr`

### 2. Run The Detector
```bash
python detector_fixed.py "https://www.youtube.com/watch?v=XXXXXXXX"
```

### 3. Read The Verdict
```
🟢 VERY LIKELY GENUINE LIVE
   Evidence: Fresh frames + advancing clock
   Confidence: HIGH
```

That's it!

---

## Understanding The Algorithm

### Frame Repetition Detection (In Detail)

**Step 1: Perceptual Hashing**
```
Image:  [2048x2560x3 pixel array] → Slow to compare
Downsampled to 16x16 → Compute hash → 64-bit number (Fast!)

Two similar images have hashes with small Hamming distance
Two different images have hashes with large Hamming distance
```

**Step 2: Collect Matches**
```
For every new frame:
  Compare its hash against all previous frame hashes
  If distance <= threshold (5): Record as match
  
Match = {
  current_time: 120.5s,
  previous_time: 0.3s,
  period: 120.2s,      ← Time between occurrence
  distance: 3           ← How similar (0=identical, 64=different)
}
```

**Step 3: Cluster by Period**
```
All periods: [120.1, 119.8, 120.3, 119.9, 120.2, 60.0, 58.0]

Cluster 1 (~120s): [120.1, 119.8, 120.3, 119.9, 120.2]  → Size=5
Cluster 2 (~60s):  [60.0, 58.0]                         → Size=2

Largest cluster: ~120s with 5 matches
If cluster_size >= min_matches (3): LOOP DETECTED! ✗
```

### Clock Progression Detection (In Detail)

**Step 1: Extract Timestamps**
```
Frame pixel data → Tesseract OCR → Text output
                    "14:32:45" ← Found it!
                    
Record: (elapsed=15.2s, timestamp="14:32:45")
```

**Step 2: Parse & Convert**
```
"14:32:45" → 14×3600 + 32×60 + 45 = 52365 seconds
"14:33:00" → 14×3600 + 33×60 + 0  = 52380 seconds
Difference: 15 seconds
```

**Step 3: Analyze Progression**
```
Elapsed: 15s    Time advanced: 15s    → ✓ Normal (real time)
Elapsed: 15s    Time advanced: 0s     → ✗ Static
Elapsed: 15s    Time advanced: -60s   → ✗✗ Reversal (loop!)
```

**Step 4: Calculate Ratio**
```
Total samples: 100
Advancing: 95     → Ratio = 95%   → CLOCK_REAL ✓
Advancing: 50     → Ratio = 50%   → CLOCK_UNCERTAIN
Advancing: 10     → Ratio = 10%   → CLOCK_STATIC ✗
Reversals > 0     → CLOCK_LOOPS ✗✗
```

---

## Dependency Checking

The detector checks all dependencies on startup:

```bash
$ python detector_fixed.py "URL"

🔍 DEPENDENCY CHECK
======================================================================

📦 Python Packages:
  ✓ Pillow (required)
  ✓ imagehash (required)
  ✓ numpy (required)
  ✓ opencv-python (required)
  ✓ pytesseract (optional but recommended)

🔧 External Tools:
  ✓ yt-dlp
  ✓ ffmpeg

🎯 OCR Support (Tesseract):
  ✓ Tesseract

✅ All critical dependencies OK
```

**If something's missing:**
- Reports exactly which package is missing
- Provides installation command
- Exits cleanly with helpful error message

---

## Example Results

### Example 1: Real Live News
```
Pre-flight check:
  Title: India TV News Live
  Status: is_live
  ✓ Currently live!

Sampling 30 minutes...
  [120 samples collected]

Analysis:
  🎬 FRAME ANALYSIS: LIKELY_REAL
     No repeated frames detected
  
  🕐 CLOCK ANALYSIS: CLOCK_REAL
     Clock advances naturally (120/120 samples)
     Timestamps: 14:32, 14:32:15, 14:32:30, ...

VERDICT:
  🟢 VERY LIKELY GENUINE LIVE
  Evidence: Fresh frames + advancing clock
  Confidence: HIGH
```

### Example 2: Fake 24/7 Loop
```
Pre-flight check:
  Title: 24/7 Meditation Music
  Status: is_live
  ✓ Currently live!

Sampling 30 minutes...
  [120 samples collected]

Analysis:
  🎬 FRAME ANALYSIS: LIKELY_FAKE
     Frames recur every ~600s (10 matches at 600.1±2s period)
  
  🕐 CLOCK ANALYSIS: CLOCK_STATIC
     Clock stuck at 09:00 for entire sample

VERDICT:
  🔴 VERY LIKELY PRERECORDED (FAKE LIVE)
  Evidence: Frames loop every 600s + clock never advances
  Confidence: VERY HIGH
```

### Example 3: Ended Stream
```
Pre-flight check:
  Title: Some Channel Stream
  Status: was_live
  
❌ NOT CURRENTLY LIVE
   (This stream has ended. Check the recording if archived.)

[Script exits - no time wasted]
```

---

## Performance & Limitations

### What It's Good At
✅ Detecting looped prerecorded video (very reliable)
✅ Detecting genuinely live streams with visible clocks (very reliable)
✅ Filtering out ended streams automatically
✅ Handling different video qualities and encoding

### What It's Limited By
⚠️ OCR fails on fancy/stylized fonts (some news stations)
⚠️ Requires visible clock for full verification
⚠️ Kann't detect manually edited loops with fake clock overlays
⚠️ Doesn't analyze chat responsiveness
⚠️ Doesn't check for guest/content changes

### Improving Accuracy
**If you get uncertain verdicts:**
1. Sample longer: `--duration 60`
2. Use stricter matching: `--threshold 4`
3. Manually check:
   - Is chat responding to messages?
   - Do new people appear on screen?
   - Does lighting/background change naturally?
   - Is audio content fresh or repetitive?

---

## Parameters Reference

| Flag | Default | Effect |
|------|---------|--------|
| `--duration` | 30 | Minutes to sample (longer catches long loops) |
| `--interval` | 15 | Seconds between samples (shorter catches short loops) |
| `--threshold` | 5 | Frame similarity 0-64 (lower = stricter) |
| `--period-tolerance` | 5.0 | Slack when matching loop periods (seconds) |
| `--min-matches` | 3 | Matches needed to declare loop |

**Tuning Examples:**
```bash
# For very strict detection (catch subtle loops)
python detector_fixed.py "URL" --threshold 4 --period-tolerance 3

# For noisy/low-res streams
python detector_fixed.py "URL" --threshold 10 --period-tolerance 8

# For long loops (> 20 min)
python detector_fixed.py "URL" --duration 120 --interval 30

# For short loops (< 5 min)
python detector_fixed.py "URL" --interval 5 --min-matches 5
```

---

## Troubleshooting

### "Dependency check shows ✗"
→ See **INSTALL.md** for step-by-step installation

### "ffmpeg not found after installing"
→ Windows: Close and reopen terminal (PATH needs to refresh)
→ macOS/Linux: Run `hash -r`

### "Tesseract not found (pytesseract installed)"
→ Python package installed, but binary not installed
→ Download from: https://github.com/UB-Mannheim/tesseract/wiki

### "Getting false positives (says FAKE when it's REAL)"
→ Increase threshold: `--threshold 8 or 10`
→ Reduce min-matches: `--min-matches 2`

### "Missing fakes (says REAL when it's FAKE)"
→ Decrease threshold: `--threshold 3 or 4`
→ Sample longer: `--duration 60`
→ Increase min-matches: `--min-matches 5`

### "No clock detected (OCR failing)"
→ Stream might have no visible timestamp
→ Try different streams to test OCR
→ Detector still works without clock (frame analysis only)

---

## How to Read Source Code

If you want to understand the implementation:

1. **FUNDAMENTALS.md** ← Start here (concepts explained)
2. **detector_fixed.py** → `check_is_live()` (pre-flight check)
3. **detector_fixed.py** → `analyze_frame_repetition()` (loop detection)
4. **detector_fixed.py** → `detect_clock_in_frame()` (OCR)
5. **detector_fixed.py** → `analyze_timestamp_progression()` (time analysis)
6. **detector_fixed.py** → `report()` (decision logic)

---

## For Your University Project

### What To Include In Report

1. **Problem Statement**
   - How to detect fake live streams
   - Why single signals fail (one heuristic isn't enough)

2. **Methodology**
   - Signal 1: Frame repetition + periodic clustering
   - Signal 2: Clock/timestamp progression
   - Signal 3: Pre-flight live status validation

3. **Algorithm Details**
   - Perceptual hashing (what, why, limitations)
   - Hamming distance for similarity
   - Periodicity clustering vs coincidental matches
   - OCR for timestamp extraction
   - Progression ratio analysis

4. **Results**
   - Test on real streams (show verdicts)
   - Test on known fakes (show loops detected)
   - Show dependency checking in action

5. **Limitations & Future Work**
   - Can't catch clever edits (fake clock overlay on loop)
   - OCR limitations
   - Future: chat responsiveness, audio novelty, guest detection

---

## Citation/Attribution

If using this in a project, you can reference:
```
YouTube Live vs Prerecorded Detector v1.0
Method: Multi-signal analysis (frame repetition + clock progression)
Libraries: yt-dlp, imagehash, opencv-python, pytesseract
```

---

## Questions?

Check these docs in order:
1. **QUICKSTART.md** - Common commands and outputs
2. **FUNDAMENTALS.md** - How the algorithms work
3. **INSTALL.md** - Dependency issues
4. **CORRECTIONS.md** - What was fixed from original

Good luck! 🎉
