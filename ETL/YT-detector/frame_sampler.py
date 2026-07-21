"""
frame_sampler.py

Pulls periodic frame snapshots from a live YouTube stream using yt-dlp
(to resolve the actual playable media URL) and ffmpeg (to grab a single
frame from it). Requires yt-dlp and ffmpeg installed and on PATH.
"""

import io
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

from PIL import Image


def resolve_ffmpeg() -> str:
    """Return a usable FFmpeg executable without relying solely on shell PATH."""
    configured = os.getenv("YT_DETECTOR_FFMPEG")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(
            f"YT_DETECTOR_FFMPEG points to a missing file: {candidate}"
        )

    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    # WinGet installs FFmpeg under a versioned package directory. Checking this
    # makes the detector work in terminals opened before PATH was refreshed.
    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    matches = list(winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"))
    if matches:
        return str(max(matches, key=lambda item: item.stat().st_mtime))

    raise FileNotFoundError(
        "FFmpeg was not found. Install it with 'winget install --id Gyan.FFmpeg -e' "
        "or set YT_DETECTOR_FFMPEG to the full path of ffmpeg.exe."
    )


def get_stream_url(youtube_url: str) -> str:
    """Resolve a YouTube watch URL to a direct, playable stream URL via yt-dlp."""
    result = subprocess.run(
        ["yt-dlp", "-g", "-f", "best[height<=480]", youtube_url],
        capture_output=True, text=True, check=True,
    )
    # yt-dlp can print more than one URL (e.g. separate video/audio) -- take the first
    return result.stdout.strip().splitlines()[0]


def grab_frame(stream_url: str) -> Image.Image:
    """Grab a single current frame from a stream URL as a PIL Image."""
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
    return Image.open(io.BytesIO(result.stdout))


def sample_stream(
    youtube_url: str,
    interval_seconds: int,
    duration_minutes: float,
    on_frame: Optional[Callable[[float, Image.Image], None]] = None,
    refresh_url_every: int = 10,
) -> Iterator[tuple]:
    """
    Yields (elapsed_seconds, PIL.Image) tuples, sampled from the stream every
    `interval_seconds` for a total of `duration_minutes`.

    refresh_url_every: re-resolve the stream URL every N samples, since
    YouTube's signed stream URLs expire after a while.
    """
    start = time.monotonic()
    end = start + duration_minutes * 60
    stream_url = get_stream_url(youtube_url)

    sample_count = 0
    while time.monotonic() < end:
        if sample_count > 0 and sample_count % refresh_url_every == 0:
            stream_url = get_stream_url(youtube_url)

        elapsed = time.monotonic() - start
        try:
            frame = grab_frame(stream_url)
        except subprocess.CalledProcessError:
            # likely a transient hiccup or an expired signed URL -- refresh once and retry
            stream_url = get_stream_url(youtube_url)
            frame = grab_frame(stream_url)

        if on_frame:
            on_frame(elapsed, frame)
        yield elapsed, frame

        sample_count += 1
        time.sleep(interval_seconds)
