#!/usr/bin/env python3
"""
Match Stats Card Generator — 4-Template Production Build
=========================================================
All layouts pixel-matched to reference images:

  T1  Single Player Stats      — photo + solid dark panel, title + stacked stat rows
  T2  Head-to-Head Insights    — split cards, pill stat rows, playing-style tags, center-V
  T3  VS Tug-of-War            — split photos top, full-width mirrored bars, score line
  T4  Performance Spotlight    — 3-column player card leaderboard, banner, sponsor footer

Run:
    python scoreboard_app.py

Verify every template without opening the GUI:
    python scoreboard_app.py --render-all ./template_previews

Requires:
    pip install pillow

Optional direct Blackmagic DeckLink output:
    pip install "gstreamer-bundle>=1.28,<1.29"
"""

from __future__ import annotations
import argparse, colorsys, copy, csv, json, os, re, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter, ImageEnhance
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

IMAGE_FILETYPES = [
    ("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.avif"),
    ("GIF images", "*.gif"),
    ("All files", "*.*"),
]

PROJECT_FILETYPES = [
    ("Scoreboard project", "*.scoreboard.json"),
    ("JSON", "*.json"),
]

STYLE_PRESET_FILETYPES = [
    ("Scoreboard style", "*.scoreboard-style.json"),
    ("JSON", "*.json"),
]

VIDEO_EXPORT_PRESETS = {
    "HD 1080i50": {
        "width":1920, "height":1080, "fps":25, "level":"4.1", "interlaced":True,
        "gst_mode":"1080i50",
    },
    "HD 1080p25": {
        "width":1920, "height":1080, "fps":25, "level":"4.1", "gst_mode":"1080p25",
    },
    "HD 1080p50": {
        "width":1920, "height":1080, "fps":50, "level":"4.2", "gst_mode":"1080p50",
    },
    "HD 720p50": {
        "width":1280, "height":720, "fps":50, "level":"4.1", "gst_mode":"720p50",
    },
}

DECKLINK_OUTPUTS = {
    "DeckLink output 1 (device 0)": 0,
    "DeckLink output 2 (device 1)": 1,
}
_GSTREAMER_DLL_HANDLES = []

TEXT_CASE_CHOICES = ("As typed", "UPPERCASE", "lowercase", "Title Case")
PANEL_STYLE_LABELS = {
    "Solid": "solid",
    "Gradient": "gradient",
    "Glass": "glass",
}
PANEL_STYLE_NAMES = {value: label for label, value in PANEL_STYLE_LABELS.items()}


# ═══════════════════════════════════════════════════════════════════════════
# FONTS
# ═══════════════════════════════════════════════════════════════════════════

_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf",
]
_BOLD_ITALIC = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
]
_ITALIC = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "C:/Windows/Fonts/ariali.ttf",
]
_fc: Dict[Tuple, Any] = {}

def _lf(paths, size):
    k = (paths[0], size)
    if k in _fc: return _fc[k]
    f = None
    for p in paths:
        if os.path.exists(p):
            try: f = ImageFont.truetype(p, size); break
            except: pass
    if f is None: f = ImageFont.load_default()
    _fc[k] = f; return f

def fb(s):  return _lf(_BOLD, max(1, s))
def fr(s):  return _lf(_REG,  max(1, s))
def fbi(s): return _lf(_BOLD_ITALIC, max(1, s))
def fi(s):  return _lf(_ITALIC, max(1, s))


FONT_FAMILIES = {
    "Default": {"regular":_REG,"bold":_BOLD,"italic":_ITALIC,"bold_italic":_BOLD_ITALIC},
    "Arial": {
        "regular":["C:/Windows/Fonts/arial.ttf"], "bold":["C:/Windows/Fonts/arialbd.ttf"],
        "italic":["C:/Windows/Fonts/ariali.ttf"], "bold_italic":["C:/Windows/Fonts/arialbi.ttf"],
    },
    "Arial Black": {"regular":["C:/Windows/Fonts/ariblk.ttf"]},
    "Bahnschrift": {"regular":["C:/Windows/Fonts/bahnschrift.ttf"]},
    "Calibri": {
        "regular":["C:/Windows/Fonts/calibri.ttf"], "bold":["C:/Windows/Fonts/calibrib.ttf"],
        "italic":["C:/Windows/Fonts/calibrii.ttf"], "bold_italic":["C:/Windows/Fonts/calibriz.ttf"],
    },
    "Cambria": {
        "regular":["C:/Windows/Fonts/cambria.ttc"], "bold":["C:/Windows/Fonts/cambriab.ttf"],
        "italic":["C:/Windows/Fonts/cambriai.ttf"], "bold_italic":["C:/Windows/Fonts/cambriaz.ttf"],
    },
    "Comic Sans MS": {
        "regular":["C:/Windows/Fonts/comic.ttf"], "bold":["C:/Windows/Fonts/comicbd.ttf"],
        "italic":["C:/Windows/Fonts/comici.ttf"], "bold_italic":["C:/Windows/Fonts/comicz.ttf"],
    },
    "Consolas": {
        "regular":["C:/Windows/Fonts/consola.ttf"], "bold":["C:/Windows/Fonts/consolab.ttf"],
        "italic":["C:/Windows/Fonts/consolai.ttf"], "bold_italic":["C:/Windows/Fonts/consolaz.ttf"],
    },
    "Courier New": {
        "regular":["C:/Windows/Fonts/cour.ttf"], "bold":["C:/Windows/Fonts/courbd.ttf"],
        "italic":["C:/Windows/Fonts/couri.ttf"], "bold_italic":["C:/Windows/Fonts/courbi.ttf"],
    },
    "Georgia": {
        "regular":["C:/Windows/Fonts/georgia.ttf"], "bold":["C:/Windows/Fonts/georgiab.ttf"],
        "italic":["C:/Windows/Fonts/georgiai.ttf"], "bold_italic":["C:/Windows/Fonts/georgiaz.ttf"],
    },
    "Impact": {"regular":["C:/Windows/Fonts/impact.ttf"]},
    "Segoe UI": {
        "regular":["C:/Windows/Fonts/segoeui.ttf"], "bold":["C:/Windows/Fonts/segoeuib.ttf"],
        "italic":["C:/Windows/Fonts/segoeuii.ttf"], "bold_italic":["C:/Windows/Fonts/segoeuiz.ttf"],
    },
    "Tahoma": {"regular":["C:/Windows/Fonts/tahoma.ttf"],"bold":["C:/Windows/Fonts/tahomabd.ttf"]},
    "Times New Roman": {
        "regular":["C:/Windows/Fonts/times.ttf"], "bold":["C:/Windows/Fonts/timesbd.ttf"],
        "italic":["C:/Windows/Fonts/timesi.ttf"], "bold_italic":["C:/Windows/Fonts/timesbi.ttf"],
    },
    "Trebuchet MS": {
        "regular":["C:/Windows/Fonts/trebuc.ttf"], "bold":["C:/Windows/Fonts/trebucbd.ttf"],
        "italic":["C:/Windows/Fonts/trebucit.ttf"], "bold_italic":["C:/Windows/Fonts/trebucbi.ttf"],
    },
    "Verdana": {
        "regular":["C:/Windows/Fonts/verdana.ttf"], "bold":["C:/Windows/Fonts/verdanab.ttf"],
        "italic":["C:/Windows/Fonts/verdanai.ttf"], "bold_italic":["C:/Windows/Fonts/verdanaz.ttf"],
    },
    "DejaVu Sans": {
        "regular":["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
        "bold":["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
        "italic":["/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"],
        "bold_italic":["/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"],
    },
    "Liberation Sans": {
        "regular":["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
        "bold":["/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
        "italic":["/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"],
        "bold_italic":["/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf"],
    },
}
FONT_CHOICES = tuple(
    family for family,variants in FONT_FAMILIES.items()
    if family == "Default" or any(os.path.exists(path) for paths in variants.values() for path in paths)
)


def _font_paths(family: str, variant: str):
    selected=FONT_FAMILIES.get(family,FONT_FAMILIES["Default"])
    fallback=FONT_FAMILIES["Default"]
    return list(selected.get(variant,selected.get("regular",[]))) + list(fallback.get(variant,_REG))


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def exnum(text: str) -> Optional[float]:
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(text))
    return float(m.group(0).replace(",", ".")) if m else None

def pct(val, maxv) -> float:
    n = exnum(val)
    if n is None: return 0.0
    try: mv = float(maxv)
    except: mv = 100.0
    if mv <= 0: mv = 100.0
    return max(0.0, min(100.0, n / mv * 100))

def load_photo(path: str) -> Optional[Image.Image]:
    if not path or not os.path.exists(path): return None
    try:
        # Scoreboards are static compositions. Animated GIFs therefore use
        # their first frame consistently in the editor, preview, and export.
        with Image.open(path) as source:
            source.seek(0)
            return source.convert("RGBA")
    except (OSError, ValueError, EOFError):
        return None


def locate_ffmpeg(explicit: str = "") -> Optional[str]:
    """Find FFmpeg in an explicit path, the environment, or known local installs."""
    app_root = Path(__file__).resolve().parents[3]
    candidates = [
        explicit,
        os.getenv("FFMPEG_PATH", ""),
        str(app_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"),
        str(app_root / "tools" / "ffmpeg.exe"),
        shutil.which("ffmpeg") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(
            winget_root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"), reverse=True,
        )
        if matches:
            return str(matches[0].resolve())
    return None


def build_mp4_command(
    ffmpeg: str, source_png: Path, output_mp4: Path, preset_name: str, duration: int,
) -> List[str]:
    """Build a deterministic, DeckLink-host-friendly H.264 MP4 command."""
    preset = VIDEO_EXPORT_PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"Unknown video preset: {preset_name}")
    duration = max(1, min(3600, int(duration)))
    width, height, fps = preset["width"], preset["height"], preset["fps"]
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,format=yuv420p"
    )
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(source_png),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", str(duration), "-vf", video_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    ]
    if preset.get("interlaced"):
        command.extend(["-flags", "+ildct+ilme", "-x264-params", "tff=1"])
    command.extend([
        "-profile:v", "high", "-level:v", preset["level"],
        "-r", str(fps), "-g", str(fps * 2), "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart", str(output_mp4),
    ])
    return command


def prepare_broadcast_frame(image: Image.Image, preset_name: str) -> Image.Image:
    """Fit a scoreboard inside an exact broadcast raster without cropping it."""
    preset = VIDEO_EXPORT_PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"Unknown video preset: {preset_name}")
    width, height = preset["width"], preset["height"]
    source = image.convert("RGB")
    scale = min(width / source.width, height / source.height)
    fitted_size = (
        max(1, int(round(source.width * scale))),
        max(1, int(round(source.height * scale))),
    )
    fitted = source.resize(fitted_size, Image.LANCZOS)
    frame = Image.new("RGB", (width, height), (0, 0, 0))
    frame.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return frame


def build_decklink_pipeline(preset_name: str, device_number: int) -> str:
    """Build the direct SDI pipeline used by the embedded GStreamer runtime."""
    preset = VIDEO_EXPORT_PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"Unknown video preset: {preset_name}")
    device_number = max(0, int(device_number))
    width, height, fps = preset["width"], preset["height"], preset["fps"]
    source_caps = (
        f"video/x-raw,format=RGB,width={width},height={height},"
        f"framerate={fps}/1,pixel-aspect-ratio=1/1"
    )
    output_caps = (
        f"video/x-raw,format=UYVY,width={width},height={height},"
        f"framerate={fps}/1,pixel-aspect-ratio=1/1,colorimetry=bt709"
    )
    stages = [
        "appsrc name=scoreboard_source is-live=true block=false format=time "
        f"do-timestamp=true caps=\"{source_caps}\"",
        "queue max-size-buffers=2 leaky=downstream",
        "videoconvert",
    ]
    if preset.get("interlaced"):
        stages.extend([
            f"{output_caps},interlace-mode=progressive",
            "interlace field-pattern=2:2 top-field-first=true",
            f"{output_caps},interlace-mode=interleaved,field-order=top-field-first",
        ])
    else:
        stages.append(f"{output_caps},interlace-mode=progressive")
    stages.append(
        "decklinkvideosink "
        f"device-number={device_number} mode={preset['gst_mode']} "
        "video-format=8bit-yuv keyer-mode=off sync=true"
    )
    return " ! ".join(stages)


def load_gstreamer():
    """Load the optional bundled GStreamer runtime with a working plugin scanner."""
    try:
        import gstreamer_libs
    except ImportError as exc:
        raise RuntimeError(
            'GStreamer is not installed. Run: pip install "gstreamer-bundle>=1.28,<1.29"'
        ) from exc

    environment, dll_paths = gstreamer_libs.gstreamer_env()
    scanner = Path(environment.get("GST_PLUGIN_SCANNER_1_0", ""))
    scanner_exe = scanner.with_suffix(".exe")
    if os.name == "nt" and scanner.suffix.lower() != ".exe" and scanner_exe.is_file():
        environment["GST_PLUGIN_SCANNER_1_0"] = str(scanner_exe)
        environment["GST_PLUGIN_SCANNER"] = str(scanner_exe)
    blackmagic = Path(r"C:\Program Files\Blackmagic Design\Blackmagic Desktop Video")
    if blackmagic.is_dir():
        environment["PATH"] = str(blackmagic) + os.pathsep + environment.get("PATH", "")
    os.environ.update(environment)
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for directory in str(dll_paths).split(os.pathsep):
            if directory and Path(directory).is_dir():
                try:
                    _GSTREAMER_DLL_HANDLES.append(os.add_dll_directory(directory))
                except OSError:
                    pass
        if blackmagic.is_dir():
            try:
                _GSTREAMER_DLL_HANDLES.append(os.add_dll_directory(str(blackmagic)))
            except OSError:
                pass

    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as exc:
        raise RuntimeError(f"Could not load GStreamer: {exc}") from exc
    Gst.init(None)
    missing = [
        name for name in ("appsrc", "queue", "videoconvert", "interlace", "decklinkvideosink")
        if Gst.ElementFactory.find(name) is None
    ]
    if missing:
        raise RuntimeError("Missing GStreamer elements: " + ", ".join(missing))
    return Gst


class DeckLinkLiveOutput:
    """Hold and update the latest scoreboard frame on one DeckLink output."""

    def __init__(self, preset_name: str, device_number: int):
        self.preset_name = preset_name
        self.device_number = int(device_number)
        self.Gst = load_gstreamer()
        try:
            self.pipeline = self.Gst.parse_launch(
                build_decklink_pipeline(preset_name, self.device_number)
            )
        except Exception as exc:
            raise RuntimeError(f"Could not create DeckLink pipeline: {exc}") from exc
        self.source = self.pipeline.get_by_name("scoreboard_source")
        self.bus = self.pipeline.get_bus()
        self.running = False
        self._frame_lock = threading.Lock()
        self._frame_data = b""
        self._stop_event = threading.Event()
        self._thread = None
        self._thread_error = None

    def start(self, image: Image.Image) -> None:
        self._set_frame(image)
        result = self.pipeline.set_state(self.Gst.State.PLAYING)
        if result == self.Gst.StateChangeReturn.FAILURE:
            self.pipeline.set_state(self.Gst.State.NULL)
            raise RuntimeError("DeckLink rejected the selected output mode or device.")
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._feed_frames, name="scoreboard-decklink-output", daemon=True,
        )
        self._thread.start()

    def update(self, image: Image.Image) -> None:
        if not self.running:
            return
        self._set_frame(image)

    def _set_frame(self, image: Image.Image) -> None:
        frame = prepare_broadcast_frame(image, self.preset_name)
        with self._frame_lock:
            self._frame_data = frame.tobytes("raw", "RGB")

    def _feed_frames(self) -> None:
        fps = VIDEO_EXPORT_PRESETS[self.preset_name]["fps"]
        duration = self.Gst.SECOND // fps
        frame_number = 0
        deadline = time.perf_counter()
        while not self._stop_event.is_set():
            with self._frame_lock:
                data = self._frame_data
            buffer = self.Gst.Buffer.new_wrapped(data)
            buffer.pts = frame_number * duration
            buffer.dts = buffer.pts
            buffer.duration = duration
            flow = self.source.emit("push-buffer", buffer)
            if flow != self.Gst.FlowReturn.OK:
                if not self._stop_event.is_set():
                    self._thread_error = f"DeckLink frame output failed: {flow.value_nick}"
                return
            frame_number += 1
            deadline += 1.0 / fps
            self._stop_event.wait(max(0.0, deadline - time.perf_counter()))

    def poll_error(self) -> Optional[str]:
        if self._thread_error:
            return self._thread_error
        message = self.bus.pop_filtered(
            self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS
        )
        if message is None:
            return None
        if message.type == self.Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            detail = debug.strip() if debug else ""
            return f"{error.message}\n{detail}".strip()
        return "DeckLink output ended unexpectedly."

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self.running:
            self.source.emit("end-of-stream")
        self.pipeline.set_state(self.Gst.State.NULL)
        self.running = False

