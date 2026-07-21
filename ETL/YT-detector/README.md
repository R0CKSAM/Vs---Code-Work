# Live vs. Fake-Live Stream Detector (prototype)

Detects whether a YouTube live stream is showing genuinely live content or
looping pre-recorded footage, by sampling frames over time and checking
whether they repeat on a consistent cycle.

## How it works

1. `frame_sampler.py` resolves the stream via `yt-dlp` and grabs a frame
   with `ffmpeg` every N seconds.
2. `loop_detector.py` perceptually hashes each frame (`imagehash.phash`)
   and compares it against every previous frame's hash (Hamming distance).
3. A single near-duplicate match is treated as coincidental (e.g. two
   similar wide shots of a news desk). A **cluster of matches recurring at
   the same interval** is treated as evidence of a loop — that's the
   actual signature of a video file being replayed.

## Setup

```bash
pip install -r requirements.txt
# plus ffmpeg on PATH — see requirements.txt for install commands
```

## Usage

```bash
python main.py "https://www.youtube.com/watch?v=XXXXXXXX" --interval 20 --duration 30
```

- `--interval`: seconds between samples. Shorter = catches shorter loops, more ffmpeg calls.
- `--duration`: total minutes to sample. Needs to comfortably exceed one full loop cycle to
  catch it — if you suspect ~20 minute loops, sample for 45–60 minutes.
- `--threshold`: how visually similar two frames must be to count as "the same shot."
  Lower = stricter match. 6 is a reasonable starting point for `hash_size=16`; raise it if
  you're getting false matches on visually busy footage, lower it if near-duplicates are slipping through.

## What's actually verified vs. not

I ran this in a sandboxed environment with **no network access to YouTube**, so I could not
test the full pipeline end-to-end against a real live stream. What I *did* verify directly:

- ✅ **Core detection logic** (`loop_detector.py`) — `test_loop_detector.py` runs it against
  synthetic frames (a repeating cycle, all-unique frames, and a single coincidental repeat) and
  confirms it correctly flags the loop, leaves fresh content unflagged, and doesn't false-positive
  on one-off similarity. Run it yourself: `python test_loop_detector.py`
- ✅ **ffmpeg frame-grabbing** (`grab_frame()` in `frame_sampler.py`) — tested against a locally
  generated synthetic video file and confirmed it correctly returns a decoded PIL Image.
- ⚠️ **Not verified**: `get_stream_url()`, the `yt-dlp` call that resolves a YouTube watch URL
  to a live media URL. This is standard, widely-used `yt-dlp` functionality, but you should
  confirm it works against your actual target stream before relying on results — YouTube
  occasionally changes things that break extraction tools until they're patched upstream.

**Recommendation**: before your first real test run, do a quick manual sanity check —
`yt-dlp -g "YOUR_URL"` on its own in a terminal — to confirm it returns a stream URL for
your target before running the full pipeline.

## Known limitations (worth a paragraph in your writeup)

- **Static/mostly-static shots** (e.g. a fixed news-desk camera during a calm segment) can
  read as "low novelty" even on a genuinely live stream. The period-consistency check (not just
  raw match count) exists specifically to reduce this false-positive risk — a real anchor shot
  won't recur at an exact fixed interval, whereas a true loop will.
- **A well-produced fake** can defeat pure frame-repetition detection by inserting a live
  clock overlay or picture-in-picture chat reaction on top of otherwise-looped footage — that's
  effectively a partial loop, and would show up as high-similarity-but-not-identical frames.
  This is exactly why the project brief suggested treating frame-repetition as the primary
  signal but combining it with others (see below) rather than relying on it alone.
- **Loop period must fit inside your sampling window.** If the underlying video is a 2-hour
  loop and you only sample for 30 minutes, you won't see it repeat.

## Natural next steps / extensions

Not built yet, but the codebase is structured so each of these can be a separate module that
feeds into the same verdict:

- **On-screen clock OCR**: crop a fixed region of interest, run `pytesseract`, parse the time,
  diff against wall-clock time.
- **Chat responsiveness**: pull live chat (e.g. via `pytchat` or the YouTube Data API) and check
  whether host commentary timing correlates with chat activity spikes.
- **Weighted multi-signal verdict**: instead of the frame-loop check alone deciding
  `probable_loop`, combine it with the above as independent weighted signals — this is likely
  the strongest framing for your final report, since it directly demonstrates why no single
  heuristic is reliable alone.
