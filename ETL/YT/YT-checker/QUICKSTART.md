# Quick Start Guide

## TL;DR - Just Run It

```bash
python detector_fixed.py "https://www.youtube.com/watch?v=XXXXXXXX"
```

That's it. The detector will:
1. ✅ Check all dependencies
2. ✅ Verify the stream is currently live
3. ✅ Sample 30 minutes of video (default)
4. ✅ Analyze frames + clock
5. ✅ Tell you: **LIVE or FAKE**

---

## Common Commands

### Basic (30 min sample, 15s intervals)
```bash
python detector_fixed.py "YOUTUBE_URL"
```

### Quick Check (10 min sample)
```bash
python detector_fixed.py "YOUTUBE_URL" --duration 10
```

### Longer Analysis (60 min, catch long loops)
```bash
python detector_fixed.py "YOUTUBE_URL" --duration 60 --interval 20
```

### Strict Mode (catches subtle loops)
```bash
python detector_fixed.py "YOUTUBE_URL" --threshold 4
```

### Loose Mode (noisy/low-res streams)
```bash
python detector_fixed.py "YOUTUBE_URL" --threshold 10
```

### Faster Sampling (catch short loops)
```bash
python detector_fixed.py "YOUTUBE_URL" --interval 5 --duration 20
```

---

## Understanding the Output

### Phase 1: Dependency Check
```
🔍 DEPENDENCY CHECK
✓ Pillow
✓ imagehash
✓ numpy
✓ opencv-python
✓ pytesseract
✓ yt-dlp
✓ ffmpeg
✓ Tesseract
✅ All critical dependencies OK
```

**If you see ✗ instead of ✓**: Follow the installation guide in INSTALL.md

---

### Phase 2: Pre-Flight Check
```
Checking if https://www.youtube.com/watch?v=... is actually live...
Title: India TV News - Breaking News
Status: is_live
✓ Currently live!
```

**If NOT currently live:**
```
Status: was_live
❌ NOT CURRENTLY LIVE
   (This stream has ended. Check the recording if archived.)
```
→ Script stops (no point sampling ended video)

---

### Phase 3: Sampling
```
Sampling frames every 15s for 30 min (~120 samples)...

Sample  1 (   0.1s)... ✓ Clock: 14:32:00
Sample  2 (  15.2s)... ✓ Clock: 14:32:15
Sample  3 (  30.1s)... ✓ (no clock visible)
Sample  4 (  45.3s)... ✓ Clock: 14:32:45
...
```

**What this means:**
- ✓ = Frame grabbed successfully
- Clock: XX:XX = Timestamp detected on screen
- (no clock visible) = No readable time on that frame

---

### Phase 4: Results
```
=======================================================================
📊 ANALYSIS RESULTS
=======================================================================
Total frames: 120
Timestamps detected: 95
Frame matches found: 0

🎬 FRAME ANALYSIS: LIKELY_REAL
   No repeated frames detected (content appears fresh)

🕐 CLOCK ANALYSIS: CLOCK_REAL
   Clock advances naturally (95/95 samples)
   Samples: ['14:32', '14:32:15', '14:32:30', ...]

=======================================================================
🎯 FINAL VERDICT
=======================================================================

🟢 VERY LIKELY GENUINE LIVE
   Evidence: Fresh frames + advancing clock
   Confidence: HIGH
=======================================================================
```

---

## Understanding Verdicts

### 🟢 VERY LIKELY GENUINE LIVE
**When you see this:**
- Frames all unique (no repetition)
- Clock advances naturally

**What it means:** This is almost certainly a real live broadcast

---

### 🟡 LIKELY GENUINE LIVE (unverified)
**When you see this:**
- Frames all unique (no repetition)
- No visible clock on stream

**What it means:** Probably real live, but can't verify with clock

**Fix:** Look for visible clock in the stream, or sample longer

---

### 🔴 VERY LIKELY PRERECORDED (FAKE LIVE)
**When you see this:**
- Frames repeat at consistent interval
- Clock is static or doesn't advance

**What it means:** This is almost certainly looped prerecorded video

**Confidence:** VERY HIGH

---

### 🔴 PROBABLY PRERECORDED (FAKE LIVE)
**When you see this:**
- Frames repeat at consistent interval
- No visible clock