def cover_crop(img: Image.Image, w: int, h: int, zoom: float = 100.0,
               focus_x: float = 50.0, focus_y: float = 50.0) -> Image.Image:
    img = img.convert("RGB")
    pw, ph = img.size
    scale = max(w / pw, h / ph) * max(1.0, float(zoom) / 100.0)
    nw, nh = max(1, int(pw*scale)), max(1, int(ph*scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = int(max(0, nw-w) * max(0.0, min(100.0, float(focus_x))) / 100.0)
    top = int(max(0, nh-h) * max(0.0, min(100.0, float(focus_y))) / 100.0)
    return img.crop((left, top, left+w, top+h))

def text_bbox(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def draw_text_centered(draw, text, font, cx, cy, fill):
    w, h = text_bbox(draw, text, font)
    bb = draw.textbbox((0,0), text, font=font)
    draw.text((cx - w//2, cy - h//2 - bb[1]), text, font=font, fill=fill)

def draw_text_right(draw, text, font, rx, y, fill):
    w, _ = text_bbox(draw, text, font)
    draw.text((rx - w, y), text, font=font, fill=fill)

def fit_font(draw, text: str, max_width: int, start_size: int,
             minimum: int = 8, factory=fb):
    """Return the largest requested font that fits the available width."""
    size = max(minimum, int(start_size))
    font = factory(size)
    while size > minimum and text_bbox(draw, text, font)[0] > max_width:
        size -= 1
        font = factory(size)
    return font

def ellipsize(draw, text: str, font, max_width: int) -> str:
    if text_bbox(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    value = text
    while value and text_bbox(draw, value + suffix, font)[0] > max_width:
        value = value[:-1]
    return value.rstrip() + suffix if value else suffix


# ═══════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════

THEME = {
    "bg":       (10, 30, 48),
    "panel":    (18, 32, 54),
    "row_bg":   (38, 54, 82),
    "bar_track":(28, 40, 58),
    "bar_lose": (80, 95, 115),
    "accent":   (210, 235, 60),
    "white":    (255, 255, 255),
    "label":    (220, 228, 235),
    "muted":    (145, 160, 180),
    "dark":     (12, 20, 34),
    "header_ink":(18, 28, 44),
}


TEXT_STYLE_TARGETS = {
    "t1": [
        ("all", "All text"),
        ("title", "Title"),
        ("stat_labels", "Stat labels"),
        ("stat_values", "Stat values"),
    ],
    "t2": [
        ("all", "All text"),
        ("header", "Header"),
        ("player_1_names", "Player 1 name"),
        ("player_1_country", "Player 1 country"),
        ("player_2_names", "Player 2 name"),
        ("player_2_country", "Player 2 country"),
        ("stat_labels", "Stat labels"),
        ("player_1_values", "Player 1 values"),
        ("player_2_values", "Player 2 values"),
        ("style_heading", "Playing style heading"),
        ("style_tags", "Playing style tags"),
        ("divider", "Center divider"),
    ],
    "t3": [
        ("all", "All text"),
        ("player_1_names", "Left player name"),
        ("player_1_team", "Left player team"),
        ("player_2_names", "Right player name"),
        ("player_2_team", "Right player team"),
        ("versus", "VS text"),
        ("score", "Score"),
        ("stat_labels", "Stat labels"),
        ("player_1_values", "Left values"),
        ("player_2_values", "Right values"),
        ("units", "Units"),
        ("sponsor", "Sponsor text"),
    ],
    "t4": [
        ("all", "All text"),
        ("banner", "Banner"),
        ("player_1_names", "Player 1 name"),
        ("player_1_team", "Player 1 team"),
        ("player_1_stat_labels", "Player 1 stat labels"),
        ("player_1_stat_values", "Player 1 stat values"),
        ("player_1_units", "Player 1 units"),
        ("player_1_result", "Player 1 result"),
        ("player_2_names", "Player 2 name"),
        ("player_2_team", "Player 2 team"),
        ("player_2_stat_labels", "Player 2 stat labels"),
        ("player_2_stat_values", "Player 2 stat values"),
        ("player_2_units", "Player 2 units"),
        ("player_2_result", "Player 2 result"),
        ("player_3_names", "Player 3 name"),
        ("player_3_team", "Player 3 team"),
        ("player_3_stat_labels", "Player 3 stat labels"),
        ("player_3_stat_values", "Player 3 stat values"),
        ("player_3_units", "Player 3 units"),
        ("player_3_result", "Player 3 result"),
        ("sponsor", "Sponsor text"),
    ],
}

GROUP_COLOR_SPECS = {
    "t2": (
        ("header", "Headers", ("header",)),
        ("names", "Player names", ("player_1_names", "player_2_names")),
        ("stat_labels", "Stat headings", ("stat_labels",)),
        ("values", "Values", ("player_1_values", "player_2_values")),
        ("bar", "Bars", ()),
        ("style", "Playing style", ("style_heading", "style_tags")),
    ),
    "t3": (
        ("names", "Player names", ("player_1_names", "player_2_names")),
        ("teams", "Teams", ("player_1_team", "player_2_team")),
        ("stat_labels", "Stat headings", ("stat_labels",)),
        ("values", "Values", ("player_1_values", "player_2_values")),
        ("bar", "Bars", ()),
        ("center", "VS and score", ("versus", "score")),
    ),
    "t4": (
        ("banner", "Banner", ("banner",)),
        ("names", "Player names", tuple(f"player_{i}_names" for i in range(1,4))),
        ("teams", "Teams", tuple(f"player_{i}_team" for i in range(1,4))),
        ("stat_labels", "Stat headings", tuple(f"player_{i}_stat_labels" for i in range(1,4))),
        ("values", "Values", tuple(f"player_{i}_stat_values" for i in range(1,4))),
        ("bar", "Bars", ()),
        ("results", "Results", tuple(f"player_{i}_result" for i in range(1,4))),
    ),
}

TEXT_ROLE_DEFAULT_COLORS = {
    "t1": {"title":"white", "stat_labels":"label", "stat_values":"accent"},
    "t2": {
        "header":"header_ink", "player_1_names":"white", "player_1_country":"muted",
        "player_2_names":"white", "player_2_country":"muted", "stat_labels":"white",
        "player_1_values":"white", "player_2_values":"white", "style_heading":"white",
        "style_tags":"accent", "divider":"white",
    },
    "t3": {
        "player_1_names":"white", "player_1_team":"muted", "player_2_names":"white",
        "player_2_team":"muted", "versus":"white", "score":"muted", "stat_labels":"label",
        "player_1_values":"white", "player_2_values":"white", "units":"muted", "sponsor":"muted",
    },
    "t4": {"banner":"white", "sponsor":"muted"},
}
for _player_number in range(1, 4):
    TEXT_ROLE_DEFAULT_COLORS["t4"].update({
        f"player_{_player_number}_names":"white",
        f"player_{_player_number}_team":"muted",
        f"player_{_player_number}_stat_labels":"label",
        f"player_{_player_number}_stat_values":"white",
        f"player_{_player_number}_units":"muted",
        f"player_{_player_number}_result":"muted",
    })


def normalize_rgb(value, fallback):
    """Return a safe RGB tuple from project data or a renderer default."""
    try:
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return tuple(max(0, min(255, int(channel))) for channel in value)
    except (TypeError, ValueError):
        pass
    return tuple(fallback)


def color_luminance(color) -> float:
    """Return WCAG relative luminance for an RGB color."""
    channels = []
    for value in normalize_rgb(color, THEME["bg"]):
        channel = value / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def readable_text_colors(background) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Return primary and secondary text colors that remain readable on a background."""
    if color_luminance(background) > 0.42:
        return (10, 24, 38), (42, 65, 80)
    return THEME["white"], THEME["muted"]


def text_style_values(cfg: Dict, role: str, default_color) -> Tuple[Tuple[int, int, int], int]:
    """Resolve inherited all-text and role-specific color/size overrides."""
    merged: Dict[str, Any] = {}
    styles = cfg.get("text_styles", {})
    if isinstance(styles, dict):
        all_style = styles.get("all")
        role_style = styles.get(role)
        if isinstance(all_style, dict):
            merged.update(all_style)
        if role != "all" and isinstance(role_style, dict):
            merged.update(role_style)
    color = normalize_rgb(merged.get("color"), default_color)
    try:
        size_pct = int(round(float(merged.get("size_pct", 100))))
    except (TypeError, ValueError):
        size_pct = 100
    return color, max(50, min(200, size_pct))


def text_font_family(cfg: Dict, role: str) -> str:
    """Resolve font inheritance independently from color and size."""
    family="Default"
    styles=cfg.get("text_styles",{})
    if isinstance(styles,dict):
        all_style=styles.get("all")
        role_style=styles.get(role)
        if isinstance(all_style,dict):
            family=all_style.get("font_family",family)
        if role != "all" and isinstance(role_style,dict):
            family=role_style.get("font_family",family)
    return family if family in FONT_CHOICES else "Default"


def text_case_mode(cfg: Dict, role: str) -> str:
    """Resolve an inherited case transform while preserving typed text by default."""
    mode="As typed"
    styles=cfg.get("text_styles",{})
    if isinstance(styles,dict):
        all_style=styles.get("all")
        role_style=styles.get(role)
        if isinstance(all_style,dict):
            mode=all_style.get("case",mode)
        if role != "all" and isinstance(role_style,dict):
            mode=role_style.get("case",mode)
    return mode if mode in TEXT_CASE_CHOICES else "As typed"


def apply_text_case(cfg: Dict, role: str, value: Any) -> str:
    """Apply the selected case transform to display text only."""
    text=str(value)
    mode=text_case_mode(cfg,role)
    if mode == "UPPERCASE":
        return text.upper()
    if mode == "lowercase":
        return text.lower()
    if mode == "Title Case":
        return text.title()
    return text


def text_font(cfg: Dict, role: str, size: int, variant: str="regular"):
    return _lf(_font_paths(text_font_family(cfg,role),variant),max(1,size))


def text_font_factory(cfg: Dict, role: str, variant: str="regular"):
    return lambda size:text_font(cfg,role,size,variant)


def styled_text(cfg: Dict, role: str, default_color, default_size: int):
    color, size_pct = text_style_values(cfg, role, default_color)
    return color, max(1, int(round(default_size * size_pct / 100.0)))


def default_text_color(cfg: Dict, template: str, role: str) -> Tuple[int, int, int]:
    if template == "t2" and role in {
        "player_1_names", "player_1_country", "player_2_names", "player_2_country"
    }:
        primary, secondary = readable_text_colors(cfg.get("background_color", THEME["panel"]))
        return primary if role.endswith("names") else secondary
    color_name = TEXT_ROLE_DEFAULT_COLORS.get(template, {}).get(role, "white")
    if color_name == "accent":
        return normalize_rgb(cfg.get("accent_color"), THEME["accent"])
    return THEME.get(color_name, THEME["white"])


T1_LAYER_KEYS = {
    "background": ("photo_path", "photo_focus_x", "photo_focus_y", "photo_zoom"),
    "player": ("player_path", "player_x_pct", "player_y_pct", "player_size_pct"),
    "logo": ("logo_path", "logo_x_pct", "logo_y_pct", "logo_size_pct"),
}


def clamp_number(value, minimum: float, maximum: float, fallback: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return fallback


def t1_overlay_geometry(cfg: Dict, layer_name: str, width: int, height: int):
    """Return the visible overlay image and its center-anchored canvas box."""
    if layer_name not in {"player", "logo"}:
        return None
    path_key, x_key, y_key, size_key = T1_LAYER_KEYS[layer_name]
    source = load_photo(cfg.get(path_key, ""))
    if source is None or source.width <= 0 or source.height <= 0:
        return None

    size_pct = clamp_number(cfg.get(size_key), 2, 300, 80 if layer_name == "player" else 14)
    if layer_name == "player":
        overlay_h = max(1, int(height * size_pct / 100.0))
        overlay_w = max(1, int(source.width * overlay_h / source.height))
    else:
        overlay_w = max(1, int(width * size_pct / 100.0))
        overlay_h = max(1, int(source.height * overlay_w / source.width))

    center_x = width * clamp_number(cfg.get(x_key), 0, 100, 32 if layer_name == "player" else 90) / 100.0
    center_y = height * clamp_number(cfg.get(y_key), 0, 100, 52 if layer_name == "player" else 10) / 100.0
    left = int(round(center_x - overlay_w / 2.0))
    top = int(round(center_y - overlay_h / 2.0))
    return source, (left, top, overlay_w, overlay_h)


def paste_t1_overlay(image: Image.Image, cfg: Dict, layer_name: str) -> None:
    geometry = t1_overlay_geometry(cfg, layer_name, image.width, image.height)
    if geometry is None:
        return
    source, (left, top, overlay_w, overlay_h) = geometry
    overlay = source.resize((overlay_w, overlay_h), Image.LANCZOS)
    image.paste(overlay, (left, top), overlay)


def free_logo_geometry(cfg: Dict, width: int, height: int):
    """Return a center-anchored logo overlay that may sit anywhere on the canvas."""
    path=cfg.get("logo_path", "")
    if not path:
        return None
    source = load_photo(path)
    if source is None or source.width <= 0 or source.height <= 0:
        return None
    size_pct = clamp_number(cfg.get("logo_size_pct"), 2, 100, 12)
    overlay_w = max(1, int(width * size_pct / 100.0))
    overlay_h = max(1, int(source.height * overlay_w / source.width))
    center_x = width * clamp_number(cfg.get("logo_x_pct"), 0, 100, 90) / 100.0
    center_y = height * clamp_number(cfg.get("logo_y_pct"), 0, 100, 10) / 100.0
    return source, (
        int(round(center_x - overlay_w / 2.0)),
        int(round(center_y - overlay_h / 2.0)),
        overlay_w,
        overlay_h,
    )


def paste_free_logo(image: Image.Image, cfg: Dict) -> None:
    geometry = free_logo_geometry(cfg, image.width, image.height)
    if geometry is None:
        return
    source, (left, top, width, height) = geometry
    overlay = source.resize((width, height), Image.LANCZOS)
    image.paste(overlay, (left, top), overlay)


def canvas_photo_boxes(template: str, cfg: Dict, width: int, height: int):
    """Photo crop regions used by both renderers and direct canvas editing."""
    if template == "t2":
        photo_width = int(
            (width // 2) * clamp_number(cfg.get("photo_width_pct"), 30, 52, 40) / 100.0
        )
        return {
            "photo_a": (0, 0, photo_width, height),
            "photo_b": (width - photo_width, 0, width, height),
        }
    if template == "t3":
        photo_height = int(height * 0.52)
        return {
            "photo_a": (0, 0, width // 2, photo_height),
            "photo_b": (width // 2, 0, width, photo_height),
        }
    if template == "t4":
        banner_height = int(height * 0.088)
        gap = int(width * 0.012)
        column_width = (width - gap * 4) // 3
        column_top = banner_height + int(height * 0.01)
        column_height = height - column_top - int(height * 0.09)
        # Includes the name area so clicking anywhere on a player card selects its photo.
        photo_top = column_top
        photo_bottom = min(height, column_top + int(column_height * 0.58))
        return {
            f"player_{index + 1}": (
                gap + index * (column_width + gap), photo_top,
                gap + index * (column_width + gap) + column_width, photo_bottom,
            )
            for index in range(3)
        }
    return {}


def apply_t1_panel_effect(
    image: Image.Image, cfg: Dict, x0: int, panel_width: int, side: str,
) -> Image.Image:
    """Composite the selected solid, gradient, or frosted-glass panel."""
    width,height=image.size
    panel_width=max(1,min(width,panel_width))
    style=cfg.get("panel_style","solid")
    if style not in PANEL_STYLE_NAMES:
        style="solid"
    primary=normalize_rgb(cfg.get("panel_color"),(8,10,14))
    secondary=normalize_rgb(cfg.get("panel_color_2"),(24,48,72))
    panel_alpha=int(round(255*clamp_number(
        cfg.get("panel_opacity_pct"),0,100,96
    )/100.0))
    fade_width=int(panel_width*clamp_number(
        cfg.get("panel_fade_pct"),0,60,22
    )/100.0)

    mask=Image.new("L",(panel_width,height),panel_alpha)
    if fade_width:
        mask_draw=ImageDraw.Draw(mask)
        for x in range(fade_width):
            alpha=int(panel_alpha*x/max(1,fade_width-1))
            edge_x=x if side == "right" else panel_width-1-x
            mask_draw.line([(edge_x,0),(edge_x,height)],fill=alpha)

    result=image.convert("RGBA")
    if style == "glass" and panel_alpha:
        blur_radius=max(0.0,height*clamp_number(
            cfg.get("panel_blur_pct"),0,8,1.8
        )/100.0)
        region=image.crop((x0,0,x0+panel_width,height)).filter(
            ImageFilter.GaussianBlur(blur_radius)
        ).convert("RGBA")
        result.paste(region,(x0,0),mask)
        tint=Image.new("RGBA",(panel_width,height),(*primary,255))
        tint_mask=mask.point(lambda alpha:int(alpha*0.42))
        result.paste(tint,(x0,0),tint_mask)
    else:
        surface=Image.new("RGBA",(panel_width,height),(*primary,255))
        if style == "gradient":
            surface_draw=ImageDraw.Draw(surface)
            for y in range(height):
                mix=y/max(1,height-1)
                color=tuple(int(round(a+(b-a)*mix)) for a,b in zip(primary,secondary))
                surface_draw.line([(0,y),(panel_width,y)],fill=(*color,255))
        result.paste(surface,(x0,0),mask)
    return result.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# CANVAS SIZES
# ═══════════════════════════════════════════════════════════════════════════

T1_SIZES = {
    "16:9  (1920x1080)": (1920, 1080),
    "16:9  (1024x576)":  (1024, 576),
    "1:1   (1024x1024)": (1024, 1024),
    "9:16  (576x1024)":  (576, 1024),
}
T2_SIZES = {
    "Wide  (1152x640)":  (1152, 640),
    "Square(1080x1080)": (1080, 1080),
    "Story (1080x1920)": (1080, 1920),
}
T3_SIZES = {
    "Square(1080x1080)": (1080, 1080),
    "Wide  (1280x720)":  (1280, 720),
    "4:5   (1080x1350)": (1080, 1350),
}
T4_SIZES = {
    "Square(1080x1080)": (1080, 1080),
    "Wide  (1620x1080)": (1620, 1080),
    "4:5   (1080x1350)": (1080, 1350),
}


# ═══════════════════════════════════════════════════════════════════════════
# T1 — SINGLE PLAYER STATS
# Ref: LsozI9nozgQzay40lO0h2wBvlM.avif
# Full-bleed photo, solid black panel right, title, stacked rows
# ═══════════════════════════════════════════════════════════════════════════

def render_t1(cfg: Dict) -> Image.Image:
    W, H = T1_SIZES.get(cfg.get("canvas_size","16:9  (1920x1080)"), (1920,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc   = normalize_rgb(cfg.get("accent_color"), THEME["accent"])
    group_bar_color = normalize_rgb(cfg.get("bar_color"), acc)
    background=normalize_rgb(cfg.get("background_color"),THEME["bg"])
    side  = cfg.get("panel_side","right")

    img = Image.new("RGB",(W,H),background)
    photo = load_photo(cfg.get("photo_path",""))
    if photo:
        img.paste(cover_crop(
            photo, W, H, cfg.get("photo_zoom", 100),
            cfg.get("photo_focus_x", 50), cfg.get("photo_focus_y", 50)
        ), (0,0))

    player_in_front = bool(cfg.get("player_in_front", False))
    if not player_in_front:
        paste_t1_overlay(img, cfg, "player")

    # Configurable panel with a soft edge toward the image.
    panel_ratio = clamp_number(cfg.get("panel_width_pct"), 20, 80, 40) / 100.0
    panel_w = int(W * panel_ratio)
    x0 = W - panel_w if side == "right" else 0
    img=apply_t1_panel_effect(img,cfg,x0,panel_w,side)

    if player_in_front:
        paste_t1_overlay(img, cfg, "player")

    draw   = ImageDraw.Draw(img)
    tx0    = x0 + int(panel_w * 0.09)
    tw     = panel_w - int(panel_w * 0.18)

    title_text=apply_text_case(
        cfg,"title",cfg.get("title","Match\nStatistics").replace("\\n","\n").strip()
    )
    title_lines=title_text.split("\n") if title_text else []
    rows=cfg.get("rows",[])
    title_col, requested_title_sz = styled_text(
        cfg, "title", THEME["white"], max(32, int(H * 0.082))
    )
    label_col, requested_label_sz = styled_text(
        cfg, "stat_labels", THEME["label"], max(14, int(H * 0.034))
    )
    value_col, requested_value_sz = styled_text(
        cfg, "stat_values", acc, max(26, int(H * 0.072))
    )

    top=int(H*clamp_number(cfg.get("content_top_pct"),2,40,8)/100.0)
    bottom=int(H*0.05)
    requested_title_gap=int(H*clamp_number(cfg.get("title_gap_pct"),0,20,4)/100.0)
    requested_row_gap=int(H*clamp_number(cfg.get("row_gap_pct"),0,15,2)/100.0)
    available=max(1,H-top-bottom)

    def layout_metrics(scale):
        title_sz=max(8,int(round(requested_title_sz*scale)))
        label_sz=max(8,int(round(requested_label_sz*scale)))
        value_sz=max(10,int(round(requested_value_sz*scale)))
        title_font=text_font(cfg,"title",title_sz,"bold")
        label_font=text_font(cfg,"stat_labels",label_sz,"regular")
        value_font=text_font(cfg,"stat_values",value_sz,"bold")
        title_line_gap=max(0,int(title_sz*0.22))
        title_heights=[max(1,text_bbox(draw,line,title_font)[1]) for line in title_lines]
        title_height=sum(title_heights)+max(0,len(title_lines)-1)*title_line_gap
        label_height=max(
            [label_sz]+[
                text_bbox(
                    draw,apply_text_case(cfg,"stat_labels",row.get("label","")),label_font
                )[1]
                for row in rows
            ]
        )
        value_height=max(
            [value_sz]+[
                text_bbox(
                    draw,apply_text_case(cfg,"stat_values",row.get("value","")),value_font
                )[1]
                for row in rows
            ]
        )
        inner_gap=max(1,int(H*0.012*scale))
        bar_gap=max(1,int(H*0.016*scale))
        bar_height=max(2,int(H*0.013*scale))
        row_height=label_height+inner_gap+value_height+bar_gap+bar_height
        return {
            "title_size":title_sz,"label_size":label_sz,"value_size":value_sz,
            "title_font":title_font,"label_font":label_font,"value_font":value_font,
            "title_line_gap":title_line_gap,"title_heights":title_heights,
            "title_height":title_height,"label_height":label_height,
            "value_height":value_height,"inner_gap":inner_gap,"bar_gap":bar_gap,
            "bar_height":bar_height,"row_height":row_height,
        }

    scale=1.0
    metrics=layout_metrics(scale)
    for _attempt in range(8):
        fixed_gap=(requested_title_gap if title_lines and rows else 0)
        fixed_gap+=max(0,len(rows)-1)*requested_row_gap
        required=metrics["title_height"]+len(rows)*metrics["row_height"]+fixed_gap
        if required <= available or scale <= 0.2:
            break
        scalable=max(1,required-fixed_gap)
        scale=max(0.2,scale*max(0.1,(available-fixed_gap)/scalable))
        metrics=layout_metrics(scale)

    remaining=max(0,available-metrics["title_height"]-len(rows)*metrics["row_height"])
    title_gap=min(requested_title_gap,remaining) if title_lines and rows else 0
    remaining=max(0,remaining-title_gap)
    row_gap=min(requested_row_gap,remaining/max(1,len(rows)-1)) if len(rows)>1 else 0

    cy=top
    for index,line in enumerate(title_lines):
        line_font=fit_font(
            draw,line,tw,metrics["title_size"],minimum=8,
            factory=text_font_factory(cfg,"title","bold"),
        )
        draw.text((tx0,cy),line,font=line_font,fill=title_col)
        cy+=max(1,text_bbox(draw,line,line_font)[1])
        if index < len(title_lines)-1:
            cy+=metrics["title_line_gap"]
    cy+=title_gap

    for row in rows:
        label = apply_text_case(cfg,"stat_labels",row.get("label",""))
        value = apply_text_case(cfg,"stat_values",row.get("value",""))
        maxv  = row.get("max","100")
        row_label_col=normalize_rgb(row.get("label_color"),label_col)
        row_value_col=normalize_rgb(row.get("value_color"),value_col)
        row_bar_col=normalize_rgb(row.get("bar_color"),group_bar_color)
        label_font=fit_font(
            draw,label,tw,metrics["label_size"],minimum=7,
            factory=text_font_factory(cfg,"stat_labels","regular"),
        )
        value_font=fit_font(
            draw,value,tw,metrics["value_size"],minimum=9,
            factory=text_font_factory(cfg,"stat_values","bold"),
        )
        draw.text((tx0,cy),label,font=label_font,fill=row_label_col)
        cy+=metrics["label_height"]+metrics["inner_gap"]
        draw.text((tx0,cy),value,font=value_font,fill=row_value_col)
        cy+=metrics["value_height"]+metrics["bar_gap"]

        bar_h=metrics["bar_height"]
        b0,b1=cy,cy+bar_h
        draw.rounded_rectangle([tx0,b0,tx0+tw,b1],radius=bar_h//2,fill=THEME["bar_track"])
        fw = int(tw * pct(value,maxv) / 100)
        if fw > 0:
            draw.rounded_rectangle(
                [tx0,b0,tx0+max(fw,bar_h),b1],radius=bar_h//2,fill=row_bar_col
            )
        cy=b1+row_gap

    # Brand marks should remain visible even when placed over panel copy.
    paste_t1_overlay(img, cfg, "logo")
    return img


# ═══════════════════════════════════════════════════════════════════════════
# T2 — HEAD-TO-HEAD INSIGHTS
# Ref: PRESS_RELEASE.webp (Tsitsipas vs Schwartzman)
# Split panel, player photos flanking, pill stat rows, playing-style tags
# ═══════════════════════════════════════════════════════════════════════════

def _pill_row(draw, x0, w, cy, rh, bh, label, value, other_value,
              max_value, mirrored, acc, bar_color, theme, cfg, value_role, row_colors=None):
    """One side of a comparison row: rounded-rect pill + bar below."""
    label=apply_text_case(cfg,"stat_labels",label)
    value=apply_text_case(cfg,value_role,value)
    n_v = exnum(value) or 0.0
    n_o = exnum(other_value) or 0.0
    winner = n_v >= n_o

    pad     = int(w * 0.06)
    row_colors=row_colors or {}
    label_col, lsz = styled_text(
        cfg, "stat_labels", theme["white"], max(12, int(rh * 0.36))
    )
    value_col, vsz = styled_text(
        cfg, value_role, acc if winner else theme["white"], max(16, int(rh * 0.46))
    )
    label_col=normalize_rgb(row_colors.get("label_color"),label_col)
    value_col=normalize_rgb(row_colors.get("value_color"),value_col)
    lf_     = fit_font(
        draw,str(label),int(w*.62),lsz,minimum=8,
        factory=text_font_factory(cfg,"stat_labels","bold"),
    )
    vf_     = fit_font(
        draw,str(value),int(w*.30),vsz,minimum=9,
        factory=text_font_factory(cfg,value_role,"bold"),
    )

    # Pill background
    draw.rounded_rectangle([x0, cy, x0+w, cy+rh], radius=8, fill=(*theme["row_bg"],230))

    if not mirrored:
        draw.text((x0+pad, cy+rh//2), label, font=lf_, fill=label_col, anchor="lm")
        draw_text_right(draw, str(value), vf_, x0+w-pad, cy+(rh-vsz)//2, value_col)
    else:
        draw.text((x0+pad, cy+rh//2), str(value), font=vf_, fill=value_col, anchor="lm")
        draw_text_right(draw, label, lf_, x0+w-pad, cy+(rh-lsz)//2, label_col)

    # Bar
    by0, by1 = cy+rh+5, cy+rh+5+bh
    draw.rounded_rectangle([x0,by0,x0+w,by1], radius=bh//2, fill=theme["bar_track"])
    fw = int(w * pct(value, max_value) / 100)
    bc = normalize_rgb(row_colors.get("bar_color"),bar_color) if winner else theme["bar_lose"]
    if fw > 0:
        draw.rounded_rectangle([x0,by0,x0+max(fw,bh),by1], radius=bh//2, fill=bc)
    return by1

def render_t2(cfg: Dict) -> Image.Image:
    W, H = T2_SIZES.get(cfg.get("canvas_size","Wide  (1152x640)"), (1152,640))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = normalize_rgb(cfg.get("accent_color"), THEME["accent"])
    bar_color = normalize_rgb(cfg.get("bar_color"), acc)
    background=normalize_rgb(cfg.get("background_color"),THEME["panel"])
    half = W // 2
    photo_width_pct = clamp_number(cfg.get("photo_width_pct"), 30, 52, 40)
    photo_fade_pct = clamp_number(cfg.get("photo_fade_pct"), 0, 35, 12)
    photo_brightness_pct = clamp_number(cfg.get("photo_brightness_pct"), 50, 120, 92)
    photo_w = int(half * photo_width_pct / 100.0)

    img = Image.new("RGB",(W,H),background)

    def paste_photo(path, x, prefix, flip=False):
        p = load_photo(path)
        if p is None: return
        p = p.convert("RGB")
        ph = cover_crop(
            p, photo_w, H, cfg.get(f"{prefix}_zoom", 100),
            cfg.get(f"{prefix}_focus_x", 50), cfg.get(f"{prefix}_focus_y", 50)
        )
        if photo_brightness_pct != 100:
            ph = ImageEnhance.Brightness(ph).enhance(photo_brightness_pct / 100.0)
        # Blend only the inner edge. Keeping the top and outer edge opaque makes
        # ordinary JPG portraits feel intentional instead of color-washed.
        mask = Image.new("L",(photo_w,H),255)
        inner_fade = int(photo_w * photo_fade_pct / 100.0)
        if inner_fade > 0:
            md = ImageDraw.Draw(mask)
            for offset in range(inner_fade):
                alpha = int(255 * offset / max(1, inner_fade - 1))
                column = photo_w - 1 - offset if not flip else offset
                md.line([(column, 0), (column, H)], fill=alpha)
            mask = mask.filter(ImageFilter.GaussianBlur(max(1, int(W * 0.003))))
        base=Image.new("RGBA",(photo_w,H),(*background,255))
        top_=Image.new("RGBA",(photo_w,H),(*background,255))
        top_.paste(ph,(0,0)); top_.putalpha(mask)
        out  = Image.alpha_composite(base,top_).convert("RGB")
        img.paste(out, (x,0))

    paste_photo(cfg.get("photo_a",""), 0, "photo_a", flip=False)
    paste_photo(cfg.get("photo_b",""), W-photo_w, "photo_b", flip=True)

    draw = ImageDraw.Draw(img, "RGBA")
    margin = int(W*0.018)
    tz_w   = half - photo_w - margin*2
    ltz_x  = photo_w + margin
    rtz_x  = half + margin

    # Header bars (white pill)
    hdr_h = int(H * 0.055)
    hdr_w = tz_w + int(tz_w*0.05)
    hdr_y = int(H*0.04)
    hdr_text = apply_text_case(cfg,"header",cfg.get("header_text","INSIGHTS | SHOT QUALITY"))
    header_col, header_sz = styled_text(
        cfg, "header", THEME["header_ink"], max(10, int(hdr_h*0.38))
    )
    hdr_f = fit_font(
        draw,hdr_text,hdr_w-int(hdr_w*.08),header_sz,minimum=8,
        factory=text_font_factory(cfg,"header","bold"),
    )
    for hx in (ltz_x, rtz_x):
        draw.rectangle([hx, hdr_y, hx+hdr_w, hdr_y+hdr_h], fill=(255,255,255))
        tw_, th_ = text_bbox(draw, hdr_text, hdr_f)
        bb = draw.textbbox((0,0), hdr_text, hdr_f)
        draw.text((hx+(hdr_w-tw_)//2, hdr_y+(hdr_h-th_)//2-bb[1]),
                  hdr_text, font=hdr_f, fill=header_col)

    # Player names
    name_y = hdr_y + hdr_h + int(H*0.028)
    ff_sz  = max(10, int(H*0.030))
    fl_sz  = max(14, int(H*0.048))
    def draw_name(x, fn, ln, abbr, role, country_role):
        # Draw italic first name muted, bold last name
        first = apply_text_case(cfg,role,fn)
        last = apply_text_case(cfg,role,ln)
        abbr = apply_text_case(cfg,country_role,abbr)
        name_default = default_text_color(cfg, "t2", role)
        country_default = default_text_color(cfg, "t2", country_role)
        first_col, first_size = styled_text(cfg, role, country_default, ff_sz)
        last_col, last_size = styled_text(cfg, role, name_default, fl_sz)
        country_col, country_size = styled_text(
            cfg, country_role, country_default, max(8, int(H*0.020))
        )
        first_font = fit_font(
            draw,first,int(tz_w*.38),first_size,minimum=8,
            factory=text_font_factory(cfg,role,"italic"),
        )
        fw_ = text_bbox(draw, first+" ", first_font)[0]
        country_font = text_font(cfg,country_role,country_size,"regular")
        reserve = text_bbox(draw, abbr, country_font)[0] + 12 if abbr else 0
        last_font = fit_font(
            draw,last,max(20,tz_w-fw_-reserve),last_size,minimum=10,
            factory=text_font_factory(cfg,role,"bold"),
        )
        draw.text((x, name_y), first, font=first_font, fill=first_col)
        draw.text((x+fw_, name_y+(first_size-last_size)//2), last, font=last_font, fill=last_col)
        if abbr:
            draw.text((x+fw_+text_bbox(draw,last,last_font)[0]+8, name_y+2),
                      abbr, font=country_font, fill=country_col)

    draw_name(ltz_x, cfg.get("name_a_first","Player"), cfg.get("name_a_last","One"),
              cfg.get("abbr_a",""), "player_1_names", "player_1_country")
    draw_name(rtz_x, cfg.get("name_b_first","Player"), cfg.get("name_b_last","Two"),
              cfg.get("abbr_b",""), "player_2_names", "player_2_country")

    # Stat rows
    rows_y = name_y + fl_sz + int(H*0.065)
    rh     = int(H * 0.098)
    rgap   = int(H * 0.022)
    bar_h  = int(H * 0.011)
    rows   = cfg.get("rows",[])

    cy = rows_y
    for row in rows:
        label = row.get("label","")
        va    = str(row.get("value_a","0"))
        vb    = str(row.get("value_b","0"))
        maxv  = str(row.get("max","10"))
        bottom_a = _pill_row(
            draw, ltz_x, tz_w, cy, rh, bar_h, label, va, vb, maxv, False, acc, bar_color, THEME,
            cfg, "player_1_values", row
        )
        bottom_b = _pill_row(
            draw, rtz_x, tz_w, cy, rh, bar_h, label, vb, va, maxv, True, acc, bar_color, THEME,
            cfg, "player_2_values", row
        )
        cy = max(bottom_a,bottom_b) + rgap

    # Playing style
    if cfg.get("show_playing_style",True):
        style_h = int(H*0.078)
        style_col, style_sz = styled_text(
            cfg, "style_heading", THEME["white"], max(10,int(H*0.028))
        )
        sf_     = text_font(cfg,"style_heading",style_sz,"bold")
        sl_lbl=apply_text_case(cfg,"style_heading",cfg.get("style_label","PLAYING STYLE"))
        for sx in (ltz_x, rtz_x):
            draw.rounded_rectangle([sx,cy,sx+tz_w,cy+style_h], radius=8, fill=(*THEME["row_bg"],230))
            tw_,th_ = text_bbox(draw,sl_lbl,sf_)
            bb = draw.textbbox((0,0),sl_lbl,sf_)
            draw.text((sx+(tz_w-tw_)//2, cy+(style_h-th_)//2-bb[1]), sl_lbl, font=sf_, fill=style_col)
        cy2 = cy + style_h + int(H*0.014)
        tag_h  = int(H*0.072)
        tag_col, tag_sz = styled_text(
            cfg, "style_tags", acc, max(9,int(H*0.022))
        )
        tag_f  = text_font(cfg,"style_tags",tag_sz,"bold")
        tags_a = cfg.get("tags_a",["",""])
        tags_b = cfg.get("tags_b",["",""])
        for sx, tags in ((ltz_x,tags_a),(rtz_x,tags_b)):
            tw_2 = (tz_w - 6) // 2
            for i, tag in enumerate(tags[:2]):
                tx0 = sx + i*(tw_2+6)
                draw.rounded_rectangle([tx0,cy2,tx0+tw_2,cy2+tag_h], radius=6, fill=(*THEME["panel"],255))
                draw.rectangle([tx0,cy2,tx0+tw_2,cy2+tag_h], outline=(75,92,118), width=1)
                words=apply_text_case(cfg,"style_tags",tag).split()
                ly = cy2 + (tag_h - len(words)*int(H*0.026))//2
                for wd in words:
                    ww,_ = text_bbox(draw,wd,tag_f)
                    draw.text((tx0+(tw_2-ww)//2, ly), wd, font=tag_f, fill=tag_col)
                    ly += max(tag_sz + 2, int(H*0.028))

    # Center V divider
    vbox_w = int(W*0.042)
    vbox_h = int(rh*1.4)
    vbox_x = W//2 - vbox_w//2
    vbox_y = rows_y + int(H*0.06)
    draw.rectangle([vbox_x,vbox_y,vbox_x+vbox_w,vbox_y+vbox_h], fill=THEME["dark"])
    divider_col, divider_sz = styled_text(
        cfg, "divider", THEME["white"], int(vbox_h*0.52)
    )
    vf2    = text_font(cfg,"divider",divider_sz,"bold_italic")
    vt=apply_text_case(cfg,"divider",cfg.get("divider_text","V"))
    tw_,th_= text_bbox(draw,vt,vf2)
    bb     = draw.textbbox((0,0),vt,vf2)
    draw.text((vbox_x+(vbox_w-tw_)//2, vbox_y+(vbox_h-th_)//2-bb[1]), vt, font=vf2, fill=divider_col)

    paste_free_logo(img, cfg)
    return img.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# T3 — VS TUG-OF-WAR
# Ref: DEhdrT7QjZPSm8ZAYVdi3lKc20.avif (Blomqvist vs Gabran)
# Split photos top half, names flanking center VS, full-width symmetric bars
# ═══════════════════════════════════════════════════════════════════════════

def render_t3(cfg: Dict) -> Image.Image:
    W, H = T3_SIZES.get(cfg.get("canvas_size","Square(1080x1080)"), (1080,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = normalize_rgb(cfg.get("accent_color"), THEME["accent"])
    bar_color = normalize_rgb(cfg.get("bar_color"), acc)
    background=normalize_rgb(cfg.get("background_color"),THEME["bg"])

    img=Image.new("RGB",(W,H),background)
    draw_bg = ImageDraw.Draw(img)

    # Photo zone top ~52% of canvas
    photo_h = int(H * 0.52)
    half    = W // 2

    def paste_half_photo(path, x, w, prefix, flip_inner=False):
        p = load_photo(path)
        if p is None:
            img.paste(Image.new("RGB",(w,photo_h),background),(x,0))
            return
        p = cover_crop(
            p, w, photo_h, cfg.get(f"{prefix}_zoom", 100),
            cfg.get(f"{prefix}_focus_x", 50), cfg.get(f"{prefix}_focus_y", 50)
        )
        # bottom fade
        mask = Image.new("L",(w,photo_h),255)
        md   = ImageDraw.Draw(mask)
        fade = int(photo_h*0.30)
        for y in range(photo_h-fade, photo_h):
            a = int(255*(1-(y-(photo_h-fade))/fade))
            md.line([(0,y),(w,y)], fill=a)
        mask = mask.filter(ImageFilter.GaussianBlur(6))
        base=Image.new("RGBA",(w,photo_h),(*background,255))
        top_ = p.convert("RGBA"); top_.putalpha(mask)
        out  = Image.alpha_composite(base,top_).convert("RGB")
        img.paste(out,(x,0))

    paste_half_photo(cfg.get("photo_a",""), 0,    half, "photo_a")
    paste_half_photo(cfg.get("photo_b",""), half, W-half, "photo_b")

    # Thin vertical seam line at center
    draw_bg.line([(half,0),(half,photo_h)], fill=(40,55,75), width=3)

    draw = ImageDraw.Draw(img)

    # Names sit in the photo fade, matching the reference composition.
    name_y  = photo_h - int(H*0.105)
    fn_sz   = max(14, int(H*0.036))
    ln_sz   = max(20, int(H*0.054))
    team_sz = max(10, int(H*0.022))

    margin = int(W*0.028)

    # Left player
    fn_a=apply_text_case(cfg,"player_1_names",cfg.get("name_a_first","CLARISSA"))
    ln_a=apply_text_case(cfg,"player_1_names",cfg.get("name_a_last","BLOMQVIST"))
    team_a=apply_text_case(cfg,"player_1_team",cfg.get("team_a","HLK"))
    fn_a_col, fn_a_sz = styled_text(cfg, "player_1_names", THEME["muted"], fn_sz)
    ln_a_col, ln_a_sz = styled_text(cfg, "player_1_names", THEME["white"], ln_sz)
    team_a_col, team_a_sz = styled_text(cfg, "player_1_team", THEME["muted"], team_sz)
    player_name_width = half - margin - int(W*0.10)
    fn_a_f = fit_font(
        draw,fn_a,player_name_width,fn_a_sz,minimum=9,
        factory=text_font_factory(cfg,"player_1_names","italic"),
    )
    ln_a_f = fit_font(
        draw,ln_a,player_name_width,ln_a_sz,minimum=12,
        factory=text_font_factory(cfg,"player_1_names","bold_italic"),
    )
    team_a_f = fit_font(
        draw,team_a,player_name_width,team_a_sz,minimum=8,
        factory=text_font_factory(cfg,"player_1_team","regular"),
    )

    # Right player
    rx    = W - margin
    fn_b  = cfg.get("name_b_first","EMELIE")
    ln_b  = cfg.get("name_b_last","GABRÁN")
    team_b= cfg.get("team_b","ÅLK")
    fn_b=apply_text_case(cfg,"player_2_names",fn_b)
    ln_b=apply_text_case(cfg,"player_2_names",ln_b)
    team_b=apply_text_case(cfg,"player_2_team",team_b)
    fn_b_col, fn_b_sz = styled_text(cfg, "player_2_names", THEME["muted"], fn_sz)
    ln_b_col, ln_b_sz = styled_text(cfg, "player_2_names", THEME["white"], ln_sz)
    team_b_col, team_b_sz = styled_text(cfg, "player_2_team", THEME["muted"], team_sz)
    fn_b_f = fit_font(
        draw,fn_b,player_name_width,fn_b_sz,minimum=9,
        factory=text_font_factory(cfg,"player_2_names","italic"),
    )
    ln_b_f = fit_font(
        draw,ln_b,player_name_width,ln_b_sz,minimum=12,
        factory=text_font_factory(cfg,"player_2_names","bold_italic"),
    )
    team_b_f = fit_font(
        draw,team_b,player_name_width,team_b_sz,minimum=8,
        factory=text_font_factory(cfg,"player_2_team","regular"),
    )

    first_line_h = max(fn_a_sz, fn_b_sz)
    last_line_h = max(ln_a_sz, ln_b_sz)
    last_y = name_y + first_line_h + 4
    team_y = last_y + last_line_h + 4
    draw.text((margin,name_y),fn_a,font=fn_a_f,fill=fn_a_col)
    draw.text((margin,last_y),ln_a,font=ln_a_f,fill=ln_a_col)
    draw.text((margin,team_y),team_a,font=team_a_f,fill=team_a_col)
    draw_text_right(draw,fn_b,fn_b_f,rx,name_y,fn_b_col)
    draw_text_right(draw,ln_b,ln_b_f,rx,last_y,ln_b_col)
    draw_text_right(draw,team_b,team_b_f,rx,team_y,team_b_col)

    # VS + score in center
    vs_col, vs_sz = styled_text(
        cfg, "versus", THEME["white"], max(22, int(H*0.058))
    )
    score_col, score_sz = styled_text(
        cfg, "score", THEME["muted"], max(12, int(H*0.026))
    )
    vs_f    = text_font(cfg,"versus",vs_sz,"bold_italic")
    sc_f    = text_font(cfg,"score",score_sz,"bold")
    vs_text=apply_text_case(cfg,"versus",cfg.get("vs_text","VS"))
    score=apply_text_case(cfg,"score",cfg.get("score","6-4  3-6  10-4"))
    draw_text_centered(draw, vs_text, vs_f, half, last_y+last_line_h//2, vs_col)
    draw_text_centered(draw, score, sc_f, half, team_y+score_sz//2, score_col)

    # Stat rows — full width, center-symmetric
    rows_y  = photo_h + int(H*0.055)
    label_col, lbl_sz = styled_text(
        cfg, "stat_labels", THEME["label"], max(11, int(H*0.026))
    )
    value_default = max(18, int(H*0.046))
    value_a_base_col, value_a_sz = styled_text(
        cfg, "player_1_values", THEME["white"], value_default
    )
    value_b_base_col, value_b_sz = styled_text(
        cfg, "player_2_values", THEME["white"], value_default
    )
    unit_col, unit_sz = styled_text(
        cfg, "units", THEME["muted"], max(9, int(value_default*0.50))
    )
    bar_h   = max(4,  int(H*0.011))
    val_a_f = text_font(cfg,"player_1_values",value_a_sz,"bold")
    val_b_f = text_font(cfg,"player_2_values",value_b_sz,"bold")
    unit_f  = text_font(cfg,"units",unit_sz,"regular")

    rows    = cfg.get("rows",[])
    n_rows  = max(1,len(rows))
    avail   = H - rows_y - int(H*0.08)
    rslot   = avail / n_rows
    side_pad= int(W * 0.04)

    cy = rows_y
    for row in rows:
        label=apply_text_case(cfg,"stat_labels",row.get("label",""))
        va=apply_text_case(cfg,"player_1_values",row.get("value_a","0"))
        vb=apply_text_case(cfg,"player_2_values",row.get("value_b","0"))
        maxv    = str(row.get("max","200"))
        unit=apply_text_case(cfg,"units",row.get("unit",""))

        na = exnum(va) or 0.0
        nb = exnum(vb) or 0.0
        a_wins = na >= nb

        row_top = cy
        value_line_h = max(value_a_sz, value_b_sz)
        label_y = row_top + int(value_line_h * 0.42)
        row_label_col=normalize_rgb(row.get("label_color"),label_col)
        row_bar_color=normalize_rgb(row.get("bar_color"),bar_color)
        row_label_font = fit_font(
            draw,label,int(W*.54),lbl_sz,minimum=8,
            factory=text_font_factory(cfg,"stat_labels","bold"),
        )
        draw_text_centered(draw,label,row_label_font,half,label_y,row_label_col)

        # Values are anchored at the outside edges, leaving the center clear.
        a_col, _ = text_style_values(
            cfg, "player_1_values", acc if a_wins else value_a_base_col
        )
        b_col, _ = text_style_values(
            cfg, "player_2_values", acc if not a_wins else value_b_base_col
        )
        row_value_a_col=normalize_rgb(row.get("value_color"),a_col)
        row_value_b_col=normalize_rgb(row.get("value_color"),b_col)
        val_a_w, _ = text_bbox(draw, va, val_a_f)
        val_b_w, _ = text_bbox(draw, vb, val_b_f)
        unit_w,_=text_bbox(draw,unit,unit_f) if unit else (0,0)
        unit_gap = 5 if unit else 0
        draw.text((side_pad, row_top), va, font=val_a_f, fill=row_value_a_col)
        right_group_x = W - side_pad - val_b_w - unit_gap - unit_w
        draw.text((right_group_x, row_top), vb, font=val_b_f, fill=row_value_b_col)

        # Optional units (KMH etc)
        if unit:
            unit_y = row_top + int(value_line_h*0.23)
            draw.text((side_pad+val_a_w+unit_gap,unit_y),unit,font=unit_f,fill=unit_col)
            draw.text((right_group_x+val_b_w+unit_gap,unit_y),unit,font=unit_f,fill=unit_col)

        # Bars — grow from center outward
        bar_cy = row_top + value_line_h + int(H*0.008)
        draw.rounded_rectangle([side_pad, bar_cy, half-4, bar_cy+bar_h],
                                radius=bar_h//2, fill=THEME["bar_track"])
        draw.rounded_rectangle([half+4, bar_cy, W-side_pad, bar_cy+bar_h],
                                radius=bar_h//2, fill=THEME["bar_track"])

        pct_a = pct(va, maxv) / 100
        pct_b = pct(vb, maxv) / 100
        bar_total = half - 4 - side_pad

        # Left bar: grows rightward from left edge to center-4
        fw_a = int(bar_total * pct_a)
        if fw_a > 0:
            draw.rounded_rectangle([half-4-fw_a, bar_cy, half-4, bar_cy+bar_h],
                                    radius=bar_h//2, fill=row_bar_color if a_wins else THEME["white"])
        # Right bar: grows leftward from right edge to center+4
        fw_b = int(bar_total * pct_b)
        if fw_b > 0:
            draw.rounded_rectangle([half+4, bar_cy, half+4+fw_b, bar_cy+bar_h],
                                    radius=bar_h//2, fill=row_bar_color if not a_wins else THEME["white"])

        cy += rslot

    # Footer sponsor logo text
    footer_text=apply_text_case(cfg,"sponsor",cfg.get("sponsor_text",""))
    if footer_text:
        footer_col, footer_sz = styled_text(
            cfg, "sponsor", THEME["muted"], max(10,int(H*0.022))
        )
        ftf = text_font(cfg,"sponsor",footer_sz,"regular")
        tw_,_ = text_bbox(draw, footer_text, ftf)
        draw.text((half-tw_//2, H-int(H*0.05)), footer_text, font=ftf, fill=footer_col)

    paste_free_logo(img, cfg)
    return img


# ═══════════════════════════════════════════════════════════════════════════
# T4 — PERFORMANCE SPOTLIGHT (3-column leaderboard)
# Ref: rnYnYY86X0jLaYZ6lR7P7g1New.avif
# Title banner, 3 equal player card columns, photo, stacked stats, result line
# ═══════════════════════════════════════════════════════════════════════════

def render_t4(cfg: Dict) -> Image.Image:
    W, H = T4_SIZES.get(cfg.get("canvas_size","Square(1080x1080)"), (1080,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = normalize_rgb(cfg.get("accent_color"), THEME["accent"])
    bar_color = normalize_rgb(cfg.get("bar_color"), acc)
    background=normalize_rgb(cfg.get("background_color"),THEME["bg"])

    img=Image.new("RGB",(W,H),background)
    draw = ImageDraw.Draw(img)

    # Banner
    banner_h = int(H * 0.088)
    banner_text=apply_text_case(cfg,"banner",cfg.get("banner_text","PERFORMANCE SPOTLIGHT"))
    banner_col, banner_sz = styled_text(
        cfg, "banner", THEME["white"], max(16, int(banner_h*0.48))
    )
    bf   = fit_font(
        draw,banner_text,int(W*.92),banner_sz,minimum=12,
        factory=text_font_factory(cfg,"banner","bold"),
    )
    tw_,th_ = text_bbox(draw, banner_text, bf)
    bb   = draw.textbbox((0,0),banner_text,bf)
    draw.text((W//2-tw_//2, (banner_h-th_)//2-bb[1]+int(H*0.012)), banner_text, font=bf, fill=banner_col)

    # Column layout
    n_players = 3
    col_gap   = int(W * 0.012)
    col_w     = (W - col_gap*(n_players+1)) // n_players
    col_y0    = banner_h + int(H*0.01)
    col_h     = H - col_y0 - int(H*0.09)  # leave footer
    players   = copy.deepcopy(cfg.get("players", []))

    # Pad to 3 players
    while len(players) < 3:
        players.append({"team":"","first":"Player","last":"","photo":"","stats":[],"result":""})

    for i, player in enumerate(players[:3]):
        cx0 = col_gap + i*(col_w + col_gap)
        cx1 = cx0 + col_w
        role_prefix = f"player_{i+1}"

        # Team label
        team_col, team_sz = styled_text(
            cfg, f"{role_prefix}_team", THEME["muted"], max(9, int(H*0.020))
        )
        first_col, name_sz_s = styled_text(
            cfg, f"{role_prefix}_names", THEME["muted"], max(10, int(H*0.026))
        )
        last_col, name_sz_l = styled_text(
            cfg, f"{role_prefix}_names", THEME["white"], max(14, int(H*0.038))
        )
        team_f_ = text_font(cfg,f"{role_prefix}_team",team_sz,"regular")

        name_y = col_y0 + int(H*0.005)
        team=apply_text_case(cfg,f"{role_prefix}_team",player.get("team",""))
        fn_=apply_text_case(cfg,f"{role_prefix}_names",player.get("first","Player"))
        ln_=apply_text_case(cfg,f"{role_prefix}_names",player.get("last",""))
        if team:
            draw.text((cx0,name_y),team,font=team_f_,fill=team_col)
            name_y += team_sz + 3
        fn_f_ = fit_font(
            draw,fn_,col_w,name_sz_s,minimum=8,
            factory=text_font_factory(cfg,f"{role_prefix}_names","italic"),
        )
        ln_f_ = fit_font(
            draw,ln_,col_w,name_sz_l,minimum=10,
            factory=text_font_factory(cfg,f"{role_prefix}_names","bold_italic"),
        )
        draw.text((cx0,name_y),fn_,font=fn_f_,fill=first_col)
        draw.text((cx0,name_y+name_sz_s+2),ln_,font=ln_f_,fill=last_col)
        name_block_h = (team_sz+3 if team else 0) + name_sz_s + 2 + name_sz_l

        # Photo
        photo_y0 = col_y0 + name_block_h + int(H*0.012)
        photo_h  = int(col_h * 0.46)
        p = load_photo(player.get("photo",""))
        if p:
            ph = cover_crop(
                p, col_w, photo_h, player.get("photo_zoom", 100),
                player.get("photo_focus_x", 50), player.get("photo_focus_y", 50)
            )
            # bottom fade into background
            mask = Image.new("L",(col_w,photo_h),255)
            md   = ImageDraw.Draw(mask)
            fade = int(photo_h*0.28)
            for y in range(photo_h-fade, photo_h):
                a = int(255*(1-(y-(photo_h-fade))/fade))
                md.line([(0,y),(col_w,y)],fill=a)
            mask = mask.filter(ImageFilter.GaussianBlur(5))
            base=Image.new("RGBA",(col_w,photo_h),(*background,255))
            ov   = ph.convert("RGBA"); ov.putalpha(mask)
            out  = Image.alpha_composite(base,ov).convert("RGB")
            img.paste(out,(cx0,photo_y0))
        else:
            draw.rectangle([cx0,photo_y0,cx1,photo_y0+photo_h],fill=background)

        draw = ImageDraw.Draw(img)

        # Stats below photo
        stat_y = photo_y0 + photo_h + int(H*0.008)
        stats  = player.get("stats",[])
        stat_label_col, lbl_sz = styled_text(
            cfg, f"{role_prefix}_stat_labels", THEME["label"], max(9, int(H*0.020))
        )
        stat_value_col, val_sz = styled_text(
            cfg, f"{role_prefix}_stat_values", THEME["white"], max(18, int(H*0.048))
        )
        unit_col, unit_sz = styled_text(
            cfg, f"{role_prefix}_units", THEME["muted"], max(8, int(max(18, int(H*0.048))*0.45))
        )
        bar_h_ = max(3,  int(H*0.008))
        vf__   = text_font(cfg,f"{role_prefix}_stat_values",val_sz,"bold")
        unit_  = text_font(cfg,f"{role_prefix}_units",unit_sz,"regular")

        # First stat gets large treatment (Fastest Serve)
        first_stat = stats[0] if stats else None
        if first_stat:
            first_label_col=normalize_rgb(first_stat.get("label_color"),stat_label_col)
            first_value_col=normalize_rgb(first_stat.get("value_color"),stat_value_col)
            first_bar_col=normalize_rgb(first_stat.get("bar_color"),bar_color)
            first_label=apply_text_case(
                cfg,f"{role_prefix}_stat_labels",first_stat.get("label","")
            )
            first_label_font = fit_font(
                draw,first_label,col_w,lbl_sz,minimum=7,
                factory=text_font_factory(cfg,f"{role_prefix}_stat_labels","regular"),
            )
            draw.text((cx0, stat_y), first_label, font=first_label_font, fill=first_label_col)
            stat_y += lbl_sz + 3
            val_str=apply_text_case(
                cfg,f"{role_prefix}_stat_values",first_stat.get("value","0")
            )
            unit_str=apply_text_case(
                cfg,f"{role_prefix}_units",first_stat.get("unit","")
            )
            draw.text((cx0, stat_y), val_str, font=vf__, fill=first_value_col)
            vw,_ = text_bbox(draw, val_str, vf__)
            if unit_str:
                draw.text((cx0+vw+4, stat_y+int(val_sz*0.2)), unit_str, font=unit_, fill=unit_col)
            stat_y += val_sz + 3
            # bar
            draw.rounded_rectangle([cx0,stat_y,cx1,stat_y+bar_h_], radius=bar_h_//2, fill=THEME["bar_track"])
            fw_=int(col_w*pct(val_str,first_stat.get("max","250"))/100)
            if fw_>0: draw.rounded_rectangle([cx0,stat_y,cx0+fw_,stat_y+bar_h_],radius=bar_h_//2,fill=first_bar_col)
            stat_y += bar_h_ + int(H*0.012)

        # Remaining stats (smaller)
        _, value_size_pct = text_style_values(
            cfg, f"{role_prefix}_stat_values", THEME["white"]
        )
        sm_val_sz = max(8, int(round(max(12, int(H*0.032)) * value_size_pct / 100.0)))
        sm_vf     = text_font(cfg,f"{role_prefix}_stat_values",sm_val_sz,"bold")
        for st in (stats[1:] if stats else []):
            row_label_col=normalize_rgb(st.get("label_color"),stat_label_col)
            row_value_col=normalize_rgb(st.get("value_color"),stat_value_col)
            row_bar_col=normalize_rgb(st.get("bar_color"),bar_color)
            lbl_str=apply_text_case(cfg,f"{role_prefix}_stat_labels",st.get("label",""))
            val_str=apply_text_case(cfg,f"{role_prefix}_stat_values",st.get("value","0"))
            unit_str=apply_text_case(cfg,f"{role_prefix}_units",st.get("unit",""))
            stat_label_font = fit_font(
                draw,lbl_str,col_w,lbl_sz,minimum=7,
                factory=text_font_factory(cfg,f"{role_prefix}_stat_labels","regular"),
            )
            draw.text((cx0, stat_y), lbl_str, font=stat_label_font, fill=row_label_col)
            stat_y += lbl_sz + 2
            draw.text((cx0, stat_y), val_str, font=sm_vf, fill=row_value_col)
            svw,_ = text_bbox(draw, val_str, sm_vf)
            if unit_str:
                draw.text((cx0+svw+3, stat_y+int(sm_val_sz*0.22)), unit_str, font=unit_, fill=unit_col)
            stat_y += sm_val_sz + 2
            draw.rounded_rectangle([cx0,stat_y,cx1,stat_y+bar_h_],radius=bar_h_//2,fill=THEME["bar_track"])
            fw_=int(col_w*pct(val_str,st.get("max","100"))/100)
            if fw_>0: draw.rounded_rectangle([cx0,stat_y,cx0+fw_,stat_y+bar_h_],radius=bar_h_//2,fill=row_bar_col)
            stat_y += bar_h_ + int(H*0.011)

        # Result line
        result = player.get("result","")
        if result:
            result_col, result_sz = styled_text(
                cfg, f"{role_prefix}_result", THEME["muted"], max(9,int(H*0.019))
            )
            rf  = text_font(cfg,f"{role_prefix}_result",result_sz,"regular")
            ry  = H - int(H*0.075)
            result=apply_text_case(cfg,f"{role_prefix}_result",result)
            result=ellipsize(draw,result,rf,col_w)
            tw__,_=text_bbox(draw,result,rf)
            draw.text((cx0+(col_w-tw__)//2,ry),result,font=rf,fill=result_col)

    # Footer sponsors / logos
    footer_text=apply_text_case(cfg,"sponsor",cfg.get("sponsor_text",""))
    if footer_text:
        footer_col, footer_sz = styled_text(
            cfg, "sponsor", THEME["muted"], max(11,int(H*0.024))
        )
        ftf = text_font(cfg,"sponsor",footer_sz,"regular")
        tw_,_ = text_bbox(draw, footer_text, ftf)
        draw.text((W//2-tw_//2, H-int(H*0.042)), footer_text, font=ftf, fill=footer_col)

    # Vertical column dividers
    for i in range(1, n_players):
        dx = col_gap + i*(col_w+col_gap) - col_gap//2
        draw.line([(dx,col_y0+int(H*0.04)),(dx,H-int(H*0.1))], fill=(38,52,70), width=1)

    paste_free_logo(img, cfg)
    return img


# ═══════════════════════════════════════════════════════════════════════════
# DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════

DEF_T1 = {
    "template":"t1", "canvas_size":"16:9  (1920x1080)", "panel_side":"right",
    "photo_path":"", "photo_zoom":100, "photo_focus_x":50, "photo_focus_y":50,
    "player_path":"", "player_x_pct":32, "player_y_pct":52, "player_size_pct":88,
    "logo_path":"", "logo_x_pct":90, "logo_y_pct":10, "logo_size_pct":12,
    "player_in_front":False,
    "panel_width_pct":40, "panel_opacity_pct":96, "panel_fade_pct":22,
    "panel_style":"solid", "panel_color":[8,10,14], "panel_color_2":[24,48,72],
    "panel_blur_pct":1.8,
    "content_top_pct":8, "title_gap_pct":4, "row_gap_pct":2,
    "title":"Match\nStatistics", "background_color":list(THEME["bg"]),
    "accent_color":list(THEME["accent"]), "bar_color":None, "text_styles":{},
    "rows":[
        {"label":"1st Serve %",              "value":"72 %","max":"100"},
        {"label":"2nd Serve win %",          "value":"71 %","max":"100"},
        {"label":"1st Serve Return win %",   "value":"54 %","max":"100"},
        {"label":"Short Rallies Won (1-4 shots)", "value":"66 %","max":"100"},
    ],
}

DEF_T2 = {
    "template":"t2", "canvas_size":"Wide  (1152x640)",
    "header_text":"INSIGHTS | SHOT QUALITY", "divider_text":"V",
    "photo_a":"","photo_b":"","logo_path":"",
    "logo_x_pct":90,"logo_y_pct":9,"logo_size_pct":10,
    "photo_a_zoom":100,"photo_a_focus_x":50,"photo_a_focus_y":50,
    "photo_b_zoom":100,"photo_b_focus_x":50,"photo_b_focus_y":50,
    "photo_width_pct":40,"photo_fade_pct":12,"photo_brightness_pct":92,
    "name_a_first":"Stefanos","name_a_last":"Tsitsipas","abbr_a":"GRE",
    "name_b_first":"Diego",   "name_b_last":"Schwartzman","abbr_b":"ARG",
    "background_color":list(THEME["panel"]),
    "accent_color":list(THEME["accent"]), "bar_color":None, "text_styles":{},
    "rows":[
        {"label":"SERVE",    "value_a":"8.2","value_b":"6.6","max":"10"},
        {"label":"RETURN",   "value_a":"7.0","value_b":"7.5","max":"10"},
        {"label":"FOREHAND", "value_a":"8.0","value_b":"7.9","max":"10"},
        {"label":"BACKHAND", "value_a":"7.5","value_b":"8.1","max":"10"},
    ],
    "show_playing_style":True, "style_label":"PLAYING STYLE",
    "tags_a":["Big Server","All Courter"],
    "tags_b":["Counter Puncher","Solid Baseliner"],
}

DEF_T3 = {
    "template":"t3", "canvas_size":"Square(1080x1080)",
    "photo_a":"","photo_b":"","logo_path":"",
    "logo_x_pct":50,"logo_y_pct":6,"logo_size_pct":12,
    "photo_a_zoom":100,"photo_a_focus_x":50,"photo_a_focus_y":50,
    "photo_b_zoom":100,"photo_b_focus_x":50,"photo_b_focus_y":50,
    "name_a_first":"Clarissa","name_a_last":"Blomqvist","team_a":"HLK",
    "name_b_first":"Emelie",  "name_b_last":"Gabrán",  "team_b":"ÅLK",
    "vs_text":"VS","score":"6-4  3-6  10-4",
    "background_color":list(THEME["bg"]),
    "accent_color":list(THEME["accent"]), "bar_color":None, "text_styles":{},
    "sponsor_text":"zenniz",
    "rows":[
        {"label":"Groundstroke Speed","value_a":"107","value_b":"111","max":"200","unit":"KMH"},
        {"label":"1st Serve Speed",   "value_a":"154","value_b":"155","max":"250","unit":"KMH"},
        {"label":"Short Rallies Won", "value_a":"54", "value_b":"45", "max":"100","unit":""},
        {"label":"Long Rallies Won %","value_a":"4",  "value_b":"15", "max":"100","unit":""},
    ],
}

DEF_T4 = {
    "template":"t4", "canvas_size":"Square(1080x1080)",
    "banner_text":"PERFORMANCE SPOTLIGHT",
    "logo_path":"","logo_x_pct":90,"logo_y_pct":5,"logo_size_pct":10,
    "background_color":list(THEME["bg"]),
    "accent_color":list(THEME["accent"]), "bar_color":None, "text_styles":{},
    "sponsor_text":"TEHO TENNIS LIIGA   ·   zenniz",
    "players":[
        {"team":"HVS","first":"Otto","last":"Virtanen","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. J. Karlsson Wistrand 6-1, 6-2",
         "stats":[
             {"label":"Fastest Serve","value":"218","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"89","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"82","unit":"%","max":"100"},
             {"label":"Short Points Won %","value":"72","unit":"%","max":"100"},
         ]},
        {"team":"HVS","first":"Viktor","last":"Durasovic","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. V. Ahti 6-3, 6-1",
         "stats":[
             {"label":"Fastest Serve","value":"200","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"68","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"75","unit":"%","max":"100"},
             {"label":"Medium Points Won %","value":"71","unit":"%","max":"100"},
         ]},
        {"team":"HVS","first":"Leevi","last":"Säätelä","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. V. Ahti 6-4, 6-3",
         "stats":[
             {"label":"Fastest Serve","value":"197","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"74","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"71","unit":"%","max":"100"},
             {"label":"Long Points Won %","value":"74","unit":"%","max":"100"},
         ]},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# UNDO STACK
# ═══════════════════════════════════════════════════════════════════════════

class UndoStack:
    MAX=60
    def __init__(self): self._s=[]; self._p=-1
    def push(self,s):
        self._s=self._s[:self._p+1]; self._s.append(copy.deepcopy(s))
        if len(self._s)>self.MAX: self._s.pop(0)
        self._p=len(self._s)-1
    def undo(self):
        if self._p>0: self._p-=1; return copy.deepcopy(self._s[self._p])
        return None
    def redo(self):
        if self._p<len(self._s)-1: self._p+=1; return copy.deepcopy(self._s[self._p])
        return None


class PhotoFramingDialog(tk.Toplevel):
    """Small, visual crop editor shared by every photo slot."""

    def __init__(self, parent, path, target_size, zoom, focus_x, focus_y, on_apply):
        super().__init__(parent)
        self.title("Adjust photo")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._source = load_photo(path)
        self._on_apply = on_apply
        self._tk_preview = None

        target_w, target_h = target_size
        ratio = target_w / max(1, target_h)
        preview_w = 520
        preview_h = max(180, min(360, int(preview_w / ratio)))
        if preview_h == 360:
            preview_w = max(240, int(preview_h * ratio))
        self._preview_size = (preview_w, preview_h)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body, width=preview_w, height=preview_h, bg="#1d2630",
            highlightthickness=1, highlightbackground="#aeb8c2",
        )
        self.canvas.pack()

        self.zoom_var = tk.DoubleVar(value=float(zoom))
        self.focus_x_var = tk.DoubleVar(value=float(focus_x))
        self.focus_y_var = tk.DoubleVar(value=float(focus_y))
        for label, variable, low, high in (
            ("Zoom", self.zoom_var, 100, 300),
            ("Move left / right", self.focus_x_var, 0, 100),
            ("Move up / down", self.focus_y_var, 0, 100),
        ):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(10, 0))
            ttk.Label(row, text=label, width=18, anchor="w").pack(side="left")
            ttk.Scale(
                row, from_=low, to=high, variable=variable,
                command=lambda _=None: self._redraw(),
            ).pack(side="left", fill="x", expand=True)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Center photo", command=self._center).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons, text="Apply framing", style="Primary.TButton", command=self._apply,
        ).pack(side="right", padx=(0, 8))
        self._redraw()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _center(self):
        self.zoom_var.set(100)
        self.focus_x_var.set(50)
        self.focus_y_var.set(50)
        self._redraw()

    def _redraw(self):
        if self._source is None:
            return
        width, height = self._preview_size
        preview = cover_crop(
            self._source, width, height, self.zoom_var.get(),
            self.focus_x_var.get(), self.focus_y_var.get(),
        )
        self._tk_preview = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(width // 2, height // 2, image=self._tk_preview)

    def _apply(self):
        self._on_apply(
            round(self.zoom_var.get(), 1),
            round(self.focus_x_var.get(), 1),
            round(self.focus_y_var.get(), 1),
        )
        self.destroy()


class LiveColorDialog(tk.Toplevel):
    """Visual palette that updates the main preview while it remains open."""

    PALETTE_WIDTH=320
    PALETTE_HEIGHT=176
    COMMON_COLORS=(
        (255,255,255),(224,228,232),(148,156,166),(52,59,68),(8,10,14),
        (239,68,68),(249,115,22),(250,204,21),(132,204,22),(34,197,94),
        (20,184,166),(6,182,212),(59,130,246),(99,102,241),(168,85,247),
        (217,70,239),(236,72,153),(190,24,93),(120,53,15),(216,255,50),
    )

    def __init__(self,parent,title,current,on_preview,on_apply,on_cancel):
        super().__init__(parent)
        self.title(title)
        self.resizable(False,False)
        self.transient(parent)
        self.grab_set()
        self._on_preview=on_preview
        self._on_apply=on_apply
        self._on_cancel=on_cancel
        self._suspend=False

        red,green,blue=normalize_rgb(current,THEME["white"])
        self._current=(red,green,blue)
        hue,saturation,brightness=colorsys.rgb_to_hsv(red/255,green/255,blue/255)
        self._hue=hue
        self._saturation=saturation
        self._brightness_var=tk.DoubleVar(value=round(brightness*100))
        self._hex_var=tk.StringVar(value=f"#{red:02X}{green:02X}{blue:02X}")

        body=ttk.Frame(self,padding=14); body.pack(fill="both",expand=True)
        ttk.Label(body,text="Click or drag to preview a color").pack(anchor="w",pady=(0,4))
        self._palette=tk.Canvas(
            body,width=self.PALETTE_WIDTH,height=self.PALETTE_HEIGHT,
            highlightthickness=1,highlightbackground="#84909b",cursor="crosshair",
        )
        self._palette.pack()
        self._palette.bind("<Button-1>",self._palette_clicked)
        self._palette.bind("<B1-Motion>",self._palette_clicked)

        ttk.Label(body,text="Common colors").pack(anchor="w",pady=(10,4))
        swatches=ttk.Frame(body); swatches.pack(fill="x")
        for index,color in enumerate(self.COMMON_COLORS):
            hex_color="#{:02x}{:02x}{:02x}".format(*color)
            swatch=tk.Button(
                swatches,text="",width=3,height=1,relief="solid",borderwidth=1,
                background=hex_color,activebackground=hex_color,cursor="hand2",
                command=lambda selected=color:self._select_rgb(selected),
            )
            swatch.grid(row=index//10,column=index%10,padx=2,pady=2)

        brightness_row=ttk.Frame(body); brightness_row.pack(fill="x",pady=(10,2))
        ttk.Label(brightness_row,text="Brightness",width=12,anchor="w").pack(side="left")
        ttk.Scale(
            brightness_row,from_=5,to=100,variable=self._brightness_var,
            command=self._brightness_changed,
        ).pack(side="left",fill="x",expand=True)
        self._brightness_label=tk.StringVar(value=f"{int(round(self._brightness_var.get()))}%")
        ttk.Label(
            brightness_row,textvariable=self._brightness_label,width=5,anchor="e",
        ).pack(side="left",padx=(6,0))

        selected_row=ttk.Frame(body); selected_row.pack(fill="x",pady=(9,2))
        ttk.Label(selected_row,text="Selected",width=12,anchor="w").pack(side="left")
        self._sample=tk.Canvas(
            selected_row,width=116,height=34,highlightthickness=1,
            highlightbackground="#9aa7b2",background=self._hex_var.get(),
        )
        self._sample.pack(side="left")
        ttk.Label(selected_row,text="Hex",width=5,anchor="e").pack(side="left",padx=(10,4))
        entry=ttk.Entry(selected_row,textvariable=self._hex_var,width=10)
        entry.pack(side="left",fill="x",expand=True)
        entry.bind("<Return>",self._hex_changed)
        entry.bind("<FocusOut>",self._hex_changed)

        buttons=ttk.Frame(body); buttons.pack(fill="x",pady=(12,0))
        ttk.Button(buttons,text="Cancel",command=self._cancel).pack(side="right")
        ttk.Button(
            buttons,text="Apply color",style="Primary.TButton",command=self._apply,
        ).pack(side="right",padx=(0,8))
        self._redraw_palette()
        self.protocol("WM_DELETE_WINDOW",self._cancel)

    def _show_color(self,color,update_hex=True,redraw_marker=True):
        self._current=normalize_rgb(color,self._current)
        if update_hex:
            self._hex_var.set("#{:02X}{:02X}{:02X}".format(*self._current))
        self._sample.configure(background="#{:02x}{:02x}{:02x}".format(*self._current))
        if redraw_marker:
            self._draw_marker()
        self._on_preview(self._current)

    def _redraw_palette(self):
        self._palette.delete("all")
        step=8
        brightness=max(0.05,min(1.0,self._brightness_var.get()/100.0))
        for y in range(0,self.PALETTE_HEIGHT,step):
            saturation=min(1.0,max(0.0,(y+step/2)/self.PALETTE_HEIGHT))
            for x in range(0,self.PALETTE_WIDTH,step):
                hue=min(1.0,max(0.0,(x+step/2)/self.PALETTE_WIDTH))
                red,green,blue=colorsys.hsv_to_rgb(hue,saturation,brightness)
                color=f"#{int(red*255):02x}{int(green*255):02x}{int(blue*255):02x}"
                self._palette.create_rectangle(
                    x,y,min(self.PALETTE_WIDTH,x+step),min(self.PALETTE_HEIGHT,y+step),
                    fill=color,outline=color,
                )
        self._draw_marker()

    def _draw_marker(self):
        self._palette.delete("marker")
        x=max(0,min(self.PALETTE_WIDTH-1,self._hue*self.PALETTE_WIDTH))
        y=max(0,min(self.PALETTE_HEIGHT-1,self._saturation*self.PALETTE_HEIGHT))
        radius=6
        self._palette.create_oval(
            x-radius-1,y-radius-1,x+radius+1,y+radius+1,
            outline="#101820",width=4,tags="marker",
        )
        self._palette.create_oval(
            x-radius,y-radius,x+radius,y+radius,
            outline="#ffffff",width=2,tags="marker",
        )

    def _palette_clicked(self,event):
        self._hue=max(0.0,min(1.0,event.x/self.PALETTE_WIDTH))
        self._saturation=max(0.0,min(1.0,event.y/self.PALETTE_HEIGHT))
        brightness=max(0.05,min(1.0,self._brightness_var.get()/100.0))
        rgb=colorsys.hsv_to_rgb(self._hue,self._saturation,brightness)
        self._show_color(tuple(int(round(channel*255)) for channel in rgb))

    def _brightness_changed(self,_value=None):
        if self._suspend:
            return
        self._brightness_label.set(f"{int(round(self._brightness_var.get()))}%")
        self._redraw_palette()
        brightness=max(0.05,min(1.0,self._brightness_var.get()/100.0))
        rgb=colorsys.hsv_to_rgb(self._hue,self._saturation,brightness)
        self._show_color(
            tuple(int(round(channel*255)) for channel in rgb),redraw_marker=False,
        )

    def _select_rgb(self,color):
        color=normalize_rgb(color,self._current)
        hue,saturation,brightness=colorsys.rgb_to_hsv(*(channel/255 for channel in color))
        self._hue=hue
        self._saturation=saturation
        self._suspend=True
        try:
            self._brightness_var.set(max(5,round(brightness*100)))
            self._brightness_label.set(f"{int(round(self._brightness_var.get()))}%")
        finally:
            self._suspend=False
        self._redraw_palette()
        self._show_color(color,redraw_marker=False)

    def _hex_changed(self,_event=None):
        value=self._hex_var.get().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}",value):
            self._hex_var.set("#{:02X}{:02X}{:02X}".format(*self._current))
            return
        color=tuple(int(value[index:index+2],16) for index in (1,3,5))
        self._select_rgb(color)

    def _apply(self):
        self._show_color(self._current)
        self._on_apply(self._current)
        self.destroy()

    def _cancel(self):
        self._on_cancel()
        self.destroy()


class MP4ExportDialog(tk.Toplevel):
    """Collect the broadcast video mode and hold duration before export."""

    def __init__(self, parent, preset, duration, on_export):
        super().__init__(parent)
        self.title("Export MP4")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._on_export = on_export
        self.preset_var = tk.StringVar(
            value=preset if preset in VIDEO_EXPORT_PRESETS else next(iter(VIDEO_EXPORT_PRESETS))
        )
        self.duration_var = tk.StringVar(value=str(duration))

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Video format:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            body, textvariable=self.preset_var, values=list(VIDEO_EXPORT_PRESETS),
            state="readonly", width=22,
        ).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(body, text="Duration (seconds):").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            body, textvariable=self.duration_var, from_=1, to=3600, width=10,
        ).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=4)

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons, text="Choose output", style="Primary.TButton", command=self._submit,
        ).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())

    def _submit(self):
        try:
            duration = int(self.duration_var.get())
        except ValueError:
            duration = 0
        if not 1 <= duration <= 3600:
            messagebox.showerror(
                "Invalid duration", "Enter a duration from 1 to 3600 seconds.", parent=self,
            )
            return
        preset = self.preset_var.get()
        self.destroy()
        self._on_export(preset, duration)


class LiveOutputDialog(tk.Toplevel):
    """Choose a DeckLink connector and television standard before going live."""

    def __init__(self, parent, preset, output_name, on_start):
        super().__init__(parent)
        self.title("DeckLink live output")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._on_start = on_start
        self.preset_var = tk.StringVar(
            value=preset if preset in VIDEO_EXPORT_PRESETS else "HD 1080i50"
        )
        self.output_var = tk.StringVar(
            value=output_name if output_name in DECKLINK_OUTPUTS else next(iter(DECKLINK_OUTPUTS))
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Video format:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            body, textvariable=self.preset_var, values=list(VIDEO_EXPORT_PRESETS),
            state="readonly", width=28,
        ).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(body, text="SDI output:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            body, textvariable=self.output_var, values=list(DECKLINK_OUTPUTS),
            state="readonly", width=28,
        ).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(
            body,
            text=(
                "Close Blackmagic Media Express before starting.\n"
                "The current scoreboard will update on SDI as you edit it."
            ),
            foreground="#53616e",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 2))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons, text="Start SDI output", style="Primary.TButton", command=self._submit,
        ).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())

    def _submit(self):
        preset = self.preset_var.get()
        output_name = self.output_var.get()
        self.destroy()
        self._on_start(preset, output_name)


# ═══════════════════════════════════════════════════════════════════════════
# ROW WIDGETS
# ═══════════════════════════════════════════════════════════════════════════

class T1Row:
    COLOR_DEFAULTS={
        "label_color":"#dce3ea", "value_color":"#d8ff32", "bar_color":"#d8ff32",
    }

    def __init__(self, parent, on_change, on_color, data=None):
        data = data or {"label":"New Stat","value":"0 %","max":"100"}
        self.on_change=on_change
        self.on_color=on_color
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data.get("label",""))
        self.vv=tk.StringVar(value=data.get("value",""))
        self.mv=tk.StringVar(value=str(data.get("max","100")))
        self.colors={}
        self._swatches={}
        self._color_defaults=dict(self.COLOR_DEFAULTS)
        for key in self.COLOR_DEFAULTS:
            color=data.get(key)
            if isinstance(color,(list,tuple)) and len(color) == 3:
                self.colors[key]=list(normalize_rgb(color,(255,255,255)))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=24).grid(row=0,column=1,padx=3,sticky="ew")
        ttk.Label(self.frame,text="Value:").grid(row=0,column=2,sticky="w")
        ttk.Entry(self.frame,textvariable=self.vv,width=10).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=4,sticky="w")
        ttk.Entry(self.frame,textvariable=self.mv,width=6).grid(row=0,column=5,padx=3)
        actions=ttk.Frame(self.frame)
        actions.grid(row=1,column=1,columnspan=5,sticky="w",pady=(2,3))
        self._individual_button=ttk.Button(
            actions,text="Individual color...",command=self.toggle_colors,
        )
        self._individual_button.pack(side="left")
        ttk.Button(actions,text="Remove",width=7,command=self.delete).pack(side="left",padx=(4,0))
        self._colors_frame=ttk.Frame(self.frame)
        ttk.Label(self._colors_frame,text="Only this row:").pack(side="left")
        for key,label in (
            ("label_color","Label"),("value_color","Value"),("bar_color","Bar"),
        ):
            hex_color=self._hex_for(key)
            button=tk.Button(
                self._colors_frame,text=label,width=6,relief="solid",borderwidth=1,
                background=hex_color,activebackground=hex_color,cursor="hand2",
                command=lambda selected=key:self.on_color(self,selected),
            )
            button.pack(side="left",padx=(4,0))
            self._swatches[key]=button
            self._paint_swatch(key)
        ttk.Button(
            self._colors_frame,text="Clear override",command=self.clear_colors,
        ).pack(side="left",padx=(6,0))
        ttk.Button(
            self._colors_frame,text="Done",command=self.hide_colors,
        ).pack(side="left",padx=(4,0))
        if self.colors:
            self.show_colors()
        self.frame.columnconfigure(1,weight=1)
        for v in (self.lv,self.vv,self.mv): v.trace_add("write",lambda *a:self.on_change())

    def show_colors(self):
        self._colors_frame.grid(row=2,column=1,columnspan=5,sticky="w",pady=(2,5))
        self._individual_button.configure(text="Hide colors")

    def hide_colors(self):
        self._colors_frame.grid_remove()
        self._individual_button.configure(text="Individual color...")

    def toggle_colors(self):
        if self._colors_frame.winfo_manager():
            self.hide_colors()
        else:
            self.show_colors()

    def _hex_for(self,key):
        color=self.colors.get(key)
        if color is not None:
            return "#{:02x}{:02x}{:02x}".format(*normalize_rgb(color,(255,255,255)))
        return self._color_defaults[key]

    @staticmethod
    def _foreground_for(hex_color):
        red,green,blue=(int(hex_color[index:index+2],16) for index in (1,3,5))
        return "#101820" if red*299+green*587+blue*114 > 150000 else "#ffffff"

    def _paint_swatch(self,key):
        if key not in self._swatches:
            return
        hex_color=self._hex_for(key)
        foreground=self._foreground_for(hex_color)
        self._swatches[key].configure(
            background=hex_color,activebackground=hex_color,
            foreground=foreground,activeforeground=foreground,
        )

    def get_color(self,key):
        color=self.colors.get(key)
        return list(color) if color is not None else None

    def set_color(self,key,color):
        if color is None:
            self.colors.pop(key,None)
        else:
            self.colors[key]=list(normalize_rgb(color,(255,255,255)))
            self.show_colors()
        if key in self._swatches:
            self._paint_swatch(key)

    def refresh_inherited_colors(self,colors):
        for key,color in colors.items():
            if key not in self.colors:
                self._color_defaults[key]="#{:02x}{:02x}{:02x}".format(
                    *normalize_rgb(color,(255,255,255))
                )
                self._paint_swatch(key)

    def clear_colors(self):
        for key in tuple(self._swatches):
            self.set_color(key,None)
        self.hide_colors()
        self.on_change()

    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self):
        data={"label":self.lv.get(),"value":self.vv.get(),"max":self.mv.get()}
        data.update({key:list(color) for key,color in self.colors.items()})
        return data

class CompactRowColors:
    """Collapsed per-row overrides shared by comparison templates."""
    def _init_row_colors(self,data,on_color,columnspan):
        self._row_color_callback=on_color
        self._row_colors={}
        self._row_color_buttons={}
        for key in ("label_color","value_color","bar_color"):
            value=data.get(key)
            if isinstance(value,(list,tuple)) and len(value) == 3:
                self._row_colors[key]=list(normalize_rgb(value,(255,255,255)))
        self._row_color_toggle=ttk.Button(
            self.frame,text="Individual colors",command=self._toggle_row_colors,
        )
        self._row_color_toggle.grid(row=1,column=1,columnspan=2,sticky="w",padx=3,pady=(2,4))
        self._row_color_frame=ttk.Frame(self.frame)
        for key,label in (("label_color","Heading"),("value_color","Value"),("bar_color","Bar")):
            button=tk.Button(
                self._row_color_frame,text=label,width=7,relief="solid",borderwidth=1,
                command=lambda selected=key:self._row_color_callback(self,selected),cursor="hand2",
            )
            button.pack(side="left",padx=(0,4))
            self._row_color_buttons[key]=button
        ttk.Button(self._row_color_frame,text="Clear",command=self._clear_row_colors).pack(side="left")
        if self._row_colors:
            self._show_row_colors()
        self._paint_row_colors()

    def _toggle_row_colors(self):
        if self._row_color_frame.winfo_ismapped():
            self._row_color_frame.grid_remove()
            self._row_color_toggle.configure(text="Individual colors")
        else:
            self._show_row_colors()

    def _show_row_colors(self):
        self._row_color_frame.grid(row=2,column=1,columnspan=9,sticky="w",padx=3,pady=(0,5))
        self._row_color_toggle.configure(text="Hide individual colors")

    def _paint_row_colors(self):
        defaults={"label_color":THEME["label"],"value_color":THEME["white"],"bar_color":THEME["accent"]}
        for key,button in self._row_color_buttons.items():
            color=normalize_rgb(self._row_colors.get(key),defaults[key])
            hex_color="#{:02x}{:02x}{:02x}".format(*color)
            button.configure(background=hex_color,activebackground=hex_color)

    def get_row_color(self,key):
        value=self._row_colors.get(key)
        return list(value) if value is not None else None

    def set_row_color(self,key,color):
        if color is None:
            self._row_colors.pop(key,None)
        else:
            self._row_colors[key]=list(normalize_rgb(color,(255,255,255)))
        self._paint_row_colors()

    def _clear_row_colors(self):
        self._row_colors.clear()
        self._paint_row_colors()
        self.on_change()

    def row_color_data(self):
        return {key:list(value) for key,value in self._row_colors.items()}


class T2Row(CompactRowColors):
    def __init__(self, parent, on_change, on_color=None, data=None):
        data = data or {"label":"Stat","value_a":"0","value_b":"0","max":"10"}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data["label"])
        self.av=tk.StringVar(value=str(data["value_a"]))
        self.bv=tk.StringVar(value=str(data["value_b"]))
        self.mv=tk.StringVar(value=str(data["max"]))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=14).grid(row=0,column=1,padx=3)
        ttk.Label(self.frame,text="P1:").grid(row=0,column=2)
        ttk.Entry(self.frame,textvariable=self.av,width=7).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="P2:").grid(row=0,column=4)
        ttk.Entry(self.frame,textvariable=self.bv,width=7).grid(row=0,column=5,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=6)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=7,padx=3)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=8,padx=(4,0))
        self._init_row_colors(data,on_color or (lambda *_:None),8)
        for v in (self.lv,self.av,self.bv,self.mv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self):
        return {"label":self.lv.get(),"value_a":self.av.get(),"value_b":self.bv.get(),
                "max":self.mv.get(),**self.row_color_data()}

class T3Row(CompactRowColors):
    def __init__(self, parent, on_change, on_color=None, data=None):
        data = data or {"label":"Stat","value_a":"0","value_b":"0","max":"200","unit":""}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data["label"])
        self.av=tk.StringVar(value=str(data["value_a"]))
        self.bv=tk.StringVar(value=str(data["value_b"]))
        self.mv=tk.StringVar(value=str(data["max"]))
        self.uv=tk.StringVar(value=data.get("unit",""))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=16).grid(row=0,column=1,padx=3)
        ttk.Label(self.frame,text="Left:").grid(row=0,column=2)
        ttk.Entry(self.frame,textvariable=self.av,width=7).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="Right:").grid(row=0,column=4)
        ttk.Entry(self.frame,textvariable=self.bv,width=7).grid(row=0,column=5,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=6)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=7,padx=3)
        ttk.Label(self.frame,text="Unit:").grid(row=0,column=8)
        ttk.Entry(self.frame,textvariable=self.uv,width=5).grid(row=0,column=9,padx=3)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=10,padx=(4,0))
        self._init_row_colors(data,on_color or (lambda *_:None),10)
        for v in (self.lv,self.av,self.bv,self.mv,self.uv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self):
        return {"label":self.lv.get(),"value_a":self.av.get(),"value_b":self.bv.get(),
                "max":self.mv.get(),"unit":self.uv.get(),**self.row_color_data()}

class T4StatWidget(CompactRowColors):
    """Single stat row for one player in T4."""
    def __init__(self, parent, on_change, on_color=None, data=None):
        data = data or {"label":"Stat","value":"0","unit":"","max":"100"}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=1)
        self.lv=tk.StringVar(value=data.get("label",""))
        self.vv=tk.StringVar(value=str(data.get("value","0")))
        self.uv=tk.StringVar(value=data.get("unit",""))
        self.mv=tk.StringVar(value=str(data.get("max","100")))
        ttk.Entry(self.frame,textvariable=self.lv,width=18).grid(row=0,column=0,padx=2)
        ttk.Entry(self.frame,textvariable=self.vv,width=6).grid(row=0,column=1,padx=2)
        ttk.Entry(self.frame,textvariable=self.uv,width=5).grid(row=0,column=2,padx=2)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=3,padx=2)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=4,padx=2)
        self._init_row_colors(data,on_color or (lambda *_:None),4)
        for v in (self.lv,self.vv,self.uv,self.mv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self):
        return {"label":self.lv.get(),"value":self.vv.get(),"unit":self.uv.get(),
                "max":self.mv.get(),**self.row_color_data()}

class T4PlayerWidget:
    """Controls for one player column in T4."""
    def __init__(self, parent, on_change, on_color=None, data=None, idx=0):
        data = data or DEF_T4["players"][0]
        self.on_change=on_change; self.on_color=on_color or (lambda *_:None); self.stat_widgets=[]
        self.frame=ttk.LabelFrame(parent, text=f"Player {idx+1}")
        self.frame.pack(fill="x",padx=4,pady=4)

        r=ttk.Frame(self.frame); r.pack(fill="x",pady=2)
        self.team_v=tk.StringVar(value=data.get("team",""))
        self.fn_v  =tk.StringVar(value=data.get("first",""))
        self.ln_v  =tk.StringVar(value=data.get("last",""))
        self.res_v =tk.StringVar(value=data.get("result",""))
        self.photo_path=data.get("photo","")
        self.photo_zoom=float(data.get("photo_zoom",100))
        self.photo_focus_x=float(data.get("photo_focus_x",50))
        self.photo_focus_y=float(data.get("photo_focus_y",50))

        ttk.Label(r,text="Team:").pack(side="left")
        ttk.Entry(r,textvariable=self.team_v,width=6).pack(side="left",padx=2)
        ttk.Label(r,text="First:").pack(side="left",padx=(8,2))
        ttk.Entry(r,textvariable=self.fn_v,width=10).pack(side="left",padx=2)
        ttk.Label(r,text="Last:").pack(side="left",padx=(8,2))
        ttk.Entry(r,textvariable=self.ln_v,width=12).pack(side="left",padx=2)

        r2=ttk.Frame(self.frame); r2.pack(fill="x",pady=2)
        ttk.Button(r2,text="Choose photo",command=self._photo).pack(side="left")
        ttk.Button(r2,text="Adjust",command=self._adjust_photo).pack(side="left",padx=(4,0))
        ttk.Button(r2,text="Remove",command=self._remove_photo).pack(side="left",padx=(4,0))
        self.photo_lbl=ttk.Label(
            r2,text=os.path.basename(self.photo_path) if self.photo_path else "No photo selected",
            foreground="#555",width=26,
        )
        self.photo_lbl.pack(side="left",padx=6)

        r3=ttk.Frame(self.frame); r3.pack(fill="x",pady=2)
        ttk.Label(r3,text="Result:").pack(side="left")
        ttk.Entry(r3,textvariable=self.res_v).pack(side="left",fill="x",expand=True,padx=4)

        # Stats sub-area
        sh=ttk.LabelFrame(self.frame,text="Stats  (stat | value | unit | bar scale)")
        sh.pack(fill="x",pady=4)
        self.stat_frame=ttk.Frame(sh); self.stat_frame.pack(fill="x")
        actions=ttk.Frame(sh); actions.pack(fill="x",padx=4,pady=3)
        ttk.Button(actions,text="Add stat",command=self._add_stat).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=self._paste_stats).pack(side="left",padx=4)
        for st in data.get("stats",[]): self._add_stat(st,commit=False)

        for v in (self.team_v,self.fn_v,self.ln_v,self.res_v):
            v.trace_add("write",lambda *a:self.on_change())

    def _photo(self):
        p=filedialog.askopenfilename(filetypes=IMAGE_FILETYPES)
        if p:
            self.photo_path=p
            self.photo_zoom=100; self.photo_focus_x=50; self.photo_focus_y=50
            self.photo_lbl.config(text=os.path.basename(p),foreground="#000")
            self.on_change()

    def _adjust_photo(self):
        if not self.photo_path or load_photo(self.photo_path) is None:
            messagebox.showinfo("Choose photo", "Choose a player photo first.", parent=self.frame)
            return
        PhotoFramingDialog(
            self.frame.winfo_toplevel(), self.photo_path, (3,4), self.photo_zoom,
            self.photo_focus_x, self.photo_focus_y, self._apply_photo_frame,
        )

    def _apply_photo_frame(self, zoom, focus_x, focus_y):
        self.photo_zoom=zoom; self.photo_focus_x=focus_x; self.photo_focus_y=focus_y
        self.on_change()

    def _remove_photo(self):
        self.photo_path=""
        self.photo_zoom=100; self.photo_focus_x=50; self.photo_focus_y=50
        self.photo_lbl.config(text="No photo selected",foreground="#555")
        self.on_change()

    def _paste_stats(self):
        try:
            text=self.frame.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Clipboard is empty", "Copy rows from Excel or Sheets first.", parent=self.frame)
            return
        rows=parse_pasted_rows(text,"t4")
        if not rows:
            messagebox.showwarning("No stats found", "The copied table did not contain usable rows.", parent=self.frame)
            return
        replace=messagebox.askyesnocancel(
            "Paste stats", "Replace existing stats?\n\nYes = replace   No = add below",
            parent=self.frame,
        )
        if replace is None:
            return
        if replace:
            for widget in self.stat_widgets:
                widget.frame.destroy()
            self.stat_widgets.clear()
        for row in rows:
            self._add_stat(row,commit=False)
        self.on_change()

    def _add_stat(self, data=None, commit=True):
        w=T4StatWidget(self.stat_frame,self._on_stat_change,self.on_color,data)
        self.stat_widgets.append(w)
        if commit: self.on_change()

    def _on_stat_change(self, remove=None):
        if remove and remove in self.stat_widgets: self.stat_widgets.remove(remove)
        self.on_change()

    def get_data(self):
        return {"team":self.team_v.get(),"first":self.fn_v.get(),"last":self.ln_v.get(),
                "photo":self.photo_path,"photo_zoom":self.photo_zoom,
                "photo_focus_x":self.photo_focus_x,"photo_focus_y":self.photo_focus_y,
                "result":self.res_v.get(),
                "stats":[w.get_data() for w in self.stat_widgets]}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE_NAMES = [
    "Single Player",
    "Head to Head",
    "Match Comparison",
    "3 Player Spotlight",
]
TEMPLATE_KEYS = ("t1", "t2", "t3", "t4")
RENDERERS = {
    "t1": render_t1,
    "t2": render_t2,
    "t3": render_t3,
    "t4": render_t4,
}
DEFAULT_CONFIGS = {
    "t1": DEF_T1,
    "t2": DEF_T2,
    "t3": DEF_T3,
    "t4": DEF_T4,
}


def normalise_text_styles(value: Any, template: str) -> Dict[str, Dict[str, Any]]:
    valid_roles = {role for role, _ in TEXT_STYLE_TARGETS[template]}
    source = value if isinstance(value, dict) else {}
    clean: Dict[str, Dict[str, Any]] = {}
    for role, style in source.items():
        if role not in valid_roles or not isinstance(style, dict):
            continue
        item: Dict[str, Any] = {}
        color = style.get("color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            try:
                item["color"] = [max(0, min(255, int(channel))) for channel in color]
            except (TypeError, ValueError):
                pass
        if "size_pct" in style:
            try:
                item["size_pct"] = max(50, min(200, int(round(float(style["size_pct"])))))
            except (TypeError, ValueError):
                pass
        family=style.get("font_family")
        if isinstance(family,str) and family in FONT_CHOICES:
            item["font_family"]=family
        case_mode=style.get("case")
        if isinstance(case_mode,str) and case_mode in TEXT_CASE_CHOICES:
            item["case"]=case_mode
        if item:
            clean[role] = item
    return clean


def normalise_project_configs(saved: Any) -> Dict[str, Dict]:
    """Merge a saved project with current defaults without trusting its shape."""
    source = saved if isinstance(saved, dict) else {}
    size_options = {"t1":T1_SIZES,"t2":T2_SIZES,"t3":T3_SIZES,"t4":T4_SIZES}
    result: Dict[str, Dict] = {}
    for key, default in DEFAULT_CONFIGS.items():
        config = copy.deepcopy(default)
        candidate = source.get(key)
        if isinstance(candidate, dict):
            config.update(copy.deepcopy(candidate))
        config["template"] = key
        if config.get("canvas_size") not in size_options[key]:
            config["canvas_size"] = default["canvas_size"]
        accent = config.get("accent_color")
        if not isinstance(accent,list) or len(accent) != 3:
            config["accent_color"] = copy.deepcopy(default["accent_color"])
        else:
            try:
                config["accent_color"] = [max(0,min(255,int(value))) for value in accent]
            except (TypeError,ValueError):
                config["accent_color"] = copy.deepcopy(default["accent_color"])
        background=config.get("background_color")
        if not isinstance(background,(list,tuple)) or len(background) != 3:
            config["background_color"]=copy.deepcopy(default["background_color"])
        else:
            config["background_color"]=list(normalize_rgb(
                background,default["background_color"]
            ))
        config["text_styles"] = normalise_text_styles(config.get("text_styles"), key)
        bar_color=config.get("bar_color")
        if bar_color is None:
            config["bar_color"]=None
        elif isinstance(bar_color,(list,tuple)) and len(bar_color) == 3:
            config["bar_color"]=list(normalize_rgb(bar_color,config["accent_color"]))
        else:
            config["bar_color"]=None
        if key in {"t2","t3","t4"}:
            config["logo_x_pct"]=clamp_number(config.get("logo_x_pct"),0,100,default["logo_x_pct"])
            config["logo_y_pct"]=clamp_number(config.get("logo_y_pct"),0,100,default["logo_y_pct"])
            config["logo_size_pct"]=clamp_number(config.get("logo_size_pct"),2,100,default["logo_size_pct"])
        if key == "t1":
            if config.get("panel_side") not in {"left", "right"}:
                config["panel_side"] = default["panel_side"]
            numeric_fields = {
                "photo_zoom":(100,300), "photo_focus_x":(0,100), "photo_focus_y":(0,100),
                "player_x_pct":(0,100), "player_y_pct":(0,100), "player_size_pct":(2,300),
                "logo_x_pct":(0,100), "logo_y_pct":(0,100), "logo_size_pct":(2,300),
                "panel_width_pct":(20,80), "panel_opacity_pct":(0,100), "panel_fade_pct":(0,60),
                "panel_blur_pct":(0,8),
                "content_top_pct":(2,40), "title_gap_pct":(0,20), "row_gap_pct":(0,15),
            }
            for field,(minimum,maximum) in numeric_fields.items():
                config[field] = clamp_number(
                    config.get(field), minimum, maximum, default[field]
                )
            if config.get("panel_style") not in PANEL_STYLE_NAMES:
                config["panel_style"]=default["panel_style"]
            for color_key in ("panel_color","panel_color_2"):
                panel_color=config.get(color_key)
                if not isinstance(panel_color,(list,tuple)) or len(panel_color) != 3:
                    config[color_key]=copy.deepcopy(default[color_key])
                else:
                    config[color_key]=list(normalize_rgb(panel_color,default[color_key]))
            config["player_in_front"] = bool(config.get("player_in_front",False))
        if key == "t2":
            for field, minimum, maximum in (
                ("photo_width_pct",30,52),
                ("photo_fade_pct",0,35),
                ("photo_brightness_pct",50,120),
            ):
                config[field] = clamp_number(
                    config.get(field), minimum, maximum, default[field]
                )
        if key == "t4":
            incoming=config.get("players") if isinstance(config.get("players"),list) else []
            players=[]
            for index in range(3):
                player=copy.deepcopy(default["players"][index])
                if index < len(incoming) and isinstance(incoming[index],dict):
                    player.update(copy.deepcopy(incoming[index]))
                stats=player.get("stats")
                player["stats"]=[row for row in stats if isinstance(row,dict)] if isinstance(stats,list) else []
                for row in player["stats"]:
                    for color_key in ("label_color","value_color","bar_color"):
                        color=row.get(color_key)
                        if isinstance(color,(list,tuple)) and len(color) == 3:
                            row[color_key]=list(normalize_rgb(color,(255,255,255)))
                        else:
                            row.pop(color_key,None)
                players.append(player)
            config["players"]=players
        else:
            rows=config.get("rows")
            config["rows"]=[row for row in rows if isinstance(row,dict)] if isinstance(rows,list) else copy.deepcopy(default["rows"])
            for row in config["rows"]:
                for color_key in ("label_color","value_color","bar_color"):
                    color=row.get(color_key)
                    if isinstance(color,(list,tuple)) and len(color) == 3:
                        row[color_key]=list(normalize_rgb(color,(255,255,255)))
                    else:
                        row.pop(color_key,None)
        result[key] = config
    return result


T1_STYLE_PRESET_KEYS = (
    "panel_side","panel_style","panel_width_pct","panel_opacity_pct","panel_fade_pct",
    "panel_blur_pct","panel_color","panel_color_2",
    "content_top_pct","title_gap_pct","row_gap_pct","player_in_front","bar_color",
)
T2_STYLE_PRESET_KEYS = ("photo_width_pct", "photo_fade_pct", "photo_brightness_pct")


def build_style_preset(config: Dict, template: str) -> Dict[str, Any]:
    settings={
        "accent_color":copy.deepcopy(config.get("accent_color",list(THEME["accent"]))),
        "bar_color":copy.deepcopy(config.get("bar_color")),
        "background_color":copy.deepcopy(config.get(
            "background_color",DEFAULT_CONFIGS[template]["background_color"]
        )),
        "text_styles":copy.deepcopy(config.get("text_styles",{})),
    }
    if template == "t1":
        for key in T1_STYLE_PRESET_KEYS:
            settings[key]=copy.deepcopy(config.get(key,DEF_T1[key]))
    elif template == "t2":
        for key in T2_STYLE_PRESET_KEYS:
            settings[key]=copy.deepcopy(config.get(key,DEF_T2[key]))
    return {"version":1,"template":template,"settings":settings}


def apply_style_preset(config: Dict, template: str, payload: Any) -> Dict:
    if not isinstance(payload,dict):
        raise ValueError("Style preset is not a valid object.")
    settings=payload.get("settings",payload)
    if not isinstance(settings,dict):
        raise ValueError("Style preset settings are missing.")
    candidate=copy.deepcopy(config)
    for key in ("accent_color","bar_color","background_color","text_styles"):
        if key in settings:
            candidate[key]=copy.deepcopy(settings[key])
    if template == "t1":
        for key in T1_STYLE_PRESET_KEYS:
            if key in settings:
                candidate[key]=copy.deepcopy(settings[key])
    elif template == "t2":
        for key in T2_STYLE_PRESET_KEYS:
            if key in settings:
                candidate[key]=copy.deepcopy(settings[key])
    return normalise_project_configs({template:candidate})[template]


def parse_pasted_rows(text: str, template: str) -> List[Dict[str, str]]:
    """Parse rows copied from Excel, Google Sheets, CSV, or pipe-delimited text."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return []
    if any("\t" in line for line in lines):
        values = [[cell.strip() for cell in line.split("\t")] for line in lines]
    elif any("|" in line for line in lines):
        values = [[cell.strip() for cell in line.split("|")] for line in lines]
    else:
        values = [[cell.strip() for cell in row] for row in csv.reader(lines)]

    if values and values[0]:
        first = values[0][0].strip().casefold()
        if first in {"label", "stat", "statistic", "metric"}:
            values = values[1:]

    rows: List[Dict[str, str]] = []
    for cells in values:
        if not cells or not cells[0]:
            continue
        cells += [""] * 5
        if template == "t1":
            rows.append({"label": cells[0], "value": cells[1], "max": cells[2] or "100"})
        elif template == "t2":
            rows.append({
                "label": cells[0], "value_a": cells[1], "value_b": cells[2],
                "max": cells[3] or "100",
            })
        elif template == "t3":
            rows.append({
                "label": cells[0], "value_a": cells[1], "value_b": cells[2],
                "max": cells[3] or "100", "unit": cells[4],
            })
        elif template == "t4":
            rows.append({
                "label": cells[0], "value": cells[1], "unit": cells[2],
                "max": cells[3] or "100",
            })
    return rows

class App:
    def __init__(self, root):
        self.root=root
        self._setup_style()
        root.geometry("1500x900")
        root.minsize(1200,700)

        self.cfgs = {
            key: copy.deepcopy(config)
            for key, config in DEFAULT_CONFIGS.items()
        }
        self.tpl     = "t1"
        self.t1_rows: List[T1Row] = []
        self.t2_rows: List[T2Row] = []
        self.t3_rows: List[T3Row] = []
        self.t4_players: List[T4PlayerWidget] = []
        self._undo   = UndoStack()
        self._suspend= False
        self._redraw_id = None
        self._undo_id   = None
        self._tk_img    = None
        self._last_render = None
        self._preview_resize_id = None
        self.current_project_path: Optional[Path] = None
        self._dirty = False
        self._text_style_controls: Dict[str, Dict[str, Any]] = {}
        self._background_swatches: Dict[str, tk.Button] = {}
        self._t1_group_swatches: Dict[str, tk.Button] = {}
        self._group_swatches={key:{} for key in ("t2","t3","t4")}
        self._canvas_layer={"t2":"photo_a","t3":"photo_a","t4":"player_1"}
        self._canvas_drag_state=None
        self._preview_image_rect = None
        self._t1_drag_state = None
        self._t1_layer_controls_suspended = False
        self._t1_panel_controls_suspended = False
        self._t1_spacing_controls_suspended = False
        self._video_export_preset = "HD 1080i50"
        self._video_export_duration = 10
        self._live_output_preset = "HD 1080i50"
        self._live_output_name = next(iter(DECKLINK_OUTPUTS))
        self._live_output: Optional[DeckLinkLiveOutput] = None
        self._live_output_poll_id = None

        self._build_ui()
        self._suspend = True
        try:
            self._rebuild_t1_rows()
            self._rebuild_t2_rows()
            self._rebuild_t3_rows()
            self._rebuild_t4_players()
        finally:
            self._suspend = False
        self._switch("t1", init=True)
        self._commit_undo()
        self._set_dirty(False)
        root.update_idletasks()
        self.redraw()
        root.bind("<Control-z>",lambda e:self.undo())
        root.bind("<Control-y>",lambda e:self.redo())
        root.bind("<Control-o>",lambda e:self.open_project())
        root.bind("<Control-s>",lambda e:self.save_project())
        root.bind("<Control-Shift-S>",lambda e:self.save_project(save_as=True))
        root.bind("<Control-e>",lambda e:self.export_png())
        root.bind("<Control-Shift-E>",lambda e:self.export_mp4())
        root.bind("<Control-l>",lambda e:self.toggle_live_output())
        root.protocol("WM_DELETE_WINDOW",self._on_close)

    def _setup_style(self):
        self.root.title("Scoreboard Maker")
        self.root.configure(bg="#eef2f5")
        style=ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame",background="#eef2f5")
        style.configure("TLabelframe",background="#f8fafb",bordercolor="#cbd4dc")
        style.configure("TLabelframe.Label",background="#f8fafb",foreground="#24313d",font=("Segoe UI",10,"bold"))
        style.configure("TLabel",background="#eef2f5",foreground="#24313d",font=("Segoe UI",9))
        style.configure("TButton",font=("Segoe UI",9),padding=(9,6))
        style.configure("Primary.TButton",background="#18794e",foreground="white",font=("Segoe UI",9,"bold"),padding=(12,7))
        style.map("Primary.TButton",background=[("active","#12613e"), ("pressed","#0e4f33")])
        style.configure("Toolbar.TFrame",background="#ffffff")
        style.configure("Title.TLabel",background="#ffffff",foreground="#15202b",font=("Segoe UI",15,"bold"))
        style.configure("Preview.TLabel",background="#eef2f5",foreground="#53616e",font=("Segoe UI",9))
        style.configure("Status.TLabel",background="#ffffff",foreground="#53616e",padding=(10,5))

    # ── UI scaffold ──────────────────────────────────────────────────────

    def _build_ui(self):
        top=ttk.Frame(self.root,style="Toolbar.TFrame",padding=(12,8)); top.pack(fill="x")
        ttk.Label(top,text="Scoreboard Maker",style="Title.TLabel").pack(side="left",padx=(0,16))
        ttk.Label(top,text="Layout",background="#ffffff").pack(side="left")
        self.tpl_var=tk.StringVar(value=TEMPLATE_NAMES[0])
        cb=ttk.Combobox(top,textvariable=self.tpl_var,values=TEMPLATE_NAMES,state="readonly",width=22)
        cb.pack(side="left",padx=(6,12))
        cb.bind("<<ComboboxSelected>>",self._on_tpl_switch)
        ttk.Button(top,text="Undo",command=self.undo).pack(side="left",padx=2)
        ttk.Button(top,text="Redo",command=self.redo).pack(side="left",padx=2)
        ttk.Separator(top,orient="vertical").pack(side="left",fill="y",padx=8)
        ttk.Button(top,text="Open project",command=self.open_project).pack(side="left",padx=2)
        ttk.Button(top,text="Save project",command=self.save_project).pack(side="left",padx=2)
        ttk.Button(top,text="Reset",command=self.reset_current_template).pack(side="left",padx=2)

        ttk.Button(top,text="Export PNG",style="Primary.TButton",command=self.export_png).pack(side="right",padx=(8,0))
        ttk.Button(top,text="Export MP4",command=self.export_mp4).pack(side="right",padx=(8,0))
        self._live_output_button=ttk.Button(
            top,text="Live Output",command=self.toggle_live_output,
        )
        self._live_output_button.pack(side="right",padx=(8,0))
        self.export_scale_var=tk.StringVar(value="Standard")
        ttk.Combobox(
            top,textvariable=self.export_scale_var,
            values=["Standard","High resolution (2x)"],state="readonly",width=20,
        ).pack(side="right")

        self.status_var=tk.StringVar(value="Ready")
        ttk.Label(self.root,textvariable=self.status_var,style="Status.TLabel",anchor="w").pack(side="bottom",fill="x")

        main=ttk.Panedwindow(self.root,orient="horizontal"); main.pack(fill="both",expand=True,padx=8,pady=8)
        lc=ttk.Frame(main,width=620); lc.pack_propagate(False)
        right=ttk.Frame(main)
        main.add(lc,weight=0); main.add(right,weight=1)

        edit_header=ttk.Frame(lc); edit_header.pack(fill="x",padx=(4,8),pady=(2,6))
        ttk.Label(edit_header,text="Edit content",font=("Segoe UI",12,"bold")).pack(side="left")
        sc=tk.Canvas(lc,borderwidth=0,highlightthickness=0,bg="#eef2f5")
        sb=ttk.Scrollbar(lc,orient="vertical",command=sc.yview)
        self.ctrl=ttk.Frame(sc)
        self.ctrl.bind("<Configure>",lambda e:sc.configure(scrollregion=sc.bbox("all")))
        self._ctrl_window=sc.create_window((0,0),window=self.ctrl,anchor="nw")
        sc.bind("<Configure>",lambda e:sc.itemconfigure(self._ctrl_window,width=e.width))
        sc.configure(yscrollcommand=sb.set)
        sc.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self._control_canvas=sc
        self.root.bind_all("<MouseWheel>",self._on_mousewheel,add="+")

        preview_header=ttk.Frame(right); preview_header.pack(fill="x",padx=8,pady=(2,6))
        ttk.Label(preview_header,text="Preview",font=("Segoe UI",12,"bold")).pack(side="left")
        self.preview_info_var=tk.StringVar(value="")
        ttk.Label(preview_header,textvariable=self.preview_info_var,style="Preview.TLabel").pack(side="right")
        self.preview_canvas=tk.Canvas(right,bg="#1c252d",highlightthickness=0,takefocus=True)
        self.preview_canvas.pack(fill="both",expand=True,padx=8,pady=(0,8))
        self.preview_canvas.bind("<Configure>",self._on_preview_resize)
        self.preview_canvas.bind("<ButtonPress-1>",self._preview_press)
        self.preview_canvas.bind("<B1-Motion>",self._preview_drag)
        self.preview_canvas.bind("<ButtonRelease-1>",self._preview_release)
        self.preview_canvas.bind("<MouseWheel>",self._preview_scale_layer)
        self.preview_canvas.bind("<KeyPress>",self._preview_key)
        if DND_FILES and hasattr(self.preview_canvas,"drop_target_register"):
            self.preview_canvas.drop_target_register(DND_FILES)
            self.preview_canvas.dnd_bind("<<Drop>>",self._drop_on_preview)

        # Build all 4 panels (hidden until switched)
        self.panels={}
        for key, builder in [("t1",self._build_t1),("t2",self._build_t2),
                               ("t3",self._build_t3),("t4",self._build_t4)]:
            p=ttk.Frame(self.ctrl); builder(p); self.panels[key]=p

    def _on_mousewheel(self,event):
        left=self._control_canvas.winfo_rootx()
        right=left+self._control_canvas.winfo_width()
        if left <= self.root.winfo_pointerx() <= right:
            self._control_canvas.yview_scroll(int(-event.delta/120),"units")

    def _on_preview_resize(self,_=None):
        if self._preview_resize_id:
            self.root.after_cancel(self._preview_resize_id)
        self._preview_resize_id=self.root.after(60,self._paint_preview)

    def _preview_point(self,event):
        """Map a preview-canvas event to full-resolution image coordinates."""
        if not self._preview_image_rect:
            return None
        left,top,width,height,image_w,image_h=self._preview_image_rect
        if not (left <= event.x <= left+width and top <= event.y <= top+height):
            return None
        return (
            (event.x-left) * image_w / max(1,width),
            (event.y-top) * image_h / max(1,height),
        )

    def _t1_layer_at_point(self,point):
        if point is None:
            return None
        config=self.cfgs["t1"]
        image_w,image_h=T1_SIZES.get(config.get("canvas_size"),(1920,1080))
        current=self._selected_t1_layer()
        order=[current,"logo","player"]
        checked=set()
        for layer in order:
            if layer == "background" or layer in checked:
                continue
            checked.add(layer)
            geometry=t1_overlay_geometry(config,layer,image_w,image_h)
            if geometry is None:
                continue
            _,(left,top,width,height)=geometry
            if left <= point[0] <= left+width and top <= point[1] <= top+height:
                return layer
        return "background"

    def _t1_selection_canvas_box(self,layer=None):
        if not self._preview_image_rect:
            return None
        left,top,width,height,image_w,image_h=self._preview_image_rect
        layer=layer or self._selected_t1_layer()
        if layer == "background":
            return (left,top,left+width,top+height)
        geometry=t1_overlay_geometry(self.cfgs["t1"],layer,image_w,image_h)
        if geometry is None:
            return None
        _,(layer_x,layer_y,layer_w,layer_h)=geometry
        return (
            left+layer_x*width/image_w,
            top+layer_y*height/image_h,
            left+(layer_x+layer_w)*width/image_w,
            top+(layer_y+layer_h)*height/image_h,
        )

    @staticmethod
    def _near_box_corner(event,box,distance=12):
        if not box:
            return False
        x0,y0,x1,y1=box
        return any(
            (event.x-x)**2+(event.y-y)**2 <= distance**2
            for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1))
        )

    def _template_canvas_size(self,tpl):
        sizes={"t1":T1_SIZES,"t2":T2_SIZES,"t3":T3_SIZES,"t4":T4_SIZES}[tpl]
        return sizes.get(self.cfgs[tpl].get("canvas_size"),next(iter(sizes.values())))

    def _other_layer_box(self,tpl,layer):
        width,height=self._template_canvas_size(tpl)
        if layer == "logo":
            geometry=free_logo_geometry(self.cfgs[tpl],width,height)
            return geometry[1] if geometry else None
        box=canvas_photo_boxes(tpl,self.cfgs[tpl],width,height).get(layer)
        if box is None:
            return None
        x0,y0,x1,y1=box
        return (x0,y0,x1-x0,y1-y0)

    def _other_selection_canvas_box(self,tpl,layer):
        if not self._preview_image_rect:
            return None
        box=self._other_layer_box(tpl,layer)
        if box is None:
            return None
        x,y,width,height=box
        left,top,shown_w,shown_h,image_w,image_h=self._preview_image_rect
        return (
            left+x*shown_w/image_w,top+y*shown_h/image_h,
            left+(x+width)*shown_w/image_w,top+(y+height)*shown_h/image_h,
        )

    def _other_layer_at_point(self,tpl,point):
        if point is None:
            return None
        logo=self._other_layer_box(tpl,"logo")
        if logo:
            x,y,width,height=logo
            if x <= point[0] <= x+width and y <= point[1] <= y+height:
                return "logo"
        for layer,box in canvas_photo_boxes(tpl,self.cfgs[tpl],*self._template_canvas_size(tpl)).items():
            x0,y0,x1,y1=box
            if x0 <= point[0] <= x1 and y0 <= point[1] <= y1:
                return layer
        return None

    def _photo_frame_values(self,tpl,layer):
        if tpl == "t4":
            index=int(layer.rsplit("_",1)[1])-1
            player=self.cfgs[tpl]["players"][index]
            return player, "photo_zoom", "photo_focus_x", "photo_focus_y"
        return self.cfgs[tpl], f"{layer}_zoom", f"{layer}_focus_x", f"{layer}_focus_y"

    def _sync_t4_frame_widget(self,layer,source):
        if self.tpl != "t4" or not layer.startswith("player_"):
            return
        index=int(layer.rsplit("_",1)[1])-1
        if index < len(self.t4_players):
            widget=self.t4_players[index]
            widget.photo_zoom=source["photo_zoom"]
            widget.photo_focus_x=source["photo_focus_x"]
            widget.photo_focus_y=source["photo_focus_y"]

    def _canvas_edit_changed(self):
        self._set_dirty(True)
        self._status("Canvas position updated")
        self._schedule_redraw(20)
        if self._undo_id:
            self.root.after_cancel(self._undo_id)
        self._undo_id=self.root.after(600,self._commit_undo)

    def _other_preview_press(self,event):
        point=self._preview_point(event)
        if point is None:
            return
        layer=self._other_layer_at_point(self.tpl,point)
        if layer is None:
            return
        self._canvas_layer[self.tpl]=layer
        self.preview_canvas.focus_set()
        if layer == "logo":
            self._canvas_drag_state={"layer":layer,"mode":"logo"}
        else:
            source,_zoom,x_key,y_key=self._photo_frame_values(self.tpl,layer)
            self._canvas_drag_state={
                "layer":layer,"mode":"photo","start":(event.x,event.y),
                "focus":(source.get(x_key,50),source.get(y_key,50)),
            }
        self._paint_preview()

    def _other_preview_drag(self,event):
        state=self._canvas_drag_state
        if not state or not self._preview_image_rect:
            return
        layer=state["layer"]
        if state["mode"] == "logo":
            point=self._preview_point(event)
            if point is None:
                return
            width,height=self._template_canvas_size(self.tpl)
            self.cfgs[self.tpl]["logo_x_pct"]=round(clamp_number(point[0]*100/width,0,100,50),1)
            self.cfgs[self.tpl]["logo_y_pct"]=round(clamp_number(point[1]*100/height,0,100,50),1)
        else:
            shown=self._other_selection_canvas_box(self.tpl,layer)
            if shown is None:
                return
            x0,y0,x1,y1=shown
            dx=(event.x-state["start"][0])*100/max(1,x1-x0)
            dy=(event.y-state["start"][1])*100/max(1,y1-y0)
            source,_zoom,x_key,y_key=self._photo_frame_values(self.tpl,layer)
            source[x_key]=round(clamp_number(state["focus"][0]-dx,0,100,50),1)
            source[y_key]=round(clamp_number(state["focus"][1]-dy,0,100,50),1)
            self._sync_t4_frame_widget(layer,source)
        self._canvas_edit_changed()

    def _other_preview_scale(self,event):
        point=self._preview_point(event)
        layer=self._other_layer_at_point(self.tpl,point) or self._canvas_layer.get(self.tpl)
        if not layer:
            return
        self._canvas_layer[self.tpl]=layer
        delta=5 if event.delta > 0 else -5
        if layer == "logo":
            current=self.cfgs[self.tpl].get("logo_size_pct",10)
            self.cfgs[self.tpl]["logo_size_pct"]=round(clamp_number(current+delta,2,100,10),1)
        else:
            source,zoom_key,_x,_y=self._photo_frame_values(self.tpl,layer)
            source[zoom_key]=round(clamp_number(source.get(zoom_key,100)+delta,100,300,100),1)
            self._sync_t4_frame_widget(layer,source)
        self._canvas_edit_changed()
        return "break"

    def _preview_press(self,event):
        if self.tpl != "t1":
            self._other_preview_press(event)
            return
        self.preview_canvas.focus_set()
        selected=self._selected_t1_layer()
        selected_box=self._t1_selection_canvas_box(selected)
        if self._near_box_corner(event,selected_box):
            x0,y0,x1,y1=selected_box
            center=((x0+x1)/2.0,(y0+y1)/2.0)
            *_,size_key=T1_LAYER_KEYS[selected]
            minimum=100 if selected == "background" else 2
            self._t1_drag_state={
                "mode":"resize",
                "layer":selected,
                "center":center,
                "start_distance":max(1.0,((event.x-center[0])**2+(event.y-center[1])**2)**0.5),
                "start_size":clamp_number(self.cfgs["t1"].get(size_key),minimum,300,100),
            }
            return
        point=self._preview_point(event)
        if point is None:
            return
        layer=self._t1_layer_at_point(point)
        self._select_t1_layer(layer.title(),repaint=False)
        self.preview_canvas.delete("selection")
        self._draw_t1_selection()
        _,x_key,y_key,_=T1_LAYER_KEYS[layer]
        config=self.cfgs["t1"]
        image_w,image_h=T1_SIZES.get(config.get("canvas_size"),(1920,1080))
        center_x=image_w * clamp_number(config.get(x_key),0,100,50) / 100.0
        center_y=image_h * clamp_number(config.get(y_key),0,100,50) / 100.0
        self._t1_drag_state={
            "mode":"move",
            "layer":layer,
            "start_canvas":(event.x,event.y),
            "start_values":(
                clamp_number(config.get(x_key),0,100,50),
                clamp_number(config.get(y_key),0,100,50),
            ),
            "offset":(point[0]-center_x,point[1]-center_y),
        }

    def _preview_drag(self,event):
        if self.tpl != "t1":
            self._other_preview_drag(event)
            return
        if not self._t1_drag_state or not self._preview_image_rect:
            return
        state=self._t1_drag_state
        layer=state["layer"]
        _,x_key,y_key,_=T1_LAYER_KEYS[layer]
        left,top,width,height,image_w,image_h=self._preview_image_rect
        config=self.cfgs["t1"]
        if state.get("mode") == "resize":
            center_x,center_y=state["center"]
            distance=max(1.0,((event.x-center_x)**2+(event.y-center_y)**2)**0.5)
            *_,size_key=T1_LAYER_KEYS[layer]
            minimum=100 if layer == "background" else 2
            config[size_key]=round(clamp_number(
                state["start_size"]*distance/state["start_distance"],minimum,300,state["start_size"],
            ),1)
            self._refresh_t1_layer_controls()
            self._txt_change("t1",20)
            return
        if layer == "background":
            start_x,start_y=state["start_canvas"]
            initial_x,initial_y=state["start_values"]
            x_value=initial_x-(event.x-start_x)*100/max(1,width)
            y_value=initial_y-(event.y-start_y)*100/max(1,height)
        else:
            image_x=(event.x-left)*image_w/max(1,width)-state["offset"][0]
            image_y=(event.y-top)*image_h/max(1,height)-state["offset"][1]
            x_value=image_x*100/max(1,image_w)
            y_value=image_y*100/max(1,image_h)
        config[x_key]=round(clamp_number(x_value,0,100,50),1)
        config[y_key]=round(clamp_number(y_value,0,100,50),1)
        self._refresh_t1_layer_controls()
        self._txt_change("t1",20)

    def _preview_release(self,_event=None):
        if self.tpl != "t1":
            self._canvas_drag_state=None
            return
        if self._t1_drag_state:
            layer=self._t1_drag_state["layer"].title()
            action="Resized" if self._t1_drag_state.get("mode") == "resize" else "Placed"
            self._t1_drag_state=None
            self._status(f"{action} {layer}")

    def _resize_t1_layer(self,delta):
        layer=self._selected_t1_layer()
        *_,size_key=T1_LAYER_KEYS[layer]
        minimum=100 if layer == "background" else 2
        current=clamp_number(self.cfgs["t1"].get(size_key),minimum,300,100)
        self.cfgs["t1"][size_key]=round(clamp_number(current+delta,minimum,300,current),1)
        self._refresh_t1_layer_controls()
        self._txt_change("t1",20)
        self._status(f"{layer.title()} size {int(round(self.cfgs['t1'][size_key]))}%")

    def _preview_key(self,event):
        if self.tpl != "t1":
            layer=self._canvas_layer.get(self.tpl)
            if not layer:
                return
            key=event.keysym
            control=bool(event.state & 0x4)
            if control and key in {"plus","equal","KP_Add","minus","underscore","KP_Subtract"}:
                event.delta=120 if key in {"plus","equal","KP_Add"} else -120
                return self._other_preview_scale(event)
            if key not in {"Up","Down","Left","Right"}:
                return
            step=5 if event.state & 0x1 else 1
            dx=-step if key == "Left" else step if key == "Right" else 0
            dy=-step if key == "Up" else step if key == "Down" else 0
            if layer == "logo":
                config=self.cfgs[self.tpl]
                config["logo_x_pct"]=round(clamp_number(config.get("logo_x_pct",50)+dx,0,100,50),1)
                config["logo_y_pct"]=round(clamp_number(config.get("logo_y_pct",50)+dy,0,100,50),1)
            else:
                source,_zoom,x_key,y_key=self._photo_frame_values(self.tpl,layer)
                source[x_key]=round(clamp_number(source.get(x_key,50)-dx,0,100,50),1)
                source[y_key]=round(clamp_number(source.get(y_key,50)-dy,0,100,50),1)
                self._sync_t4_frame_widget(layer,source)
            self._canvas_edit_changed()
            return "break"
        key=event.keysym
        control=bool(event.state & 0x4)
        shift=bool(event.state & 0x1)
        grow_keys={"plus","equal","KP_Add"}
        shrink_keys={"minus","underscore","KP_Subtract"}
        if control and (key in grow_keys|shrink_keys or key in {"Up","Down","Left","Right"}):
            grow=key in grow_keys|{"Up","Right"}
            self._resize_t1_layer(5 if grow else -5)
            return "break"
        if key not in {"Up","Down","Left","Right"}:
            return
        layer=self._selected_t1_layer()
        _,x_key,y_key,_=T1_LAYER_KEYS[layer]
        step=5 if shift else 1
        dx=(-step if key == "Left" else step if key == "Right" else 0)
        dy=(-step if key == "Up" else step if key == "Down" else 0)
        if layer == "background":
            dx,dy=-dx,-dy
        config=self.cfgs["t1"]
        config[x_key]=round(clamp_number(config.get(x_key,50)+dx,0,100,50),1)
        config[y_key]=round(clamp_number(config.get(y_key,50)+dy,0,100,50),1)
        self._refresh_t1_layer_controls()
        self._txt_change("t1",20)
        self._status(f"Moved {layer.title()}")
        return "break"

    def _preview_scale_layer(self,event):
        if self.tpl != "t1":
            return self._other_preview_scale(event)
        if self._preview_point(event) is None:
            return
        hit=self._t1_layer_at_point(self._preview_point(event))
        if hit in {"player","logo"}:
            self._select_t1_layer(hit.title(),repaint=False)
        direction=1 if event.delta > 0 else -1
        self._resize_t1_layer(direction*5)
        return "break"

    def _switch(self, key, init=False):
        self._t1_drag_state=None
        for p in self.panels.values(): p.pack_forget()
        self.panels[key].pack(fill="both",expand=True)
        self.tpl=key
        self.preview_canvas.configure(cursor="fleur" if key == "t1" else "")
        if not init:
            self._commit_undo()
            self.redraw()

    def _on_tpl_switch(self, _=None):
        idx=TEMPLATE_NAMES.index(self.tpl_var.get())
        self._switch(TEMPLATE_KEYS[idx])

    # ── T1 controls ──────────────────────────────────────────────────────

    def _build_t1(self, p):
        pad={"padx":10,"pady":5}
        ib=ttk.LabelFrame(p,text="Images"); ib.pack(fill="x",**pad)
        self._make_photo_row(ib,"t1","photo_path","_t1_img_lbl","Background")
        self._make_t1_layer_row(ib,"player_path","_t1_player_lbl","Player cutout","Player")
        self._make_t1_layer_row(ib,"logo_path","_t1_logo_lbl","Logo","Logo")

        tb=ttk.LabelFrame(p,text="Title"); tb.pack(fill="x",**pad)
        self._t1_title=tk.Text(tb,height=2,width=30)
        self._t1_title.insert("1.0",self.cfgs["t1"]["title"])
        self._t1_title.pack(padx=6,pady=4,fill="x")
        self._t1_title.bind("<KeyRelease>",lambda e:self._txt_change("t1"))

        lb=ttk.LabelFrame(p,text="Canvas and panel"); lb.pack(fill="x",**pad)
        ttk.Label(lb,text="Panel side:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        self._t1_side=tk.StringVar(value=self.cfgs["t1"]["panel_side"])
        ttk.Combobox(lb,textvariable=self._t1_side,values=["right","left"],state="readonly",width=8).grid(row=0,column=1,sticky="w",padx=6)
        self._t1_side.trace_add("write",lambda *a:self._disc_change("t1"))
        ttk.Label(lb,text="Canvas:").grid(row=1,column=0,sticky="w",padx=6)
        self._t1_size=tk.StringVar(value=self.cfgs["t1"]["canvas_size"])
        ttk.Combobox(lb,textvariable=self._t1_size,values=list(T1_SIZES.keys()),state="readonly",width=22).grid(row=1,column=1,sticky="w",padx=6)
        self._t1_size.trace_add("write",lambda *a:self._disc_change("t1"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t1")).grid(row=2,column=0,columnspan=2,sticky="w",padx=6,pady=5)
        self._make_background_color_control(lb,"t1").grid(
            row=2,column=2,columnspan=2,sticky="w",padx=6,pady=5
        )
        ttk.Label(lb,text="Panel effect:").grid(row=3,column=0,sticky="w",padx=6,pady=3)
        self._t1_panel_style=tk.StringVar(
            value=PANEL_STYLE_NAMES.get(self.cfgs["t1"].get("panel_style"),"Solid")
        )
        panel_style_box=ttk.Combobox(
            lb,textvariable=self._t1_panel_style,values=list(PANEL_STYLE_LABELS),
            state="readonly",width=16,
        )
        panel_style_box.grid(row=3,column=1,sticky="w",padx=6,pady=3)
        panel_style_box.bind("<<ComboboxSelected>>",lambda _event:self._t1_panel_style_changed())
        self._t1_panel_width=tk.DoubleVar(value=self.cfgs["t1"]["panel_width_pct"])
        self._t1_panel_opacity=tk.DoubleVar(value=self.cfgs["t1"]["panel_opacity_pct"])
        self._t1_panel_fade=tk.DoubleVar(value=self.cfgs["t1"]["panel_fade_pct"])
        self._t1_panel_blur=tk.DoubleVar(value=self.cfgs["t1"]["panel_blur_pct"])
        self._t1_panel_labels={}

        def panel_scale(row,label,variable,minimum,maximum,key):
            ttk.Label(lb,text=label+":").grid(row=row,column=0,sticky="w",padx=6,pady=3)
            ttk.Scale(
                lb,from_=minimum,to=maximum,variable=variable,
                command=lambda value:self._t1_panel_changed(key,value),
            ).grid(row=row,column=1,columnspan=2,sticky="ew",padx=6,pady=3)
            value_label=tk.StringVar(value=f"{int(round(variable.get()))}%")
            ttk.Label(lb,textvariable=value_label,width=6,anchor="e").grid(row=row,column=3,sticky="e",padx=6)
            self._t1_panel_labels[key]=value_label

        panel_scale(4,"Panel width",self._t1_panel_width,20,80,"panel_width_pct")
        panel_scale(5,"Panel opacity",self._t1_panel_opacity,0,100,"panel_opacity_pct")
        panel_scale(6,"Edge fade",self._t1_panel_fade,0,60,"panel_fade_pct")
        panel_scale(7,"Glass blur",self._t1_panel_blur,0,8,"panel_blur_pct")
        lb.columnconfigure(2,weight=1)

        ttk.Label(lb,text="Panel color:").grid(row=8,column=0,sticky="w",padx=6,pady=4)
        panel_hex=self._color_hex(self.cfgs["t1"]["panel_color"])
        self._t1_panel_color_swatch=tk.Button(
            lb,text="",width=4,relief="solid",borderwidth=1,background=panel_hex,
            activebackground=panel_hex,command=self._pick_t1_panel_color,cursor="hand2",
        )
        self._t1_panel_color_swatch.grid(row=8,column=1,sticky="w",padx=6,pady=4)
        ttk.Button(lb,text="Choose panel color",command=self._pick_t1_panel_color).grid(
            row=8,column=2,columnspan=2,sticky="w",padx=3,pady=4,
        )

        ttk.Label(lb,text="Gradient end:").grid(row=9,column=0,sticky="w",padx=6,pady=4)
        panel_2_hex=self._color_hex(self.cfgs["t1"]["panel_color_2"])
        self._t1_panel_color_2_swatch=tk.Button(
            lb,text="",width=4,relief="solid",borderwidth=1,background=panel_2_hex,
            activebackground=panel_2_hex,
            command=lambda:self._pick_t1_panel_color("panel_color_2"),cursor="hand2",
        )
        self._t1_panel_color_2_swatch.grid(row=9,column=1,sticky="w",padx=6,pady=4)
        ttk.Button(
            lb,text="Choose gradient color",
            command=lambda:self._pick_t1_panel_color("panel_color_2"),
        ).grid(row=9,column=2,columnspan=2,sticky="w",padx=3,pady=4)

        self._t1_player_front=tk.BooleanVar(value=self.cfgs["t1"].get("player_in_front",False))
        ttk.Checkbutton(
            lb,text="Player above panel",variable=self._t1_player_front,
            command=lambda:self._disc_change("t1"),
        ).grid(row=10,column=0,columnspan=4,sticky="w",padx=6,pady=(2,6))

        place=ttk.LabelFrame(p,text="Image placement"); place.pack(fill="x",**pad)
        ttk.Label(place,text="Selected image:").grid(row=0,column=0,sticky="w",padx=6,pady=(6,3))
        self._t1_layer_var=tk.StringVar(value="Background")
        layer_box=ttk.Combobox(
            place,textvariable=self._t1_layer_var,values=["Background","Player","Logo"],
            state="readonly",width=20,
        )
        layer_box.grid(row=0,column=1,columnspan=2,sticky="ew",padx=6,pady=(6,3))
        layer_box.bind("<<ComboboxSelected>>",lambda _event:self._refresh_t1_layer_controls())

        self._t1_layer_x=tk.DoubleVar(value=50)
        self._t1_layer_y=tk.DoubleVar(value=50)
        self._t1_layer_size=tk.DoubleVar(value=100)
        self._t1_layer_value_labels={}
        self._t1_layer_scales={}

        def layer_scale(row,label,variable,key):
            ttk.Label(place,text=label+":").grid(row=row,column=0,sticky="w",padx=6,pady=3)
            scale=ttk.Scale(
                place,from_=0,to=100,variable=variable,
                command=lambda value:self._t1_layer_changed(key,value),
            )
            scale.grid(row=row,column=1,sticky="ew",padx=6,pady=3)
            value_label=tk.StringVar(value="50%")
            ttk.Label(place,textvariable=value_label,width=6,anchor="e").grid(row=row,column=2,sticky="e",padx=6)
            self._t1_layer_scales[key]=scale
            self._t1_layer_value_labels[key]=value_label

        layer_scale(1,"Horizontal",self._t1_layer_x,"x")
        layer_scale(2,"Vertical",self._t1_layer_y,"y")
        layer_scale(3,"Size",self._t1_layer_size,"size")
        place.columnconfigure(1,weight=1)
        ttk.Button(place,text="Reset position",command=self._reset_t1_layer).grid(
            row=4,column=0,columnspan=3,sticky="w",padx=6,pady=(3,7),
        )
        self._refresh_t1_layer_controls()

        spacing=ttk.LabelFrame(p,text="Text layout"); spacing.pack(fill="x",**pad)
        self._t1_content_top=tk.DoubleVar(value=self.cfgs["t1"]["content_top_pct"])
        self._t1_title_gap=tk.DoubleVar(value=self.cfgs["t1"]["title_gap_pct"])
        self._t1_row_gap=tk.DoubleVar(value=self.cfgs["t1"]["row_gap_pct"])
        self._t1_spacing_labels={}

        def spacing_scale(row,label,variable,minimum,maximum,key):
            ttk.Label(spacing,text=label+":").grid(row=row,column=0,sticky="w",padx=6,pady=3)
            ttk.Scale(
                spacing,from_=minimum,to=maximum,variable=variable,
                command=lambda value:self._t1_spacing_changed(key,value),
            ).grid(row=row,column=1,sticky="ew",padx=6,pady=3)
            value_label=tk.StringVar(value=f"{int(round(variable.get()))}%")
            ttk.Label(spacing,textvariable=value_label,width=6,anchor="e").grid(
                row=row,column=2,sticky="e",padx=6,pady=3,
            )
            self._t1_spacing_labels[key]=value_label

        spacing_scale(0,"Top position",self._t1_content_top,2,40,"content_top_pct")
        spacing_scale(1,"Title gap",self._t1_title_gap,0,20,"title_gap_pct")
        spacing_scale(2,"Row gap",self._t1_row_gap,0,15,"row_gap_pct")
        spacing.columnconfigure(1,weight=1)
        self._build_t1_group_colors(p)
        self._build_text_style_panel(p, "t1")

        sb=ttk.LabelFrame(p,text="Stat Rows"); sb.pack(fill="x",**pad)
        self._t1_rf=ttk.Frame(sb); self._t1_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t1_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t1")).pack(side="left",padx=4)

    def _rebuild_t1_rows(self):
        for r in self.t1_rows: r.frame.destroy()
        self.t1_rows.clear()
        for d in self.cfgs["t1"].get("rows",[]): self._add_t1_row(d,commit=False)

    def _add_t1_row(self,data=None,commit=True):
        r=T1Row(
            self._t1_rf,self._t1_row_change,self._pick_t1_row_color,data
        ); self.t1_rows.append(r)
        self._refresh_t1_row_swatches()
        if commit: self._disc_change("t1")

    def _t1_row_change(self,remove=None):
        if remove and remove in self.t1_rows: self.t1_rows.remove(remove); self._disc_change("t1"); return
        self._refresh_t1_row_swatches()
        self._txt_change("t1")

    def _refresh_t1_row_swatches(self):
        label_color=text_style_values(
            self.cfgs["t1"],"stat_labels",
            default_text_color(self.cfgs["t1"],"t1","stat_labels"),
        )[0]
        value_color=text_style_values(
            self.cfgs["t1"],"stat_values",
            default_text_color(self.cfgs["t1"],"t1","stat_values"),
        )[0]
        accent=normalize_rgb(self.cfgs["t1"].get("accent_color"),THEME["accent"])
        bar_color=normalize_rgb(self.cfgs["t1"].get("bar_color"),accent)
        inherited={
            "label_color":label_color,"value_color":value_color,"bar_color":bar_color,
        }
        for row in self.t1_rows:
            row.refresh_inherited_colors(inherited)

    def _pick_t1_row_color(self,row,key):
        role={"label_color":"stat_labels","value_color":"stat_values"}.get(key)
        if role:
            fallback=text_style_values(
                self.cfgs["t1"],role,
                default_text_color(self.cfgs["t1"],"t1",role),
            )[0]
        else:
            fallback=normalize_rgb(self.cfgs["t1"].get("accent_color"),THEME["accent"])
        before=row.get_color(key)
        current=normalize_rgb(before,fallback)
        row_number=self.t1_rows.index(row)+1 if row in self.t1_rows else 1
        label={"label_color":"label","value_color":"value","bar_color":"bar"}[key]

        def preview(color):
            row.set_color(key,color)
            self.cfgs["t1"]=self._collect_t1()
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change("t1")

        def cancel():
            row.set_color(key,before)
            self.cfgs["t1"]=self._collect_t1()
            self._schedule_redraw(20)

        LiveColorDialog(
            self.root,f"Stat {row_number} {label} color",current,preview,apply,cancel,
        )

    def _collect_t1(self):
        return {**self.cfgs["t1"],"panel_side":self._t1_side.get(),
                "panel_style":PANEL_STYLE_LABELS.get(self._t1_panel_style.get(),"solid"),
                "canvas_size":self._t1_size.get(),"title":self._t1_title.get("1.0","end-1c"),
                "panel_width_pct":round(self._t1_panel_width.get(),1),
                "panel_opacity_pct":round(self._t1_panel_opacity.get(),1),
                "panel_fade_pct":round(self._t1_panel_fade.get(),1),
                "panel_blur_pct":round(self._t1_panel_blur.get(),1),
                "content_top_pct":round(self._t1_content_top.get(),1),
                "title_gap_pct":round(self._t1_title_gap.get(),1),
                "row_gap_pct":round(self._t1_row_gap.get(),1),
                "player_in_front":self._t1_player_front.get(),
                "rows":[r.get_data() for r in self.t1_rows]}

    # ── T2 controls ──────────────────────────────────────────────────────

    def _build_t2(self, p):
        pad={"padx":10,"pady":5}
        pb=ttk.LabelFrame(p,text="Photos"); pb.pack(fill="x",**pad)
        self._make_photo_row(pb,"t2","photo_a","_t2_img_a","Player 1")
        self._make_photo_row(pb,"t2","photo_b","_t2_img_b","Player 2")
        self._make_photo_row(pb,"t2","logo_path","_t2_logo","Logo",framing=False)

        nb=ttk.LabelFrame(p,text="Player Names"); nb.pack(fill="x",**pad)
        self._t2_nvars={}
        for key,lbl in [("name_a_first","P1 First"),("name_a_last","P1 Last"),("abbr_a","P1 Abbr"),
                         ("name_b_first","P2 First"),("name_b_last","P2 Last"),("abbr_b","P2 Abbr")]:
            r=ttk.Frame(nb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl+":",width=10,anchor="w").pack(side="left")
            v=tk.StringVar(value=self.cfgs["t2"].get(key,""))
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t2")); self._t2_nvars[key]=v

        hb=ttk.LabelFrame(p,text="Header & Divider"); hb.pack(fill="x",**pad)
        self._t2_header=tk.StringVar(value=self.cfgs["t2"]["header_text"])
        self._t2_divider=tk.StringVar(value=self.cfgs["t2"]["divider_text"])
        for lbl,var in [("Header:",self._t2_header),("Divider:",self._t2_divider)]:
            r=ttk.Frame(hb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl,width=8,anchor="w").pack(side="left")
            ttk.Entry(r,textvariable=var).pack(side="left",fill="x",expand=True,padx=4)
            var.trace_add("write",lambda *a:self._txt_change("t2"))

        lb=ttk.LabelFrame(p,text="Appearance and size"); lb.pack(fill="x",**pad)
        self._t2_size=tk.StringVar(value=self.cfgs["t2"]["canvas_size"])
        ttk.Label(lb,text="Canvas:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        ttk.Combobox(lb,textvariable=self._t2_size,values=list(T2_SIZES.keys()),state="readonly",width=18).grid(row=0,column=1,sticky="w",padx=6)
        self._t2_size.trace_add("write",lambda *a:self._disc_change("t2"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t2")).grid(row=1,column=0,columnspan=2,sticky="w",padx=6,pady=5)
        self._make_background_color_control(lb,"t2").grid(
            row=2,column=0,columnspan=2,sticky="w",padx=6,pady=(0,6)
        )
        self._t2_photo_width=tk.DoubleVar(value=self.cfgs["t2"]["photo_width_pct"])
        self._t2_photo_fade=tk.DoubleVar(value=self.cfgs["t2"]["photo_fade_pct"])
        self._t2_photo_brightness=tk.DoubleVar(value=self.cfgs["t2"]["photo_brightness_pct"])
        self._t2_photo_labels={}

        def photo_scale(row,label,variable,minimum,maximum,key):
            ttk.Label(lb,text=label+":").grid(row=row,column=0,sticky="w",padx=6,pady=3)
            ttk.Scale(
                lb,from_=minimum,to=maximum,variable=variable,
                command=lambda value:self._t2_photo_changed(key,value),
            ).grid(row=row,column=1,columnspan=2,sticky="ew",padx=6,pady=3)
            value_label=tk.StringVar(value=f"{int(round(variable.get()))}%")
            ttk.Label(lb,textvariable=value_label,width=6,anchor="e").grid(
                row=row,column=3,sticky="e",padx=6,pady=3,
            )
            self._t2_photo_labels[key]=value_label

        photo_scale(3,"Photo width",self._t2_photo_width,30,52,"photo_width_pct")
        photo_scale(4,"Edge blend",self._t2_photo_fade,0,35,"photo_fade_pct")
        photo_scale(5,"Photo brightness",self._t2_photo_brightness,50,120,"photo_brightness_pct")
        ttk.Button(
            lb,text="Use recommended dark style",command=self._apply_t2_recommended_style,
        ).grid(row=6,column=0,columnspan=4,sticky="w",padx=6,pady=(4,7))
        lb.columnconfigure(2,weight=1)
        self._build_group_colors(p,"t2")
        self._build_text_style_panel(p, "t2")

        sb=ttk.LabelFrame(p,text="Comparison Rows  (winner auto-highlighted)"); sb.pack(fill="x",**pad)
        self._t2_rf=ttk.Frame(sb); self._t2_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t2_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t2")).pack(side="left",padx=4)

        sty=ttk.LabelFrame(p,text="Playing Style"); sty.pack(fill="x",**pad)
        self._t2_show_style=tk.BooleanVar(value=self.cfgs["t2"]["show_playing_style"])
        ttk.Checkbutton(sty,text="Show playing style",variable=self._t2_show_style,command=lambda:self._disc_change("t2")).pack(anchor="w",padx=6)
        self._t2_tag_vars={}
        for key,lbl in [("tags_a0","P1 tag 1"),("tags_a1","P1 tag 2"),("tags_b0","P2 tag 1"),("tags_b1","P2 tag 2")]:
            r=ttk.Frame(sty); r.pack(fill="x",pady=2,padx=6)
            ttk.Label(r,text=lbl+":",width=9,anchor="w").pack(side="left")
            side="a" if "a" in key else "b"; idx=int(key[-1])
            v=tk.StringVar(value=self.cfgs["t2"][f"tags_{side}"][idx])
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t2")); self._t2_tag_vars[key]=v

    def _rebuild_t2_rows(self):
        for r in self.t2_rows: r.frame.destroy()
        self.t2_rows.clear()
        for d in self.cfgs["t2"].get("rows",[]): self._add_t2_row(d,commit=False)

    def _add_t2_row(self,data=None,commit=True):
        r=T2Row(self._t2_rf,self._t2_row_change,lambda row,key:self._pick_row_color("t2",row,key),data); self.t2_rows.append(r)
        if commit: self._disc_change("t2")

    def _t2_row_change(self,remove=None):
        if remove and remove in self.t2_rows: self.t2_rows.remove(remove); self._disc_change("t2"); return
        self._txt_change("t2")

    def _collect_t2(self):
        return {**self.cfgs["t2"],
                "canvas_size":self._t2_size.get(),
                "header_text":self._t2_header.get(),"divider_text":self._t2_divider.get(),
                "photo_width_pct":round(self._t2_photo_width.get(),1),
                "photo_fade_pct":round(self._t2_photo_fade.get(),1),
                "photo_brightness_pct":round(self._t2_photo_brightness.get(),1),
                **{k:v.get() for k,v in self._t2_nvars.items()},
                "rows":[r.get_data() for r in self.t2_rows],
                "show_playing_style":self._t2_show_style.get(),
                "tags_a":[self._t2_tag_vars["tags_a0"].get(),self._t2_tag_vars["tags_a1"].get()],
                "tags_b":[self._t2_tag_vars["tags_b0"].get(),self._t2_tag_vars["tags_b1"].get()]}

    # ── T3 controls ──────────────────────────────────────────────────────

    def _t2_photo_changed(self,key,value):
        if self._suspend:
            return
        try:
            numeric=float(value)
        except (TypeError,ValueError):
            return
        self._t2_photo_labels[key].set(f"{int(round(numeric))}%")
        self._disc_change("t2")

    def _refresh_t2_appearance_controls(self):
        values={
            "photo_width_pct":self.cfgs["t2"].get("photo_width_pct",DEF_T2["photo_width_pct"]),
            "photo_fade_pct":self.cfgs["t2"].get("photo_fade_pct",DEF_T2["photo_fade_pct"]),
            "photo_brightness_pct":self.cfgs["t2"].get(
                "photo_brightness_pct",DEF_T2["photo_brightness_pct"]
            ),
        }
        variables={
            "photo_width_pct":self._t2_photo_width,
            "photo_fade_pct":self._t2_photo_fade,
            "photo_brightness_pct":self._t2_photo_brightness,
        }
        previous=self._suspend
        self._suspend=True
        try:
            for key,value in values.items():
                variables[key].set(value)
                self._t2_photo_labels[key].set(f"{int(round(value))}%")
        finally:
            self._suspend=previous

    def _apply_t2_recommended_style(self):
        config=self._collect_t2()
        config.update({
            "background_color":copy.deepcopy(DEF_T2["background_color"]),
            "accent_color":copy.deepcopy(DEF_T2["accent_color"]),
            "photo_width_pct":DEF_T2["photo_width_pct"],
            "photo_fade_pct":DEF_T2["photo_fade_pct"],
            "photo_brightness_pct":DEF_T2["photo_brightness_pct"],
        })
        # Restore automatic contrast while preserving chosen fonts, case, and sizes.
        for style in config.get("text_styles",{}).values():
            if isinstance(style,dict):
                style.pop("color",None)
        self.cfgs["t2"]=config
        self._refresh_t2_appearance_controls()
        self._refresh_background_swatch("t2")
        self._refresh_text_style_controls("t2")
        self._disc_change("t2")
        self._status("Recommended Head-to-Head style applied")

    def _build_t3(self, p):
        pad={"padx":10,"pady":5}
        pb=ttk.LabelFrame(p,text="Photos"); pb.pack(fill="x",**pad)
        self._make_photo_row(pb,"t3","photo_a","_t3_img_a","Left player")
        self._make_photo_row(pb,"t3","photo_b","_t3_img_b","Right player")
        self._make_photo_row(pb,"t3","logo_path","_t3_logo","Logo",framing=False)

        nb=ttk.LabelFrame(p,text="Players & Match Info"); nb.pack(fill="x",**pad)
        self._t3_vars={}
        fields=[("name_a_first","L First"),("name_a_last","L Last"),("team_a","L Team"),
                ("name_b_first","R First"),("name_b_last","R Last"),("team_b","R Team"),
                ("vs_text","VS text"),("score","Score line"),("sponsor_text","Sponsor text")]
        for key,lbl in fields:
            r=ttk.Frame(nb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl+":",width=12,anchor="w").pack(side="left")
            v=tk.StringVar(value=self.cfgs["t3"].get(key,""))
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t3")); self._t3_vars[key]=v

        lb=ttk.LabelFrame(p,text="Appearance and size"); lb.pack(fill="x",**pad)
        self._t3_size=tk.StringVar(value=self.cfgs["t3"]["canvas_size"])
        ttk.Label(lb,text="Canvas:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        ttk.Combobox(lb,textvariable=self._t3_size,values=list(T3_SIZES.keys()),state="readonly",width=18).grid(row=0,column=1,padx=6)
        self._t3_size.trace_add("write",lambda *a:self._disc_change("t3"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t3")).grid(row=1,column=0,columnspan=2,sticky="w",padx=6,pady=5)
        self._make_background_color_control(lb,"t3").grid(
            row=2,column=0,columnspan=2,sticky="w",padx=6,pady=(0,6)
        )
        self._build_group_colors(p,"t3")
        self._build_text_style_panel(p, "t3")

        sb=ttk.LabelFrame(p,text="Stat Rows  (left | stat | right | scale | unit)"); sb.pack(fill="x",**pad)
        self._t3_rf=ttk.Frame(sb); self._t3_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t3_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t3")).pack(side="left",padx=4)

    def _rebuild_t3_rows(self):
        for r in self.t3_rows: r.frame.destroy()
        self.t3_rows.clear()
        for d in self.cfgs["t3"].get("rows",[]): self._add_t3_row(d,commit=False)

    def _add_t3_row(self,data=None,commit=True):
        r=T3Row(self._t3_rf,self._t3_row_change,lambda row,key:self._pick_row_color("t3",row,key),data); self.t3_rows.append(r)
        if commit: self._disc_change("t3")

    def _t3_row_change(self,remove=None):
        if remove and remove in self.t3_rows: self.t3_rows.remove(remove); self._disc_change("t3"); return
        self._txt_change("t3")

    def _collect_t3(self):
        return {**self.cfgs["t3"],"canvas_size":self._t3_size.get(),
                **{k:v.get() for k,v in self._t3_vars.items()},
                "rows":[r.get_data() for r in self.t3_rows]}

    # ── T4 controls ──────────────────────────────────────────────────────

    def _build_t4(self, p):
        pad={"padx":10,"pady":5}
        pb=ttk.LabelFrame(p,text="Brand image"); pb.pack(fill="x",**pad)
        self._make_photo_row(pb,"t4","logo_path","_t4_logo","Logo",framing=False)
        gb=ttk.LabelFrame(p,text="Global Settings"); gb.pack(fill="x",**pad)
        r0=ttk.Frame(gb); r0.pack(fill="x",pady=3)
        self._t4_banner=tk.StringVar(value=self.cfgs["t4"]["banner_text"])
        self._t4_sponsor=tk.StringVar(value=self.cfgs["t4"]["sponsor_text"])
        ttk.Label(r0,text="Banner:").pack(side="left")
        ttk.Entry(r0,textvariable=self._t4_banner).pack(side="left",fill="x",expand=True,padx=4)
        self._t4_banner.trace_add("write",lambda *a:self._txt_change("t4"))
        r1=ttk.Frame(gb); r1.pack(fill="x",pady=3)
        ttk.Label(r1,text="Sponsor:").pack(side="left")
        ttk.Entry(r1,textvariable=self._t4_sponsor).pack(side="left",fill="x",expand=True,padx=4)
        self._t4_sponsor.trace_add("write",lambda *a:self._txt_change("t4"))
        r2=ttk.Frame(gb); r2.pack(fill="x",pady=3)
        self._t4_size=tk.StringVar(value=self.cfgs["t4"]["canvas_size"])
        ttk.Label(r2,text="Canvas:").pack(side="left")
        ttk.Combobox(r2,textvariable=self._t4_size,values=list(T4_SIZES.keys()),state="readonly",width=18).pack(side="left",padx=6)
        self._t4_size.trace_add("write",lambda *a:self._disc_change("t4"))
        ttk.Button(r2,text="Accent…",command=lambda:self._pick_accent("t4")).pack(side="left",padx=6)

        self._make_background_color_control(r2,"t4").pack(side="left",padx=6)
        self._build_group_colors(p,"t4")
        self._build_text_style_panel(p, "t4")

        # 3 player widgets
        self._t4_player_frame=ttk.Frame(p); self._t4_player_frame.pack(fill="x",**pad)

    def _rebuild_t4_players(self):
        for w in self.t4_players: w.frame.destroy()
        self.t4_players.clear()
        for i,d in enumerate(self.cfgs["t4"].get("players",DEF_T4["players"])[:3]):
            w=T4PlayerWidget(
                self._t4_player_frame,lambda:self._txt_change("t4"),
                lambda row,key:self._pick_row_color("t4",row,key),d,i,
            )
            self.t4_players.append(w)

    def _collect_t4(self):
        return {**self.cfgs["t4"],"canvas_size":self._t4_size.get(),
                "banner_text":self._t4_banner.get(),"sponsor_text":self._t4_sponsor.get(),
                "players":[w.get_data() for w in self.t4_players]}

    # ── Shared pickers ───────────────────────────────────────────────────

    def _make_background_color_control(self,parent,tpl):
        row=ttk.Frame(parent)
        color=self._color_hex(self.cfgs[tpl].get(
            "background_color",DEFAULT_CONFIGS[tpl]["background_color"]
        ))
        swatch=tk.Button(
            row,text="",width=4,relief="solid",borderwidth=1,
            background=color,activebackground=color,cursor="hand2",
            command=lambda:self._pick_background(tpl),
        )
        swatch.pack(side="left")
        ttk.Button(
            row,text="Background color",command=lambda:self._pick_background(tpl),
        ).pack(side="left",padx=(5,0))
        self._background_swatches[tpl]=swatch
        return row

    def _build_group_colors(self,parent,tpl):
        box=ttk.LabelFrame(parent,text="Group Colors")
        box.pack(fill="x",padx=10,pady=5)
        for index,(group,label,_roles) in enumerate(GROUP_COLOR_SPECS[tpl]):
            ttk.Label(box,text=label+":",width=16,anchor="w").grid(
                row=index,column=0,sticky="w",padx=6,pady=3,
            )
            swatch=tk.Button(
                box,text="",width=5,relief="solid",borderwidth=1,cursor="hand2",
                command=lambda selected=group:self._pick_group_color(tpl,selected),
            )
            swatch.grid(row=index,column=1,sticky="w",padx=(2,5),pady=3)
            ttk.Button(
                box,text="Change group",
                command=lambda selected=group:self._pick_group_color(tpl,selected),
            ).grid(row=index,column=2,sticky="w",padx=3,pady=3)
            self._group_swatches[tpl][group]=swatch
        ttk.Button(
            box,text="Reset group colors",command=lambda:self._reset_group_colors(tpl),
        ).grid(row=len(GROUP_COLOR_SPECS[tpl]),column=0,columnspan=3,sticky="w",padx=6,pady=(5,7))
        self._refresh_group_swatches(tpl)

    def _group_spec(self,tpl,group):
        return next(spec for spec in GROUP_COLOR_SPECS[tpl] if spec[0] == group)

    def _group_color(self,tpl,group):
        config=self.cfgs[tpl]
        _key,_label,roles=self._group_spec(tpl,group)
        if group == "bar":
            return normalize_rgb(config.get("bar_color"),config.get("accent_color",THEME["accent"]))
        role=roles[0]
        return text_style_values(config,role,default_text_color(config,tpl,role))[0]

    def _refresh_group_swatches(self,tpl):
        for group,swatch in self._group_swatches.get(tpl,{}).items():
            color=self._color_hex(self._group_color(tpl,group))
            swatch.configure(background=color,activebackground=color)

    def _pick_group_color(self,tpl,group):
        before_styles=copy.deepcopy(self.cfgs[tpl].get("text_styles",{}))
        before_bar=copy.deepcopy(self.cfgs[tpl].get("bar_color"))
        _key,label,roles=self._group_spec(tpl,group)

        def preview(color):
            if group == "bar":
                self.cfgs[tpl]["bar_color"]=list(color)
            else:
                styles=self.cfgs[tpl].setdefault("text_styles",{})
                for role in roles:
                    styles.setdefault(role,{})["color"]=list(color)
            self._refresh_group_swatches(tpl)
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change(tpl)

        def cancel():
            self.cfgs[tpl]["text_styles"]=before_styles
            self.cfgs[tpl]["bar_color"]=before_bar
            self._refresh_group_swatches(tpl)
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        LiveColorDialog(self.root,label+" color",self._group_color(tpl,group),preview,apply,cancel)

    def _reset_group_colors(self,tpl):
        styles=self.cfgs[tpl].setdefault("text_styles",{})
        for _group,_label,roles in GROUP_COLOR_SPECS[tpl]:
            for role in roles:
                style=styles.get(role)
                if isinstance(style,dict):
                    style.pop("color",None)
                    if not style:
                        styles.pop(role,None)
        self.cfgs[tpl]["bar_color"]=None
        self._refresh_group_swatches(tpl)
        self._refresh_text_style_controls(tpl)
        self._disc_change(tpl)

    def _pick_row_color(self,tpl,row,key):
        group={"label_color":"stat_labels","value_color":"values","bar_color":"bar"}[key]
        current=normalize_rgb(row.get_row_color(key),self._group_color(tpl,group))
        before=row.get_row_color(key)

        def preview(color):
            row.set_row_color(key,color)
            self.cfgs[tpl]={
                "t2":self._collect_t2,"t3":self._collect_t3,"t4":self._collect_t4,
            }[tpl]()
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change(tpl)

        def cancel():
            row.set_row_color(key,before)
            self.cfgs[tpl]={
                "t2":self._collect_t2,"t3":self._collect_t3,"t4":self._collect_t4,
            }[tpl]()
            self._schedule_redraw(20)

        label={"label_color":"heading","value_color":"value","bar_color":"bar"}[key]
        LiveColorDialog(self.root,"Individual "+label+" color",current,preview,apply,cancel)

    def _build_t1_group_colors(self,parent):
        box=ttk.LabelFrame(parent,text="Group Colors (applies to all rows)")
        box.pack(fill="x",padx=10,pady=5)
        groups=(
            ("title","Title"),
            ("stat_labels","Stat headings"),
            ("stat_values","Values"),
            ("bar","Bars"),
        )
        for row_index,(group,label) in enumerate(groups):
            ttk.Label(box,text=label+":",width=16,anchor="w").grid(
                row=row_index,column=0,sticky="w",padx=6,pady=3,
            )
            swatch=tk.Button(
                box,text="",width=5,height=1,relief="solid",borderwidth=1,
                cursor="hand2",command=lambda selected=group:self._pick_t1_group_color(selected),
            )
            swatch.grid(row=row_index,column=1,sticky="w",padx=(2,5),pady=3)
            ttk.Button(
                box,text=f"Change all {label.lower()}",
                command=lambda selected=group:self._pick_t1_group_color(selected),
            ).grid(row=row_index,column=2,sticky="w",padx=3,pady=3)
            self._t1_group_swatches[group]=swatch
        ttk.Button(
            box,text="Reset group colors",command=self._reset_t1_group_colors,
        ).grid(row=len(groups),column=0,columnspan=3,sticky="w",padx=6,pady=(5,7))
        self._refresh_t1_group_swatches()

    def _t1_group_color(self,group):
        config=self.cfgs["t1"]
        if group == "bar":
            return normalize_rgb(
                config.get("bar_color"),
                normalize_rgb(config.get("accent_color"),THEME["accent"]),
            )
        default=default_text_color(config,"t1",group)
        return text_style_values(config,group,default)[0]

    def _refresh_t1_group_swatches(self):
        for group,swatch in self._t1_group_swatches.items():
            color=self._color_hex(self._t1_group_color(group))
            swatch.configure(background=color,activebackground=color)

    def _pick_t1_group_color(self,group):
        current=self._t1_group_color(group)
        before_styles=copy.deepcopy(self.cfgs["t1"].get("text_styles",{}))
        before_bar=copy.deepcopy(self.cfgs["t1"].get("bar_color"))

        def preview(color):
            if group == "bar":
                self.cfgs["t1"]["bar_color"]=list(color)
                self._refresh_t1_group_swatches()
                self._refresh_t1_row_swatches()
            else:
                styles=self.cfgs["t1"].setdefault("text_styles",{})
                styles.setdefault(group,{})["color"]=list(color)
                self._refresh_text_style_controls("t1")
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change("t1")

        def cancel():
            self.cfgs["t1"]["text_styles"]=before_styles
            self.cfgs["t1"]["bar_color"]=before_bar
            self._refresh_text_style_controls("t1")
            self._refresh_t1_group_swatches()
            self._refresh_t1_row_swatches()
            self._schedule_redraw(20)

        label=dict(
            title="Title",stat_labels="Stat headings",stat_values="Values",bar="Bars",
        )[group]
        LiveColorDialog(self.root,f"All {label.lower()} color",current,preview,apply,cancel)

    def _reset_t1_group_colors(self):
        styles=self.cfgs["t1"].setdefault("text_styles",{})
        for role in ("title","stat_labels","stat_values"):
            style=styles.get(role)
            if not isinstance(style,dict):
                continue
            style.pop("color",None)
            if not style:
                styles.pop(role,None)
        self.cfgs["t1"]["bar_color"]=None
        self._refresh_text_style_controls("t1")
        self._refresh_t1_group_swatches()
        self._refresh_t1_row_swatches()
        self._disc_change("t1")

    def _build_text_style_panel(self, parent, tpl):
        title="Advanced Text Styling" if tpl == "t1" else "Text Styling"
        box=ttk.LabelFrame(parent,text=title); box.pack(fill="x",padx=10,pady=5)
        targets=TEXT_STYLE_TARGETS[tpl]
        labels=[label for _,label in targets]

        ttk.Label(box,text="Text group:").grid(row=0,column=0,sticky="w",padx=6,pady=(6,3))
        target_var=tk.StringVar(value=labels[0])
        target_box=ttk.Combobox(
            box,textvariable=target_var,values=labels,state="readonly",width=26,
        )
        target_box.grid(row=0,column=1,columnspan=3,sticky="ew",padx=6,pady=(6,3))

        ttk.Label(box,text="Color:").grid(row=1,column=0,sticky="w",padx=6,pady=3)
        swatch=tk.Button(
            box,text="",width=4,height=1,relief="solid",borderwidth=1,
            command=lambda:self._pick_text_color(tpl),cursor="hand2",
        )
        swatch.grid(row=1,column=1,sticky="w",padx=(6,3),pady=3)
        ttk.Button(box,text="Choose color",command=lambda:self._pick_text_color(tpl)).grid(
            row=1,column=2,columnspan=2,sticky="w",padx=3,pady=3,
        )

        ttk.Label(box,text="Font:").grid(row=2,column=0,sticky="w",padx=6,pady=3)
        font_var=tk.StringVar(value="Default")
        font_box=ttk.Combobox(
            box,textvariable=font_var,values=FONT_CHOICES,state="readonly",width=26,
        )
        font_box.grid(row=2,column=1,columnspan=3,sticky="ew",padx=6,pady=3)
        font_box.bind("<<ComboboxSelected>>",lambda _event:self._text_font_changed(tpl))

        ttk.Label(box,text="Case:").grid(row=3,column=0,sticky="w",padx=6,pady=3)
        case_var=tk.StringVar(value="As typed")
        case_box=ttk.Combobox(
            box,textvariable=case_var,values=TEXT_CASE_CHOICES,state="readonly",width=26,
        )
        case_box.grid(row=3,column=1,columnspan=3,sticky="ew",padx=6,pady=3)
        case_box.bind("<<ComboboxSelected>>",lambda _event:self._text_case_changed(tpl))

        ttk.Label(box,text="Size:").grid(row=4,column=0,sticky="w",padx=6,pady=3)
        size_var=tk.DoubleVar(value=100)
        size_scale=ttk.Scale(
            box,from_=50,to=200,variable=size_var,
            command=lambda value:self._text_size_changed(tpl,value),
        )
        size_scale.grid(row=4,column=1,columnspan=2,sticky="ew",padx=6,pady=3)
        size_label=tk.StringVar(value="100%")
        ttk.Label(box,textvariable=size_label,width=6,anchor="e").grid(
            row=4,column=3,sticky="e",padx=6,pady=3,
        )

        actions=ttk.Frame(box); actions.grid(row=5,column=0,columnspan=4,sticky="w",padx=6,pady=(3,7))
        ttk.Button(actions,text="Reset selected",command=lambda:self._reset_text_style(tpl)).pack(side="left")
        ttk.Button(actions,text="Reset all text",command=lambda:self._reset_text_style(tpl,True)).pack(side="left",padx=4)
        presets=ttk.Frame(box); presets.grid(row=6,column=0,columnspan=4,sticky="w",padx=6,pady=(0,7))
        ttk.Button(presets,text="Save style",command=self.save_style_preset).pack(side="left")
        ttk.Button(presets,text="Load style",command=self.load_style_preset).pack(side="left",padx=4)
        box.columnconfigure(2,weight=1)

        self._text_style_controls[tpl]={
            "target_var":target_var,"swatch":swatch,"size_var":size_var,
            "size_label":size_label,"font_var":font_var,"case_var":case_var,"suspend":False,
        }
        target_box.bind("<<ComboboxSelected>>",lambda _event:self._refresh_text_style_controls(tpl))
        self._refresh_text_style_controls(tpl)

    def _selected_text_role(self, tpl):
        selected=self._text_style_controls[tpl]["target_var"].get()
        return next(
            (role for role,label in TEXT_STYLE_TARGETS[tpl] if label == selected),
            "all",
        )

    @staticmethod
    def _color_hex(color):
        return "#{:02x}{:02x}{:02x}".format(*normalize_rgb(color, THEME["white"]))

    def _refresh_text_style_controls(self, tpl):
        controls=self._text_style_controls.get(tpl)
        if not controls:
            return
        role=self._selected_text_role(tpl)
        default=default_text_color(self.cfgs[tpl],tpl,role)
        color,size_pct=text_style_values(self.cfgs[tpl],role,default)
        family=text_font_family(self.cfgs[tpl],role)
        case_mode=text_case_mode(self.cfgs[tpl],role)
        controls["suspend"]=True
        try:
            controls["size_var"].set(size_pct)
            controls["size_label"].set(f"{size_pct}%")
            controls["font_var"].set(family)
            controls["case_var"].set(case_mode)
            hex_color=self._color_hex(color)
            controls["swatch"].configure(background=hex_color,activebackground=hex_color)
        finally:
            controls["suspend"]=False
        if tpl == "t1":
            self._refresh_t1_group_swatches()
            self._refresh_t1_row_swatches()
        else:
            self._refresh_group_swatches(tpl)

    def _pick_text_color(self, tpl):
        controls=self._text_style_controls[tpl]
        role=self._selected_text_role(tpl)
        default=default_text_color(self.cfgs[tpl],tpl,role)
        current,_=text_style_values(self.cfgs[tpl],role,default)
        before_styles=copy.deepcopy(self.cfgs[tpl].get("text_styles",{}))

        def preview(color):
            styles=self.cfgs[tpl].setdefault("text_styles",{})
            styles.setdefault(role,{})["color"]=list(color)
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change(tpl)

        def cancel():
            self.cfgs[tpl]["text_styles"]=before_styles
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        LiveColorDialog(
            self.root,f"{controls['target_var'].get()} color",current,
            preview,apply,cancel,
        )

    def _text_font_changed(self, tpl):
        controls=self._text_style_controls[tpl]
        if controls["suspend"] or self._suspend:
            return
        family=controls["font_var"].get()
        if family not in FONT_CHOICES:
            family="Default"
        role=self._selected_text_role(tpl)
        styles=self.cfgs[tpl].setdefault("text_styles",{})
        styles.setdefault(role,{})["font_family"]=family
        self._disc_change(tpl)

    def _text_case_changed(self, tpl):
        controls=self._text_style_controls[tpl]
        if controls["suspend"] or self._suspend:
            return
        case_mode=controls["case_var"].get()
        if case_mode not in TEXT_CASE_CHOICES:
            case_mode="As typed"
        role=self._selected_text_role(tpl)
        styles=self.cfgs[tpl].setdefault("text_styles",{})
        styles.setdefault(role,{})["case"]=case_mode
        self._disc_change(tpl)

    def _text_size_changed(self, tpl, value):
        controls=self._text_style_controls[tpl]
        if controls["suspend"] or self._suspend:
            return
        size_pct=max(50,min(200,int(round(float(value)))))
        controls["size_label"].set(f"{size_pct}%")
        role=self._selected_text_role(tpl)
        styles=self.cfgs[tpl].setdefault("text_styles",{})
        styles.setdefault(role,{})["size_pct"]=size_pct
        self._txt_change(tpl)

    def _reset_text_style(self, tpl, reset_all=False):
        styles=self.cfgs[tpl].setdefault("text_styles",{})
        if reset_all:
            styles.clear()
        else:
            styles.pop(self._selected_text_role(tpl),None)
        self._refresh_text_style_controls(tpl)
        self._disc_change(tpl)

    def save_style_preset(self):
        self._collect()
        selected=filedialog.asksaveasfilename(
            defaultextension=".scoreboard-style.json",filetypes=STYLE_PRESET_FILETYPES,
            initialfile=f"{self.tpl}_style.scoreboard-style.json",parent=self.root,
        )
        if not selected:
            return False
        path=Path(selected)
        temporary=path.with_name(path.name+".tmp")
        try:
            payload=build_style_preset(self.cfgs[self.tpl],self.tpl)
            temporary.write_text(json.dumps(payload,indent=2),encoding="utf-8")
            os.replace(temporary,path)
            self._status(f"Saved style {path.name}")
            return True
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Save style failed",str(exc),parent=self.root)
            return False

    def load_style_preset(self):
        selected=filedialog.askopenfilename(filetypes=STYLE_PRESET_FILETYPES,parent=self.root)
        if not selected:
            return False
        path=Path(selected)
        try:
            payload=json.loads(path.read_text(encoding="utf-8"))
            preset_template=payload.get("template") if isinstance(payload,dict) else None
            if preset_template in TEMPLATE_KEYS and preset_template != self.tpl:
                expected=TEMPLATE_NAMES[TEMPLATE_KEYS.index(preset_template)]
                raise ValueError(f"This style belongs to {expected}. Switch layouts before loading it.")
            configs=self._collect()
            configs[self.tpl]=apply_style_preset(configs[self.tpl],self.tpl,payload)
            self._apply_state({"tpl":self.tpl,"cfgs":configs})
            self._commit_undo()
            self._set_dirty(True)
            self._status(f"Loaded style {path.name}")
            return True
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
            messagebox.showerror("Load style failed",str(exc),parent=self.root)
            return False

    def _make_t1_layer_row(self,parent,key,label_attr,title,layer_label):
        row=ttk.Frame(parent); row.pack(fill="x",padx=6,pady=4)
        ttk.Label(row,text=title,width=14,anchor="w").pack(side="left")
        label=ttk.Label(row,width=22,foreground="#555",anchor="w")
        setattr(self,label_attr,label)
        ttk.Button(
            row,text="Choose",command=lambda:self._pick_photo("t1",key,label),
        ).pack(side="left")
        ttk.Button(
            row,text="Select",command=lambda:self._select_t1_layer(layer_label),
        ).pack(side="left",padx=(4,0))
        ttk.Button(
            row,text="Remove",command=lambda:self._remove_photo("t1",key,label),
        ).pack(side="left",padx=(4,0))
        label.pack(side="left",padx=8,fill="x",expand=True)
        self._set_photo_label(label,self.cfgs["t1"].get(key,""))
        self._register_file_drop(row,"t1",key,label,layer_label)

    def _t1_panel_changed(self,key,value):
        if self._t1_panel_controls_suspended or self._suspend:
            return
        self._t1_panel_labels[key].set(f"{int(round(float(value)))}%")
        self._txt_change("t1")

    def _t1_panel_style_changed(self):
        if self._t1_panel_controls_suspended or self._suspend:
            return
        self.cfgs["t1"]["panel_style"]=PANEL_STYLE_LABELS.get(
            self._t1_panel_style.get(),"solid"
        )
        self._disc_change("t1")

    def _pick_t1_panel_color(self,key="panel_color"):
        fallback=DEF_T1[key]
        current=normalize_rgb(self.cfgs["t1"].get(key),fallback)
        before=list(current)
        swatch=(
            self._t1_panel_color_swatch if key == "panel_color"
            else self._t1_panel_color_2_swatch
        )

        def preview(color):
            self.cfgs["t1"][key]=list(color)
            hex_color=self._color_hex(color)
            swatch.configure(background=hex_color,activebackground=hex_color)
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change("t1")

        def cancel():
            self.cfgs["t1"][key]=before
            hex_color=self._color_hex(before)
            swatch.configure(background=hex_color,activebackground=hex_color)
            self._schedule_redraw(20)

        title="Panel color" if key == "panel_color" else "Gradient end color"
        LiveColorDialog(self.root,title,current,preview,apply,cancel)

    def _refresh_t1_panel_controls(self):
        self._t1_panel_controls_suspended=True
        try:
            values={
                "panel_width_pct":self.cfgs["t1"].get("panel_width_pct",40),
                "panel_opacity_pct":self.cfgs["t1"].get("panel_opacity_pct",96),
                "panel_fade_pct":self.cfgs["t1"].get("panel_fade_pct",22),
                "panel_blur_pct":self.cfgs["t1"].get("panel_blur_pct",1.8),
            }
            variables={
                "panel_width_pct":self._t1_panel_width,
                "panel_opacity_pct":self._t1_panel_opacity,
                "panel_fade_pct":self._t1_panel_fade,
                "panel_blur_pct":self._t1_panel_blur,
            }
            for key,value in values.items():
                variables[key].set(value)
                self._t1_panel_labels[key].set(f"{int(round(float(value)))}%")
            self._t1_player_front.set(bool(self.cfgs["t1"].get("player_in_front",False)))
            self._t1_panel_style.set(PANEL_STYLE_NAMES.get(
                self.cfgs["t1"].get("panel_style"),"Solid"
            ))
            color=self._color_hex(self.cfgs["t1"].get("panel_color",[8,10,14]))
            self._t1_panel_color_swatch.configure(background=color,activebackground=color)
            color_2=self._color_hex(self.cfgs["t1"].get("panel_color_2",[24,48,72]))
            self._t1_panel_color_2_swatch.configure(background=color_2,activebackground=color_2)
        finally:
            self._t1_panel_controls_suspended=False

    def _t1_spacing_changed(self,key,value):
        if self._t1_spacing_controls_suspended or self._suspend:
            return
        numeric=round(float(value),1)
        self.cfgs["t1"][key]=numeric
        self._t1_spacing_labels[key].set(f"{int(round(numeric))}%")
        self._txt_change("t1",20)

    def _refresh_t1_spacing_controls(self):
        self._t1_spacing_controls_suspended=True
        try:
            controls={
                "content_top_pct":self._t1_content_top,
                "title_gap_pct":self._t1_title_gap,
                "row_gap_pct":self._t1_row_gap,
            }
            for key,variable in controls.items():
                value=self.cfgs["t1"].get(key,DEF_T1[key])
                variable.set(value)
                self._t1_spacing_labels[key].set(f"{int(round(float(value)))}%")
        finally:
            self._t1_spacing_controls_suspended=False

    def _selected_t1_layer(self):
        return self._t1_layer_var.get().strip().casefold() or "background"

    def _select_t1_layer(self,layer_label,repaint=True):
        self._t1_layer_var.set(layer_label)
        self._refresh_t1_layer_controls()
        if repaint:
            self._paint_preview()

    def _refresh_t1_layer_controls(self):
        layer=self._selected_t1_layer()
        _,x_key,y_key,size_key=T1_LAYER_KEYS[layer]
        config=self.cfgs["t1"]
        minimum=100 if layer == "background" else 2
        maximum=300
        self._t1_layer_controls_suspended=True
        try:
            self._t1_layer_scales["size"].configure(from_=minimum,to=maximum)
            values={
                "x":clamp_number(config.get(x_key),0,100,50),
                "y":clamp_number(config.get(y_key),0,100,50),
                "size":clamp_number(config.get(size_key),minimum,maximum,100),
            }
            for key,variable in {
                "x":self._t1_layer_x,"y":self._t1_layer_y,"size":self._t1_layer_size,
            }.items():
                variable.set(values[key])
                self._t1_layer_value_labels[key].set(f"{int(round(values[key]))}%")
        finally:
            self._t1_layer_controls_suspended=False

    def _t1_layer_changed(self,field,value):
        if self._t1_layer_controls_suspended or self._suspend:
            return
        layer=self._selected_t1_layer()
        _,x_key,y_key,size_key=T1_LAYER_KEYS[layer]
        key={"x":x_key,"y":y_key,"size":size_key}[field]
        minimum=100 if layer == "background" and field == "size" else (2 if field == "size" else 0)
        maximum=300 if field == "size" else 100
        numeric=clamp_number(value,minimum,maximum,100 if field == "size" else 50)
        self.cfgs["t1"][key]=round(numeric,1)
        self._t1_layer_value_labels[field].set(f"{int(round(numeric))}%")
        self._txt_change("t1")

    def _reset_t1_layer(self):
        layer=self._selected_t1_layer()
        _,x_key,y_key,size_key=T1_LAYER_KEYS[layer]
        default=DEF_T1
        self.cfgs["t1"].update({
            x_key:default[x_key],y_key:default[y_key],size_key:default[size_key],
        })
        self._refresh_t1_layer_controls()
        self._disc_change("t1")

    def _register_file_drop(self,widget,tpl,key,label,layer_label=None):
        if not DND_FILES or not hasattr(widget,"drop_target_register"):
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind(
            "<<Drop>>",
            lambda event:self._drop_photo(event,tpl,key,label,layer_label),
        )

    def _drop_file_path(self,event):
        try:
            candidates=self.root.tk.splitlist(event.data)
        except (tk.TclError,AttributeError):
            candidates=[str(getattr(event,"data","")).strip("{}")]
        for candidate in candidates:
            path=str(candidate).strip()
            if path and load_photo(path) is not None:
                return path
        return ""

    def _drop_photo(self,event,tpl,key,label,layer_label=None):
        path=self._drop_file_path(event)
        if not path:
            self._status("Drop ignored: choose a supported image file")
            return getattr(event,"action",None)
        self._assign_photo(tpl,key,label,path,layer_label)
        return getattr(event,"action",None)

    def _drop_on_preview(self,event):
        path=self._drop_file_path(event)
        if not path:
            self._status("Drop ignored: choose a supported image file")
            return getattr(event,"action",None)
        if self.tpl == "t1":
            layer=self._selected_t1_layer()
            key=T1_LAYER_KEYS[layer][0]
            label={"background":self._t1_img_lbl,"player":self._t1_player_lbl,"logo":self._t1_logo_lbl}[layer]
            self._assign_photo("t1",key,label,path,self._t1_layer_var.get())
            return getattr(event,"action",None)
        layer=self._canvas_layer.get(self.tpl)
        if layer == "logo":
            label={"t2":self._t2_logo,"t3":self._t3_logo,"t4":self._t4_logo}[self.tpl]
            self._assign_photo(self.tpl,"logo_path",label,path)
        elif self.tpl == "t4" and layer and layer.startswith("player_"):
            index=int(layer.rsplit("_",1)[1])-1
            widget=self.t4_players[index]
            widget.photo_path=path
            widget.photo_zoom=100; widget.photo_focus_x=50; widget.photo_focus_y=50
            widget.photo_lbl.config(text=os.path.basename(path),foreground="#000")
            self._disc_change("t4")
        elif layer in {"photo_a","photo_b"}:
            label={
                ("t2","photo_a"):self._t2_img_a,("t2","photo_b"):self._t2_img_b,
                ("t3","photo_a"):self._t3_img_a,("t3","photo_b"):self._t3_img_b,
            }[(self.tpl,layer)]
            self._assign_photo(self.tpl,layer,label,path)
        return getattr(event,"action",None)

    def _assign_photo(self,tpl,key,label,path,layer_label=None):
        previous=self.cfgs[tpl].get(key,"")
        self.cfgs[tpl][key]=path
        is_t1_overlay=tpl == "t1" and key in {"player_path","logo_path"}
        if not is_t1_overlay and key != "logo_path":
            zoom_key,x_key,y_key=self._frame_keys(key)
            self.cfgs[tpl].update({zoom_key:100,x_key:50,y_key:50})
        self._set_photo_label(label,path)
        if tpl == "t1":
            selected=layer_label or ({"photo_path":"Background","player_path":"Player","logo_path":"Logo"}[key])
            self._select_t1_layer(selected)
        elif key == "logo_path":
            self._canvas_layer[tpl]="logo"
        elif tpl in {"t2","t3"} and key in {"photo_a","photo_b"}:
            self._canvas_layer[tpl]=key
        self._status(f"Added {os.path.basename(path)}" if not previous else f"Replaced with {os.path.basename(path)}")
        self._disc_change(tpl)

    def _make_photo_row(self,parent,tpl,key,label_attr,title,framing=True):
        row=ttk.Frame(parent); row.pack(fill="x",padx=6,pady=4)
        ttk.Label(row,text=title,width=14,anchor="w").pack(side="left")
        label=ttk.Label(row,width=26,foreground="#555",anchor="w")
        setattr(self,label_attr,label)
        ttk.Button(
            row,text="Choose",command=lambda:self._pick_photo(tpl,key,label),
        ).pack(side="left")
        if framing:
            ttk.Button(
                row,text="Adjust",command=lambda:self._adjust_photo(tpl,key),
            ).pack(side="left",padx=(4,0))
        ttk.Button(
            row,text="Remove",command=lambda:self._remove_photo(tpl,key,label),
        ).pack(side="left",padx=(4,0))
        label.pack(side="left",padx=8,fill="x",expand=True)
        self._set_photo_label(label,self.cfgs[tpl].get(key,""))
        self._register_file_drop(row,tpl,key,label)

    @staticmethod
    def _set_photo_label(label,path):
        label.config(
            text=os.path.basename(path) if path else "Drop or choose image",
            foreground="#202830" if path else "#687681",
        )

    @staticmethod
    def _frame_keys(key):
        if key == "photo_path":
            return "photo_zoom","photo_focus_x","photo_focus_y"
        return f"{key}_zoom",f"{key}_focus_x",f"{key}_focus_y"

    def _photo_target_size(self,tpl):
        config=self.cfgs[tpl]
        if tpl == "t1":
            return T1_SIZES.get(config.get("canvas_size"),(16,9))
        if tpl == "t2":
            width,height=T2_SIZES.get(config.get("canvas_size"),(1152,640))
            photo_pct=clamp_number(config.get("photo_width_pct"),30,52,40)
            return max(1,int((width/2)*(photo_pct/100))),height
        width,height=T3_SIZES.get(config.get("canvas_size"),(1080,1080))
        return max(1,width//2),max(1,int(height*.52))

    def _pick_photo(self, tpl, key, lbl):
        p=filedialog.askopenfilename(filetypes=IMAGE_FILETYPES)
        if p:
            self._assign_photo(tpl,key,lbl,p)

    def _adjust_photo(self,tpl,key):
        path=self.cfgs[tpl].get(key,"")
        if not path or load_photo(path) is None:
            messagebox.showinfo("Choose photo", "Choose a photo first.", parent=self.root)
            return
        zoom_key,x_key,y_key=self._frame_keys(key)
        def apply_frame(zoom,focus_x,focus_y):
            self.cfgs[tpl].update({zoom_key:zoom,x_key:focus_x,y_key:focus_y})
            self._disc_change(tpl)
        PhotoFramingDialog(
            self.root,path,self._photo_target_size(tpl),
            self.cfgs[tpl].get(zoom_key,100),self.cfgs[tpl].get(x_key,50),
            self.cfgs[tpl].get(y_key,50),apply_frame,
        )

    def _remove_photo(self,tpl,key,label):
        self.cfgs[tpl][key]=""
        is_t1_overlay=tpl == "t1" and key in {"player_path","logo_path"}
        if not is_t1_overlay and key != "logo_path":
            zoom_key,x_key,y_key=self._frame_keys(key)
            self.cfgs[tpl].update({zoom_key:100,x_key:50,y_key:50})
        self._set_photo_label(label,"")
        if tpl == "t1":
            self._refresh_t1_layer_controls()
        self._disc_change(tpl)

    def _paste_rows(self,tpl):
        try:
            text=self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Clipboard is empty", "Copy rows from Excel or Sheets first.", parent=self.root)
            return
        rows=parse_pasted_rows(text,tpl)
        if not rows:
            messagebox.showwarning("No stats found", "The copied table did not contain usable rows.", parent=self.root)
            return
        replace=messagebox.askyesnocancel(
            "Paste stats", "Replace existing stats?\n\nYes = replace   No = add below",
            parent=self.root,
        )
        if replace is None:
            return
        self.cfgs[tpl]["rows"]=rows if replace else self.cfgs[tpl].get("rows",[])+rows
        {"t1":self._rebuild_t1_rows,"t2":self._rebuild_t2_rows,"t3":self._rebuild_t3_rows}[tpl]()
        self._disc_change(tpl)

    def _pick_accent(self, tpl):
        current=normalize_rgb(self.cfgs[tpl].get("accent_color"),THEME["accent"])
        before=list(current)

        def preview(color):
            self.cfgs[tpl]["accent_color"]=list(color)
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change(tpl)

        def cancel():
            self.cfgs[tpl]["accent_color"]=before
            self._refresh_text_style_controls(tpl)
            self._schedule_redraw(20)

        LiveColorDialog(self.root,"Accent color",current,preview,apply,cancel)

    def _refresh_background_swatch(self,tpl):
        swatch=self._background_swatches.get(tpl)
        if swatch is None:
            return
        color=self._color_hex(self.cfgs[tpl].get(
            "background_color",DEFAULT_CONFIGS[tpl]["background_color"]
        ))
        swatch.configure(background=color,activebackground=color)

    def _pick_background(self,tpl):
        fallback=DEFAULT_CONFIGS[tpl]["background_color"]
        current=normalize_rgb(self.cfgs[tpl].get("background_color"),fallback)
        before=list(current)

        def preview(color):
            self.cfgs[tpl]["background_color"]=list(color)
            self._refresh_background_swatch(tpl)
            self._schedule_redraw(20)

        def apply(_color):
            self._disc_change(tpl)

        def cancel():
            self.cfgs[tpl]["background_color"]=before
            self._refresh_background_swatch(tpl)
            self._schedule_redraw(20)

        LiveColorDialog(self.root,"Background color",current,preview,apply,cancel)

    # ── Change / undo flow ───────────────────────────────────────────────

    def _collect(self):
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        if not self._suspend:
            self.cfgs[self.tpl]=collectors[self.tpl]()
        return {k: copy.deepcopy(v) for k,v in self.cfgs.items()}

    def _disc_change(self, tpl):
        if self._suspend: return
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        self.cfgs[tpl]=collectors[tpl]()
        self._set_dirty(True)
        self._status("Updated")
        self._schedule_redraw()
        self._commit_undo()

    def _txt_change(self, tpl, delay=130):
        if self._suspend: return
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        self.cfgs[tpl]=collectors[tpl]()
        self._set_dirty(True)
        self._status("Editing")
        self._schedule_redraw(delay)
        if self._undo_id: self.root.after_cancel(self._undo_id)
        self._undo_id=self.root.after(600,self._commit_undo)

    def _commit_undo(self):
        self._undo_id=None
        self._undo.push({"tpl":self.tpl,"cfgs":self._collect()})

    def _apply_state(self, state):
        self._suspend=True
        try:
            self.cfgs=copy.deepcopy(state["cfgs"])
            # restore UI for each template
            t1=self.cfgs["t1"]
            self._t1_side.set(t1["panel_side"]); self._t1_size.set(t1["canvas_size"])
            self._t1_title.delete("1.0","end"); self._t1_title.insert("1.0",t1["title"])
            self._set_photo_label(self._t1_img_lbl,t1.get("photo_path",""))
            self._set_photo_label(self._t1_player_lbl,t1.get("player_path",""))
            self._set_photo_label(self._t1_logo_lbl,t1.get("logo_path",""))
            self._refresh_t1_panel_controls()
            self._refresh_t1_layer_controls()
            self._refresh_t1_spacing_controls()
            self._rebuild_t1_rows()

            t2=self.cfgs["t2"]
            self._t2_size.set(t2["canvas_size"]); self._t2_header.set(t2["header_text"])
            self._t2_divider.set(t2["divider_text"])
            for k,v in self._t2_nvars.items(): v.set(t2.get(k,""))
            self._t2_show_style.set(t2["show_playing_style"])
            for key in ["tags_a0","tags_a1","tags_b0","tags_b1"]:
                side="a" if "a" in key else "b"; idx=int(key[-1])
                self._t2_tag_vars[key].set(t2[f"tags_{side}"][idx])
            self._set_photo_label(self._t2_img_a,t2.get("photo_a",""))
            self._set_photo_label(self._t2_img_b,t2.get("photo_b",""))
            self._set_photo_label(self._t2_logo,t2.get("logo_path",""))
            self._refresh_t2_appearance_controls()
            self._rebuild_t2_rows()

            t3=self.cfgs["t3"]
            self._t3_size.set(t3["canvas_size"])
            for k,v in self._t3_vars.items(): v.set(t3.get(k,""))
            self._set_photo_label(self._t3_img_a,t3.get("photo_a",""))
            self._set_photo_label(self._t3_img_b,t3.get("photo_b",""))
            self._set_photo_label(self._t3_logo,t3.get("logo_path",""))
            self._rebuild_t3_rows()

            t4=self.cfgs["t4"]
            self._t4_size.set(t4["canvas_size"])
            self._t4_banner.set(t4["banner_text"]); self._t4_sponsor.set(t4["sponsor_text"])
            self._set_photo_label(self._t4_logo,t4.get("logo_path",""))
            self._rebuild_t4_players()
            for template in TEMPLATE_KEYS:
                self._refresh_text_style_controls(template)
                self._refresh_background_swatch(template)

            # switch to correct template
            key=state["tpl"]; idx=TEMPLATE_KEYS.index(key)
            self.tpl_var.set(TEMPLATE_NAMES[idx])
            for p in self.panels.values(): p.pack_forget()
            self.panels[key].pack(fill="both",expand=True)
            self.tpl=key
        finally:
            self._suspend=False
        self.redraw()

    def undo(self):
        s=self._undo.undo()
        if s:
            self._apply_state(s)
            self._set_dirty(True)
            self._status("Undid last change")

    def redo(self):
        s=self._undo.redo()
        if s:
            self._apply_state(s)
            self._set_dirty(True)
            self._status("Redid change")

    # ── Projects and data safety ─────────────────────────────────────────

    def _status(self,text):
        if hasattr(self,"status_var"):
            self.status_var.set(text)

    def _set_dirty(self,value):
        self._dirty=bool(value)
        name=self.current_project_path.stem if self.current_project_path else "Untitled"
        marker=" *" if self._dirty else ""
        self.root.title(f"{name}{marker} - Scoreboard Maker")

    def _confirm_discard(self):
        if not self._dirty:
            return True
        answer=messagebox.askyesnocancel(
            "Unsaved changes", "Save your scoreboard project before continuing?",
            parent=self.root,
        )
        if answer is None:
            return False
        if answer:
            return self.save_project()
        return True

    def open_project(self):
        if not self._confirm_discard():
            return False
        path=filedialog.askopenfilename(filetypes=PROJECT_FILETYPES,parent=self.root)
        if not path:
            return False
        try:
            payload=json.loads(Path(path).read_text(encoding="utf-8"))
            raw_configs=payload.get("templates",payload) if isinstance(payload,dict) else {}
            configs=normalise_project_configs(raw_configs)
            active=payload.get("active_template","t1") if isinstance(payload,dict) else "t1"
            if active not in TEMPLATE_KEYS:
                active="t1"
            self._apply_state({"tpl":active,"cfgs":configs})
            self._undo=UndoStack(); self._commit_undo()
            self.current_project_path=Path(path)
            self._set_dirty(False)
            self._status(f"Opened {Path(path).name}")
            return True
        except (OSError,ValueError,TypeError,KeyError) as exc:
            messagebox.showerror("Open failed",str(exc),parent=self.root)
            self._status("Could not open project")
            return False

    def save_project(self,save_as=False):
        self._collect()
        path=self.current_project_path
        if save_as or path is None:
            selected=filedialog.asksaveasfilename(
                defaultextension=".scoreboard.json",filetypes=PROJECT_FILETYPES,
                initialfile="scoreboard_project.scoreboard.json",parent=self.root,
            )
            if not selected:
                return False
            path=Path(selected)
        payload={
            "version":2,
            "active_template":self.tpl,
            "templates":self.cfgs,
        }
        temporary=path.with_name(path.name+".tmp")
        try:
            temporary.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
            os.replace(temporary,path)
            self.current_project_path=path
            self._set_dirty(False)
            self._status(f"Saved {path.name}")
            return True
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Save failed",str(exc),parent=self.root)
            self._status("Could not save project")
            return False

    def reset_current_template(self):
        name=TEMPLATE_NAMES[TEMPLATE_KEYS.index(self.tpl)]
        if not messagebox.askyesno(
            "Reset layout",f"Reset {name} to its original content?",parent=self.root,
        ):
            return
        configs=self._collect()
        configs[self.tpl]=copy.deepcopy(DEFAULT_CONFIGS[self.tpl])
        self._apply_state({"tpl":self.tpl,"cfgs":configs})
        self._commit_undo()
        self._set_dirty(True)
        self._status(f"Reset {name}")

    def _on_close(self):
        if self._confirm_discard():
            self._stop_live_output(silent=True)
            self.root.destroy()

    # ── Render ───────────────────────────────────────────────────────────

    def _schedule_redraw(self,delay=130):
        if self._redraw_id: self.root.after_cancel(self._redraw_id)
        self._redraw_id=self.root.after(delay,self.redraw)

    def redraw(self):
        self._redraw_id=None
        try:
            img=RENDERERS[self.tpl](self.cfgs[self.tpl])
        except Exception as e:
            print(f"Render error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self._status(f"Preview error: {e}")
            return
        self._last_render=img
        self.preview_info_var.set(f"{img.width:,} x {img.height:,} px")
        self._paint_preview()
        if self._live_output is not None:
            try:
                self._live_output.update(img)
            except RuntimeError as exc:
                self._stop_live_output(silent=True)
                messagebox.showerror("Live output stopped",str(exc),parent=self.root)

    def _paint_preview(self):
        self._preview_resize_id=None
        if self._last_render is None or not self.preview_canvas.winfo_exists():
            return
        canvas_w=max(320,self.preview_canvas.winfo_width())
        canvas_h=max(240,self.preview_canvas.winfo_height())
        image_w,image_h=self._last_render.size
        scale=min((canvas_w-48)/image_w,(canvas_h-48)/image_h,1.0)
        width=max(1,int(image_w*scale)); height=max(1,int(image_h*scale))
        preview=self._last_render.resize((width,height),Image.LANCZOS)
        self._tk_img=ImageTk.PhotoImage(preview)
        x=canvas_w//2; y=canvas_h//2
        left=x-width//2; top=y-height//2
        self._preview_image_rect=(left,top,width,height,image_w,image_h)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(
            left+7,top+8,left+width+7,top+height+8,
            fill="#10161b",outline="",
        )
        self.preview_canvas.create_image(x,y,image=self._tk_img)
        self._draw_t1_selection()

    def _draw_t1_selection(self):
        """Draw editor-only bounds; these guides never appear in exports."""
        if not self._preview_image_rect:
            return
        if self.tpl != "t1":
            layer=self._canvas_layer.get(self.tpl)
            box=self._other_selection_canvas_box(self.tpl,layer) if layer else None
            if box is None:
                return
            x0,y0,x1,y1=box
            self.preview_canvas.create_rectangle(
                x0,y0,x1,y1,outline="#35d4ff",width=2,dash=(6,4),tags="selection",
            )
            return
        layer=self._selected_t1_layer()
        box=self._t1_selection_canvas_box(layer)
        if box is None:
            return
        x0,y0,x1,y1=box
        self.preview_canvas.create_rectangle(
            x0,y0,x1,y1,outline="#35d4ff",width=2,dash=(6,4),tags="selection",
        )
        handle=4
        for hx,hy in ((x0,y0),(x1,y0),(x0,y1),(x1,y1)):
            self.preview_canvas.create_rectangle(
                hx-handle,hy-handle,hx+handle,hy+handle,
                fill="#f7fbfd",outline="#1688a6",width=1,tags="selection",
            )

    def export_png(self):
        config=copy.deepcopy(self.cfgs[self.tpl])
        scale=2 if self.export_scale_var.get().startswith("High") else 1
        config["_render_scale"]=scale
        base=self.current_project_path.stem.replace(".scoreboard","") if self.current_project_path else "scoreboard"
        p=filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG image","*.png")],initialfile=f"{base}_{self.tpl}.png",parent=self.root)
        if not p:
            return
        try:
            self._status("Exporting PNG")
            self.root.update_idletasks()
            img=RENDERERS[self.tpl](config)
            img.save(p,format="PNG")
            self._status(f"Exported {Path(p).name} ({img.width:,} x {img.height:,})")
            messagebox.showinfo("Export complete",f"Saved {Path(p).name}",parent=self.root)
        except (OSError,ValueError) as exc:
            self._status("Export failed")
            messagebox.showerror("Export failed",str(exc),parent=self.root)

    def toggle_live_output(self):
        if self._live_output is not None:
            self._stop_live_output()
            return
        LiveOutputDialog(
            self.root, self._live_output_preset, self._live_output_name,
            self._start_live_output,
        )

    def _start_live_output(self, preset, output_name):
        if output_name not in DECKLINK_OUTPUTS:
            messagebox.showerror("Invalid output","Choose a DeckLink output.",parent=self.root)
            return
        if self._last_render is None:
            self.redraw()
        if self._last_render is None:
            messagebox.showerror(
                "No scoreboard", "The current scoreboard could not be rendered.", parent=self.root,
            )
            return
        self._live_output_preset = preset
        self._live_output_name = output_name
        self._status(f"Starting {preset} on {output_name}")
        self.root.update_idletasks()
        output = None
        try:
            output = DeckLinkLiveOutput(preset, DECKLINK_OUTPUTS[output_name])
            output.start(self._last_render)
            self._live_output = output
            self._live_output_button.configure(text="Stop Live")
            self._status(f"LIVE: {preset} on {output_name}")
            self._poll_live_output()
        except (OSError,ValueError,RuntimeError) as exc:
            if output is not None:
                output.stop()
            self._status("DeckLink output did not start")
            messagebox.showerror(
                "DeckLink output failed",
                f"{exc}\n\nClose Media Express, check the SDI device, and try again.",
                parent=self.root,
            )

    def _poll_live_output(self):
        self._live_output_poll_id = None
        if self._live_output is None:
            return
        error = self._live_output.poll_error()
        if error:
            self._stop_live_output(silent=True)
            messagebox.showerror("Live output stopped",error,parent=self.root)
            return
        self._live_output_poll_id = self.root.after(350,self._poll_live_output)

    def _stop_live_output(self, silent=False):
        if self._live_output_poll_id:
            try:
                self.root.after_cancel(self._live_output_poll_id)
            except tk.TclError:
                pass
            self._live_output_poll_id = None
        output, self._live_output = self._live_output, None
        if output is not None:
            output.stop()
        if hasattr(self,"_live_output_button"):
            self._live_output_button.configure(text="Live Output")
        if not silent:
            self._status("DeckLink live output stopped")

    def export_mp4(self):
        ffmpeg = locate_ffmpeg()
        if not ffmpeg:
            messagebox.showerror(
                "FFmpeg not found",
                "Install FFmpeg or set FFMPEG_PATH to the full ffmpeg.exe path.",
                parent=self.root,
            )
            return
        MP4ExportDialog(
            self.root, self._video_export_preset, self._video_export_duration,
            lambda preset,duration:self._export_mp4(ffmpeg,preset,duration),
        )

    def _export_mp4(self, ffmpeg, preset, duration):
        base=self.current_project_path.stem.replace(".scoreboard","") if self.current_project_path else "scoreboard"
        selected=filedialog.asksaveasfilename(
            defaultextension=".mp4",filetypes=[("MP4 video","*.mp4")],
            initialfile=f"{base}_{self.tpl}_{preset.lower().replace(' ','_')}.mp4",
            parent=self.root,
        )
        if not selected:
            return
        self._video_export_preset=preset
        self._video_export_duration=duration
        try:
            self._status(f"Exporting {preset} MP4")
            self.root.update_idletasks()
            config=copy.deepcopy(self.cfgs[self.tpl])
            config["_render_scale"]=1
            image=RENDERERS[self.tpl](config)
            with tempfile.TemporaryDirectory(prefix="scoreboard_mp4_") as temporary:
                source=Path(temporary) / "scoreboard_frame.png"
                image.save(source,format="PNG")
                command=build_mp4_command(
                    ffmpeg,source,Path(selected),preset,duration,
                )
                completed=subprocess.run(
                    command,capture_output=True,text=True,check=False,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                )
            if completed.returncode:
                detail=(completed.stderr or completed.stdout or "FFmpeg failed").strip()
                raise RuntimeError(detail[-1800:])
            self._status(f"Exported {Path(selected).name} ({preset}, {duration}s)")
            messagebox.showinfo(
                "Export complete",
                f"Saved {Path(selected).name}\n{preset} | {duration} seconds | 48 kHz stereo",
                parent=self.root,
            )
        except (OSError,ValueError,RuntimeError) as exc:
            self._status("MP4 export failed")
            messagebox.showerror("MP4 export failed",str(exc),parent=self.root)


def render_default(template: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = RENDERERS[template](copy.deepcopy(DEFAULT_CONFIGS[template]))
    image.save(output, format="PNG")
    print(f"Rendered {template}: {output} ({image.width}x{image.height})")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Four-template match stats card generator.")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--headless", type=Path, help="Render one default template to PNG.")
    output_group.add_argument("--render-all", type=Path, help="Render all default templates into a directory.")
    output_group.add_argument("--web", action="store_true", help="Run the browser editor.")
    parser.add_argument("--template", choices=TEMPLATE_KEYS, default="t1")
    parser.add_argument("--host", default="127.0.0.1", help="Web bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8080, help="Web port (default: 8080).")
    args = parser.parse_args(argv)

    if args.headless:
        render_default(args.template, args.headless)
        return
    if args.render_all:
        for key in TEMPLATE_KEYS:
            render_default(key, args.render_all / f"scoreboard_{key}.png")
        return
    if args.web:
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        import scoreboard_web
        scoreboard_web.run_server(sys.modules[__name__], args.host, args.port)
        return

    root=TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    App(root); root.mainloop()

if __name__=="__main__":
    main()
