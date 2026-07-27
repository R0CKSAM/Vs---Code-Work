# Fundamentals: How YouTube Live vs Prerecorded Detector Works

## The Big Picture

The detector answers: **"Is this stream actually broadcasting live right now, or is it playing a pre-recorded looped video?"**

It uses three independent signals:

1. **Frame Repetition** (strongest signal)
2. **Clock/Timestamp Progression** (secondary confirmation)
3. **Pre-flight Live Status** (filter out ended streams)

If a video is really a loop, all three will show evidence. If it's genuinely live, all three will show fresh content.

---

## Signal #1: Frame Repetition Analysis (STRONGEST)

### The Core Insight
- **Real live broadcast**: Each frame looks different (camera pans, people move, scene changes)
- **Looped prerecorded**: The exact same frames keep appearing every N seconds
- **Example**: A 2-minute loop plays 15 times in 30 minutes → you see the same shot of a news desk at 0s, 120s, 240s, 360s, etc.

### How It Works

#### Step 1: Perceptual Hashing
Frame comparison doesn't use pixel-by-pixel matching (too slow, brittle). Instead, we use **perceptual hashing**.

```
Real Image:        Perceptual Hash:
[pixel data]  →    64-bit number
1920×1080 RGB      Simple fingerprint

Two similar images → similar hashes → close Hamming distance
Two different images → different hashes → large Hamming distance
```

**What is Hamming distance?**
```
Hash 1: 1011010110101010... (64 bits)
Hash 2: 1011010110001010... (64 bits)
        ││││││││││ ││││││  (difference)
                    
Hamming distance = count of bit positions that differ = 2

Lower distance = more similar images
Distance 0 = identical images
Distance 64 = completely different
```

**Why perceptual hashing?**
- ✅ Fast to compute (one hash per frame in milliseconds)
- ✅ Robust to compression (YouTube reencodes streams)
- ✅ Robust to slight camera shake, lighting changes
- ❌ But NOT exact pixel match (which is actually good — real live broadcasts have tiny encoding variations)

#### Step 2: Sample Frames Over Time
```
Real Live Stream:
  t=0s:   Frame A (wide shot)
  t=15s:  Frame B (anchor talking)
  t=30s:  Frame C (graphics)
  t=45s:  Frame D (anchor in different pose)
  [all hashes are very different]

Prerecorded Loop (2-min loop):
  t=0s:   Frame A (wide shot) → Hash_A
  t=15s:  Frame B (anchor talking) → Hash_B
  ...
  t=120s: Frame A again (SAME wide shot) → Hash_A [MATCH!]
  t=135s: Frame B again → Hash_B [MATCH!]
```

#### Step 3: Compare Hashes
For every new frame:
```python
for previous_frame in all_frames_seen_so_far:
    distance = hash_current - hash_previous
    if distance <= THRESHOLD (e.g., 5):
        RECORD THIS MATCH
        remember: period = current_time - previous_time
```

#### Step 4: Detect Periodic Recurrence
```
Raw matches collected:
  Frame at 120s matches frame at 0s → period = 120s
  Frame at 122s matches frame at 2s → period = 120s
  Frame at 124s matches frame at 4s → period = 120s
  [... 7 more matches all ~120s apart ...]

Algorithm:
  1. Collect all periods: [120.1, 120.3, 119.8, 120.2, 120.0, ...]
  2. Cluster periods within TOLERANCE (±5s): all are ~120s
  3. Count cluster size: 10 matches at ~120s period
  4. If cluster_size >= MIN_MATCHES (e.g., 3): **LOOP DETECTED**
```

**Why cluster by period instead of just counting matches?**

Without clustering:
```
Two similar frames by coincidence:
  t=50s: Wide shot → matches wide shot at t=30s (period=20s)
  That's just 1 match, so no loop → WRONG!
```

With clustering:
```
Real loop:
  Frame A recurs at periods: 119.8s, 120.1s, 120.0s, 120.2s, 119.9s [5 matches]
  Frame B recurs at periods: 120.0s, 120.3s, 119.8s, 120.1s [4 matches]
  → Cluster around 120s with 9 matches → LOOP CONFIRMED!
  
One coincidental match:
  Frame C matches at period 20s [1 match]
  → Doesn't form a cluster → IGNORED!
```