**What it means:** Likely looped, but can't verify with clock

**Confidence:** MEDIUM-HIGH

---

### 🟡 CONFLICTING SIGNALS
**When you see this:**
- Frames repeat at consistent interval
- BUT clock advances

**What it means:** Rare case. Possibly:
1. Very poor frame quality (many false positives)
2. Manually edited loop with clock overlay
3. Very short loop but clock speeds up to show "live"

**Recommendation:** Manual review. Check chat, look for guest changes, listen to audio

---

### 🟡 UNCERTAIN
**When you see this:**
- Signals are weak or mixed

**Recommendation:**
- Sample longer (increase `--duration`)
- Use stricter threshold (`--threshold 4`)
- Check other signals: chat responsiveness, guest changes

---

## Parameters Explained

| Parameter | Default | What It Does |
|-----------|---------|--------------|
| `--duration` | 30 | Total minutes to sample (longer = catches longer loops) |
| `--interval` | 15 | Seconds between samples (shorter = catches shorter loops) |
| `--threshold` | 5 | Frame similarity (0-64, lower = stricter matching) |
| `--period-tolerance` | 5.0 | Seconds of slack in loop period detection (±tolerance) |
| `--min-matches` | 3 | How many matches needed to declare loop |

### Tuning Guide

**If getting false positives (says FAKE when it's real):**
```bash
# Increase threshold (less strict matching)
python detector_fixed.py "URL" --threshold 8
```

**If missing fakes (says REAL when it's looped):**
```bash
# Decrease threshold (stricter matching)
python detector_fixed.py "URL" --threshold 3

# OR sample longer to catch the loop cycle
python detector_fixed.py "URL" --duration 60
```

**If detecting very short loops (< 30s):**
```bash
# Sample faster
python detector_fixed.py "URL" --interval 5 --duration 20
```

**If getting conflicting signals on noisy streams:**
```bash
# Increase tolerance for period matching
python detector_fixed.py "URL" --period-tolerance 10.0
```

---

## Example Scenarios

### Scenario 1: News Channel
```bash
python detector_fixed.py "https://www.youtube.com/watch?v=NEWS_CHANNEL"
```

**Expected output:**
- ✓ Currently live
- 🟢 VERY LIKELY GENUINE LIVE (fresh frames + advancing clock)

### Scenario 2: Suspicious 24/7 Stream
```bash
python detector_fixed.py "https://www.youtube.com/watch?v=24_7_WEIRD"
```

**If it's fake:**
- 🔴 VERY LIKELY PRERECORDED (frames loop at regular interval)

**If it's real:**
- 🟢 VERY LIKELY GENUINE LIVE (all unique frames)

### Scenario 3: Ended Stream
```bash
python detector_fixed.py "https://www.youtube.com/watch?v=ENDED_STREAM"
```

**Output:**
```
Status: was_live
❌ NOT CURRENTLY LIVE
   (This stream has ended.)
```
→ Script stops immediately (no time wasted)

---

## Tips & Tricks

1. **Test on known real streams first** to understand normal behavior
2. **Test on known fake streams** (YouTube has fake 24/7 streams) to see loop detection
3. **Use stricter threshold for HD streams**, looser for low-res
4. **Sample longer if you suspect very long loops** (> 1 hour)
5. **Look at the clock samples** if you get uncertain verdict
6. **Check if timestamps are visible** during sampling output

---

## Getting Help

If detector says "UNCERTAIN" or you don't trust the result:

1. **Check the clock progression** in output
2. **Look at frame match count** (0 = no loops, 5+ = likely loop)
3. **Sample longer** (30+ min should catch most loops)
4. **Check other signals:**
   - Is chat responsive to questions?
   - Do new guests/people appear?
   - Do camera angles change naturally?
   - Listen to audio: is it repetitive?

---

## Performance

| Duration | Samples | Time | CPU | Disk Space |
|----------|---------|------|-----|-----------|
| 10 min | 40 | ~5 min | Low | ~200 MB |
| 30 min | 120 | ~20 min | Low | ~600 MB |
| 60 min | 240 | ~45 min | Low | ~1.2 GB |

(Depends on frame size, network speed, disk speed)
