#!/usr/bin/env python3
"""
Scoreboard / Match Stats Card Generator — FINAL MERGED BUILD v3.0
==================================================================
Merged from:
  • v2.0 (mine)   — audit log, undo/redo, themes, photo treatments,
                    score block, watermark, stat presets, sub-labels,
                    batch export, headless CLI, 17 unit tests
  • Pro Edition 1 — customtkinter UI, tkinterdnd2 DnD, threaded render
                    pipeline, background cache, font dropdown + .ttf browse,
                    row duplicate, PNG/JPEG/WebP export, 1x/2x/4x scale
  • Pro Edition 2 — glassmorphism blur panel, drop shadow, numpy gradient
                    fast-path, spacing/margin sliders, panel gradient dir,
                    JSON load/save/reset, photo fit (cover/contain/stretch),
                    draggable PNG overlay with canvas drag

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
    from tkinter import colorchooser, filedialog, messagebox
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

AUDIT_PATH = Path("audit.log")
_audit = logging.getLogger("audit")
_audit.setLevel(logging.DEBUG)
_fh = logging.FileHandler(AUDIT_PATH, encoding="utf-8")
_fh.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
))
_audit.addHandler(_fh)
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

CONFIG_PATH = Path("scoreboard_config.json")

DEFAULT_CFG: Dict[str, Any] = {
    # canvas
    "canvas_preset":   "16:9  (1024×576)",
    "export_scale":    1,           # 1x | 2x | 4x
    "export_format":   "PNG",       # PNG | JPEG | WebP
    "export_quality":  95,
    # photo / overlay
    "photo_path":       "",
    "photo_fit":        "cover",    # cover | contain | stretch
    "photo_treatment":  "none",     # none | blur_edges | vignette | grayscale | sepia
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
    # rows
    "stat_rows": [],
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


def rgb_lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))


def clamp_rgb(c: RGB) -> RGB:
    return (max(0,min(255,c[0])), max(0,min(255,c[1])), max(0,min(255,c[2])))


def hex_to_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))


def rgb_to_hex(c: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


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

def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = {**DEFAULT_CFG, **saved}
            audit("CONFIG_LOAD", str(path))
            return cfg
        except Exception as e:
            audit("CONFIG_LOAD_ERROR", str(e))
    return copy.deepcopy(DEFAULT_CFG)


def save_config(cfg: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
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
    _bg_cache: Optional[Image.Image] = None
    _bg_key:   Optional[tuple]       = None

    # ── background ───────────────────────────────────────────────────────

    @classmethod
    def get_background(cls, cfg: Dict, W: int, H: int) -> Image.Image:
        theme = THEMES.get(cfg["theme_name"], THEMES["Dark Pro"])
        key = (cfg["photo_path"], W, H, cfg["photo_fit"],
               cfg["photo_treatment"], tuple(theme.bg))
        if cls._bg_key == key and cls._bg_cache:
            return cls._bg_cache.copy()

        img = Image.new("RGB", (W, H), theme.bg)
        p = cfg["photo_path"]
        if p and Path(p).exists():
            try:
                photo = Image.open(p).convert("RGB")
                fit = cfg.get("photo_fit", "cover")
                pw, ph = photo.size
                if fit == "cover":
                    if pw/ph > W/H:
                        nh, nw = H, int(pw*H/ph)
                    else:
                        nw, nh = W, int(ph*W/pw)
                    photo = photo.resize((nw, nh), Image.LANCZOS)
                    photo = photo.crop(((nw-W)//2, (nh-H)//2,
                                        (nw-W)//2+W, (nh-H)//2+H))
                elif fit == "contain":
                    photo.thumbnail((W, H), Image.LANCZOS)
                    img.paste(photo, ((W-photo.width)//2,
                                      (H-photo.height)//2))
                    photo = None
                else:  # stretch
                    photo = photo.resize((W, H), Image.LANCZOS)

                if photo:
                    photo = cls._apply_treatment(photo, cfg["photo_treatment"], W, H)
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
            vig = Image.new("L", (W, H), 255)
            vd  = ImageDraw.Draw(vig)
            for i in range(80):
                t  = i/80; pad_x, pad_y = int(W*.5*t), int(H*.5*t)
                vd.rectangle([pad_x, pad_y, W-pad_x, H-pad_y],
                              fill=int(255*(1-t**1.8)))
            vig = vig.filter(ImageFilter.GaussianBlur(40))
            return Image.composite(photo, Image.new("RGB",(W,H),(0,0,0)), vig)
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

    # ── score block ───────────────────────────────────────────────────────

    @staticmethod
    def _draw_score_block(draw, cfg, theme, accent, tx, tw, H, fam, bp, rp):
        sf  = get_font(max(14, int(H*.032)), bold=True,  family=fam, custom_path=bp)
        scf = get_font(max(28, int(H*.065)), bold=True,  family=fam, custom_path=bp)
        inf = get_font(max(11, int(H*.022)), bold=False, family=fam, custom_path=rp)
        y   = int(H*.06)
        ta, tb  = cfg.get("team_a","A"), cfg.get("team_b","B")
        sc, mi  = cfg.get("score","0–0"), cfg.get("match_info","")

        draw.text((tx, y), ta, font=sf, fill=theme.title)
        bbtb = draw.textbbox((0,0), tb, font=sf)
        draw.text((tx+tw-(bbtb[2]-bbtb[0]), y), tb, font=sf, fill=theme.title)
        y += (bbtb[3]-bbtb[1]) + int(H*.01)

        sbb = draw.textbbox((0,0), sc, font=scf)
        draw.text((tx+(tw-(sbb[2]-sbb[0]))//2, y), sc, font=scf, fill=accent)
        y += (sbb[3]-sbb[1]) + int(H*.006)

        if mi:
            ibb = draw.textbbox((0,0), mi, font=inf)
            draw.text((tx+(tw-(ibb[2]-ibb[0]))//2, y), mi, font=inf, fill=theme.label)
            y += (ibb[3]-ibb[1]) + int(H*.01)

        sep = y + int(H*.01)
        draw.line([(tx,sep),(tx+tw,sep)], fill=(*accent,120),
                  width=max(1,int(H*.003)))
        return sep + int(H*.025)

    # ── watermark ─────────────────────────────────────────────────────────

    @staticmethod
    def _apply_watermark(img: Image.Image, cfg: Dict) -> Image.Image:
        wt  = cfg.get("watermark_text","").strip()
        wl  = cfg.get("watermark_logo_path","").strip()
        wa  = max(10, min(255, cfg.get("watermark_opacity",100)))
        W, H = img.size

        if wt:
            lay = Image.new("RGBA",(W,H),(0,0,0,0))
            wd  = ImageDraw.Draw(lay)
            wf  = get_font(max(14,int(H*.028)), bold=True)
            bb  = wd.textbbox((0,0), wt, font=wf)
            wd.text((W-(bb[2]-bb[0])-int(W*.025),
                     H-(bb[3]-bb[1])-int(H*.025)),
                    wt, font=wf, fill=(255,255,255,wa))
            img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")

        if wl and Path(wl).exists():
            try:
                logo = Image.open(wl).convert("RGBA")
                mh   = int(H*.08)
                logo = logo.resize((int(logo.width*mh/logo.height), mh), Image.LANCZOS)
                r,g,b,a = logo.split()
                logo.putalpha(a.point(lambda p: int(p*wa/255)))
                img = img.convert("RGBA")
                img.paste(logo, (int(W*.025), H-mh-int(H*.025)), logo)
                img = img.convert("RGB")
            except Exception: pass
        return img

    # ── main render ───────────────────────────────────────────────────────

    @classmethod
    def render(cls, cfg: Dict, scale: int = 1) -> Image.Image:
        bw, bh = CANVAS_SIZES.get(cfg["canvas_preset"], (1024,576))
        W, H   = bw*scale, bh*scale

        theme  = THEMES.get(cfg["theme_name"], THEMES["Dark Pro"])
        acc_h  = cfg.get("accent_override","").strip()
        accent: RGB = (clamp_rgb(hex_to_rgb(acc_h))
                       if acc_h and acc_h.startswith("#") else theme.accent)

        fam  = cfg.get("font_family","Arial")
        bp   = cfg.get("font_bold_path","")
        rp   = cfg.get("font_regular_path","")

        panel_pct  = max(20, min(70, cfg["panel_width_pct"]))
        panel_w    = int(W * panel_pct / 100)
        panel_side = cfg["panel_side"]
        pan_alpha  = min(255, cfg["panel_opacity"])
        direction  = cfg.get("panel_gradient_dir","horizontal_fade")

        # ── background ──────────────────────────────────────────────────
        img = cls.get_background(cfg, W, H)

        # ── PNG overlay (draggable player/subject) ───────────────────────
        ol = cfg.get("overlay_path","").strip()
        if ol and Path(ol).exists():
            try:
                ov  = Image.open(ol).convert("RGBA")
                th  = int(H * cfg.get("overlay_scale",80) / 100)
                tw_ = int(ov.width * th / ov.height)
                if tw_ > 0 and th > 0:
                    ov   = ov.resize((tw_, th), Image.LANCZOS)
                    px   = int(W * cfg.get("overlay_x",5) / 100)
                    py   = int(H * cfg.get("overlay_y",5) / 100)
                    tmp  = Image.new("RGBA",(W,H),(0,0,0,0))
                    tmp.paste(ov, (px, py), ov)
                    img  = Image.alpha_composite(img.convert("RGBA"), tmp).convert("RGB")
            except Exception as e:
                audit("OVERLAY_ERROR", str(e))

        # ── panel placement ──────────────────────────────────────────────
        x0 = W - panel_w if panel_side == "right" else 0

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

        draw = ImageDraw.Draw(img,"RGBA")

        # ── text column ─────────────────────────────────────────────────
        mx = int(panel_w * cfg["margin_x"] / 100)
        tx = x0 + mx
        tw = panel_w - 2*mx

        def tsize(key: str, frac: float, floor_: int) -> int:
            ov = cfg.get(key, 0)
            return int(ov) if ov else max(floor_, int(H*frac))

        title_sz = tsize("title_size", 0.082, 24)*scale
        label_sz = tsize("label_size", 0.036, 13)*scale
        value_sz = tsize("value_size", 0.072, 22)*scale
        sub_sz   = max(12, int(label_sz * .8))

        tf   = get_font(title_sz, bold=True,  family=fam, custom_path=bp)
        lf   = get_font(label_sz, bold=False, family=fam, custom_path=rp)
        vf   = get_font(value_sz, bold=True,  family=fam, custom_path=bp)
        sf_  = get_font(sub_sz,   bold=False, family=fam, custom_path=rp)
        sl_f = get_font(max(10*scale, int(H*.022*scale)),
                        bold=False, family=fam, custom_path=rp)

        my_px = int(H * cfg["margin_y"] / 100)
        cur_y = my_px

        # ── score block ─────────────────────────────────────────────────
        if cfg.get("show_score_block"):
            cur_y = cls._draw_score_block(draw, cfg, theme, accent, tx, tw, H, fam, bp, rp)

        # ── subtitle ────────────────────────────────────────────────────
        sub = cfg.get("subtitle","").strip()
        if sub:
            draw.text((tx,cur_y), sub.upper(), font=sf_, fill=accent)
            bb = draw.textbbox((0,0), sub.upper(), font=sf_)
            cur_y += (bb[3]-bb[1]) + int(H * cfg["spacing_items"] / 100)

        # ── title ───────────────────────────────────────────────────────
        for line in cfg["title"].replace("\\n","\n").split("\n"):
            draw.text((tx,cur_y), line, font=tf, fill=theme.title)
            bb = draw.textbbox((0,0), line, font=tf)
            cur_y += (bb[3]-bb[1]) + int(title_sz*.22)
        cur_y += int(H * cfg["spacing_title"] / 100)

        # ── stat rows ───────────────────────────────────────────────────
        rows  = cfg.get("stat_rows",[])
        n     = max(1, len(rows))
        avail = H - cur_y - int(H*.04)
        slot  = avail / n
        bar_h = max(4*scale, int(H*.013))
        sip   = int(H * cfg["spacing_items"] / 100)
        srp   = int(H * cfg["spacing_rows"]  / 100)

        for row in rows:
            sy = cur_y
            lbl = row.get("label","")
            val = row.get("value","0")
            sub2= row.get("sublabel","")
            pct = auto_percent(val, row.get("max","100"))

            draw.text((tx,sy), lbl, font=lf, fill=theme.label)
            bb = draw.textbbox((0,0), lbl, font=lf)
            sy += (bb[3]-bb[1]) + sip

            if sub2:
                draw.text((tx,sy), sub2, font=sl_f, fill=(*theme.label[:3],150))
                bb2 = draw.textbbox((0,0), sub2, font=sl_f)
                sy += (bb2[3]-bb2[1]) + sip

            draw.text((tx,sy), val, font=vf, fill=accent)
            vbb = draw.textbbox((0,0), val, font=vf)
            sy += (vbb[3]-vbb[1]) + sip

            by0, by1 = sy, sy+bar_h
            draw.rounded_rectangle([tx,by0,tx+tw,by1],
                radius=bar_h//2, fill=(*theme.bar_track,200))
            fw = int(tw*pct/100)
            if fw >= bar_h:
                draw.rounded_rectangle([tx,by0,tx+fw,by1],
                    radius=bar_h//2, fill=accent)

            cur_y += slot

        # ── watermark ───────────────────────────────────────────────────
        img = cls._apply_watermark(img, cfg)
        return img


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


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

if GUI_AVAILABLE:
    class ScoreboardApp(TkinterDnD.Tk):
        def __init__(self):
            super().__init__()
            self.title("Match Stats Studio — Final v3.0")
            self.geometry("1560x960")
            self.minsize(1200,720)

            # DnD
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_file_drop)

            self.cfg   = load_config()
            self._undo = UndoStack()
            self._undo.push(self.cfg)

            self._stat_widgets: List[StatRowWidget] = []
            self._tk_img       = None
            self._last_render  = None
            self._drag         = {"x":0,"y":0,"active":False}
            self._preview_scale = 1.0
            self._render_q     = queue.Queue()
            self._redraw_timer = None
            self._cfg_path: Optional[str] = None

            self._build_ui()
            self._apply_cfg_to_ui()
            self._rebuild_row_widgets()
            self._start_render_worker()
            self.schedule_redraw()

            self.bind("<Control-z>", lambda _: self._undo_action())
            self.bind("<Control-y>", lambda _: self._redo_action())
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            audit("APP_START","")

        # ── DnD ─────────────────────────────────────────────────────────

        def _on_file_drop(self, event):
            p = event.data.strip("{}")
            ext = Path(p).suffix.lower()
            if ext not in (".png",".jpg",".jpeg",".webp",".bmp"): return
            if ext == ".png":
                self.cfg["overlay_path"] = p
                self._status(f"Overlay loaded: {Path(p).name}")
            else:
                self.cfg["photo_path"] = p
                self._img_lbl.configure(text=Path(p).name)
                self._status(f"Background loaded: {Path(p).name}")
            self.schedule_redraw()
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
                text="Live Preview  ·  Drop JPG/PNG here  ·  Drag overlay with mouse",
                font=("Arial",13,"bold"), text_color="#666"
            ).pack(pady=(14,0))
            self.preview_canvas = tk.Canvas(
                self.preview_panel, bg="#1a1a1a", highlightthickness=0)
            self.preview_canvas.pack(padx=16, pady=12, fill="both", expand=True)
            self.preview_canvas.bind("<ButtonPress-1>",   self._drag_start)
            self.preview_canvas.bind("<B1-Motion>",       self._drag_move)
            self.preview_canvas.bind("<ButtonRelease-1>", self._drag_end)

            self._build_toolbar()
            self._build_preset_section()
            self._build_file_section()
            self._build_image_section()
            self._build_content_section()
            self._build_score_section()
            self._build_watermark_section()
            self._build_theme_section()
            self._build_layout_section()
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
                ("💾 Save PNG", self.export_png),
                ("📦 Batch",    self.batch_export),
                ("📋 Audit Log",self._show_audit),
            ]:
                ctk.CTkButton(tb, text=txt, command=cmd, width=90,
                              height=28).pack(side="left", padx=3, pady=4)

        def _build_preset_section(self):
            sec = self._sec("Quick Presets")
            row = ctk.CTkFrame(sec, fg_color="transparent"); row.pack(fill="x")
            ctk.CTkLabel(row, text="Theme preset:").pack(side="left")
            ctk.CTkComboBox(row, values=list(THEMES.keys()), width=180,
                            command=lambda v: self._apply_theme_preset(v)
                            ).pack(side="left", padx=6)
            ctk.CTkLabel(row, text="Sport:").pack(side="left", padx=(12,4))
            ctk.CTkComboBox(row, values=list(STAT_PRESETS.keys()), width=130,
                            command=lambda v: self._apply_stat_preset(v)
                            ).pack(side="left")

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

            r2 = ctk.CTkFrame(sec, fg_color="transparent"); r2.pack(fill="x", pady=4)
            ctk.CTkButton(r2, text="Browse Overlay PNG",
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
            ctk.CTkComboBox(r0, variable=self._canvas_var,
                            values=list(CANVAS_SIZES.keys()), width=220,
                            command=lambda _: self._on_change()
                            ).pack(side="left", padx=6)
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

        def _build_rows_section(self):
            sec = self._sec("Stat Metrics & Data Rows")
            self._rows_frame = ctk.CTkFrame(sec, fg_color="transparent")
            self._rows_frame.pack(fill="x")
            btn_r = ctk.CTkFrame(sec, fg_color="transparent"); btn_r.pack(fill="x", pady=4)
            ctk.CTkButton(btn_r, text="+ Add Row",
                          command=lambda: self._add_row()).pack(side="left", padx=4)
            ctk.CTkButton(btn_r, text="Clear All",
                          command=self._clear_rows,
                          fg_color="#A33", hover_color="#D44").pack(side="left", padx=4)

        def _build_export_section(self):
            sec = self._sec("Export")
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

        # ── canvas drag (overlay repositioning) ──────────────────────────

        def _drag_start(self, e):
            self._drag.update(x=e.x, y=e.y, active=True)

        def _drag_move(self, e):
            if not self._drag["active"]: return
            dx, dy = e.x-self._drag["x"], e.y-self._drag["y"]
            self._drag.update(x=e.x, y=e.y)
            bw, bh = CANVAS_SIZES.get(self.cfg["canvas_preset"],(1024,576))
            s = max(0.01, self._preview_scale)
            self.cfg["overlay_x"] += dx/s/bw*100
            self.cfg["overlay_y"] += dy/s/bh*100
            self.schedule_redraw()

        def _drag_end(self, _): self._drag["active"] = False

        # ── config sync ─────────────────────────────────────────────────

        def _collect_cfg(self) -> Dict:
            def si(v, d):
                try: return int(v)
                except: return d
            rows = [w.get_data() for w in self._stat_widgets]
            return {
                **self.cfg,
                "canvas_preset":    self._canvas_var.get(),
                "panel_side":       self._side_var.get(),
                "panel_width_pct":  int(self._pw_var.get()),
                "panel_opacity":    int(self._op_var.get()),
                "panel_gradient_dir": self._grad_var.get(),
                "glassmorphism":    self._glass_var.get(),
                "drop_shadow":      self._shadow_var.get(),
                "photo_fit":        self._fit_var.get(),
                "photo_treatment":  self._treat_var.get(),
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
                "export_format":  self._fmt_var.get(),
                "export_scale":   si(self._escale_var.get(),1),
                "export_quality": si(self._qual_var.get(),95),
                "stat_rows": rows,
            }

        def _apply_cfg_to_ui(self):
            c = self.cfg
            self._canvas_var.set(c["canvas_preset"])
            self._side_var.set(c["panel_side"])
            self._pw_var.set(c["panel_width_pct"])
            self._op_var.set(c["panel_opacity"])
            self._grad_var.set(c["panel_gradient_dir"])
            self._glass_var.set(c.get("glassmorphism",True))
            self._shadow_var.set(c.get("drop_shadow",True))
            self._fit_var.set(c.get("photo_fit","cover"))
            self._treat_var.set(c.get("photo_treatment","none"))
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
            widget.destroy()
            self._stat_widgets.remove(widget)
            self._on_change()

        def _clear_rows(self):
            for w in self._stat_widgets: w.destroy()
            self._stat_widgets.clear()
            self._add_row()

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
            for w in self._stat_widgets: w.pack_forget()
            for w in self._stat_widgets: w.pack(fill="x", pady=3)
            self._on_change()

        # ── change / undo flow ───────────────────────────────────────────

        def _on_change(self, _=None):
            self.cfg = self._collect_cfg()
            self._undo.push(self.cfg)
            save_config(self.cfg)
            self.schedule_redraw()

        def _undo_action(self):
            s = self._undo.undo()
            if s:
                self.cfg = s; self._apply_cfg_to_ui()
                self._rebuild_row_widgets(); self.redraw_now()
                self._status("Undo")

        def _redo_action(self):
            s = self._undo.redo()
            if s:
                self.cfg = s; self._apply_cfg_to_ui()
                self._rebuild_row_widgets(); self.redraw_now()
                self._status("Redo")

        # ── preset appliers ──────────────────────────────────────────────

        def _apply_theme_preset(self, name):
            self.cfg["theme_name"] = name
            self._on_change()
            audit("THEME_PRESET", name)

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
                filetypes=[("Images","*.jpg *.jpeg *.png *.webp *.bmp")])
            if p:
                self.cfg["photo_path"] = p
                self._img_lbl.configure(text=Path(p).name, text_color="#fff")
                self._on_change(); audit("BG_CHOSEN", p)

        def _browse_overlay(self):
            p = filedialog.askopenfilename(filetypes=[("PNG","*.png")])
            if p:
                self.cfg["overlay_path"] = p
                self._status(f"Overlay: {Path(p).name}")
                self._on_change(); audit("OVERLAY_CHOSEN", p)

        def _clear_overlay(self):
            self.cfg.update(overlay_path="", overlay_x=5.0, overlay_y=5.0)
            self._status("Overlay cleared"); self._on_change()

        def _browse_logo(self):
            p = filedialog.askopenfilename(
                filetypes=[("Images","*.png *.jpg *.jpeg *.webp")])
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
                    self.cfg = load_config(Path(p))
                    self._cfg_path = p
                    self._apply_cfg_to_ui()
                    self._rebuild_row_widgets()
                    self.schedule_redraw()
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
                self.cfg = copy.deepcopy(DEFAULT_CFG)
                self._apply_cfg_to_ui()
                self._rebuild_row_widgets()
                self._on_change()
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
                        cfg = self._render_q.get_nowait()
                    try:
                        img = Renderer.render(cfg, scale=1)
                        self.after(0, lambda i=img: self._update_preview(i))
                    except Exception as exc:
                        logger.error("Render error: %s", exc)
                        audit("RENDER_ERROR", traceback.format_exc())
                    finally:
                        self._render_q.task_done()
            threading.Thread(target=worker, daemon=True).start()

        def redraw_now(self):
            try:
                img = Renderer.render(self._collect_cfg(), scale=1)
                self._update_preview(img)
            except Exception as exc:
                self._status(f"Render error: {exc}")

        def _update_preview(self, img: Image.Image):
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
            self._status("Preview updated")

        # ── export ───────────────────────────────────────────────────────

        def export_png(self):
            cfg = self._collect_cfg()
            fmt = cfg["export_format"].lower()
            ext = "jpg" if fmt=="jpeg" else fmt
            p = filedialog.asksaveasfilename(
                defaultextension=f".{ext}",
                filetypes=[(cfg["export_format"], f"*.{ext}")],
                initialfile=f"scoreboard.{ext}")
            if p:
                try:
                    self._status("Exporting…"); self.update()
                    img = Renderer.render(cfg, scale=cfg["export_scale"])
                    kw = {"quality": cfg["export_quality"]} if fmt in ("jpeg","webp") else {}
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
            saved = []
            for preset in BATCH_PRESETS:
                try:
                    img = Renderer.render({**cfg,"canvas_preset":preset}, scale=1)
                    slug = preset.replace(":","_").replace(" ","_").replace("×","x")
                    out  = Path(folder)/f"scoreboard_{slug}.png"
                    img.save(out, format="PNG")
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

class _TestRenderer(unittest.TestCase):
    def _cfg(self, **kw):
        c = copy.deepcopy(DEFAULT_CFG)
        c["stat_rows"] = [{"label":"A","value":"72 %","max":"100","sublabel":""}]
        c.update(kw); return c

    def test_render_default(self):
        img = Renderer.render(self._cfg()); self.assertEqual(img.size,(1024,576))

    def test_render_square(self):
        img = Renderer.render(self._cfg(canvas_preset="1:1   (1024×1024)"))
        self.assertEqual(img.size,(1024,1024))

    def test_all_themes(self):
        for name in THEMES:
            img = Renderer.render(self._cfg(theme_name=name))
            self.assertIsInstance(img, Image.Image)

    def test_score_block(self):
        img = Renderer.render(self._cfg(show_score_block=True))
        self.assertIsInstance(img, Image.Image)

    def test_left_panel(self):
        img = Renderer.render(self._cfg(panel_side="left"))
        self.assertEqual(img.size,(1024,576))

    def test_accent_override(self):
        img = Renderer.render(self._cfg(accent_override="#ff0000"))
        self.assertIsInstance(img, Image.Image)

    def test_watermark(self):
        img = Renderer.render(self._cfg(watermark_text="© VETO"))
        self.assertIsInstance(img, Image.Image)

    def test_glass_shadow(self):
        img = Renderer.render(self._cfg(glassmorphism=False, drop_shadow=False))
        self.assertIsInstance(img, Image.Image)

    def test_gradient_vertical(self):
        img = Renderer.render(self._cfg(panel_gradient_dir="vertical"))
        self.assertIsInstance(img, Image.Image)

    def test_photo_treatments(self):
        for t in ["none","blur_edges","vignette","grayscale","sepia"]:
            self.assertIsInstance(Renderer.render(self._cfg(photo_treatment=t)), Image.Image)

    def test_scale_2x(self):
        img = Renderer.render(self._cfg(), scale=2)
        self.assertEqual(img.size,(2048,1152))

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
    ap = argparse.ArgumentParser(description="Scoreboard Generator v3.0")
    ap.add_argument("--test",     action="store_true", help="Run unit tests")
    ap.add_argument("--headless", metavar="OUT.png",   help="Render to file, no GUI")
    args = ap.parse_args()

    if args.test:
        print("Running test suite …")
        suite = unittest.TestLoader().loadTestsFromTestCase
        all_  = unittest.TestSuite([
            *suite(_TestHelpers)._tests,
            *suite(_TestRenderer)._tests,
            *suite(_TestUndo)._tests,
        ])
        res = unittest.TextTestRunner(verbosity=2).run(all_)
        sys.exit(0 if res.wasSuccessful() else 1)

    if args.headless:
        cfg = load_config()
        img = Renderer.render(cfg)
        img.save(args.headless, format="PNG")
        print(f"Rendered → {args.headless}")
        audit("HEADLESS", args.headless)
        return

    if not GUI_AVAILABLE:
        sys.exit("GUI libraries missing.  Install:  pip install customtkinter tkinterdnd2\n"
                 "Or use --headless for CLI rendering.")

    app = ScoreboardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