### Configuration Tuning

```python
hash_threshold = 5         # 0-64, lower = stricter matching
                           # Too loose (10+): false positives on similar but different frames
                           # Too strict (2-3): misses matches due to compression artifacts

period_tolerance = 5.0     # seconds of slack in period clustering
                           # Real loops drift slightly due to network jitter
                           # Typical: 5.0-10.0 seconds

min_period_matches = 3     # how many matches needed to declare loop
                           # Typical: 3-5
                           # Lower = catch shorter loops faster
                           # Higher = avoid false positives on weak evidence
```

---

## Signal #2: Clock/Timestamp Progression (VERIFICATION)

### The Core Insight
- **Real live**: On-screen clock advances roughly matching real elapsed time
- **Looped video**: Clock either stays static or repeats (resets at end of loop)

### How It Works

#### Step 1: Optical Character Recognition (OCR)
Extract visible timestamps from video frames using **Tesseract OCR**:

```
Frame pixel data → Tesseract OCR → Text ("14:32:45")
                                ↓
                           Regex parsing
                                ↓
                          Validate time format
                                ↓
                          Store as (elapsed_seconds, "14:32:45")
```

**Challenge**: Clock can be in different locations, fonts, colors
```
Solution: 
  1. Convert frame to grayscale (removes color noise)
  2. Enhance contrast (makes text pop out)
  3. Scan FULL image (don't assume corner placement)
  4. Use regex to find HH:MM(:SS) pattern: ([0-1]?[0-9]|2[0-3]):([0-5][0-9])
```

#### Step 2: Parse Timestamps
```python
"14:32:45" → 14*3600 + 32*60 + 45 = 52365 seconds (from midnight)
"14:33:00" → 52380 seconds
Difference: 15 seconds (one minute elapsed in real time)
```

#### Step 3: Analyze Progression
For each pair of consecutive timestamps:
```
Real time elapsed: 15 seconds
Timestamp difference: +15 seconds (time advanced)
Result: ✓ ADVANCES

Real time elapsed: 15 seconds
Timestamp difference: 0 seconds (time static)
Result: ✗ STATIC (suspicious for live)

Real time elapsed: 15 seconds
Timestamp difference: -60 seconds (time went backwards!)
Result: ✗✗ REVERSAL (loop detected!)
```

#### Step 4: Calculate Progression Ratio
```python
Total samples: 22
Advancing samples: 20
Reversals: 0
Static: 2

Advance ratio: 20/22 = 91% → CLOCK_REAL ✓

Advance ratio: 10/22 = 45% → CLOCK_UNCERTAIN 
(Some advances but too much static)

Reversals > 0 → CLOCK_LOOPS ✗✗
(Time reversed = loop detected for sure)
```

### Why Clock Alone Isn't Enough

A clever fake can:
- Overlay a real clock on prerecorded video ✗
- Use a picture-in-picture of live chat reactions ✗
- Add a countdown timer (goes backward) ✗

**Solution**: Combine with frame analysis. If frames loop BUT clock advances, that's suspicious (conflicting signals → manual review needed).

---

## Signal #3: Pre-Flight Live Status Check

### The Core Insight
YouTube's API tells you what state a video is in via the `live_status` field.

```python
live_status values:
  "is_live"      → Currently broadcasting (SAMPLE THIS)
  "was_live"     → Ended (don't waste time sampling)
  "is_upcoming"  → Scheduled (hasn't started)
  "not_live"     → Regular pre-recorded video
```

### Why Check First?
```
❌ Without pre-flight check:
   Start sampling a "was_live" video
   Run for 30 minutes
   Detector says "frames look fresh" (because recording is new)
   False positive: says it's live when it actually ended

✅ With pre-flight check:
   Query yt-dlp for live_status
   See "was_live"
   Immediately report: "NOT CURRENTLY LIVE (stream has ended)"
   Don't waste time sampling
```

---

## The Decision Tree

