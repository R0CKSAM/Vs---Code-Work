#!/usr/bin/env python3
"""
Scoreboard / Match Stats Card Generator — PRODUCTION BUILD v5.0
==================================================================
Inherited from v3.0 (Final Merged Build) and upgraded with:

  Studio workflow:
    • One editor hosts Single Player, Head-to-Head, VS Tug-of-War, and
      Performance Spotlight layouts.
    • Per-photo zoom and focal-point framing for every template.
    • Safe-area/centre guides, smart snapping, visible/locked layers,
      real layer paint order, and reusable named export presets.

  Rendering:
    • Two-layer render pipeline — expensive base layer (background,
      glassmorphism blur, drop shadow, gradient panel) is cached
      behind a content-hash key. Text / overlay re-renders are up to
      10× faster on subsequent frames because only the foreground
      layer is redrawn.
    • Renderer.render() now returns (Image, HitboxDict) where HitboxDict
      maps element ids → (x1, y1, x2, y2) pixel bounding boxes.

  Moveable Elements:
    • Every element (title, subtitle, score block, each stat row,
      watermark text and logo, PNG overlay) has a unique element id
      and can be independently dragged on the preview canvas.
    • Positions are stored in cfg["positions"] as percentage coords
      so they survive canvas-size changes.
    • Auto-layout is preserved — elements without an override continue
      to flow vertically. A drag detaches the element; double-click
      re-attaches it to the auto-layout flow.
    • Dragging an element is committed to the Undo/Redo stack on
      mouse-up so Ctrl-Z works as expected.
    • Reordering stat rows also swaps their saved drag positions.

  Tests:
    • 3 new unit tests: hitbox dict returned, score hitbox present,
      watermark hitbox present, position-override pixel accuracy.

Run (GUI):
    python scoreboard_final.py

Run (CLI / headless):
    python scoreboard_final.py --headless output.png

Run (self-test):
    python scoreboard_final.py --test

Requirements:
    pip install pillow customtkinter tkinterdnd2
    pip install numpy          # optional — faster gradients
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import logging
import os
import queue
import re
import sys
import threading
import traceback
import unittest
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Pillow ──────────────────────────────────────────────────────────────────
try:
    from PIL import (Image, ImageDraw, ImageEnhance, ImageFilter,
                     ImageFont, ImageOps)
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

# ── numpy (optional) ────────────────────────────────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ── GUI libs (optional — only needed for the GUI) ───────────────────────────
try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
    import customtkinter as ctk
    from tkinterdnd2 import DND_FILES, TkinterDnD
    from PIL import ImageTk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════════

APP_DIR = Path(__file__).resolve().parent
AUDIT_PATH = APP_DIR / "audit.log"
EXPORT_PRESET_PATH = APP_DIR / "scoreboard_export_presets.json"
_audit = logging.getLogger("audit")
_audit.setLevel(logging.DEBUG)
if not _audit.handlers:
    try:
        _fh = logging.FileHandler(AUDIT_PATH, encoding="utf-8")
        _fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        _audit.addHandler(_fh)
    except OSError:
        # Rendering and tests must not fail because the install directory is
        # read-only or the log is temporarily locked by another process.
        _audit.addHandler(logging.NullHandler())
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("ScoreboardApp")


def audit(event: str, detail: str = "") -> None:
    _audit.info("%s | %s", event, detail)


# ═══════════════════════════════════════════════════════════════════════════
# TYPES
# ═══════════════════════════════════════════════════════════════════════════

RGB  = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]


# ═══════════════════════════════════════════════════════════════════════════
# THEMES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Theme:
    name: str
    bg: RGB
    panel_top: RGB
    panel_bottom: RGB
    accent: RGB
    title: RGB
    label: RGB
    bar_track: RGB
    panel_alpha: int = 220

    def to_dict(self) -> dict:  return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Theme":
        t = cls.__new__(cls); t.__dict__.update(d); return t


THEMES: Dict[str, Theme] = {
    "Dark Pro":        Theme("Dark Pro",        (10,30,48),   (6,8,12),     (14,34,52),   (223,255,60),  (255,255,255), (200,215,225), (55,75,95),  230),
    "Broadcast Dark":  Theme("Broadcast Dark",  (10,30,48),   (8,10,14),    (14,34,52),   (223,255,60),  (255,255,255), (225,230,232), (70,90,105), 220),
    "Cyberpunk Neon":  Theme("Cyberpunk Neon",  (15,5,25),    (20,10,35),   (5,2,10),     (255,0,128),   (0,255,240),   (240,240,240), (60,20,80),  230),
    "Emerald Pitch":   Theme("Emerald Pitch",   (5,25,15),    (10,30,20),   (2,12,8),     (46,213,115),  (255,255,255), (200,230,210), (30,60,45),  225),
    "Minimal Light":   Theme("Minimal Light",   (240,242,245),(255,255,255),(235,238,242),(0,102,255),   (20,25,30),    (60,70,80),    (200,210,220),240),
    "Broadcast Red":   Theme("Broadcast Red",   (12,12,18),   (20,6,6),     (6,2,2),      (230,50,50),   (255,255,255), (220,200,200), (80,40,40),  235),
    "Ocean":           Theme("Ocean",           (5,20,45),    (8,30,65),    (3,15,40),    (0,210,200),   (240,250,255), (150,200,230), (30,70,110), 220),
    "Platinum":        Theme("Platinum",        (18,18,22),   (28,28,35),   (15,15,20),   (192,192,215), (255,255,255), (175,175,195), (60,60,75),  240),
}


# ═══════════════════════════════════════════════════════════════════════════
# STAT PRESETS
# ═══════════════════════════════════════════════════════════════════════════

STAT_PRESETS: Dict[str, List[Dict]] = {
    "Tennis": [
        {"label": "1st Serve %",               "value": "72 %",  "max": "100", "sublabel": ""},
        {"label": "2nd Serve Win %",            "value": "61 %",  "max": "100", "sublabel": ""},
        {"label": "1st Serve Return Win %",     "value": "54 %",  "max": "100", "sublabel": ""},
        {"label": "Break Points Won",           "value": "4",     "max": "7",   "sublabel": "out of 7 chances"},
        {"label": "Short Rallies Won (1–4 sh)", "value": "66 %",  "max": "100", "sublabel": ""},
        {"label": "Aces",                       "value": "8",     "max": "20",  "sublabel": ""},
    ],
    "Football": [
        {"label": "Possession",    "value": "58 %",   "max": "100", "sublabel": ""},
        {"label": "Shots on Goal", "value": "7",      "max": "15",  "sublabel": "of 14 total"},
        {"label": "Pass Accuracy", "value": "87 %",   "max": "100", "sublabel": ""},
        {"label": "Distance (km)", "value": "11.2",   "max": "14",  "sublabel": ""},
        {"label": "Sprint Speed",  "value": "34 KMH", "max": "40",  "sublabel": "top speed"},
    ],
    "Cricket": [
        {"label": "Batting Average", "value": "52.4", "max": "100", "sublabel": ""},
        {"label": "Strike Rate",     "value": "138",  "max": "200", "sublabel": ""},
        {"label": "Boundaries",      "value": "12",   "max": "20",  "sublabel": "8 fours, 4 sixes"},
        {"label": "Economy Rate",    "value": "6.8",  "max": "12",  "sublabel": "bowling"},
        {"label": "Wickets",         "value": "3",    "max": "10",  "sublabel": ""},
    ],
    "Basketball": [
        {"label": "Points",       "value": "28",   "max": "50",  "sublabel": ""},
        {"label": "Field Goal %", "value": "54 %", "max": "100", "sublabel": ""},
        {"label": "3-Point %",    "value": "42 %", "max": "100", "sublabel": "5 of 12"},
        {"label": "Rebounds",     "value": "9",    "max": "20",  "sublabel": "6 def, 3 off"},
        {"label": "Assists",      "value": "7",    "max": "15",  "sublabel": ""},
    ],
    "Custom": [],
}

SYSTEM_FONTS = [
    "Arial", "Helvetica", "Verdana", "Tahoma", "Trebuchet MS",
    "Impact", "Times New Roman", "Courier New", "Consolas",
]

CANVAS_SIZES: Dict[str, Tuple[int, int]] = {
    "16:9  (1024×576)":            (1024, 576),
    "1:1   (1024×1024)":           (1024, 1024),
    "9:16  (576×1024)":            (576, 1024),
    "4:5   (1024×1280)":           (1024, 1280),
    "Full HD (1920×1080)":         (1920, 1080),
    "4K (3840×2160)":              (3840, 2160),
    "Twitter Header (1500×500)":   (1500, 500),
    "Instagram Story (1080×1920)": (1080, 1920),
}

BATCH_PRESETS = ["16:9  (1024×576)", "1:1   (1024×1024)", "9:16  (576×1024)"]
MAX_EXPORT_PIXELS = 80_000_000

LAYOUT_PRESETS: Dict[str, Dict[str, Any]] = {
    "Broadcast Stats": {
        "canvas_preset": "16:9  (1024×576)", "panel_side": "right",
        "panel_width_pct": 42, "panel_opacity": 220,
        "show_score_block": False,
    },
    "Player Feature": {
        "canvas_preset": "1:1   (1024×1024)", "panel_side": "left",
        "panel_width_pct": 48, "panel_opacity": 225,
        "show_score_block": False,
    },
    "Score Focus": {
        "canvas_preset": "16:9  (1024×576)", "panel_side": "right",
        "panel_width_pct": 46, "panel_opacity": 235,
        "show_score_block": True,
    },
    "Social Story": {
        "canvas_preset": "Instagram Story (1080×1920)", "panel_side": "right",
        "panel_width_pct": 62, "panel_opacity": 230,
        "show_score_block": False,
    },
}

TEMPLATE_NAMES = [
    "Single Player Pro",
    "Head-to-Head Insights",
    "VS Tug-of-War",
    "Performance Spotlight",
]

BUILTIN_EXPORT_PRESETS: Dict[str, Dict[str, Any]] = {
    "Social PNG": {"export_format": "PNG", "export_scale": 1, "export_quality": 95},
    "High Resolution PNG": {"export_format": "PNG", "export_scale": 2, "export_quality": 95},
    "Client Review JPEG": {"export_format": "JPEG", "export_scale": 1, "export_quality": 90},
    "Archive WebP": {"export_format": "WebP", "export_scale": 2, "export_quality": 95},
}

CONFIG_PATH = APP_DIR / "scoreboard_config.json"

DEFAULT_CFG: Dict[str, Any] = {
    "template_name":    "Single Player Pro",
    # canvas
    "canvas_preset":   "16:9  (1024×576)",
    "export_scale":    1,           # 1x | 2x | 4x
    "export_format":   "PNG",       # PNG | JPEG | WebP
    "export_quality":  95,
    # photo / overlay
    "photo_path":       "",
    "photo_fit":        "cover",    # cover | contain | stretch
    "photo_treatment":  "none",     # none | blur_edges | vignette | grayscale | sepia
    "photo_zoom":       100.0,
    "photo_focus_x":    50.0,
    "photo_focus_y":    50.0,
    "overlay_path":     "",
    "overlay_x":        5.0,        # % of canvas width
    "overlay_y":        5.0,        # % of canvas height
    "overlay_scale":    80.0,       # % of canvas height
    # panel
    "panel_side":       "right",
    "panel_width_pct":  42,
    "panel_opacity":    220,
    "panel_gradient_dir": "horizontal_fade",  # horizontal_fade | vertical
    "glassmorphism":    True,
    "drop_shadow":      True,
    # spacing (% of canvas)
    "margin_x":         9.0,
    "margin_y":         5.0,
    "spacing_title":    3.0,
    "spacing_rows":     3.0,
    "spacing_items":    1.0,
    # text
    "title":            "Match\nStatistics",
    "subtitle":         "",
    "show_score_block": False,
    "team_a": "Team A", "team_b": "Team B",
    "score": "3 – 1", "match_info": "Full Time",
    # watermark
    "watermark_text":        "",
    "watermark_logo_path":   "",
    "watermark_opacity":     100,
    # theme / color
    "theme_name":       "Dark Pro",
    "accent_override":  "",         # hex or ""
    # typography
    "font_family":      "Arial",
    "font_bold_path":   "",
    "font_regular_path": "",
    "title_size":       0,          # 0 = auto
    "label_size":       0,
    "value_size":       0,
    "auto_fit_text":    True,
    # rows
    "stat_rows": copy.deepcopy(STAT_PRESETS["Tennis"][:4]),
    "positions": {},
    "layer_order": [],
    "layer_states": {},
    "snap_enabled": True,
    "snap_threshold": 8,
    "show_safe_area": True,
    "show_center_guides": False,
    "safe_area_pct": 5.0,
    "template_configs": {},
}


# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def extract_number(text: str) -> Optional[float]:
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
    return float(m.group(0).replace(",", ".")) if m else None


def auto_percent(value_text: str, max_value: str) -> float:
    num = extract_number(value_text)
    if num is None: return 0.0
    try:   mv = float(max_value)
    except: mv = 100.0
    if mv <= 0: mv = 100.0
    return max(0.0, min(100.0, num / mv * 100))


def parse_stat_rows(text: str) -> List[Dict[str, str]]:
    """Parse spreadsheet/CSV clipboard data into scoreboard stat rows."""
    text = text.strip()
    if not text:
        return []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample else csv.excel
    records = [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]
    if not records:
        return []

    header = [cell.strip().lower().replace(" ", "_") for cell in records[0]]
    aliases = {
        "label": {"label", "metric", "stat", "name"},
        "value": {"value", "result", "score"},
        "max": {"max", "maximum", "scale", "target"},
        "sublabel": {"sublabel", "sub_label", "detail", "note", "context"},
    }
    has_header = any(cell in values for cell in header for values in aliases.values())
    columns: Dict[str, int] = {}
    if has_header:
        for key, values in aliases.items():
            columns[key] = next((i for i, cell in enumerate(header) if cell in values), -1)
        records = records[1:]
    else:
        columns = {"label": 0, "value": 1, "max": 2, "sublabel": 3}

    result = []
    for record in records:
        def cell(key: str, default: str = "") -> str:
            index = columns.get(key, -1)
            return record[index].strip() if 0 <= index < len(record) else default

        label = cell("label")
        value = cell("value")
        if label or value:
            result.append({
                "label": label or "Metric",
                "value": value or "0",
                "max": cell("max", "100") or "100",
                "sublabel": cell("sublabel"),
            })
    return result


def parse_comparison_rows(text: str, include_unit: bool = False) -> List[Dict[str, str]]:
    """Parse pasted comparison metrics: label, A, B, max, and optional unit."""
    records = [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text.strip()), csv.excel_tab)
        if any(cell.strip() for cell in row)
    ]
    if not records:
        return []
    if records[0][0].lower() in {"label", "metric", "stat"}:
        records = records[1:]
    rows = []
    for record in records:
        if len(record) < 3:
            continue
        row = {
            "label": record[0] or "Metric",
            "value_a": record[1] or "0",
            "value_b": record[2] or "0",
            "max": record[3] if len(record) > 3 and record[3] else "100",
        }
        if include_unit:
            row["unit"] = record[4] if len(record) > 4 else ""
        rows.append(row)
    return rows


def parse_player_stats(text: str) -> List[Dict[str, str]]:
    """Parse pasted spotlight metrics: label, value, unit, maximum."""
    records = [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text.strip()), csv.excel_tab)
        if any(cell.strip() for cell in row)
    ]
    if not records:
        return []
    if records[0][0].lower() in {"label", "metric", "stat"}:
        records = records[1:]
    return [
        {
            "label": record[0] or "Metric",
            "value": record[1] if len(record) > 1 and record[1] else "0",
            "unit": record[2] if len(record) > 2 else "",
            "max": record[3] if len(record) > 3 and record[3] else "100",
        }
        for record in records
        if record
    ]


def _load_template_pack():
    """Load the companion four-layout renderer without making GUI startup depend on it."""
    try:
        import scoreboard_app as template_pack
        return template_pack
    except ImportError:
        try:
            from . import scoreboard_app as template_pack
            return template_pack
        except ImportError as exc:
            raise RuntimeError("scoreboard_app.py is required for comparison templates") from exc


def template_defaults() -> Dict[str, Dict[str, Any]]:
    pack = _load_template_pack()
    return {
        "Head-to-Head Insights": copy.deepcopy(pack.DEF_T2),
        "VS Tug-of-War": copy.deepcopy(pack.DEF_T3),
        "Performance Spotlight": copy.deepcopy(pack.DEF_T4),
    }


def active_canvas_options(cfg: Dict[str, Any]) -> Dict[str, Tuple[int, int]]:
    template = cfg.get("template_name", "Single Player Pro")
    if template == "Single Player Pro":
        return CANVAS_SIZES
    pack = _load_template_pack()
    return {
        "Head-to-Head Insights": pack.T2_SIZES,
        "VS Tug-of-War": pack.T3_SIZES,
        "Performance Spotlight": pack.T4_SIZES,
    }.get(template, CANVAS_SIZES)


def active_canvas_size(cfg: Dict[str, Any]) -> Tuple[int, int]:
    template = cfg.get("template_name", "Single Player Pro")
    options = active_canvas_options(cfg)
    if template == "Single Player Pro":
        selected = cfg.get("canvas_preset")
    else:
        selected = cfg.get("template_configs", {}).get(template, {}).get("canvas_size")
    return options.get(selected, next(iter(options.values())))


def default_layer_ids(cfg: Dict[str, Any]) -> List[str]:
    """Return the meaningful editable layers in their default paint order."""
    if cfg.get("template_name", "Single Player Pro") != "Single Player Pro":
        return ["template_artwork"]
    ids = []
    if cfg.get("overlay_path"):
        ids.append("overlay")
    if cfg.get("show_score_block"):
        ids.append("score")
    if cfg.get("subtitle", "").strip():
        ids.append("subtitle")
    ids.append("title")
    ids.extend(f"row_{index}" for index, _ in enumerate(cfg.get("stat_rows", [])))
    if cfg.get("watermark_text", "").strip():
        ids.append("wm_text")
    if cfg.get("watermark_logo_path", "").strip():
        ids.append("wm_logo")
    return ids


def normalised_layer_order(cfg: Dict[str, Any]) -> List[str]:
    defaults = default_layer_ids(cfg)
    configured = cfg.get("layer_order", [])
    order = [layer_id for layer_id in configured if layer_id in defaults]
    order.extend(layer_id for layer_id in defaults if layer_id not in order)
    return order


def layer_state(cfg: Dict[str, Any], layer_id: str) -> Dict[str, bool]:
    state = cfg.get("layer_states", {}).get(layer_id, {})
    return {
        "visible": bool(state.get("visible", True)),
        "locked": bool(state.get("locked", False)),
    }


def load_export_presets(path: Path = EXPORT_PRESET_PATH) -> Dict[str, Dict[str, Any]]:
    presets = copy.deepcopy(BUILTIN_EXPORT_PRESETS)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                custom = json.load(handle)
            if isinstance(custom, dict):
                presets.update({str(k): v for k, v in custom.items() if isinstance(v, dict)})
        except (OSError, json.JSONDecodeError) as exc:
            audit("EXPORT_PRESET_LOAD_ERROR", str(exc))
    return presets


def save_export_presets(presets: Dict[str, Dict[str, Any]], path: Path = EXPORT_PRESET_PATH) -> None:
    custom = {k: v for k, v in presets.items() if k not in BUILTIN_EXPORT_PRESETS}
    try:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(custom, handle, indent=2, ensure_ascii=False)
        temporary.replace(path)
    except OSError as exc:
        audit("EXPORT_PRESET_SAVE_ERROR", str(exc))


def rgb_lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))


def clamp_rgb(c: RGB) -> RGB:
    return (max(0,min(255,c[0])), max(0,min(255,c[1])), max(0,min(255,c[2])))


def hex_to_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))


def rgb_to_hex(c: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def _text_dimensions(draw: ImageDraw.ImageDraw, text: str,
                     font: ImageFont.ImageFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text or " ", font=font)
    return box[2] - box[0], box[3] - box[1]


def _ellipsize(draw: ImageDraw.ImageDraw, text: str,
               font: ImageFont.ImageFont, max_width: int) -> str:
    if _text_dimensions(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _text_dimensions(draw, text[:mid].rstrip() + suffix, font)[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + suffix if lo else suffix


def _wrap_text(draw: ImageDraw.ImageDraw, text: str,
               font: ImageFont.ImageFont, max_width: int) -> List[str]:
    lines: List[str] = []
    for paragraph in text.replace("\\n", "\n").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _text_dimensions(draw, candidate, font)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _trim_transparent(image: Image.Image) -> Image.Image:
    if "A" not in image.getbands():
        return image
    bounds = image.getchannel("A").getbbox()
    return image.crop(bounds) if bounds else image


# ── cross-platform font discovery ────────────────────────────────────────────

_FONT_PATHS: Dict[str, List[str]] = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ],
}

# system-font name → typical file names (Windows / cross-platform)
_SYSNAME_MAP: Dict[str, Dict[str, str]] = {
    "arial":          {"bold": "arialbd.ttf",    "regular": "arial.ttf"},
    "verdana":        {"bold": "verdanab.ttf",   "regular": "verdana.ttf"},
    "tahoma":         {"bold": "tahomabd.ttf",   "regular": "tahoma.ttf"},
    "trebuchet ms":   {"bold": "trebucbd.ttf",   "regular": "trebuc.ttf"},
    "impact":         {"bold": "impact.ttf",     "regular": "impact.ttf"},
    "times new roman":{"bold": "timesbd.ttf",   "regular": "times.ttf"},
    "courier new":    {"bold": "courbd.ttf",     "regular": "cour.ttf"},
    "consolas":       {"bold": "consolab.ttf",   "regular": "consola.ttf"},
}

_font_cache: Dict[Tuple, ImageFont.FreeTypeFont] = {}


def _find_font_file(variant: str, family: str = "") -> Optional[str]:
    """Locate a font file: custom path > system name map > path list."""
    fam = family.lower()
    if fam in _SYSNAME_MAP:
        fname = _SYSNAME_MAP[fam][variant]
        for prefix in ["C:/Windows/Fonts/", "/Library/Fonts/",
                       "/usr/share/fonts/truetype/msttcorefonts/"]:
            p = prefix + fname
            if Path(p).exists(): return p
        # bare filename (Windows adds to PATH)
        try:
            ImageFont.truetype(fname, 12)
            return fname
        except Exception:
            pass
    for p in _FONT_PATHS[variant]:
        if Path(p).exists(): return p
    return None


def get_font(size: int, bold: bool = False,
             family: str = "", custom_path: str = "") -> ImageFont.FreeTypeFont:
    variant = "bold" if bold else "regular"
    key = (custom_path, family, variant, size)
    if key in _font_cache: return _font_cache[key]

    font = None
    # 1. explicit custom path
    if custom_path and Path(custom_path).exists():
        try: font = ImageFont.truetype(custom_path, size)
        except Exception: pass
    # 2. system name map / path list
    if font is None:
        p = _find_font_file(variant, family)
        if p:
            try: font = ImageFont.truetype(p, size)
            except Exception: pass
    # 3. last resort
    if font is None:
        font = ImageFont.load_default()

    _font_cache[key] = font
    return font


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════

def _normalise_config(saved: Any) -> Dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CFG)
    if isinstance(saved, dict):
        cfg.update(saved)
    if cfg.get("canvas_preset") not in CANVAS_SIZES:
        cfg["canvas_preset"] = DEFAULT_CFG["canvas_preset"]
    if cfg.get("theme_name") not in THEMES:
        cfg["theme_name"] = DEFAULT_CFG["theme_name"]
    if cfg.get("panel_side") not in ("left", "right"):
        cfg["panel_side"] = DEFAULT_CFG["panel_side"]
    if cfg.get("template_name") not in TEMPLATE_NAMES:
        cfg["template_name"] = DEFAULT_CFG["template_name"]
    defaults = template_defaults()
    stored_templates = cfg.get("template_configs")
    if not isinstance(stored_templates, dict):
        stored_templates = {}
    clean_templates = {}
    for template_name, default in defaults.items():
        value = stored_templates.get(template_name, {})
        merged = copy.deepcopy(default)
        if isinstance(value, dict):
            merged.update(value)
        options = active_canvas_options({"template_name": template_name})
        if merged.get("canvas_size") not in options:
            merged["canvas_size"] = default["canvas_size"]
        clean_templates[template_name] = merged
    cfg["template_configs"] = clean_templates
    if not isinstance(cfg.get("positions"), dict):
        cfg["positions"] = {}
    else:
        clean_positions = {}
        for key, value in cfg["positions"].items():
            if isinstance(value, (list, tuple)) and len(value) == 2:
                try:
                    clean_positions[str(key)] = [
                        max(0.0, min(100.0, float(value[0]))),
                        max(0.0, min(100.0, float(value[1]))),
                    ]
                except (TypeError, ValueError):
                    pass
        cfg["positions"] = clean_positions
    if not isinstance(cfg.get("stat_rows"), list):
        cfg["stat_rows"] = copy.deepcopy(DEFAULT_CFG["stat_rows"])
    if not cfg["stat_rows"] and not cfg.get("show_score_block"):
        cfg["stat_rows"] = copy.deepcopy(DEFAULT_CFG["stat_rows"])
    if not isinstance(cfg.get("layer_states"), dict):
        cfg["layer_states"] = {}
    else:
        cfg["layer_states"] = {
            str(key): {
                "visible": bool(value.get("visible", True)),
                "locked": bool(value.get("locked", False)),
            }
            for key, value in cfg["layer_states"].items()
            if isinstance(value, dict)
        }
    if not isinstance(cfg.get("layer_order"), list):
        cfg["layer_order"] = []
    cfg["layer_order"] = normalised_layer_order(cfg)
    for key, low, high, default in [
        ("safe_area_pct", 0.0, 25.0, 5.0),
        ("snap_threshold", 1, 30, 8),
    ]:
        try:
            cfg[key] = max(low, min(high, float(cfg.get(key, default))))
        except (TypeError, ValueError):
            cfg[key] = default
    cfg["snap_enabled"] = bool(cfg.get("snap_enabled", True))
    cfg["show_safe_area"] = bool(cfg.get("show_safe_area", True))
    cfg["show_center_guides"] = bool(cfg.get("show_center_guides", False))
    return cfg


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = _normalise_config(saved)
            audit("CONFIG_LOAD", str(path))
            return cfg
        except Exception as e:
            audit("CONFIG_LOAD_ERROR", str(e))
    return copy.deepcopy(DEFAULT_CFG)


def save_config(cfg: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        temporary.replace(path)
        audit("CONFIG_SAVE", str(path))
    except Exception as e:
        audit("CONFIG_SAVE_ERROR", str(e))


# ═══════════════════════════════════════════════════════════════════════════
# UNDO / REDO STACK
# ═══════════════════════════════════════════════════════════════════════════

class UndoStack:
    MAX = 50
    def __init__(self):
        self._s: List[Dict] = []
        self._c = -1

    def push(self, state: Dict) -> None:
        if self._c >= 0 and self._s[self._c] == state:
            return
        self._s = self._s[:self._c+1]
        self._s.append(copy.deepcopy(state))
        if len(self._s) > self.MAX: self._s.pop(0)
        self._c = len(self._s) - 1

    def undo(self) -> Optional[Dict]:
        if self._c > 0:
            self._c -= 1; return copy.deepcopy(self._s[self._c])
        return None

    def redo(self) -> Optional[Dict]:
        if self._c < len(self._s) - 1:
            self._c += 1; return copy.deepcopy(self._s[self._c])
        return None

    @property
    def can_undo(self) -> bool: return self._c > 0
    @property
    def can_redo(self) -> bool: return self._c < len(self._s) - 1


# ═══════════════════════════════════════════════════════════════════════════
# CORE RENDERER  (pure Pillow, no GUI deps)
# ═══════════════════════════════════════════════════════════════════════════

class Renderer:
    _bg_cache:   Optional[Image.Image] = None
    _bg_key:     Optional[tuple]       = None
    _base_cache: Optional[Image.Image] = None
    _base_key:   Optional[tuple]       = None

    # ── background ───────────────────────────────────────────────────────

    @classmethod
    def get_background(cls, cfg: Dict, W: int, H: int) -> Image.Image:
        theme = THEMES.get(cfg.get("theme_name"), THEMES["Dark Pro"])
        p = cfg.get("photo_path", "")
        try:
            stat = Path(p).stat() if p else None
            asset_key = (p, stat.st_mtime_ns, stat.st_size) if stat else (p, None, None)
        except OSError:
            asset_key = (p, None, None)
        key = (
            asset_key, W, H, cfg.get("photo_fit", "cover"),
            cfg.get("photo_treatment", "none"), tuple(theme.bg),
            float(cfg.get("photo_zoom", 100.0)),
            float(cfg.get("photo_focus_x", 50.0)),
            float(cfg.get("photo_focus_y", 50.0)),
        )
        if cls._bg_key == key and cls._bg_cache:
            return cls._bg_cache.copy()

        img = Image.new("RGB", (W, H), theme.bg)
        if p and Path(p).exists():
            try:
                with Image.open(p) as source:
                    photo = source.convert("RGB")
                fit = cfg.get("photo_fit", "cover")
                pw, ph = photo.size
                if fit == "cover":
                    zoom = max(1.0, float(cfg.get("photo_zoom", 100.0)) / 100.0)
                    resize_scale = max(W / pw, H / ph) * zoom
                    nw, nh = max(W, int(pw * resize_scale)), max(H, int(ph * resize_scale))
                    photo = photo.resize((nw, nh), Image.LANCZOS)
                    focus_x = max(0.0, min(100.0, float(cfg.get("photo_focus_x", 50.0)))) / 100.0
                    focus_y = max(0.0, min(100.0, float(cfg.get("photo_focus_y", 50.0)))) / 100.0
                    left = int((nw - W) * focus_x)
                    top = int((nh - H) * focus_y)
                    photo = photo.crop((left, top, left + W, top + H))
                elif fit == "contain":
                    photo.thumbnail((W, H), Image.LANCZOS)
                    photo = cls._apply_treatment(
                        photo, cfg.get("photo_treatment", "none"), photo.width, photo.height
                    )
                    img.paste(photo, ((W-photo.width)//2,
                                      (H-photo.height)//2))
                    photo = None
                else:  # stretch
                    photo = photo.resize((W, H), Image.LANCZOS)

                if photo:
                    photo = cls._apply_treatment(
                        photo, cfg.get("photo_treatment", "none"), W, H
                    )
                    img.paste(photo, (0, 0))
            except Exception as e:
                audit("PHOTO_ERROR", str(e))

        cls._bg_cache, cls._bg_key = img, key
        return img.copy()

    @staticmethod
    def _apply_treatment(photo: Image.Image, treatment: str, W: int, H: int) -> Image.Image:
        if treatment == "grayscale":
            return ImageOps.grayscale(photo).convert("RGB")
        if treatment == "sepia":
            g = ImageOps.grayscale(photo).convert("RGB")
            return Image.blend(g, Image.new("RGB", g.size, (112,66,20)), 0.45)
        if treatment == "blur_edges":
            blurred = photo.filter(ImageFilter.GaussianBlur(22))
            cx, cy = W//2, H//2
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).ellipse(
                [cx-int(W*.38), cy-int(H*.38), cx+int(W*.38), cy+int(H*.38)], fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(60))
            return Image.composite(photo, blurred, mask)
        if treatment == "vignette":
            vig = ImageOps.invert(Image.radial_gradient("L")).resize((W, H), Image.LANCZOS)
            vig = vig.point(lambda p: 70 + int(p * 185 / 255))
            return Image.composite(photo, Image.new("RGB", (W, H), (0,0,0)), vig)
        return photo

    # ── panel ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_gradient_panel(pw: int, H: int, top: RGB, bot: RGB,
                              alpha: int, direction: str,
                              panel_side: str) -> Image.Image:
        if HAS_NUMPY and direction == "vertical":
            t    = np.linspace(0, 1, H, dtype=np.float32)[:, None]
            ct   = np.array(top, dtype=np.float32)
            cb   = np.array(bot, dtype=np.float32)
            rgb  = (ct*(1-t) + cb*t).astype(np.uint8)
            arr  = np.tile(rgb[:, None, :], (1, pw, 1))
            a_arr= np.full((H, pw, 1), alpha, dtype=np.uint8)
            return Image.fromarray(
                np.concatenate([arr, a_arr], axis=-1), mode="RGBA")

        layer = Image.new("RGBA", (pw, H), (0,0,0,0))
        pd    = ImageDraw.Draw(layer)
        pr, pg, pb = top

        if direction == "horizontal_fade":
            fade = max(1, int(pw * .32))
            for x in range(pw):
                if panel_side == "right":
                    a = int(alpha * ((x/fade)**1.6)) if x < fade else alpha
                else:
                    rx = pw - 1 - x
                    a = int(alpha * ((rx/fade)**1.6)) if rx < fade else alpha
                pd.line([(x,0),(x,H)], fill=(pr,pg,pb,a))
        else:  # vertical (pure-Python fallback)
            for y in range(H):
                t = y / max(1, H-1)
                r = int(top[0]+(bot[0]-top[0])*t)
                g = int(top[1]+(bot[1]-top[1])*t)
                b = int(top[2]+(bot[2]-top[2])*t)
                pd.line([(0,y),(pw,y)], fill=(r,g,b,alpha))
        return layer



    # ── watermark ─────────────────────────────────────────────────────────

    @staticmethod
    def _watermark_layers(cfg: Dict, hitboxes: Dict, W: int, H: int) -> List[Tuple[str, Image.Image, Tuple[int, int]]]:
        """Build branding independently so visibility and z-order are real."""
        layers: List[Tuple[str, Image.Image, Tuple[int, int]]] = []
        opacity = max(0, min(255, int(cfg.get("watermark_opacity", 100))))
        positions = cfg.get("positions", {})
        text_value = str(cfg.get("watermark_text", "")).strip()
        logo_path = str(cfg.get("watermark_logo_path", "")).strip()

        if text_value:
            font = get_font(max(14, int(H*.028)), bold=True)
            measure = ImageDraw.Draw(Image.new("RGBA", (1,1)))
            text_box = measure.textbbox((0,0), text_value, font=font)
            width, height = text_box[2]-text_box[0], text_box[3]-text_box[1]
            if positions.get("wm_text"):
                x = int(W * positions["wm_text"][0] / 100)
                y = int(H * positions["wm_text"][1] / 100)
            else:
                margin_x, margin_y = int(W*.025), int(H*.025)
                x = margin_x if cfg.get("panel_side", "right") == "right" else W-width-margin_x
                reserve = int(H*.095) if logo_path and Path(logo_path).exists() else 0
                y = H-height-margin_y-reserve
            layer = Image.new("RGBA", (max(1, width+2), max(1, height+2)), (0,0,0,0))
            ImageDraw.Draw(layer, "RGBA").text((-text_box[0], -text_box[1]), text_value, font=font,
                                                fill=(255,255,255,opacity))
            hitboxes["wm_text"] = (x, y, x+width, y+height)
            layers.append(("wm_text", layer, (x, y)))

        if logo_path and Path(logo_path).exists():
            try:
                logo = _trim_transparent(Image.open(logo_path).convert("RGBA"))
                height = int(H*.08)
                width = max(1, int(logo.width * height / max(1, logo.height)))
                logo = logo.resize((width, height), Image.LANCZOS)
                if positions.get("wm_logo"):
                    x = int(W * positions["wm_logo"][0] / 100)
                    y = int(H * positions["wm_logo"][1] / 100)
                else:
                    margin_x = int(W*.025)
                    x = margin_x if cfg.get("panel_side", "right") == "right" else W-width-margin_x
                    y = H-height-int(H*.025)
                red, green, blue, alpha = logo.split()
                logo.putalpha(alpha.point(lambda value: int(value * opacity / 255)))
                hitboxes["wm_logo"] = (x, y, x+width, y+height)
                layers.append(("wm_logo", logo, (x, y)))
            except Exception as exc:
                audit("WATERMARK_LOGO_ERROR", str(exc))
        return layers

    # ── main render ───────────────────────────────────────────────────────

    @classmethod
    def render(cls, cfg: Dict, scale: int = 1) -> Tuple[Image.Image, Dict[str, Tuple[int, int, int, int]]]:
        hitboxes = {}
        scale = max(1, int(scale))
        bw, bh = CANVAS_SIZES.get(cfg.get("canvas_preset"), (1024,576))
        W, H   = bw*scale, bh*scale

        theme  = THEMES.get(cfg["theme_name"], THEMES["Dark Pro"])
        acc_h  = cfg.get("accent_override","").strip()
        accent: RGB = (clamp_rgb(hex_to_rgb(acc_h))
                       if acc_h and acc_h.startswith("#") else theme.accent)

        fam  = cfg.get("font_family","Arial")
        bp   = cfg.get("font_bold_path","")
        rp   = cfg.get("font_regular_path","")

        panel_pct  = max(20, min(70, cfg.get("panel_width_pct", 42)))
        panel_w    = int(W * panel_pct / 100)
        panel_side = cfg.get("panel_side", "right")
        pan_alpha  = max(0, min(255, cfg.get("panel_opacity", 220)))
        direction  = cfg.get("panel_gradient_dir","horizontal_fade")

        # ── base layer cache check ──────────────────────────────────────────────────
        x0 = W - panel_w if panel_side == "right" else 0
        photo_path = cfg.get("photo_path", "")
        try:
            photo_stat = Path(photo_path).stat() if photo_path else None
            photo_asset_key = (
                photo_path,
                photo_stat.st_mtime_ns if photo_stat else None,
                photo_stat.st_size if photo_stat else None,
            )
        except OSError:
            photo_asset_key = (photo_path, None, None)
        base_key = (
            photo_asset_key, W, H, cfg.get("photo_fit", "cover"),
            cfg.get("photo_treatment", "none"), tuple(theme.bg),
            float(cfg.get("photo_zoom", 100.0)),
            float(cfg.get("photo_focus_x", 50.0)),
            float(cfg.get("photo_focus_y", 50.0)),
            panel_w, panel_side, cfg.get("glassmorphism", True), cfg.get("drop_shadow", True),
            tuple(theme.panel_top), tuple(theme.panel_bottom), pan_alpha, direction, scale
        )
        if cls._base_key == base_key and cls._base_cache:
            img = cls._base_cache.copy()
        else:
            img = cls.get_background(cfg, W, H)
            # glassmorphism blur under panel
            if cfg.get("glassmorphism", True):
                box    = (x0, 0, x0+panel_w, H)
                blurred = img.crop(box).filter(ImageFilter.GaussianBlur(15*scale))
                img.paste(blurred, box)
            # drop shadow
            if cfg.get("drop_shadow", True):
                sw   = 30*scale
                shad = Image.new("RGBA", (panel_w+sw, H), (0,0,0,0))
                sd   = ImageDraw.Draw(shad)
                sd.rectangle([0,0,panel_w,H], fill=(0,0,0,160))
                shad = shad.filter(ImageFilter.GaussianBlur(14*scale))
                ov2  = Image.new("RGBA",(W,H),(0,0,0,0))
                sx   = x0-sw//2 if panel_side=="right" else 0
                ov2.paste(shad,(sx,0),shad)
                img  = Image.alpha_composite(img.convert("RGBA"), ov2).convert("RGB")
            # gradient panel
            panel_layer = cls._make_gradient_panel(
                panel_w, H, theme.panel_top, theme.panel_bottom,
                pan_alpha, direction, panel_side
            )
            canvas = Image.new("RGBA",(W,H),(0,0,0,0))
            canvas.paste(panel_layer,(x0,0),panel_layer)
            img = Image.alpha_composite(img.convert("RGBA"), canvas).convert("RGB")
            cls._base_key = base_key
            cls._base_cache = img.copy()

        element_layers: List[Tuple[str, Image.Image, Tuple[int, int]]] = []

        # ── PNG overlay (draggable player/subject) ───────────────────────
        ol = cfg.get("overlay_path","").strip()
        if ol and Path(ol).exists():
            try:
                ov  = _trim_transparent(Image.open(ol).convert("RGBA"))
                th  = int(H * cfg.get("overlay_scale",80) / 100)
                tw_ = int(ov.width * th / ov.height)
                if tw_ > 0 and th > 0:
                    ov   = ov.resize((tw_, th), Image.LANCZOS)
                    # use position override if available, else cfg
                    pos_ov = cfg.get("positions", {}).get("overlay")
                    if pos_ov:
                        px, py = int(W * pos_ov[0] / 100), int(H * pos_ov[1] / 100)
                    else:
                        px, py = int(W * cfg.get("overlay_x",5) / 100), int(H * cfg.get("overlay_y",5) / 100)

                    element_layers.append(("overlay", ov, (px, py)))
                    hitboxes["overlay"] = (px, py, px+tw_, py+th)
            except Exception as e:
                audit("OVERLAY_ERROR", str(e))

        draw = ImageDraw.Draw(img,"RGBA")

        def apply_pos(id: str, default_x: int, default_y: int, w: int, h: int) -> Tuple[int, int]:
            pos = cfg.get("positions", {}).get(id)
            if pos:
                rx, ry = int(W * pos[0] / 100), int(H * pos[1] / 100)
            else:
                rx, ry = default_x, default_y
            hitboxes[id] = (rx, ry, rx+w, ry+h)
            return rx, ry

        # ── text column ─────────────────────────────────────────────────
        mx = int(panel_w * cfg.get("margin_x", 9.0) / 100)
        tx = x0 + mx
        tw = max(20 * scale, panel_w - 2*mx)

        def tsize(key: str, frac: float, floor_: int) -> int:
            ov = cfg.get(key, 0)
            base_size = int(ov) if ov else max(floor_, int(bh * frac))
            return max(1, base_size * scale)

        title_sz = tsize("title_size", 0.082, 24)
        label_sz = tsize("label_size", 0.036, 13)
        value_sz = tsize("value_size", 0.072, 22)
        sub_sz   = max(12 * scale, int(label_sz * .8))

        tf   = get_font(title_sz, bold=True,  family=fam, custom_path=bp)
        lf   = get_font(label_sz, bold=False, family=fam, custom_path=rp)
        vf   = get_font(value_sz, bold=True,  family=fam, custom_path=bp)
        sf_  = get_font(sub_sz,   bold=False, family=fam, custom_path=rp)
        sl_f = get_font(max(10*scale, int(bh*.022)*scale),
                        bold=False, family=fam, custom_path=rp)

        my_px = int(H * cfg.get("margin_y", 5.0) / 100)
        cur_y = my_px

        # ── score block ─────────────────────────────────────────────────
        if cfg.get("show_score_block"):
            sb_id = "score"
            sf  = get_font(max(14, int(H*.032)), bold=True,  family=fam, custom_path=bp)
            scf = get_font(max(28, int(H*.065)), bold=True,  family=fam, custom_path=bp)
            inf = get_font(max(11, int(H*.022)), bold=False, family=fam, custom_path=rp)
            ta, tb  = cfg.get("team_a","A"), cfg.get("team_b","B")
            sc, mi  = cfg.get("score","0–0"), cfg.get("match_info","")
            if cfg.get("auto_fit_text", True):
                ta = _ellipsize(draw, ta, sf, max(1, tw // 2 - 8 * scale))
                tb = _ellipsize(draw, tb, sf, max(1, tw // 2 - 8 * scale))
                sc = _ellipsize(draw, sc, scf, tw)
                mi = _ellipsize(draw, mi, inf, tw)

            # calculate height and width of block
            bbta = draw.textbbox((0,0), ta, font=sf)
            bbtb = draw.textbbox((0,0), tb, font=sf)
            sbb = draw.textbbox((0,0), sc, font=scf)
            ibb = draw.textbbox((0,0), mi, font=inf) if mi else (0,0,0,0)

            team_h = max(bbta[3]-bbta[1], bbtb[3]-bbtb[1])
            sb_h = team_h + int(H*.01) + (sbb[3]-sbb[1]) + int(H*.006)
            if mi: sb_h += (ibb[3]-ibb[1]) + int(H*.01)
            sb_h += int(H*.01) + max(1,int(H*.003))

            sx, sy = apply_pos(sb_id, tx, cur_y, tw, sb_h)

            # draw
            score_layer = Image.new("RGBA", (max(1, tw), max(1, sb_h)), (0,0,0,0))
            score_draw = ImageDraw.Draw(score_layer, "RGBA")
            y = 0
            score_draw.text((-bbta[0], y-bbta[1]), ta, font=sf, fill=theme.title)
            score_draw.text((tw-(bbtb[2]-bbtb[0])-bbtb[0], y-bbtb[1]), tb, font=sf, fill=theme.title)
            y += team_h + int(H*.01)
            score_draw.text(((tw-(sbb[2]-sbb[0]))//2-sbb[0], y-sbb[1]), sc, font=scf, fill=accent)
            y += (sbb[3]-sbb[1]) + int(H*.006)
            if mi:
                score_draw.text(((tw-(ibb[2]-ibb[0]))//2-ibb[0], y-ibb[1]), mi, font=inf, fill=theme.label)
                y += (ibb[3]-ibb[1]) + int(H*.01)
            sep = y + int(H*.01)
            score_draw.line([(0,sep),(tw,sep)], fill=(*accent,120), width=max(1,int(H*.003)))
            element_layers.append((sb_id, score_layer, (sx, sy)))

            # only advance cur_y if not customized
            if sb_id not in cfg.get("positions", {}):
                cur_y += sb_h + int(H*.025)

        # ── subtitle ────────────────────────────────────────────────────
        sub = cfg.get("subtitle","").strip()
        if sub:
            sub = sub.upper()
            if cfg.get("auto_fit_text", True):
                sub = _ellipsize(draw, sub, sf_, tw)
            bb = draw.textbbox((0,0), sub, font=sf_)
            sub_w, sub_h = bb[2]-bb[0], bb[3]-bb[1]
            sx, sy = apply_pos("subtitle", tx, cur_y, sub_w, sub_h)
            subtitle_layer = Image.new("RGBA", (max(1, sub_w+2*scale), max(1, sub_h+2*scale)), (0,0,0,0))
            ImageDraw.Draw(subtitle_layer, "RGBA").text((-bb[0],-bb[1]), sub, font=sf_, fill=accent)
            element_layers.append(("subtitle", subtitle_layer, (sx, sy)))
            if "subtitle" not in cfg.get("positions", {}):
                cur_y += sub_h + int(H * cfg.get("spacing_items", 1.0) / 100)

        # ── title ───────────────────────────────────────────────────────
        raw_title = str(cfg.get("title", "Match\nStatistics"))
        auto_fit = cfg.get("auto_fit_text", True)
        lines = _wrap_text(draw, raw_title, tf, tw) if auto_fit else raw_title.replace("\\n","\n").split("\n")
        max_title_height = int(H * (0.34 if len(cfg.get("stat_rows", [])) <= 4 else 0.26))
        min_title_size = max(10 * scale, int(bh * .022) * scale)
        while auto_fit and title_sz > min_title_size:
            line_heights = [_text_dimensions(draw, line, tf)[1] for line in lines]
            title_h_probe = sum(line_heights) + max(0, len(lines) - 1) * int(title_sz * .22)
            widest = max((_text_dimensions(draw, line, tf)[0] for line in lines), default=0)
            if len(lines) <= 4 and title_h_probe <= max_title_height and widest <= tw:
                break
            title_sz = max(min_title_size, title_sz - scale)
            tf = get_font(title_sz, bold=True, family=fam, custom_path=bp)
            lines = _wrap_text(draw, raw_title, tf, tw)
        if auto_fit and len(lines) > 4:
            lines = lines[:4]
            lines[-1] = _ellipsize(draw, lines[-1], tf, tw)
        if auto_fit:
            lines = [_ellipsize(draw, line, tf, tw) for line in lines]
        title_w, title_h = 0, 0
        for index, line in enumerate(lines):
            bb = draw.textbbox((0,0), line, font=tf)
            title_w = max(title_w, bb[2]-bb[0])
            title_h += bb[3]-bb[1]
            if index < len(lines) - 1:
                title_h += int(title_sz*.22)

        sx, sy = apply_pos("title", tx, cur_y, title_w, title_h)
        title_layer = Image.new("RGBA", (max(1, title_w+2*scale), max(1, title_h+2*scale)), (0,0,0,0))
        title_draw = ImageDraw.Draw(title_layer, "RGBA")
        line_y = 0
        for index, line in enumerate(lines):
            bb = draw.textbbox((0,0), line, font=tf)
            title_draw.text((-bb[0], line_y-bb[1]), line, font=tf, fill=theme.title)
            line_y += bb[3]-bb[1]
            if index < len(lines) - 1:
                line_y += int(title_sz*.22)
        element_layers.append(("title", title_layer, (sx, sy)))

        if "title" not in cfg.get("positions", {}):
            cur_y += title_h + int(H * cfg.get("spacing_title", 3.0) / 100)

        # ── stat rows ───────────────────────────────────────────────────
        rows  = cfg.get("stat_rows",[])
        n     = max(1, len(rows))
        avail = max(1, H - cur_y - int(H*.04))
        bar_h = max(4*scale, int(H*.013))
        sip   = int(H * cfg.get("spacing_items", 1.0) / 100)
        requested_row_gap = int(H * cfg.get("spacing_rows", 3.0) / 100)
        row_gap = min(
            requested_row_gap,
            int(avail * .25 / max(1, n - 1)) if n > 1 else 0,
        )
        slot = max(1.0, (avail - row_gap * max(0, n - 1)) / n)

        for i, row in enumerate(rows):
            lbl = row.get("label","")
            val = row.get("value","0")
            sub2= row.get("sublabel","")
            pct = auto_percent(val, row.get("max","100"))

            row_lf, row_vf, row_slf = lf, vf, sl_f
            local_sip = min(sip, max(scale, int(slot * .08))) if auto_fit else sip
            if auto_fit:
                label_px, value_px = label_sz, value_sz
                sub_px = max(6 * scale, int(label_px * .62))
                for _ in range(12):
                    row_lf = get_font(max(6 * scale, label_px), bold=False, family=fam, custom_path=rp)
                    row_vf = get_font(max(8 * scale, value_px), bold=True, family=fam, custom_path=bp)
                    row_slf = get_font(max(6 * scale, sub_px), bold=False, family=fam, custom_path=rp)
                    lh = _text_dimensions(draw, lbl, row_lf)[1]
                    vh = _text_dimensions(draw, val, row_vf)[1]
                    sh = _text_dimensions(draw, sub2, row_slf)[1] if sub2 else 0
                    gaps = local_sip * (3 if sub2 else 2)
                    needed = lh + vh + sh + gaps + bar_h
                    if needed <= slot or (label_px <= 6 * scale and value_px <= 8 * scale):
                        break
                    factor = max(.65, min(.95, (slot - bar_h - gaps) / max(1, lh + vh + sh)))
                    label_px = max(6 * scale, int(label_px * factor))
                    value_px = max(8 * scale, int(value_px * factor))
                    sub_px = max(6 * scale, int(sub_px * factor))
                lbl = _ellipsize(draw, lbl, row_lf, tw)
                val = _ellipsize(draw, val, row_vf, tw)
                sub2 = _ellipsize(draw, sub2, row_slf, tw) if sub2 else ""

            bb = draw.textbbox((0,0), lbl or " ", font=row_lf)
            bb2 = draw.textbbox((0,0), sub2 or " ", font=row_slf)
            vbb = draw.textbbox((0,0), val or " ", font=row_vf)
            row_h = min(slot, (bb[3]-bb[1]) + (vbb[3]-vbb[1]) +
                        ((bb2[3]-bb2[1]) if sub2 else 0) +
                        local_sip * (3 if sub2 else 2) + bar_h)

            rx, ry = apply_pos(f"row_{i}", tx, int(cur_y), tw, int(row_h))
            sy = 0

            row_layer = Image.new("RGBA", (max(1, tw), max(1, int(row_h)+2*scale)), (0,0,0,0))
            row_draw = ImageDraw.Draw(row_layer, "RGBA")

            row_draw.text((-bb[0],sy-bb[1]), lbl, font=row_lf, fill=theme.label)
            sy += (bb[3]-bb[1]) + local_sip
            if sub2:
                row_draw.text((-bb2[0],sy-bb2[1]), sub2, font=row_slf, fill=(*theme.label[:3],150))
                sy += (bb2[3]-bb2[1]) + local_sip

            row_draw.text((-vbb[0],sy-vbb[1]), val, font=row_vf, fill=accent)
            sy += (vbb[3]-vbb[1]) + local_sip

            by0, by1 = sy, sy+bar_h
            row_draw.rounded_rectangle([0,by0,tw,by1], radius=bar_h//2, fill=(*theme.bar_track,200))
            fw = int(tw*pct/100)
            if fw >= bar_h:
                row_draw.rounded_rectangle([0,by0,fw,by1], radius=bar_h//2, fill=accent)
            element_layers.append((f"row_{i}", row_layer, (rx, ry)))

            if f"row_{i}" not in cfg.get("positions", {}):
                cur_y += slot + row_gap

        # ── watermark ───────────────────────────────────────────────────
        element_layers.extend(cls._watermark_layers(cfg, hitboxes, W, H))
        order = normalised_layer_order(cfg)
        rank = {layer_id: index for index, layer_id in enumerate(order)}
        fallback = len(order)
        for layer_id, layer, origin in sorted(
            element_layers, key=lambda item: rank.get(item[0], fallback)
        ):
            if layer_state(cfg, layer_id)["visible"]:
                rgba = img.convert("RGBA")
                rgba.alpha_composite(layer, dest=origin)
                img = rgba.convert("RGB")
            else:
                hitboxes.pop(layer_id, None)
        return img, hitboxes


class UnifiedRenderer:
    """Dispatch the active layout while keeping one project and export contract."""

    @staticmethod
    def render(cfg: Dict, scale: int = 1) -> Tuple[Image.Image, Dict[str, Tuple[int, int, int, int]]]:
        template = cfg.get("template_name", "Single Player Pro")
        if template == "Single Player Pro":
            return Renderer.render(cfg, scale=scale)

        pack = _load_template_pack()
        template_cfg = copy.deepcopy(
            cfg.get("template_configs", {}).get(template, template_defaults().get(template, {}))
        )
        template_cfg["_render_scale"] = max(1, int(scale))
        theme = THEMES.get(cfg.get("theme_name"), THEMES["Dark Pro"])
        accent = cfg.get("accent_override", "").strip()
        template_cfg["accent_color"] = list(
            hex_to_rgb(accent) if accent.startswith("#") else theme.accent
        )
        renderers = {
            "Head-to-Head Insights": pack.render_t2,
            "VS Tug-of-War": pack.render_t3,
            "Performance Spotlight": pack.render_t4,
        }
        image = renderers[template](template_cfg)
        width, height = image.size
        if not layer_state(cfg, "template_artwork")["visible"]:
            image = Image.new("RGB", (width, height), theme.bg)
            return image, {}
        return image, {"template_artwork": (0, 0, width, height)}


# ═══════════════════════════════════════════════════════════════════════════
# STAT ROW WIDGET  (CustomTkinter)
# ═══════════════════════════════════════════════════════════════════════════

if GUI_AVAILABLE:
    class StatRowWidget(ctk.CTkFrame):
        def __init__(self, parent, index: int, data: Optional[Dict],
                     on_change, on_delete, on_move):
            super().__init__(parent, fg_color="transparent")
            data = data or {"label":"New Stat","value":"0 %","max":"100","sublabel":""}
            self.on_change, self.on_delete, self.on_move = on_change, on_delete, on_move

            self.lv = ctk.StringVar(value=data.get("label",""))
            self.vv = ctk.StringVar(value=data.get("value",""))
            self.mv = ctk.StringVar(value=str(data.get("max","100")))
            self.sv = ctk.StringVar(value=data.get("sublabel",""))

            # row 0: label / value / max
            r0 = ctk.CTkFrame(self, fg_color="transparent"); r0.pack(fill="x")
            ctk.CTkLabel(r0,text="Lbl:").pack(side="left",padx=(0,2))
            ctk.CTkEntry(r0,textvariable=self.lv,width=140).pack(side="left",padx=2)
            ctk.CTkLabel(r0,text="Val:").pack(side="left",padx=(8,2))
            ctk.CTkEntry(r0,textvariable=self.vv,width=70).pack(side="left",padx=2)
            ctk.CTkLabel(r0,text="Max:").pack(side="left",padx=(8,2))
            ctk.CTkEntry(r0,textvariable=self.mv,width=50).pack(side="left",padx=2)
            bkw = {"width":28,"height":26,"fg_color":"#444","hover_color":"#666"}
            ctk.CTkButton(r0,text="↑",command=lambda:self.on_move(self,-1),**bkw).pack(side="right",padx=1)
            ctk.CTkButton(r0,text="↓",command=lambda:self.on_move(self,+1),**bkw).pack(side="right",padx=1)
            ctk.CTkButton(r0,text="⎘",command=lambda:self.on_move(self,0,True),**bkw).pack(side="right",padx=1)
            ctk.CTkButton(r0,text="✕",width=28,height=26,fg_color="#A33",hover_color="#D44",
                          command=lambda:self.on_delete(self)).pack(side="right",padx=(4,1))

            # row 1: sub-label
            r1 = ctk.CTkFrame(self, fg_color="transparent"); r1.pack(fill="x",pady=(2,0))
            ctk.CTkLabel(r1,text="Sub-label:").pack(side="left",padx=(0,4))
            ctk.CTkEntry(r1,textvariable=self.sv,width=280).pack(side="left")

            for v in (self.lv,self.vv,self.mv,self.sv):
                v.trace_add("write", lambda *_: self.on_change())

        def get_data(self) -> Dict:
            return {"label":self.lv.get(),"value":self.vv.get(),
                    "max":self.mv.get(),"sublabel":self.sv.get()}

        def set_index(self, i: int): pass  # visual index not shown; kept for API compat


    class TemplateContentDialog(tk.Toplevel):
        """Compact, keyboard-friendly editor for the three comparison layouts."""

        def __init__(self, parent, template_name: str, data: Dict[str, Any], on_apply):
            super().__init__(parent)
            self.title(f"Edit {template_name}")
            self.geometry("820x760")
            self.minsize(720, 620)
            self.transient(parent)
            self.template_name = template_name
            self.data = copy.deepcopy(data)
            self.on_apply = on_apply
            self.vars: Dict[str, tk.StringVar] = {}
            self.player_vars: List[Dict[str, tk.StringVar]] = []
            self.player_stat_boxes: List[tk.Text] = []

            outer = ttk.Frame(self, padding=12)
            outer.pack(fill="both", expand=True)
            if template_name == "Performance Spotlight":
                self._build_spotlight(outer)
            else:
                self._build_comparison(outer)

            buttons = ttk.Frame(outer)
            buttons.pack(fill="x", pady=(10, 0))
            ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=4)
            ttk.Button(buttons, text="Apply", command=self._apply).pack(side="right", padx=4)
            self.bind("<Control-Return>", lambda _: self._apply())
            self.grab_set()

        def _entry(self, parent, label: str, key: str, row: int, column: int = 0,
                   width: int = 24, source: Optional[Dict[str, Any]] = None):
            source = self.data if source is None else source
            ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=4, pady=3)
            var = tk.StringVar(value=str(source.get(key, "")))
            ttk.Entry(parent, textvariable=var, width=width).grid(
                row=row, column=column+1, sticky="ew", padx=4, pady=3
            )
            self.vars[key] = var
            return var

        def _photo_fields(self, parent, prefix: str, source: Dict[str, Any], row: int,
                          variable_store: Dict[str, tk.StringVar]):
            path_key = prefix if prefix == "photo" else prefix
            path_var = tk.StringVar(value=str(source.get(path_key, "")))
            variable_store[path_key] = path_var
            ttk.Label(parent, text="Photo").grid(row=row, column=0, sticky="w", padx=4, pady=3)
            ttk.Entry(parent, textvariable=path_var).grid(
                row=row, column=1, columnspan=3, sticky="ew", padx=4, pady=3
            )

            def browse():
                path = filedialog.askopenfilename(
                    parent=self,
                    filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.avif")],
                )
                if path:
                    path_var.set(path)

            ttk.Button(parent, text="Browse", command=browse).grid(row=row, column=4, padx=4)
            for offset, (label, suffix, default) in enumerate([
                ("Zoom %", "zoom", 100),
                ("Focus X", "focus_x", 50),
                ("Focus Y", "focus_y", 50),
            ]):
                key = f"{prefix}_{suffix}"
                var = tk.StringVar(value=str(source.get(key, default)))
                variable_store[key] = var
                ttk.Label(parent, text=label).grid(row=row+1, column=offset*2, sticky="e", padx=3)
                ttk.Spinbox(parent, from_=0 if suffix != "zoom" else 100,
                            to=300 if suffix == "zoom" else 100,
                            textvariable=var, width=7).grid(row=row+1, column=offset*2+1, sticky="w")

        @staticmethod
        def _rows_to_text(rows: List[Dict[str, Any]], include_unit: bool) -> str:
            header = ["Metric", "Player A", "Player B", "Max"]
            if include_unit:
                header.append("Unit")
            output = ["\t".join(header)]
            for row in rows:
                values = [
                    str(row.get("label", "")), str(row.get("value_a", "")),
                    str(row.get("value_b", "")), str(row.get("max", "100")),
                ]
                if include_unit:
                    values.append(str(row.get("unit", "")))
                output.append("\t".join(values))
            return "\n".join(output)

        @staticmethod
        def _stats_to_text(stats: List[Dict[str, Any]]) -> str:
            output = ["Metric\tValue\tUnit\tMax"]
            for stat in stats:
                output.append("\t".join([
                    str(stat.get("label", "")), str(stat.get("value", "")),
                    str(stat.get("unit", "")), str(stat.get("max", "100")),
                ]))
            return "\n".join(output)

        def _build_comparison(self, outer):
            common = ttk.LabelFrame(outer, text="Match")
            common.pack(fill="x")
            common.columnconfigure(1, weight=1)
            common.columnconfigure(3, weight=1)
            if self.template_name == "Head-to-Head Insights":
                self._entry(common, "Header", "header_text", 0, width=30)
                self._entry(common, "Center mark", "divider_text", 0, column=2, width=12)
            else:
                self._entry(common, "Center mark", "vs_text", 0, width=12)
                self._entry(common, "Score", "score", 0, column=2, width=24)
                self._entry(common, "Sponsor", "sponsor_text", 1, width=30)
                self._entry(common, "Logo path", "logo_path", 1, column=2, width=24)

            players = ttk.Frame(outer)
            players.pack(fill="x", pady=8)
            for index, suffix in enumerate(("a", "b")):
                frame = ttk.LabelFrame(players, text=f"Player {'A' if suffix == 'a' else 'B'}")
                frame.pack(side="left", fill="both", expand=True, padx=(0,4) if index == 0 else (4,0))
                frame.columnconfigure(1, weight=1)
                self._entry(frame, "First name", f"name_{suffix}_first", 0, source=self.data)
                self._entry(frame, "Last name", f"name_{suffix}_last", 1, source=self.data)
                identity_key = f"abbr_{suffix}" if self.template_name == "Head-to-Head Insights" else f"team_{suffix}"
                self._entry(frame, "Country" if identity_key.startswith("abbr") else "Team",
                            identity_key, 2, source=self.data)
                local_vars = self.vars
                self._photo_fields(frame, f"photo_{suffix}", self.data, 3, local_vars)

            if self.template_name == "Head-to-Head Insights":
                styles = ttk.LabelFrame(outer, text="Playing styles")
                styles.pack(fill="x", pady=(0,8))
                styles.columnconfigure(1, weight=1)
                styles.columnconfigure(3, weight=1)
                for column, suffix in ((0, "a"), (2, "b")):
                    key = f"tags_{suffix}"
                    value = ", ".join(self.data.get(key, []))
                    ttk.Label(styles, text=f"Player {suffix.upper()}").grid(row=0, column=column, padx=4)
                    var = tk.StringVar(value=value)
                    self.vars[key] = var
                    ttk.Entry(styles, textvariable=var).grid(
                        row=0, column=column+1, sticky="ew", padx=4, pady=4
                    )

            metrics = ttk.LabelFrame(outer, text="Metrics (paste from Excel; one row per metric)")
            metrics.pack(fill="both", expand=True)
            self.rows_box = tk.Text(metrics, wrap="none", height=12, font=("Consolas", 10))
            self.rows_box.pack(fill="both", expand=True, padx=6, pady=6)
            self.rows_box.insert("1.0", self._rows_to_text(
                self.data.get("rows", []), self.template_name == "VS Tug-of-War"
            ))

        def _build_spotlight(self, outer):
            heading = ttk.LabelFrame(outer, text="Board")
            heading.pack(fill="x")
            heading.columnconfigure(1, weight=1)
            self._entry(heading, "Banner", "banner_text", 0, width=34)
            self._entry(heading, "Sponsor", "sponsor_text", 1, width=34)

            notebook = ttk.Notebook(outer)
            notebook.pack(fill="both", expand=True, pady=8)
            players = copy.deepcopy(self.data.get("players", []))
            while len(players) < 3:
                players.append({"team":"", "first":"Player", "last":"", "photo":"", "stats":[], "result":""})
            for index, player in enumerate(players[:3]):
                tab = ttk.Frame(notebook, padding=8)
                notebook.add(tab, text=f"Player {index+1}")
                tab.columnconfigure(1, weight=1)
                local: Dict[str, tk.StringVar] = {}
                for row, (label, key) in enumerate([
                    ("Team", "team"), ("First name", "first"),
                    ("Last name", "last"), ("Result", "result"),
                ]):
                    ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
                    var = tk.StringVar(value=str(player.get(key, "")))
                    local[key] = var
                    ttk.Entry(tab, textvariable=var).grid(row=row, column=1, columnspan=3,
                                                          sticky="ew", padx=4, pady=3)
                self._photo_fields(tab, "photo", player, 4, local)
                ttk.Label(tab, text="Stats (Metric, Value, Unit, Max)").grid(
                    row=6, column=0, columnspan=4, sticky="w", padx=4, pady=(8,2)
                )
                box = tk.Text(tab, wrap="none", height=11, font=("Consolas", 10))
                box.grid(row=7, column=0, columnspan=5, sticky="nsew", padx=4, pady=4)
                tab.rowconfigure(7, weight=1)
                box.insert("1.0", self._stats_to_text(player.get("stats", [])))
                self.player_vars.append(local)
                self.player_stat_boxes.append(box)

        @staticmethod
        def _number(value: str, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _apply(self):
            for key, var in self.vars.items():
                if key.startswith("tags_"):
                    self.data[key] = [part.strip() for part in var.get().split(",") if part.strip()]
                elif key.endswith(("_zoom", "_focus_x", "_focus_y")):
                    self.data[key] = self._number(var.get(), 100 if key.endswith("_zoom") else 50)
                else:
                    self.data[key] = var.get()

            if self.template_name == "Performance Spotlight":
                players = []
                for variables, box in zip(self.player_vars, self.player_stat_boxes):
                    player = {key: var.get() for key, var in variables.items()}
                    for key in ("photo_zoom", "photo_focus_x", "photo_focus_y"):
                        player[key] = self._number(
                            variables[key].get(), 100 if key == "photo_zoom" else 50
                        )
                    player["stats"] = parse_player_stats(box.get("1.0", "end-1c"))
                    players.append(player)
                self.data["players"] = players
            else:
                self.data["rows"] = parse_comparison_rows(
                    self.rows_box.get("1.0", "end-1c"),
                    include_unit=self.template_name == "VS Tug-of-War",
                )
            self.on_apply(self.data)
            self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

if GUI_AVAILABLE:
    class ScoreboardApp(TkinterDnD.Tk):
        def __init__(self):
            super().__init__()
            self.title("Match Stats Studio - Production v5.0")
            self.geometry("1560x960")
            self.minsize(1200,720)

            # DnD
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_file_drop)

            self.cfg   = load_config()
            self._suspend_changes = True
            self._undo = UndoStack()

            self._stat_widgets: List[StatRowWidget] = []
            self._tk_img       = None
            self._last_render  = None
            self._hitboxes     = {}
            self._drag         = {"x":0,"y":0,"active":False,"element":None}
            self._selected_element = None
            self._snap_guides: List[Tuple[str, float]] = []
            self._preview_scale = 1.0
            self._render_q     = queue.Queue()
            self._redraw_timer = None
            self._history_timer = None
            self._save_timer = None
            self._cfg_path: Optional[str] = None
            self._export_presets = load_export_presets()

            self._build_ui()
            self._apply_cfg_to_ui()
            self._rebuild_row_widgets()
            self._refresh_layer_controls()
            self._suspend_changes = False
            self.cfg = self._collect_cfg()
            self._undo.push(self.cfg)
            self._start_render_worker()
            self.schedule_redraw()

            self.bind("<Control-z>", lambda _: self._undo_action())
            self.bind("<Control-y>", lambda _: self._redo_action())
            self.bind("<Control-e>", lambda _: self.export_png())
            self.bind("<Control-Shift-E>", lambda _: self.batch_export())
            self.bind("<Control-Shift-S>", lambda _: self._save_json())
            for index, template in enumerate(TEMPLATE_NAMES, start=1):
                self.bind(
                    f"<Control-Key-{index}>",
                    lambda _, value=template: self._shortcut_template(value),
                )
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            audit("APP_START","")

        # ── DnD ─────────────────────────────────────────────────────────

        def _on_file_drop(self, event):
            paths = self.tk.splitlist(event.data)
            if not paths:
                return
            p = paths[0]
            ext = Path(p).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif"):
                self._status("Unsupported image type")
                return
            template = self.cfg.get("template_name", "Single Player Pro")
            if template != "Single Player Pro":
                data = self.cfg.setdefault("template_configs", {}).setdefault(template, {})
                if template == "Performance Spotlight":
                    players = data.setdefault("players", [])
                    while len(players) < 3:
                        players.append({"team":"", "first":"Player", "last":"", "photo":"", "stats":[]})
                    target = next((player for player in players[:3] if not player.get("photo")), players[0])
                    target["photo"] = p
                else:
                    target_key = "photo_a" if not data.get("photo_a") else "photo_b"
                    data[target_key] = p
                self._status(f"Photo added to {template}")
                self._on_change()
                audit("DND_TEMPLATE_PHOTO", p)
                return
            transparent = False
            try:
                with Image.open(p) as dropped:
                    if "A" in dropped.getbands():
                        transparent = dropped.getchannel("A").getextrema()[0] < 255
                    transparent = transparent or "transparency" in dropped.info
            except Exception:
                pass
            if transparent:
                self.cfg["overlay_path"] = p
                self._status(f"Overlay loaded: {Path(p).name}")
            else:
                self.cfg["photo_path"] = p
                self._img_lbl.configure(text=Path(p).name)
                self._status(f"Background loaded: {Path(p).name}")
            self._on_change()
            audit("DND_DROP", p)

        # ── UI construction ──────────────────────────────────────────────

        def _build_ui(self):
            self.main = ctk.CTkFrame(self, fg_color="transparent")
            self.main.pack(fill="both", expand=True)

            # ── Left scrollable controls ─────────────────────────────────
            self.ctrl_panel = ctk.CTkScrollableFrame(
                self.main, width=560, corner_radius=0)
            self.ctrl_panel.pack(side="left", fill="y")

            # ── Right preview ────────────────────────────────────────────
            self.preview_panel = ctk.CTkFrame(
                self.main, fg_color="#1a1a1a", corner_radius=0)
            self.preview_panel.pack(side="right", fill="both", expand=True)
            ctk.CTkLabel(
                self.preview_panel,
                text="Live Preview  ·  Double click element to reset position",
                font=("Arial",13,"bold"), text_color="#666"
            ).pack(pady=(14,0))
            self.preview_canvas = tk.Canvas(
                self.preview_panel, bg="#1a1a1a", highlightthickness=0)
            self.preview_canvas.pack(padx=16, pady=12, fill="both", expand=True)
            self.preview_canvas.bind("<ButtonPress-1>",   self._drag_start)
            self.preview_canvas.bind("<B1-Motion>",       self._drag_move)
            self.preview_canvas.bind("<ButtonRelease-1>", self._drag_end)
            self.preview_canvas.bind("<Double-1>",        self._drag_reset)
            for sequence, delta in [
                ("<Left>", (-1,0)), ("<Right>", (1,0)),
                ("<Up>", (0,-1)), ("<Down>", (0,1)),
            ]:
                self.preview_canvas.bind(
                    sequence, lambda event, d=delta: self._nudge_selected(event, *d)
                )

            self._build_toolbar()
            self._build_preset_section()
            self._build_file_section()
            self._build_image_section()
            self._build_content_section()
            self._build_score_section()
            self._build_watermark_section()
            self._build_theme_section()
            self._build_layout_section()
            self._build_layer_section()
            self._build_spacing_section()
            self._build_font_section()
            self._build_rows_section()
            self._build_export_section()

            # status bar
            self._status_var = ctk.StringVar(value="Ready")
            ctk.CTkLabel(self, textvariable=self._status_var, anchor="w",
                         fg_color="#222", corner_radius=0, height=24
                         ).pack(side="bottom", fill="x", padx=0)

        def _sec(self, title: str) -> ctk.CTkFrame:
            wrap = ctk.CTkFrame(self.ctrl_panel, fg_color="#2b2b2b")
            wrap.pack(fill="x", padx=10, pady=6)
            ctk.CTkLabel(wrap, text=title, font=("Arial",13,"bold")
                         ).pack(anchor="w", padx=10, pady=(8,3))
            inner = ctk.CTkFrame(wrap, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=(0,8))
            return inner

        # ── sections ────────────────────────────────────────────────────

        def _build_toolbar(self):
            tb = ctk.CTkFrame(self.ctrl_panel, fg_color="#1e1e1e")
            tb.pack(fill="x", padx=10, pady=4)
            for txt, cmd in [
                ("↩ Undo",      self._undo_action),
                ("↪ Redo",      self._redo_action),
                ("💾 Export",   self.export_png),
                ("📦 Batch",    self.batch_export),
                ("📋 Audit Log",self._show_audit),
            ]:
                ctk.CTkButton(tb, text=txt, command=cmd, width=90,
                              height=28).pack(side="left", padx=3, pady=4)

        def _build_preset_section(self):
            sec = self._sec("Quick Presets")
            template_row = ctk.CTkFrame(sec, fg_color="transparent")
            template_row.pack(fill="x", pady=(0,6))
            ctk.CTkLabel(template_row, text="Template:").pack(side="left")
            self._template_var = ctk.StringVar(
                value=self.cfg.get("template_name", "Single Player Pro")
            )
            ctk.CTkComboBox(
                template_row, variable=self._template_var, values=TEMPLATE_NAMES,
                width=240, command=self._on_template_change,
            ).pack(side="left", padx=6)
            self._edit_template_btn = ctk.CTkButton(
                template_row, text="Edit Content", command=self._edit_template_content,
                width=110,
            )
            self._edit_template_btn.pack(side="left", padx=4)
            self._template_hint_var = ctk.StringVar(value="")
            ctk.CTkLabel(
                sec, textvariable=self._template_hint_var, anchor="w",
                text_color="#8fa1b3", font=("Arial", 11),
            ).pack(fill="x", pady=(0,6))
            self._set_template_hint(self._template_var.get())
            row = ctk.CTkFrame(sec, fg_color="transparent"); row.pack(fill="x")
            ctk.CTkLabel(row, text="Theme preset:").pack(side="left")
            self._quick_theme_var = ctk.StringVar(value=self.cfg.get("theme_name", "Dark Pro"))
            ctk.CTkComboBox(row, variable=self._quick_theme_var,
                            values=list(THEMES.keys()), width=180,
                            command=lambda v: self._apply_theme_preset(v)
                            ).pack(side="left", padx=6)
            ctk.CTkLabel(row, text="Sport:").pack(side="left", padx=(12,4))
            self._quick_sport_var = ctk.StringVar(value="Tennis")
            ctk.CTkComboBox(row, variable=self._quick_sport_var,
                            values=list(STAT_PRESETS.keys()), width=130,
                            command=lambda v: self._apply_stat_preset(v)
                            ).pack(side="left")
            row2 = ctk.CTkFrame(sec, fg_color="transparent"); row2.pack(fill="x", pady=(6,0))
            ctk.CTkLabel(row2, text="Layout:").pack(side="left")
            self._layout_preset_var = ctk.StringVar(value="Broadcast Stats")
            ctk.CTkComboBox(row2, variable=self._layout_preset_var,
                            values=list(LAYOUT_PRESETS.keys()), width=220,
                            command=self._apply_layout_preset).pack(side="left", padx=6)

        def _build_file_section(self):
            sec = self._sec("Project File")
            for txt, cmd in [("Load JSON", self._load_json),
                              ("Save JSON", self._save_json),
                              ("Reset",     self._reset)]:
                fg = "#A33" if txt == "Reset" else ctk.ThemeManager.theme["CTkButton"]["fg_color"]
                hv = "#D44" if txt == "Reset" else None
                kw = {"fg_color":fg,"hover_color":hv} if txt == "Reset" else {}
                ctk.CTkButton(sec, text=txt, width=100, command=cmd, **kw
                              ).pack(side="left", padx=4)

        def _build_image_section(self):
            sec = self._sec("Images  (Drag & Drop or Browse)")
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=2)
            ctk.CTkButton(r0, text="Browse BG", command=self._browse_bg, width=110
                          ).pack(side="left")
            self._img_lbl = ctk.CTkLabel(r0, text="No background", text_color="#777")
            self._img_lbl.pack(side="left", padx=8)

            r1 = ctk.CTkFrame(sec, fg_color="transparent"); r1.pack(fill="x", pady=2)
            ctk.CTkLabel(r1, text="BG Fit:").pack(side="left")
            self._fit_var = ctk.StringVar(value=self.cfg.get("photo_fit","cover"))
            ctk.CTkComboBox(r1, variable=self._fit_var,
                            values=["cover","contain","stretch"], width=100,
                            command=lambda _: self._on_change()
                            ).pack(side="left", padx=6)
            ctk.CTkLabel(r1, text="Treatment:").pack(side="left", padx=(10,4))
            self._treat_var = ctk.StringVar(value=self.cfg.get("photo_treatment","none"))
            ctk.CTkComboBox(r1, variable=self._treat_var,
                            values=["none","blur_edges","vignette","grayscale","sepia"],
                            width=110, command=lambda _: self._on_change()
                            ).pack(side="left")

            for label, attr, key, lo, hi in [
                ("Zoom", "_photo_zoom_var", "photo_zoom", 100, 300),
                ("Focus X", "_photo_fx_var", "photo_focus_x", 0, 100),
                ("Focus Y", "_photo_fy_var", "photo_focus_y", 0, 100),
            ]:
                frame = ctk.CTkFrame(sec, fg_color="transparent"); frame.pack(fill="x", pady=2)
                ctk.CTkLabel(frame, text=label + ":", width=64, anchor="w").pack(side="left")
                value = tk.DoubleVar(value=self.cfg.get(key, DEFAULT_CFG[key]))
                setattr(self, attr, value)
                value_label = ctk.CTkLabel(frame, text=f"{value.get():.0f}%", width=48)
                setattr(self, attr + "_label", value_label)
                ctk.CTkSlider(
                    frame, from_=lo, to=hi, variable=value,
                    command=lambda v, lbl=value_label: self._image_slider_changed(lbl, v),
                ).pack(side="left", fill="x", expand=True, padx=6)
                value_label.pack(side="left")

            r2 = ctk.CTkFrame(sec, fg_color="transparent"); r2.pack(fill="x", pady=4)
            ctk.CTkButton(r2, text="Reset Photo Frame", command=self._reset_photo_frame,
                          width=140).pack(side="left")
            ctk.CTkButton(r2, text="Browse Overlay",
                          command=self._browse_overlay, width=160).pack(side="left")
            ctk.CTkButton(r2, text="Clear Overlay",
                          command=self._clear_overlay, width=110,
                          fg_color="#A33", hover_color="#D44").pack(side="left", padx=6)

            r3 = ctk.CTkFrame(sec, fg_color="transparent"); r3.pack(fill="x", pady=2)
            ctk.CTkLabel(r3, text="Overlay scale %:").pack(side="left")
            self._ov_scale = tk.DoubleVar(value=self.cfg.get("overlay_scale",80))
            ctk.CTkSlider(r3, from_=5, to=200, variable=self._ov_scale,
                          command=lambda _: self._on_change()
                          ).pack(side="left", fill="x", expand=True, padx=8)

        def _image_slider_changed(self, label, value):
            label.configure(text=f"{float(value):.0f}%")
            self._on_change()

        def _reset_photo_frame(self):
            self._photo_zoom_var.set(100.0)
            self._photo_fx_var.set(50.0)
            self._photo_fy_var.set(50.0)
            for attr in ("_photo_zoom_var", "_photo_fx_var", "_photo_fy_var"):
                getattr(self, attr + "_label").configure(text=f"{getattr(self, attr).get():.0f}%")
            self._on_change()

        def _build_content_section(self):
            sec = self._sec("Titles & Headlines")
            ctk.CTkLabel(sec, text="Subtitle (shown above title):").pack(anchor="w")
            self._sub_var = ctk.StringVar(value=self.cfg.get("subtitle",""))
            ctk.CTkEntry(sec, textvariable=self._sub_var).pack(fill="x", pady=4)
            self._sub_var.trace_add("write", lambda *_: self._on_change())

            ctk.CTkLabel(sec, text="Main Title (newlines supported):").pack(anchor="w")
            self._title_box = ctk.CTkTextbox(sec, height=60)
            self._title_box.pack(fill="x", pady=4)
            self._title_box.insert("1.0", self.cfg.get("title","Match\nStatistics"))
            self._title_box.bind("<KeyRelease>", lambda _: self._on_change())

        def _build_score_section(self):
            sec = self._sec("Score Block (optional)")
            self._show_score_var = ctk.BooleanVar(value=self.cfg.get("show_score_block",False))
            ctk.CTkCheckBox(sec, text="Show score block",
                            variable=self._show_score_var,
                            command=self._on_change).pack(anchor="w")
            self._score_vars = []
            defaults = [self.cfg.get("team_a","Team A"), self.cfg.get("team_b","Team B"),
                        self.cfg.get("score","3 – 1"),  self.cfg.get("match_info","Full Time")]
            for lbl, dfl in zip(["Team A:", "Team B:", "Score:", "Info:"], defaults):
                r = ctk.CTkFrame(sec, fg_color="transparent"); r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=lbl, width=60, anchor="w").pack(side="left")
                v = ctk.StringVar(value=dfl)
                ctk.CTkEntry(r, textvariable=v).pack(side="left", fill="x", expand=True)
                v.trace_add("write", lambda *_: self._on_change())
                self._score_vars.append(v)

        def _build_watermark_section(self):
            sec = self._sec("Watermark / Branding")
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=2)
            ctk.CTkLabel(r0, text="Text:").pack(side="left")
            self._wm_text_var = ctk.StringVar(value=self.cfg.get("watermark_text",""))
            ctk.CTkEntry(r0, textvariable=self._wm_text_var, width=200
                         ).pack(side="left", padx=6)
            self._wm_text_var.trace_add("write", lambda *_: self._on_change())
            r1 = ctk.CTkFrame(sec, fg_color="transparent"); r1.pack(fill="x", pady=2)
            ctk.CTkButton(r1, text="Logo image…",
                          command=self._browse_logo, width=120).pack(side="left")
            self._wm_logo_lbl = ctk.CTkLabel(r1, text="None", text_color="#777")
            self._wm_logo_lbl.pack(side="left", padx=8)
            r2 = ctk.CTkFrame(sec, fg_color="transparent"); r2.pack(fill="x", pady=2)
            ctk.CTkLabel(r2, text="Opacity:").pack(side="left")
            self._wm_op_var = tk.IntVar(value=self.cfg.get("watermark_opacity",100))
            ctk.CTkSlider(r2, from_=0, to=255, variable=self._wm_op_var,
                          command=lambda _: self._on_change()
                          ).pack(side="left", fill="x", expand=True, padx=6)

        def _build_theme_section(self):
            sec = self._sec("Color & Theme")
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=3)
            ctk.CTkLabel(r0, text="Theme:").pack(side="left")
            self._theme_var = ctk.StringVar(value=self.cfg.get("theme_name","Dark Pro"))
            ctk.CTkComboBox(r0, variable=self._theme_var, values=list(THEMES.keys()),
                            width=160, command=lambda _: self._on_change()
                            ).pack(side="left", padx=6)
            ctk.CTkButton(r0, text="Accent override…",
                          command=self._pick_accent, width=130).pack(side="left", padx=4)
            self._acc_swatch = ctk.CTkLabel(r0, text="  ", width=30, height=20,
                                             fg_color="#cccccc", corner_radius=4)
            self._acc_swatch.pack(side="left", padx=2)
            ctk.CTkButton(r0, text="Clear", width=55,
                          command=self._clear_accent).pack(side="left", padx=2)

            # individual color pickers
            color_keys = [
                ("BG", "bg_color_override"), ("Panel Top","panel_top_override"),
            ]
            # (theme colours are changed via the theme dropdown; individual overrides
            #  are intentionally kept minimal to avoid UI clutter)

        def _build_layout_section(self):
            sec = self._sec("Layout & Panel")
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=3)
            ctk.CTkLabel(r0, text="Canvas:").pack(side="left")
            self._canvas_var = ctk.StringVar(value=self.cfg["canvas_preset"])
            self._canvas_combo = ctk.CTkComboBox(
                r0, variable=self._canvas_var,
                values=list(CANVAS_SIZES.keys()), width=220,
                command=lambda _: self._on_change(),
            )
            self._canvas_combo.pack(side="left", padx=6)
            ctk.CTkLabel(r0, text="Side:").pack(side="left", padx=(10,4))
            self._side_var = ctk.StringVar(value=self.cfg["panel_side"])
            ctk.CTkComboBox(r0, variable=self._side_var, values=["right","left"],
                            width=80, command=lambda _: self._on_change()
                            ).pack(side="left")

            r1 = ctk.CTkFrame(sec, fg_color="transparent"); r1.pack(fill="x", pady=3)
            ctk.CTkLabel(r1, text="Panel width %:").pack(side="left")
            self._pw_var = tk.IntVar(value=self.cfg["panel_width_pct"])
            ctk.CTkSlider(r1, from_=20, to=70, variable=self._pw_var,
                          command=lambda _: self._on_change()
                          ).pack(side="left", fill="x", expand=True, padx=6)

            r2 = ctk.CTkFrame(sec, fg_color="transparent"); r2.pack(fill="x", pady=3)
            ctk.CTkLabel(r2, text="Panel opacity:").pack(side="left")
            self._op_var = tk.IntVar(value=self.cfg["panel_opacity"])
            ctk.CTkSlider(r2, from_=60, to=255, variable=self._op_var,
                          command=lambda _: self._on_change()
                          ).pack(side="left", fill="x", expand=True, padx=6)

            r3 = ctk.CTkFrame(sec, fg_color="transparent"); r3.pack(fill="x", pady=3)
            ctk.CTkLabel(r3, text="Gradient:").pack(side="left")
            self._grad_var = ctk.StringVar(value=self.cfg["panel_gradient_dir"])
            ctk.CTkComboBox(r3, variable=self._grad_var,
                            values=["horizontal_fade","vertical"], width=160,
                            command=lambda _: self._on_change()
                            ).pack(side="left", padx=6)
            self._glass_var = ctk.BooleanVar(value=self.cfg.get("glassmorphism",True))
            ctk.CTkCheckBox(r3, text="Glassmorphism",
                            variable=self._glass_var, command=self._on_change
                            ).pack(side="left", padx=10)
            self._shadow_var = ctk.BooleanVar(value=self.cfg.get("drop_shadow",True))
            ctk.CTkCheckBox(r3, text="Shadow",
                            variable=self._shadow_var, command=self._on_change
                            ).pack(side="left", padx=6)
            r4 = ctk.CTkFrame(sec, fg_color="transparent"); r4.pack(fill="x", pady=(5,0))
            ctk.CTkButton(
                r4, text="Reset all moved elements", command=self._reset_positions,
                width=180,
            ).pack(side="left")

        def _build_layer_section(self):
            sec = self._sec("Layers, Guides & Snapping")
            row = ctk.CTkFrame(sec, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="Layer:").pack(side="left")
            self._layer_var = ctk.StringVar(value="title")
            self._layer_combo = ctk.CTkComboBox(
                row, variable=self._layer_var, values=["title"], width=190,
                command=lambda _: self._load_selected_layer_state(),
            )
            self._layer_combo.pack(side="left", padx=6)
            self._layer_visible_var = ctk.BooleanVar(value=True)
            self._layer_locked_var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(
                row, text="Visible", variable=self._layer_visible_var,
                command=self._change_layer_state, width=78,
            ).pack(side="left", padx=3)
            ctk.CTkCheckBox(
                row, text="Lock", variable=self._layer_locked_var,
                command=self._change_layer_state, width=64,
            ).pack(side="left", padx=3)

            order_row = ctk.CTkFrame(sec, fg_color="transparent")
            order_row.pack(fill="x", pady=(2,6))
            ctk.CTkButton(
                order_row, text="Move Back", command=lambda: self._move_layer(-1), width=100,
            ).pack(side="left", padx=3)
            ctk.CTkButton(
                order_row, text="Move Front", command=lambda: self._move_layer(1), width=100,
            ).pack(side="left", padx=3)
            ctk.CTkButton(
                order_row, text="Reset Order", command=self._reset_layer_order, width=100,
            ).pack(side="left", padx=3)

            guides = ctk.CTkFrame(sec, fg_color="transparent")
            guides.pack(fill="x", pady=2)
            self._snap_var = ctk.BooleanVar(value=self.cfg.get("snap_enabled", True))
            self._safe_var = ctk.BooleanVar(value=self.cfg.get("show_safe_area", True))
            self._center_guides_var = ctk.BooleanVar(value=self.cfg.get("show_center_guides", False))
            ctk.CTkCheckBox(
                guides, text="Snap", variable=self._snap_var, command=self._on_change, width=72,
            ).pack(side="left", padx=3)
            ctk.CTkCheckBox(
                guides, text="Safe area", variable=self._safe_var, command=self._on_change, width=98,
            ).pack(side="left", padx=3)
            ctk.CTkCheckBox(
                guides, text="Center", variable=self._center_guides_var,
                command=self._on_change, width=88,
            ).pack(side="left", padx=3)

            safe_row = ctk.CTkFrame(sec, fg_color="transparent")
            safe_row.pack(fill="x", pady=2)
            ctk.CTkLabel(safe_row, text="Safe margin:", width=88, anchor="w").pack(side="left")
            self._safe_pct_var = tk.DoubleVar(value=self.cfg.get("safe_area_pct", 5.0))
            self._safe_pct_label = ctk.CTkLabel(safe_row, text="5%", width=42)
            ctk.CTkSlider(
                safe_row, from_=0, to=20, variable=self._safe_pct_var,
                command=self._safe_margin_changed,
            ).pack(side="left", fill="x", expand=True, padx=6)
            self._safe_pct_label.pack(side="left")

        def _build_spacing_section(self):
            sec = self._sec("Padding & Spacing  (% of canvas)")
            sliders = [
                ("Side margin",   "_mx_var",  "margin_x",      0, 30, 9.0),
                ("Top margin",    "_my_var",  "margin_y",      0, 30, 5.0),
                ("Title gap",     "_st_var",  "spacing_title", 0, 15, 3.0),
                ("Row gap",       "_sr_var",  "spacing_rows",  0, 20, 3.0),
                ("Item gap",      "_si_var",  "spacing_items", 0, 10, 1.0),
            ]
            for label, attr, key, lo, hi, dfl in sliders:
                r = ctk.CTkFrame(sec, fg_color="transparent"); r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=label+":", width=90, anchor="w").pack(side="left")
                v = tk.DoubleVar(value=self.cfg.get(key, dfl))
                setattr(self, attr, v)
                ctk.CTkSlider(r, from_=lo, to=hi, variable=v,
                              command=lambda _: self._on_change()
                              ).pack(side="left", fill="x", expand=True, padx=6)

        def _build_font_section(self):
            sec = self._sec("Typography")
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=3)
            ctk.CTkLabel(r0, text="System font:").pack(side="left")
            self._fam_var = ctk.StringVar(value=self.cfg.get("font_family","Arial"))
            ctk.CTkComboBox(r0, variable=self._fam_var, values=SYSTEM_FONTS, width=150,
                            command=lambda _: self._on_change()
                            ).pack(side="left", padx=6)

            self._font_bold_var = ctk.StringVar(value=self.cfg.get("font_bold_path",""))
            self._font_reg_var  = ctk.StringVar(value=self.cfg.get("font_regular_path",""))
            for lbl, var, ftype in [("Bold .ttf:", self._font_bold_var,"bold"),
                                     ("Reg .ttf:",  self._font_reg_var, "regular")]:
                r = ctk.CTkFrame(sec, fg_color="transparent"); r.pack(fill="x", pady=2)
                ctk.CTkLabel(r, text=lbl, width=72, anchor="w").pack(side="left")
                ctk.CTkEntry(r, textvariable=var).pack(side="left", fill="x", expand=True, padx=4)
                ctk.CTkButton(r, text="…", width=35,
                              command=lambda t=ftype: self._browse_font(t)
                              ).pack(side="left")

            size_row = ctk.CTkFrame(sec, fg_color="transparent"); size_row.pack(fill="x",pady=4)
            self._tsz = ctk.StringVar(value=str(self.cfg.get("title_size",0)))
            self._lsz = ctk.StringVar(value=str(self.cfg.get("label_size",0)))
            self._vsz = ctk.StringVar(value=str(self.cfg.get("value_size",0)))
            for lbl, var in [("Title px (0=auto):",self._tsz),
                              ("Label:",self._lsz),("Value:",self._vsz)]:
                ctk.CTkLabel(size_row, text=lbl).pack(side="left", padx=(6,2))
                e = ctk.CTkEntry(size_row, textvariable=var, width=52)
                e.pack(side="left")
                e.bind("<KeyRelease>", lambda _: self._on_change())
            self._auto_fit_var = ctk.BooleanVar(value=self.cfg.get("auto_fit_text", True))
            ctk.CTkCheckBox(
                sec, text="Automatically fit long text and dense rows",
                variable=self._auto_fit_var, command=self._on_change,
            ).pack(anchor="w", pady=(4,0))

        def _build_rows_section(self):
            sec = self._sec("Stat Metrics & Data Rows")
            self._rows_frame = ctk.CTkFrame(sec, fg_color="transparent")
            self._rows_frame.pack(fill="x")
            btn_r = ctk.CTkFrame(sec, fg_color="transparent"); btn_r.pack(fill="x", pady=4)
            ctk.CTkButton(btn_r, text="+ Add Row",
                          command=lambda: self._add_row(), width=100).pack(side="left", padx=4)
            ctk.CTkButton(btn_r, text="Paste Table",
                          command=self._paste_rows, width=110).pack(side="left", padx=4)
            ctk.CTkButton(btn_r, text="Clear All",
                          command=self._clear_rows,
                          width=90,
                          fg_color="#A33", hover_color="#D44").pack(side="left", padx=4)

        def _build_export_section(self):
            sec = self._sec("Export")
            preset_row = ctk.CTkFrame(sec, fg_color="transparent")
            preset_row.pack(fill="x", pady=(0,4))
            ctk.CTkLabel(preset_row, text="Preset:").pack(side="left")
            self._export_preset_var = ctk.StringVar(value="Social PNG")
            self._export_preset_combo = ctk.CTkComboBox(
                preset_row, variable=self._export_preset_var,
                values=list(self._export_presets.keys()), width=175,
            )
            self._export_preset_combo.pack(side="left", padx=6)
            ctk.CTkButton(
                preset_row, text="Apply", command=self._apply_export_preset, width=62,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                preset_row, text="Save", command=self._save_export_preset, width=58,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                preset_row, text="Delete", command=self._delete_export_preset, width=64,
            ).pack(side="left", padx=2)
            r0 = ctk.CTkFrame(sec, fg_color="transparent"); r0.pack(fill="x", pady=4)
            ctk.CTkLabel(r0, text="Format:").pack(side="left")
            self._fmt_var = ctk.StringVar(value=self.cfg.get("export_format","PNG"))
            ctk.CTkComboBox(r0, variable=self._fmt_var,
                            values=["PNG","JPEG","WebP"], width=80
                            ).pack(side="left", padx=6)
            ctk.CTkLabel(r0, text="Scale:").pack(side="left", padx=(10,4))
            self._escale_var = ctk.StringVar(value=str(self.cfg.get("export_scale",1)))
            ctk.CTkComboBox(r0, variable=self._escale_var,
                            values=["1","2","4"], width=60
                            ).pack(side="left")
            ctk.CTkLabel(r0, text="Quality:").pack(side="left", padx=(10,4))
            self._qual_var = ctk.StringVar(value=str(self.cfg.get("export_quality",95)))
            ctk.CTkEntry(r0, textvariable=self._qual_var, width=50).pack(side="left")

            ctk.CTkButton(sec, text="Export Final Graphic",
                          command=self.export_png, height=38,
                          font=("Arial",14,"bold"),
                          fg_color="#18844D", hover_color="#1FA560"
                          ).pack(fill="x", pady=(6,2))
            ctk.CTkButton(sec, text="Batch Export (3 resolutions)",
                          command=self.batch_export, height=32
                          ).pack(fill="x", pady=2)

        # ── canvas drag (element repositioning) ──────────────────────────

        def _safe_margin_changed(self, value):
            self._safe_pct_label.configure(text=f"{float(value):.0f}%")
            self._on_change()

        def _refresh_layer_controls(self):
            order = normalised_layer_order(self.cfg)
            self.cfg["layer_order"] = order
            current = self._layer_var.get() if hasattr(self, "_layer_var") else ""
            if hasattr(self, "_layer_combo"):
                self._layer_combo.configure(values=order or ["template_artwork"])
            if not order:
                return
            if current not in order:
                current = order[-1]
                self._layer_var.set(current)
            self._load_selected_layer_state()

        def _load_selected_layer_state(self):
            layer_id = self._layer_var.get()
            state = layer_state(self.cfg, layer_id)
            self._suspend_changes = True
            try:
                self._layer_visible_var.set(state["visible"])
                self._layer_locked_var.set(state["locked"])
            finally:
                self._suspend_changes = False
            if layer_id in self._hitboxes:
                self._selected_element = layer_id
                if self._last_render is not None:
                    self._update_preview(self._last_render, self._hitboxes)

        def _change_layer_state(self):
            if self._suspend_changes:
                return
            layer_id = self._layer_var.get()
            self.cfg.setdefault("layer_states", {})[layer_id] = {
                "visible": self._layer_visible_var.get(),
                "locked": self._layer_locked_var.get(),
            }
            if not self._layer_visible_var.get() and self._selected_element == layer_id:
                self._selected_element = None
            self._on_change()

        def _move_layer(self, direction: int):
            layer_id = self._layer_var.get()
            order = normalised_layer_order(self.cfg)
            if layer_id not in order:
                return
            index = order.index(layer_id)
            target = max(0, min(len(order)-1, index + direction))
            if target == index:
                return
            order[index], order[target] = order[target], order[index]
            self.cfg["layer_order"] = order
            self._refresh_layer_controls()
            self._on_change()

        def _reset_layer_order(self):
            self.cfg["layer_order"] = default_layer_ids(self.cfg)
            self._refresh_layer_controls()
            self._on_change()

        def _snap_position(self, layer_id: str, x: float, y: float,
                           width: float, height: float) -> Tuple[float, float]:
            """Snap element edges/centres to canvas, safe-area, and nearby layers."""
            self._snap_guides = []
            if not self.cfg.get("snap_enabled", True):
                return x, y
            canvas_w, canvas_h = active_canvas_size(self.cfg)
            safe = float(self.cfg.get("safe_area_pct", 5.0)) / 100.0
            x_targets = [0.0, canvas_w*safe, canvas_w/2, canvas_w*(1-safe), float(canvas_w)]
            y_targets = [0.0, canvas_h*safe, canvas_h/2, canvas_h*(1-safe), float(canvas_h)]
            for other_id, (x1, y1, x2, y2) in self._hitboxes.items():
                if other_id == layer_id or not layer_state(self.cfg, other_id)["visible"]:
                    continue
                x_targets.extend([x1, (x1+x2)/2, x2])
                y_targets.extend([y1, (y1+y2)/2, y2])

            threshold = float(self.cfg.get("snap_threshold", 8))

            def snap_axis(origin: float, size: float, targets: List[float]):
                best = None
                for anchor in (origin, origin + size/2, origin + size):
                    for target in targets:
                        distance = target - anchor
                        if abs(distance) <= threshold and (best is None or abs(distance) < abs(best[0])):
                            best = (distance, target)
                return (origin + best[0], best[1]) if best else (origin, None)

            x, guide_x = snap_axis(x, width, x_targets)
            y, guide_y = snap_axis(y, height, y_targets)
            if guide_x is not None:
                self._snap_guides.append(("x", guide_x))
            if guide_y is not None:
                self._snap_guides.append(("y", guide_y))
            return x, y

        def _drag_start(self, e):
            """Hit-test against all rendered element bounding boxes."""
            if not self._tk_img:
                return
            # canvas → scaled-image coordinates
            cw = self.preview_canvas.winfo_width()
            ch = self.preview_canvas.winfo_height()
            iw, ih = self._tk_img.width(), self._tk_img.height()
            ox = (cw - iw) / 2
            oy = (ch - ih) / 2
            s = max(0.01, self._preview_scale)
            img_x = (e.x - ox) / s
            img_y = (e.y - oy) / s

            hit = None
            pad = 10  # px tolerance
            for eid in normalised_layer_order(self.cfg):
                if eid not in self._hitboxes:
                    continue
                x1, y1, x2, y2 = self._hitboxes[eid]
                if x1 - pad <= img_x <= x2 + pad and y1 - pad <= img_y <= y2 + pad:
                    hit = eid  # last match wins (top-most z-order)

            if hit:
                self._selected_element = hit
                self._layer_var.set(hit)
                self._load_selected_layer_state()
                self.preview_canvas.focus_set()
                if (layer_state(self.cfg, hit)["locked"] or
                        self.cfg.get("template_name") != "Single Player Pro"):
                    self._drag.update(x=e.x, y=e.y, active=False, element=None)
                    self._status(f"Selected locked layer: {hit}" if layer_state(self.cfg, hit)["locked"]
                                 else "Template artwork is edited through Edit Content")
                    return
                self._drag.update(x=e.x, y=e.y, active=True, element=hit)
                if "positions" not in self.cfg:
                    self.cfg["positions"] = {}
                # Initialise absolute position from current auto-layout hitbox
                if hit not in self.cfg["positions"]:
                    bw, bh = active_canvas_size(self.cfg)
                    hx1, hy1, _, _ = self._hitboxes[hit]
                    self.cfg["positions"][hit] = [
                        hx1 / bw * 100,
                        hy1 / bh * 100,
                    ]
            else:
                self._selected_element = None
                self._drag.update(x=e.x, y=e.y, active=False, element=None)

        def _drag_move(self, e):
            if not self._drag["active"] or not self._drag.get("element"):
                return
            dx = e.x - self._drag["x"]
            dy = e.y - self._drag["y"]
            self._drag.update(x=e.x, y=e.y)

            eid = self._drag["element"]
            bw, bh = active_canvas_size(self.cfg)
            s = max(0.01, self._preview_scale)
            pos = self.cfg["positions"][eid]
            pos[0] += dx / s / bw * 100
            pos[1] += dy / s / bh * 100
            x1, y1, x2, y2 = self._hitboxes.get(eid, (0,0,0,0))
            width, height = x2-x1, y2-y1
            px, py = self._snap_position(
                eid, pos[0] / 100 * bw, pos[1] / 100 * bh, width, height
            )
            pos[0] = max(0.0, min(100.0 - width / bw * 100, px / bw * 100))
            pos[1] = max(0.0, min(100.0 - height / bh * 100, py / bh * 100))
            self.schedule_redraw()

        def _drag_end(self, _):
            if self._drag["active"]:
                self._drag["active"] = False
                self._snap_guides = []
                self._on_change()  # commit to undo stack

        def _drag_reset(self, e):
            """Double-click: reset the element under cursor to auto-layout."""
            self._drag_start(e)
            eid = self._drag.get("element")
            if eid and "positions" in self.cfg and eid in self.cfg["positions"]:
                del self.cfg["positions"][eid]
                self._drag["active"] = False
                self._on_change()
                self._status(f"Reset '{eid}' to auto-layout")

        def _reset_positions(self):
            self.cfg["positions"] = {}
            self._selected_element = None
            self._on_change()
            self._status("All elements returned to auto-layout")

        def _nudge_selected(self, event, dx: int, dy: int):
            eid = self._selected_element
            if not eid or eid not in self._hitboxes:
                return
            if layer_state(self.cfg, eid)["locked"]:
                return "break"
            bw, bh = active_canvas_size(self.cfg)
            if eid not in self.cfg.setdefault("positions", {}):
                x1, y1, _, _ = self._hitboxes[eid]
                self.cfg["positions"][eid] = [x1 / bw * 100, y1 / bh * 100]
            step = 10 if event.state & 0x0001 else 1
            pos = self.cfg["positions"][eid]
            pos[0] += dx * step / bw * 100
            pos[1] += dy * step / bh * 100
            x1, y1, x2, y2 = self._hitboxes[eid]
            pos[0] = max(0.0, min(100.0 - (x2-x1) / bw * 100, pos[0]))
            pos[1] = max(0.0, min(100.0 - (y2-y1) / bh * 100, pos[1]))
            self._on_change()
            return "break"

        # ── config sync ─────────────────────────────────────────────────

        def _collect_cfg(self) -> Dict:
            def si(v, d):
                try: return int(v)
                except: return d
            rows = [w.get_data() for w in self._stat_widgets]
            result = {
                **self.cfg,
                "template_name":    self._template_var.get(),
                "canvas_preset":    self.cfg.get("canvas_preset", DEFAULT_CFG["canvas_preset"]),
                "panel_side":       self._side_var.get(),
                "panel_width_pct":  int(self._pw_var.get()),
                "panel_opacity":    int(self._op_var.get()),
                "panel_gradient_dir": self._grad_var.get(),
                "glassmorphism":    self._glass_var.get(),
                "drop_shadow":      self._shadow_var.get(),
                "photo_fit":        self._fit_var.get(),
                "photo_treatment":  self._treat_var.get(),
                "photo_zoom":       self._photo_zoom_var.get(),
                "photo_focus_x":    self._photo_fx_var.get(),
                "photo_focus_y":    self._photo_fy_var.get(),
                "overlay_scale":    self._ov_scale.get(),
                "margin_x":         self._mx_var.get(),
                "margin_y":         self._my_var.get(),
                "spacing_title":    self._st_var.get(),
                "spacing_rows":     self._sr_var.get(),
                "spacing_items":    self._si_var.get(),
                "subtitle":         self._sub_var.get(),
                "title":            self._title_box.get("1.0","end-1c"),
                "show_score_block": self._show_score_var.get(),
                "team_a":  self._score_vars[0].get(),
                "team_b":  self._score_vars[1].get(),
                "score":   self._score_vars[2].get(),
                "match_info": self._score_vars[3].get(),
                "watermark_text":      self._wm_text_var.get(),
                "watermark_opacity":   self._wm_op_var.get(),
                "theme_name":    self._theme_var.get(),
                "font_family":   self._fam_var.get(),
                "font_bold_path":    self._font_bold_var.get(),
                "font_regular_path": self._font_reg_var.get(),
                "title_size": si(self._tsz.get(),0),
                "label_size": si(self._lsz.get(),0),
                "value_size": si(self._vsz.get(),0),
                "auto_fit_text": self._auto_fit_var.get(),
                "export_format":  self._fmt_var.get(),
                "export_scale":   si(self._escale_var.get(),1),
                "export_quality": si(self._qual_var.get(),95),
                "stat_rows": rows,
                "positions": copy.deepcopy(self.cfg.get("positions", {})),
                "layer_order": copy.deepcopy(self.cfg.get("layer_order", [])),
                "layer_states": copy.deepcopy(self.cfg.get("layer_states", {})),
                "snap_enabled": self._snap_var.get(),
                "show_safe_area": self._safe_var.get(),
                "show_center_guides": self._center_guides_var.get(),
                "safe_area_pct": self._safe_pct_var.get(),
                "template_configs": copy.deepcopy(self.cfg.get("template_configs", {})),
            }
            if result["template_name"] == "Single Player Pro":
                result["canvas_preset"] = self._canvas_var.get()
            else:
                result["template_configs"].setdefault(result["template_name"], {})[
                    "canvas_size"
                ] = self._canvas_var.get()
            result["layer_order"] = normalised_layer_order(result)
            return result

        def _apply_cfg_to_ui(self):
            c = self.cfg
            template = c.get("template_name", "Single Player Pro")
            self._template_var.set(template)
            self._set_template_hint(template)
            options = active_canvas_options(c)
            self._canvas_combo.configure(values=list(options.keys()))
            selected_canvas = (
                c.get("canvas_preset") if template == "Single Player Pro"
                else c.get("template_configs", {}).get(template, {}).get("canvas_size")
            )
            if selected_canvas not in options:
                selected_canvas = next(iter(options))
            self._canvas_var.set(selected_canvas)
            self._side_var.set(c["panel_side"])
            self._pw_var.set(c["panel_width_pct"])
            self._op_var.set(c["panel_opacity"])
            self._grad_var.set(c["panel_gradient_dir"])
            self._glass_var.set(c.get("glassmorphism",True))
            self._shadow_var.set(c.get("drop_shadow",True))
            self._fit_var.set(c.get("photo_fit","cover"))
            self._treat_var.set(c.get("photo_treatment","none"))
            self._photo_zoom_var.set(c.get("photo_zoom",100))
            self._photo_fx_var.set(c.get("photo_focus_x",50))
            self._photo_fy_var.set(c.get("photo_focus_y",50))
            for attr in ("_photo_zoom_var", "_photo_fx_var", "_photo_fy_var"):
                getattr(self, attr + "_label").configure(text=f"{getattr(self, attr).get():.0f}%")
            self._ov_scale.set(c.get("overlay_scale",80))
            self._mx_var.set(c.get("margin_x",9.0))
            self._my_var.set(c.get("margin_y",5.0))
            self._st_var.set(c.get("spacing_title",3.0))
            self._sr_var.set(c.get("spacing_rows",3.0))
            self._si_var.set(c.get("spacing_items",1.0))
            self._sub_var.set(c.get("subtitle",""))
            self._title_box.delete("1.0","end")
            self._title_box.insert("1.0", c.get("title","Match\nStatistics"))
            self._show_score_var.set(c.get("show_score_block",False))
            for v,k in zip(self._score_vars,["team_a","team_b","score","match_info"]):
                v.set(c.get(k,""))
            self._wm_text_var.set(c.get("watermark_text",""))
            self._wm_op_var.set(c.get("watermark_opacity",100))
            self._theme_var.set(c.get("theme_name","Dark Pro"))
            self._fam_var.set(c.get("font_family","Arial"))
            self._font_bold_var.set(c.get("font_bold_path",""))
            self._font_reg_var.set(c.get("font_regular_path",""))
            self._tsz.set(str(c.get("title_size",0)))
            self._lsz.set(str(c.get("label_size",0)))
            self._vsz.set(str(c.get("value_size",0)))
            self._auto_fit_var.set(c.get("auto_fit_text",True))
            self._snap_var.set(c.get("snap_enabled", True))
            self._safe_var.set(c.get("show_safe_area", True))
            self._center_guides_var.set(c.get("show_center_guides", False))
            self._safe_pct_var.set(c.get("safe_area_pct", 5.0))
            self._safe_pct_label.configure(text=f"{self._safe_pct_var.get():.0f}%")
            self._fmt_var.set(c.get("export_format","PNG"))
            self._escale_var.set(str(c.get("export_scale",1)))
            self._qual_var.set(str(c.get("export_quality",95)))
            ph = c.get("photo_path","")
            self._img_lbl.configure(
                text=Path(ph).name if ph else "No background",
                text_color="#fff" if ph else "#777")
            lo = c.get("watermark_logo_path","")
            self._wm_logo_lbl.configure(
                text=Path(lo).name if lo else "None",
                text_color="#fff" if lo else "#777")
            self._update_accent_swatch(c.get("accent_override",""))
            self._quick_theme_var.set(c.get("theme_name","Dark Pro"))
            self._refresh_layer_controls()

        # ── row management ───────────────────────────────────────────────

        def _rebuild_row_widgets(self):
            for w in self._stat_widgets: w.destroy()
            self._stat_widgets.clear()
            for row in self.cfg.get("stat_rows",[]):
                self._add_row(data=row, push_undo=False)

        def _add_row(self, data=None, push_undo=True):
            w = StatRowWidget(self._rows_frame, len(self._stat_widgets),
                              data, self._on_change, self._del_row, self._move_row)
            w.pack(fill="x", pady=3)
            self._stat_widgets.append(w)
            if push_undo: self._on_change()

        def _del_row(self, widget: StatRowWidget):
            if len(self._stat_widgets) <= 1:
                messagebox.showwarning("Warning","Keep at least one row."); return
            index = self._stat_widgets.index(widget)
            old_count = len(self._stat_widgets)
            widget.destroy()
            self._stat_widgets.remove(widget)
            for collection_key in ("positions", "layer_states"):
                collection = self.cfg.setdefault(collection_key, {})
                collection.pop(f"row_{index}", None)
                for old_index in range(index + 1, old_count):
                    old_key, new_key = f"row_{old_index}", f"row_{old_index-1}"
                    if old_key in collection:
                        collection[new_key] = collection.pop(old_key)
                    else:
                        collection.pop(new_key, None)
            remapped_order = []
            for layer_id in self.cfg.get("layer_order", []):
                if layer_id == f"row_{index}":
                    continue
                match = re.fullmatch(r"row_(\d+)", layer_id)
                if match and int(match.group(1)) > index:
                    layer_id = f"row_{int(match.group(1))-1}"
                remapped_order.append(layer_id)
            self.cfg["layer_order"] = remapped_order
            self._on_change()

        def _clear_rows(self):
            for w in self._stat_widgets: w.destroy()
            self._stat_widgets.clear()
            for collection_key in ("positions", "layer_states"):
                collection = self.cfg.setdefault(collection_key, {})
                for key in list(collection):
                    if re.fullmatch(r"row_\d+", key):
                        collection.pop(key, None)
            self.cfg["layer_order"] = [
                layer_id for layer_id in self.cfg.get("layer_order", [])
                if not re.fullmatch(r"row_\d+", layer_id)
            ]
            self._add_row()

        def _paste_rows(self):
            try:
                rows = parse_stat_rows(self.clipboard_get())
            except tk.TclError:
                rows = []
            if not rows:
                messagebox.showwarning(
                    "Paste Table",
                    "Copy spreadsheet rows first. Use columns: Label, Value, Max, Sub-label.",
                )
                return
            replace = messagebox.askyesnocancel(
                "Paste Table",
                f"Found {len(rows)} rows.\n\nYes: replace current rows\nNo: append rows",
            )
            if replace is None:
                return
            self._suspend_changes = True
            try:
                if replace:
                    for widget in self._stat_widgets:
                        widget.destroy()
                    self._stat_widgets.clear()
                    for collection_key in ("positions", "layer_states"):
                        collection = self.cfg.setdefault(collection_key, {})
                        for key in list(collection):
                            if re.fullmatch(r"row_\d+", key):
                                collection.pop(key, None)
                    self.cfg["layer_order"] = [
                        layer_id for layer_id in self.cfg.get("layer_order", [])
                        if not re.fullmatch(r"row_\d+", layer_id)
                    ]
                for row in rows:
                    self._add_row(data=row, push_undo=False)
            finally:
                self._suspend_changes = False
            self._on_change()
            self._status(f"Pasted {len(rows)} stat rows")

        def _move_row(self, widget, delta, duplicate=False):
            if widget not in self._stat_widgets: return
            idx = self._stat_widgets.index(widget)
            if duplicate:
                d = widget.get_data()
                self._add_row(data=copy.deepcopy(d), push_undo=False)
                # move new clone to idx+1
                new = self._stat_widgets.pop()
                self._stat_widgets.insert(idx+1, new)
            else:
                ni = idx + delta
                if 0 <= ni < len(self._stat_widgets):
                    self._stat_widgets[idx], self._stat_widgets[ni] = \
                        self._stat_widgets[ni], self._stat_widgets[idx]
                    # swap any custom positions that match these row indices
                    pos = self.cfg.get("positions", {})
                    p1 = pos.pop(f"row_{idx}", None)
                    p2 = pos.pop(f"row_{ni}", None)
                    if p1: pos[f"row_{ni}"] = p1
                    if p2: pos[f"row_{idx}"] = p2
                    states = self.cfg.setdefault("layer_states", {})
                    s1 = states.pop(f"row_{idx}", None)
                    s2 = states.pop(f"row_{ni}", None)
                    if s1: states[f"row_{ni}"] = s1
                    if s2: states[f"row_{idx}"] = s2
                    order = self.cfg.get("layer_order", [])
                    self.cfg["layer_order"] = [
                        f"row_{ni}" if layer_id == f"row_{idx}" else
                        f"row_{idx}" if layer_id == f"row_{ni}" else layer_id
                        for layer_id in order
                    ]
            for w in self._stat_widgets: w.pack_forget()
            for w in self._stat_widgets: w.pack(fill="x", pady=3)
            self._on_change()

        # ── change / undo flow ───────────────────────────────────────────

        def _on_change(self, _=None):
            if self._suspend_changes:
                return
            previous_order = list(self.cfg.get("layer_order", []))
            self.cfg = self._collect_cfg()
            refreshed_order = normalised_layer_order(self.cfg)
            if refreshed_order != previous_order:
                self.cfg["layer_order"] = refreshed_order
                self._refresh_layer_controls()
            self.schedule_redraw()
            if self._history_timer:
                self.after_cancel(self._history_timer)
            if self._save_timer:
                self.after_cancel(self._save_timer)
            self._history_timer = self.after(350, self._commit_history)
            self._save_timer = self.after(500, self._persist_session)

        def _commit_history(self):
            self._history_timer = None
            if not self._suspend_changes:
                self.cfg = self._collect_cfg()
                self._undo.push(self.cfg)

        def _persist_session(self):
            self._save_timer = None
            if not self._suspend_changes:
                save_config(self._collect_cfg())

        def _flush_history(self):
            if self._history_timer:
                self.after_cancel(self._history_timer)
                self._history_timer = None
                self.cfg = self._collect_cfg()
                self._undo.push(self.cfg)

        def _restore_state(self, state: Dict, reset_history: bool = False):
            self._suspend_changes = True
            try:
                self.cfg = _normalise_config(copy.deepcopy(state))
                self._apply_cfg_to_ui()
                self._rebuild_row_widgets()
            finally:
                self._suspend_changes = False
            if reset_history:
                self._undo = UndoStack()
                self._undo.push(self.cfg)
            save_config(self.cfg)
            self.redraw_now()

        def _undo_action(self):
            self._flush_history()
            s = self._undo.undo()
            if s:
                self._restore_state(s)
                self._status("Undo")

        def _redo_action(self):
            s = self._undo.redo()
            if s:
                self._restore_state(s)
                self._status("Redo")

        # ── preset appliers ──────────────────────────────────────────────

        def _set_template_hint(self, template):
            if template == "Single Player Pro":
                text = "Use the image, title, score, typography and row controls below."
            else:
                text = "Use Edit Content for players, photos, crop framing and comparison metrics."
            self._template_hint_var.set(text)

        def _shortcut_template(self, template):
            self._template_var.set(template)
            self._on_template_change(template)
            return "break"

        def _on_template_change(self, name):
            if self._suspend_changes:
                return
            previous = self.cfg.get("template_name", "Single Player Pro")
            self._suspend_changes = True
            try:
                self._template_var.set(previous)
                self.cfg = self._collect_cfg()
                self._template_var.set(name)
            finally:
                self._suspend_changes = False
            self.cfg["template_name"] = name
            self._set_template_hint(name)
            self.cfg["positions"] = {}
            self._selected_element = None
            options = active_canvas_options(self.cfg)
            self._canvas_combo.configure(values=list(options.keys()))
            selected = (
                self.cfg.get("canvas_preset") if name == "Single Player Pro"
                else self.cfg.get("template_configs", {}).get(name, {}).get("canvas_size")
            )
            self._canvas_var.set(selected if selected in options else next(iter(options)))
            self.cfg["layer_order"] = default_layer_ids(self.cfg)
            self._refresh_layer_controls()
            self._on_change()
            audit("TEMPLATE", name)

        def _edit_template_content(self):
            template = self._template_var.get()
            if template == "Single Player Pro":
                self._status("Single Player content is edited in the controls below")
                return
            data = copy.deepcopy(self.cfg.get("template_configs", {}).get(template, {}))
            TemplateContentDialog(self, template, data, self._save_template_content)

        def _save_template_content(self, data: Dict[str, Any]):
            template = self._template_var.get()
            self.cfg.setdefault("template_configs", {})[template] = copy.deepcopy(data)
            self._on_change()
            self._status(f"Updated {template}")

        def _apply_export_preset(self):
            name = self._export_preset_var.get()
            preset = self._export_presets.get(name)
            if not preset:
                return
            self._fmt_var.set(str(preset.get("export_format", "PNG")))
            self._escale_var.set(str(preset.get("export_scale", 1)))
            self._qual_var.set(str(preset.get("export_quality", 95)))
            self._on_change()
            self._status(f"Applied export preset: {name}")

        def _save_export_preset(self):
            name = simpledialog.askstring(
                "Save Export Preset", "Preset name:", parent=self
            )
            if not name:
                return
            name = name.strip()
            if name in BUILTIN_EXPORT_PRESETS:
                messagebox.showwarning("Built-in Preset", "Choose a different name for a custom preset.")
                return
            cfg = self._collect_cfg()
            self._export_presets[name] = {
                "export_format": cfg.get("export_format", "PNG"),
                "export_scale": cfg.get("export_scale", 1),
                "export_quality": cfg.get("export_quality", 95),
            }
            save_export_presets(self._export_presets)
            self._export_preset_combo.configure(values=list(self._export_presets.keys()))
            self._export_preset_var.set(name)
            self._status(f"Saved export preset: {name}")

        def _delete_export_preset(self):
            name = self._export_preset_var.get()
            if name in BUILTIN_EXPORT_PRESETS:
                messagebox.showwarning("Built-in Preset", "Built-in presets cannot be deleted.")
                return
            if name not in self._export_presets:
                return
            del self._export_presets[name]
            save_export_presets(self._export_presets)
            self._export_preset_combo.configure(values=list(self._export_presets.keys()))
            self._export_preset_var.set(next(iter(self._export_presets)))
            self._status(f"Deleted export preset: {name}")

        def _apply_theme_preset(self, name):
            self._theme_var.set(name)
            self._quick_theme_var.set(name)
            self._on_change()
            audit("THEME_PRESET", name)

        def _apply_layout_preset(self, name):
            preset = LAYOUT_PRESETS.get(name)
            if not preset:
                return
            self._suspend_changes = True
            try:
                self.cfg.update(copy.deepcopy(preset))
                self._apply_cfg_to_ui()
            finally:
                self._suspend_changes = False
            self._on_change()
            audit("LAYOUT_PRESET", name)

        def _apply_stat_preset(self, name):
            rows = STAT_PRESETS.get(name,[])
            for w in self._stat_widgets: w.destroy()
            self._stat_widgets.clear()
            for r in rows: self._add_row(data=r, push_undo=False)
            self._on_change()
            audit("STAT_PRESET", name)

        # ── file pickers ─────────────────────────────────────────────────

        def _browse_bg(self):
            p = filedialog.askopenfilename(
                filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.bmp *.avif")])
            if p:
                self.cfg["photo_path"] = p
                self._img_lbl.configure(text=Path(p).name, text_color="#fff")
                self._on_change(); audit("BG_CHOSEN", p)

        def _browse_overlay(self):
            p = filedialog.askopenfilename(
                filetypes=[("Transparent images","*.png *.webp *.avif")])
            if p:
                self.cfg["overlay_path"] = p
                self._status(f"Overlay: {Path(p).name}")
                self._on_change(); audit("OVERLAY_CHOSEN", p)

        def _clear_overlay(self):
            self.cfg.update(overlay_path="", overlay_x=5.0, overlay_y=5.0)
            self._status("Overlay cleared"); self._on_change()

        def _browse_logo(self):
            p = filedialog.askopenfilename(
                filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.avif")])
            if p:
                self.cfg["watermark_logo_path"] = p
                self._wm_logo_lbl.configure(text=Path(p).name, text_color="#fff")
                self._on_change(); audit("LOGO_CHOSEN", p)

        def _browse_font(self, ftype):
            p = filedialog.askopenfilename(
                title=f"Select {ftype} font",
                filetypes=[("Fonts","*.ttf *.otf")])
            if p:
                (self._font_bold_var if ftype=="bold" else self._font_reg_var).set(p)
                self._on_change()

        def _pick_accent(self):
            cur = self.cfg.get("accent_override","") or "#dfff3c"
            res = colorchooser.askcolor(title="Accent colour", initialcolor=cur)
            if res[1]:
                self.cfg["accent_override"] = res[1]
                self._update_accent_swatch(res[1])
                self._on_change(); audit("ACCENT", res[1])

        def _clear_accent(self):
            self.cfg["accent_override"] = ""
            self._update_accent_swatch("")
            self._on_change()

        def _update_accent_swatch(self, h):
            self._acc_swatch.configure(fg_color=h if h and h.startswith("#") else "#666666")

        # ── JSON project load / save / reset ─────────────────────────────

        def _load_json(self):
            p = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
            if p:
                try:
                    self._cfg_path = p
                    self._restore_state(load_config(Path(p)), reset_history=True)
                    self._status(f"Loaded: {Path(p).name}")
                    audit("LOAD_JSON", p)
                except Exception as e:
                    messagebox.showerror("Error", str(e))

        def _save_json(self):
            if not self._cfg_path:
                self._cfg_path = filedialog.asksaveasfilename(
                    defaultextension=".json", filetypes=[("JSON","*.json")])
            if self._cfg_path:
                save_config(self._collect_cfg(), Path(self._cfg_path))
                self._status(f"Saved: {Path(self._cfg_path).name}")
                audit("SAVE_JSON", self._cfg_path)

        def _reset(self):
            if messagebox.askyesno("Reset","Reset everything to defaults?"):
                self._restore_state(copy.deepcopy(DEFAULT_CFG), reset_history=True)
                audit("RESET","")

        # ── threaded render pipeline ─────────────────────────────────────

        def schedule_redraw(self, *_):
            if self._redraw_timer: self.after_cancel(self._redraw_timer)
            self._redraw_timer = self.after(140, self._push_render)

        def _push_render(self):
            self._render_q.put(self._collect_cfg())

        def _start_render_worker(self):
            def worker():
                while True:
                    cfg = self._render_q.get()
                    while not self._render_q.empty():
                        newer = self._render_q.get_nowait()
                        self._render_q.task_done()
                        cfg = newer
                    try:
                        img, hitboxes = UnifiedRenderer.render(cfg, scale=1)
                        self.after(0, lambda i=img, h=hitboxes: self._update_preview(i, h))
                    except Exception as exc:
                        logger.error("Render error: %s", exc)
                        audit("RENDER_ERROR", traceback.format_exc())
                    finally:
                        self._render_q.task_done()
            threading.Thread(target=worker, daemon=True).start()

        def redraw_now(self):
            try:
                img, hitboxes = UnifiedRenderer.render(self._collect_cfg(), scale=1)
                self._update_preview(img, hitboxes)
            except Exception as exc:
                self._status(f"Render error: {exc}")

        def _update_preview(self, img: Image.Image, hitboxes: Dict = None):
            if hitboxes is not None: self._hitboxes = hitboxes
            self._last_render = img
            mw = max(400, self.preview_panel.winfo_width()-32)
            mh = max(300, self.preview_panel.winfo_height()-80)
            w, h = img.size
            self._preview_scale = min(mw/w, mh/h, 1.0)
            nw, nh = int(w*self._preview_scale), int(h*self._preview_scale)
            self._tk_img = ImageTk.PhotoImage(img.resize((nw,nh), Image.LANCZOS))
            self.preview_canvas.delete("all")
            cx = self.preview_canvas.winfo_width()//2
            cy = self.preview_canvas.winfo_height()//2
            self.preview_canvas.create_image(cx, cy, image=self._tk_img, anchor="center")
            ox, oy = cx - nw / 2, cy - nh / 2
            canvas_w, canvas_h = active_canvas_size(self.cfg)
            if self.cfg.get("show_safe_area", True):
                margin = float(self.cfg.get("safe_area_pct", 5.0)) / 100.0
                self.preview_canvas.create_rectangle(
                    ox + canvas_w*margin*self._preview_scale,
                    oy + canvas_h*margin*self._preview_scale,
                    ox + canvas_w*(1-margin)*self._preview_scale,
                    oy + canvas_h*(1-margin)*self._preview_scale,
                    outline="#f2b84b", width=1, dash=(6,4),
                )
            if self.cfg.get("show_center_guides", False):
                self.preview_canvas.create_line(
                    ox + nw/2, oy, ox + nw/2, oy+nh,
                    fill="#667788", width=1, dash=(4,4),
                )
                self.preview_canvas.create_line(
                    ox, oy+nh/2, ox+nw, oy+nh/2,
                    fill="#667788", width=1, dash=(4,4),
                )
            for axis, value in self._snap_guides:
                if axis == "x":
                    x = ox + value*self._preview_scale
                    self.preview_canvas.create_line(x, oy, x, oy+nh, fill="#35d07f", width=1)
                else:
                    y = oy + value*self._preview_scale
                    self.preview_canvas.create_line(ox, y, ox+nw, y, fill="#35d07f", width=1)
            selected = self._selected_element
            if selected in self._hitboxes:
                x1, y1, x2, y2 = self._hitboxes[selected]
                self.preview_canvas.create_rectangle(
                    ox + x1*self._preview_scale,
                    oy + y1*self._preview_scale,
                    ox + x2*self._preview_scale,
                    oy + y2*self._preview_scale,
                    outline="#35a7ff", width=2, dash=(4,3),
                )
            self._status("Preview updated")

        # ── export ───────────────────────────────────────────────────────

        def _prepare_export(self, cfg: Dict) -> Optional[Tuple[str, str, int, int]]:
            fmt = str(cfg.get("export_format", "PNG")).lower()
            if fmt not in ("png", "jpeg", "webp"):
                fmt = "png"
            ext = "jpg" if fmt == "jpeg" else fmt
            scale = max(1, min(4, int(cfg.get("export_scale", 1))))
            quality = max(1, min(100, int(cfg.get("export_quality", 95))))
            bw, bh = active_canvas_size(cfg)
            pixels = bw * bh * scale * scale
            if pixels > MAX_EXPORT_PIXELS:
                width, height = bw * scale, bh * scale
                proceed = messagebox.askyesno(
                    "Large Export",
                    f"This export is {width:,} × {height:,} ({pixels/1_000_000:.0f} MP) "
                    "and may require more than 1 GB of memory. Continue?",
                )
                if not proceed:
                    return None
            return fmt, ext, scale, quality

        def export_png(self):
            cfg = self._collect_cfg()
            prepared = self._prepare_export(cfg)
            if not prepared:
                return
            fmt, ext, scale, quality = prepared
            p = filedialog.asksaveasfilename(
                defaultextension=f".{ext}",
                filetypes=[(fmt.upper(), f"*.{ext}")],
                initialfile=f"scoreboard.{ext}")
            if p:
                try:
                    self._status("Exporting…"); self.update()
                    img, _ = UnifiedRenderer.render(cfg, scale=scale)
                    kw = {"quality": quality} if fmt in ("jpeg","webp") else {}
                    img.save(p, format=fmt.upper(), **kw)
                    self._status(f"Exported → {Path(p).name}")
                    messagebox.showinfo("Saved", f"Exported:\n{p}")
                    audit("EXPORT", p)
                except Exception as exc:
                    messagebox.showerror("Export Error", str(exc))
                    audit("EXPORT_ERROR", str(exc))

        def batch_export(self):
            folder = filedialog.askdirectory(title="Choose output folder")
            if not folder: return
            cfg = self._collect_cfg()
            prepared = self._prepare_export(cfg)
            if not prepared:
                return
            fmt, ext, scale, quality = prepared
            saved = []
            presets = (BATCH_PRESETS if cfg.get("template_name") == "Single Player Pro"
                       else list(active_canvas_options(cfg).keys()))
            for preset in presets:
                try:
                    batch_cfg = copy.deepcopy(cfg)
                    if batch_cfg.get("template_name") == "Single Player Pro":
                        batch_cfg["canvas_preset"] = preset
                    else:
                        batch_cfg["template_configs"][batch_cfg["template_name"]]["canvas_size"] = preset
                    img, _ = UnifiedRenderer.render(batch_cfg, scale=scale)
                    slug = preset.replace(":","_").replace(" ","_").replace("×","x")
                    out  = Path(folder)/f"scoreboard_{slug}.{ext}"
                    kw = {"quality": quality} if fmt in ("jpeg", "webp") else {}
                    img.save(out, format=fmt.upper(), **kw)
                    saved.append(str(out))
                    audit("BATCH", str(out))
                except Exception as exc:
                    audit("BATCH_ERROR", f"{preset}: {exc}")
            messagebox.showinfo("Batch Export",
                f"Exported {len(saved)} files to:\n{folder}")
            self._status(f"Batch → {folder}")

        # ── audit log viewer ─────────────────────────────────────────────

        def _show_audit(self):
            win = tk.Toplevel(self)
            win.title("Audit Log"); win.geometry("820x520")
            txt = tk.Text(win, wrap="none", font=("Courier",9), bg="#111", fg="#ccc")
            sb  = tk.Scrollbar(win, command=txt.yview); txt.config(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y"); txt.pack(fill="both", expand=True)
            if AUDIT_PATH.exists():
                txt.insert("1.0", AUDIT_PATH.read_text(encoding="utf-8", errors="replace"))
            txt.see("end"); txt.config(state="disabled")

        # ── misc ─────────────────────────────────────────────────────────

        def _status(self, msg: str):
            self._status_var.set(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")

        def _on_close(self):
            for timer in (self._redraw_timer, self._history_timer, self._save_timer):
                if timer:
                    try:
                        self.after_cancel(timer)
                    except Exception:
                        pass
            save_config(self._collect_cfg())
            audit("APP_CLOSE","")
            self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class _TestHelpers(unittest.TestCase):
    def test_extract_percent(self):   self.assertAlmostEqual(extract_number("72 %"), 72.0)
    def test_extract_decimal(self):  self.assertAlmostEqual(extract_number("8,8 M"), 8.8)
    def test_extract_none(self):     self.assertIsNone(extract_number("N/A"))
    def test_percent_clamped(self):  self.assertEqual(auto_percent("120 %","100"), 100.0)
    def test_percent_scaled(self):   self.assertAlmostEqual(auto_percent("7","14"), 50.0)
    def test_hex_roundtrip(self):    self.assertEqual(rgb_to_hex(hex_to_rgb("#dfff3c")), "#dfff3c")
    def test_lerp(self):             self.assertEqual(rgb_lerp((0,0,0),(100,200,50),.5),(50,100,25))
    def test_parse_clipboard_rows(self):
        rows = parse_stat_rows("Metric\tValue\tMax\tNote\nAces\t8\t20\tFirst set")
        self.assertEqual(rows, [{"label":"Aces", "value":"8", "max":"20", "sublabel":"First set"}])
    def test_parse_comparison_rows(self):
        rows = parse_comparison_rows("Metric\tA\tB\tMax\tUnit\nSpeed\t154\t155\t250\tKMH", True)
        self.assertEqual(rows[0]["unit"], "KMH")
        self.assertEqual(rows[0]["value_b"], "155")
    def test_parse_player_stats(self):
        rows = parse_player_stats("Metric\tValue\tUnit\tMax\nServe\t218\tKMH\t300")
        self.assertEqual(rows[0], {"label":"Serve", "value":"218", "unit":"KMH", "max":"300"})

class _TestRenderer(unittest.TestCase):
    def _cfg(self, **kw):
        c = copy.deepcopy(DEFAULT_CFG)
        c["stat_rows"] = [{"label":"A","value":"72 %","max":"100","sublabel":""}]
        c.update(kw); return c

    def test_render_default(self):
        img, hb = Renderer.render(self._cfg())
        self.assertEqual(img.size, (1024,576))
        self.assertIsInstance(hb, dict)

    def test_render_square(self):
        img, _ = Renderer.render(self._cfg(canvas_preset="1:1   (1024×1024)"))
        self.assertEqual(img.size,(1024,1024))

    def test_all_themes(self):
        for name in THEMES:
            img, _ = Renderer.render(self._cfg(theme_name=name))
            self.assertIsInstance(img, Image.Image)

    def test_score_block(self):
        img, hb = Renderer.render(self._cfg(show_score_block=True))
        self.assertIsInstance(img, Image.Image)
        self.assertIn("score", hb)

    def test_left_panel(self):
        img, _ = Renderer.render(self._cfg(panel_side="left"))
        self.assertEqual(img.size,(1024,576))

    def test_accent_override(self):
        img, _ = Renderer.render(self._cfg(accent_override="#ff0000"))
        self.assertIsInstance(img, Image.Image)

    def test_watermark(self):
        img, hb = Renderer.render(self._cfg(watermark_text="© VETO"))
        self.assertIsInstance(img, Image.Image)
        self.assertIn("wm_text", hb)

    def test_glass_shadow(self):
        img, _ = Renderer.render(self._cfg(glassmorphism=False, drop_shadow=False))
        self.assertIsInstance(img, Image.Image)

    def test_gradient_vertical(self):
        img, _ = Renderer.render(self._cfg(panel_gradient_dir="vertical"))
        self.assertIsInstance(img, Image.Image)

    def test_photo_treatments(self):
        for t in ["none","blur_edges","vignette","grayscale","sepia"]:
            img, _ = Renderer.render(self._cfg(photo_treatment=t))
            self.assertIsInstance(img, Image.Image)

    def test_scale_2x(self):
        base, hb1 = Renderer.render(self._cfg(), scale=1)
        img, hb2 = Renderer.render(self._cfg(), scale=2)
        self.assertEqual(img.size,(2048,1152))
        width1 = hb1["title"][2] - hb1["title"][0]
        width2 = hb2["title"][2] - hb2["title"][0]
        self.assertAlmostEqual(width2 / width1, 2.0, delta=.1)

    def test_dense_rows_do_not_overlap(self):
        cfg = self._cfg(stat_rows=[
            {"label":f"Long metric label {i}", "value":f"{i * 11} percent",
             "max":"100", "sublabel":"Supporting detail"}
            for i in range(10)
        ])
        _, hb = Renderer.render(cfg)
        boxes = [hb[f"row_{i}"] for i in range(10)]
        self.assertTrue(all(boxes[i][3] <= boxes[i+1][1] for i in range(9)))

    def test_row_spacing_changes_layout(self):
        rows = [
            {"label":f"Metric {i}", "value":"50", "max":"100", "sublabel":""}
            for i in range(3)
        ]
        _, compact = Renderer.render(self._cfg(stat_rows=rows, spacing_rows=0))
        _, open_ = Renderer.render(self._cfg(stat_rows=rows, spacing_rows=8))
        self.assertNotEqual(compact["row_1"][1], open_["row_1"][1])

    def test_long_title_fits_panel(self):
        cfg = self._cfg(title="An Extremely Long Championship Scoreboard Headline That Must Fit Automatically")
        _, hb = Renderer.render(cfg)
        panel_right = 1024
        self.assertLessEqual(hb["title"][2], panel_right)

    def test_vignette_keeps_center_brighter(self):
        photo = Image.new("RGB", (100, 100), (255,255,255))
        treated = Renderer._apply_treatment(photo, "vignette", 100, 100)
        self.assertGreater(treated.getpixel((50,50))[0], treated.getpixel((0,0))[0])

    def test_hitboxes_for_rows(self):
        img, hb = Renderer.render(self._cfg())
        self.assertIn("row_0", hb)
        self.assertIn("title", hb)

    def test_position_override(self):
        """Elements with a position override should use it."""
        cfg = self._cfg(positions={"title": [10.0, 20.0]})
        img, hb = Renderer.render(cfg)
        # title hitbox x should be near 10% of 1024 = ~102
        self.assertAlmostEqual(hb["title"][0], 102, delta=5)

    def test_hidden_layer_is_not_painted_or_selectable(self):
        cfg = self._cfg(layer_states={"title": {"visible": False, "locked": False}})
        _, hitboxes = Renderer.render(cfg)
        self.assertNotIn("title", hitboxes)

    def test_layer_order_is_preserved(self):
        cfg = self._cfg(layer_order=["row_0", "title"])
        self.assertEqual(normalised_layer_order(cfg), ["row_0", "title"])

    def test_layer_order_changes_overlap_pixels(self):
        shared = {"title": [62.0, 20.0], "row_0": [62.0, 20.0]}
        back_title, _ = Renderer.render(self._cfg(
            positions=shared, layer_order=["title", "row_0"]
        ))
        front_title, _ = Renderer.render(self._cfg(
            positions=shared, layer_order=["row_0", "title"]
        ))
        self.assertNotEqual(back_title.tobytes(), front_title.tobytes())


class _TestUnifiedRenderer(unittest.TestCase):
    def test_every_template_renders_at_native_size(self):
        cfg = _normalise_config({})
        for template in TEMPLATE_NAMES:
            current = copy.deepcopy(cfg)
            current["template_name"] = template
            image, hitboxes = UnifiedRenderer.render(current)
            self.assertEqual(image.size, active_canvas_size(current))
            self.assertTrue(hitboxes)

    def test_comparison_template_scales_natively(self):
        cfg = _normalise_config({"template_name": "Head-to-Head Insights"})
        image, hitboxes = UnifiedRenderer.render(cfg, scale=2)
        width, height = active_canvas_size(cfg)
        self.assertEqual(image.size, (width*2, height*2))
        self.assertEqual(hitboxes["template_artwork"], (0, 0, width*2, height*2))

class _TestUndo(unittest.TestCase):
    def test_undo_redo(self):
        s = UndoStack(); s.push({"v":1}); s.push({"v":2}); s.push({"v":3})
        self.assertEqual(s.undo()["v"],2); self.assertEqual(s.undo()["v"],1)
        self.assertIsNone(s.undo()); self.assertEqual(s.redo()["v"],2)

    def test_branch(self):
        s = UndoStack(); s.push({"v":1}); s.push({"v":2}); s.undo()
        s.push({"v":99}); self.assertFalse(s.can_redo)


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Scoreboard Generator v5.0")
    ap.add_argument("--test",     action="store_true", help="Run unit tests")
    ap.add_argument("--headless", metavar="OUT.png",   help="Render to file, no GUI")
    ap.add_argument("--template", choices=TEMPLATE_NAMES,
                    help="Template to use with --headless")
    ap.add_argument("--render-all", metavar="OUT_DIR",
                    help="Render every template to a directory")
    args = ap.parse_args()

    if args.test:
        print("Running test suite...")
        suite = unittest.TestLoader().loadTestsFromTestCase
        all_  = unittest.TestSuite([
            *suite(_TestHelpers)._tests,
            *suite(_TestRenderer)._tests,
            *suite(_TestUnifiedRenderer)._tests,
            *suite(_TestUndo)._tests,
        ])
        res = unittest.TextTestRunner(verbosity=2).run(all_)
        sys.exit(0 if res.wasSuccessful() else 1)

    if args.render_all:
        cfg = load_config()
        output_dir = Path(args.render_all)
        output_dir.mkdir(parents=True, exist_ok=True)
        for template in TEMPLATE_NAMES:
            current = copy.deepcopy(cfg)
            current["template_name"] = template
            img, _ = UnifiedRenderer.render(current)
            output = output_dir / (template.lower().replace(" ", "_").replace("-", "_") + ".png")
            img.save(output, format="PNG")
            print(f"Rendered: {output}")
        audit("HEADLESS_ALL", str(output_dir))
        return

    if args.headless:
        cfg = load_config()
        if args.template:
            cfg["template_name"] = args.template
        img, _ = UnifiedRenderer.render(cfg)
        Path(args.headless).parent.mkdir(parents=True, exist_ok=True)
        img.save(args.headless, format="PNG")
        print(f"Rendered: {args.headless}")
        audit("HEADLESS", args.headless)
        return

    if not GUI_AVAILABLE:
        sys.exit("GUI libraries missing.  Install:  pip install customtkinter tkinterdnd2\n"
                 "Or use --headless for CLI rendering.")

    app = ScoreboardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