```
                         START
                           ↓
                  Is currently live?
                    /              \
                  NO               YES
                   ↓                ↓
              Report "Not Live"   Sample frames
              (Exit)               Sample clock
                                   Analyze both
                                        ↓
                        ┌───────────────┼───────────────┐
                        ↓               ↓               ↓
                   Frames loop?   Clock advances?   Both signals
                   /        \      /         \
                  YES        NO   YES         NO
                   ↓          ↓    ↓          ↓
                  
    FRAMES LOOP + CLOCK ADVANCES = CONFLICTING (rare, manual review)
    FRAMES LOOP + CLOCK STATIC/REVERSE = FAKE LIVE (high confidence)
    FRAMES FRESH + CLOCK ADVANCES = GENUINE LIVE (high confidence)
    FRAMES FRESH + NO CLOCK = LIKELY LIVE (medium confidence)
```

---

## Real-World Example Walkthrough

### Scenario 1: News Channel Playing Recorded Loop

**Stream**: 24/7 fake news channel (just looping prerecorded 1-hour package)

```
SAMPLING:
t=0s:    Frame A → Hash_A, Clock: 14:00
t=15s:   Frame B → Hash_B, Clock: 14:00 (static!)
t=30s:   Frame C → Hash_C, Clock: 14:00 (still static!)
...
t=3600s: Frame A again! → Hash_A (MATCH with t=0!)

ANALYSIS:
Frame repetition:
  - Frame A appears at t=0s and t=3600s → period = 3600s
  - Frame B appears at t=15s and t=3615s → period = 3600s
  - [60+ more matches at ~3600s period]
  → CLUSTER SIZE = 60+ matches → LOOP DETECTED

Clock analysis:
  - Clock stuck at 14:00 for entire sample
  → Advance ratio = 0% → CLOCK_STATIC

VERDICT: 🔴 VERY LIKELY PRERECORDED (FAKE LIVE)
  Evidence: Frames loop every 3600s + clock never advances
  Confidence: VERY HIGH
```

### Scenario 2: Genuine Breaking News Live

**Stream**: India TV News breaking news coverage

```
SAMPLING:
t=0s:    Frame A (anchor) → Hash_A, Clock: 14:00
t=15s:   Frame B (ticker) → Hash_B, Clock: 14:15
t=30s:   Frame C (graphics) → Hash_C, Clock: 14:30
t=45s:   Frame D (video clip) → Hash_D, Clock: 14:45
...
t=3600s: Frame E (different scene) → Hash_E, Clock: 15:00

ANALYSIS:
Frame repetition:
  - No frame appears twice (all unique)
  - Match count = 0
  → LOOP DETECTION = NO LOOP

Clock analysis:
  - Clock advances: 14:00 → 14:15 → 14:30 → 14:45 → 15:00
  - All advances are +15s per 15s real time elapsed
  → Advance ratio = 100% → CLOCK_REAL

VERDICT: 🟢 VERY LIKELY GENUINE LIVE
  Evidence: Fresh frames + advancing clock
  Confidence: VERY HIGH
```

---

## Key Takeaways

| Concept | What It Means | Why It Matters |
|---------|--------------|----------------|
| **Perceptual Hash** | Fingerprint of image content (64 bits) | Lets us compare millions of frames quickly |
| **Hamming Distance** | Number of different bits between hashes (0-64) | Measures how similar two images are |
| **Periodicity** | Frames recur at same interval (e.g., every 120s) | Signature of a looping video |
| **Clock Drift** | ±3-5s variation in time progression | Normal for streaming; allows some tolerance |
| **Advance Ratio** | % of timestamps that advanced forward | Real live > 70%, fake static < 30% |
| **Reversal** | Time went backward | Definitive proof of loop |

---

## Limitations & Considerations

1. **Static/boring content** (news desk, weather) can look repetitive even when live
   - Mitigation: Use period clustering; accidental matches won't cluster

2. **Poor OCR accuracy** on fancy fonts or low quality video
   - Mitigation: Fall back to frame analysis if clock detection fails

3. **Network jitter** causes slight timestamp variations
   - Mitigation: Allow ±3s tolerance in time progression checks

4. **Clever manipulation** (clock overlay on loop) defeats frame+clock together
   - Mitigation: Would need chat responsiveness or audio novelty analysis

5. **Extremely short loops** (< 30 seconds) need shorter sampling intervals
   - Mitigation: Use `--interval 5` for suspected short loops

