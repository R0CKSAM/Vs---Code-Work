#!/usr/bin/env python3
"""
Scoreboard / Match Stats Studio (Broadcast Edition)
===================================================
A modular, broadcast-grade graphics suite to generate TV-ready
sports match statistics, leaderboards, and head-to-head scorecards.

Architecture:
- Data Models: ScoreboardConfig, PlayerData, H2HStatRow (Type-safe & JSON serializable)
- GraphicsKit: Procedural arena lighting, glassmorphic cards, comparison bars, flag badges
- Layout Engines:
    * ATPHeadToHeadRenderer (Image 1: H2H with Ratings & Dual Bars)
    * ServiceGridRenderer (Image 2: 3-Col Service & Set Breakdown)
    * ShotBreakdownRenderer (Image 3: Winners/Errors & Points Matrix)
    * ClassicSidebarRenderer (Original Layout preserved)
- Interface:
    * Desktop GUI (ScoreboardStudioApp with modern Dark UI & Toggle Switches)
    * Headless CLI & Python API for technical automation
"""

import argparse
import json
import logging
import math
import os
import queue
import re
import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter, ImageOps

# Optional NumPy for accelerated numerical processing
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ------------------------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ScoreboardStudio")

# ------------------------------------------------------------------------------
# Constants, Aspect Ratios & Modes
# ------------------------------------------------------------------------------
ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "16:9 Broadcast (1920x1080)": (1920, 1080),
    "16:9 Landscape (1280x720)": (1280, 720),
    "16:9 Compact (1024x576)": (1024, 576),
    "1:1 Square (1080x1080)": (1080, 1080),
    "9:16 Social Story (1080x1920)": (1080, 1920),
    "4:5 Feed Portrait (1080x1350)": (1080, 1350),
}

LAYOUT_MODES = {
    "h2h_broadcast": "ATP Head-to-Head (Image 1)",
    "service_table": "Service & Match Grid (Image 2)",
    "shot_breakdown": "Winners & Shot Analysis (Image 3)",
    "classic_sidebar": "Classic Single Card (Original)",
}

# ------------------------------------------------------------------------------
# Built-In Presets
# ------------------------------------------------------------------------------
PRESET_THEMES: Dict[str, Dict[str, Any]] = {
    "ATP Brisbane Blue (Image 1)": {
        "layout_mode": "h2h_broadcast",
        "bg_color": [7, 16, 38],
        "panel_top_color": [10, 24, 54],
        "panel_bottom_color": [5, 12, 28],
        "accent_color": [223, 255, 60],        # Electric Lime / Neon Yellow
        "secondary_accent": [0, 102, 255],      # Royal Tennis Blue
        "highlight_color": [223, 255, 60],
        "bar_track_color": [30, 48, 80],
        "title_color": [255, 255, 255],
        "label_color": [215, 228, 245],
    },
    "Winston-Salem Dark (Image 2)": {
        "layout_mode": "service_table",
        "bg_color": [14, 23, 38],
        "panel_top_color": [22, 36, 60],
        "panel_bottom_color": [10, 16, 28],
        "accent_color": [223, 255, 60],        # Ball Lime
        "secondary_accent": [40, 80, 130],
        "highlight_color": [223, 255, 60],
        "bar_track_color": [45, 65, 95],
        "title_color": [255, 255, 255],
        "label_color": [200, 215, 230],
    },
    "Rome Masters 1000 (Image 3)": {
        "layout_mode": "shot_breakdown",
        "bg_color": [12, 20, 32],
        "panel_top_color": [18, 30, 48],
        "panel_bottom_color": [8, 14, 24],
        "accent_color": [223, 255, 60],
        "secondary_accent": [0, 190, 120],      # Italian Green
        "highlight_color": [223, 255, 60],
        "bar_track_color": [40, 60, 85],
        "title_color": [255, 255, 255],
        "label_color": [220, 230, 240],
    },
    "US Open Night Session": {
        "layout_mode": "h2h_broadcast",
        "bg_color": [5, 12, 28],
        "panel_top_color": [12, 28, 62],
        "panel_bottom_color": [3, 8, 20],
        "accent_color": [245, 210, 40],        # Bright Gold
        "secondary_accent": [0, 85, 215],
        "highlight_color": [245, 210, 40],
        "bar_track_color": [25, 45, 75],
        "title_color": [255, 255, 255],
        "label_color": [220, 235, 255],
    },
    "Cyberpunk Neon": {
        "layout_mode": "h2h_broadcast",
        "bg_color": [15, 6, 28],
        "panel_top_color": [26, 10, 45],
        "panel_bottom_color": [8, 2, 16],
        "accent_color": [0, 255, 240],         # Cyan
        "secondary_accent": [255, 0, 128],      # Magenta
        "highlight_color": [255, 0, 128],
        "bar_track_color": [60, 20, 80],
        "title_color": [255, 255, 255],
        "label_color": [245, 240, 255],
    },
    "Wimbledon Lawn Green": {
        "layout_mode": "h2h_broadcast",
        "bg_color": [8, 28, 16],
        "panel_top_color": [12, 40, 24],
        "panel_bottom_color": [5, 18, 10],
        "accent_color": [235, 200, 75],         # Gold
        "secondary_accent": [90, 50, 130],      # Purple
        "highlight_color": [235, 200, 75],
        "bar_track_color": [25, 65, 40],
        "title_color": [255, 255, 255],
        "label_color": [215, 235, 220],
    },
    "Roland Garros Clay": {
        "layout_mode": "shot_breakdown",
        "bg_color": [36, 18, 12],
        "panel_top_color": [54, 28, 18],
        "panel_bottom_color": [24, 10, 6],
        "accent_color": [255, 195, 85],         # Clay Gold
        "secondary_accent": [180, 60, 30],      # Terracotta
        "highlight_color": [255, 210, 90],
        "bar_track_color": [80, 45, 35],
        "title_color": [255, 255, 255],
        "label_color": [245, 225, 215],
    },
    "Minimal Light Broadcast": {
        "layout_mode": "h2h_broadcast",
        "bg_color": [238, 242, 246],
        "panel_top_color": [255, 255, 255],
        "panel_bottom_color": [230, 235, 242],
        "accent_color": [0, 102, 255],
        "secondary_accent": [16, 185, 129],
        "highlight_color": [0, 102, 255],
        "bar_track_color": [205, 215, 225],
        "title_color": [15, 23, 42],
        "label_color": [51, 65, 85],
    }
}

# ------------------------------------------------------------------------------
# Data Models (Type-Safe & JSON Serializable)
# ------------------------------------------------------------------------------
@dataclass
class PlayerData:
    name: str = "Player"
    country: str = "USA"
    rating: str = "8.0"
    sets: List[str] = field(default_factory=lambda: ["6", "6"])
    photo_path: str = ""


@dataclass
class ScoreboardConfig:
    # Layout Mode
    layout_mode: str = "h2h_broadcast"

    # Tournament & Match Header
    tournament_name: str = "BRISBANE INTERNATIONAL"
    tournament_badge: str = "ATP 250"
    round_text: str = "ROUND 1"
    match_time: str = "0:59'"
    title_text: str = "MATCH STATISTICS"
    subtitle_text: str = "FINAL RESULTS"

    # Players
    player1: PlayerData = field(default_factory=lambda: PlayerData(
        name="ALEKSANDAR VUKIC", country="AUS", rating="6.5", sets=["2", "2"]
    ))
    player2: PlayerData = field(default_factory=lambda: PlayerData(
        name="FRANCES TIAFOE", country="USA", rating="8.8", sets=["6", "6"]
    ))

    # Feature Toggles (Controlled by Switches)
    show_player_photos: bool = True
    show_ratings: bool = True
    show_flags: bool = True
    show_header_banner: bool = True
    show_comparison_bars: bool = True
    auto_highlight_leader: bool = True
    show_summary_table: bool = True
    show_bg_photo: bool = False
    dark_overlay: bool = True

    # Background photo & Classic sidebar controls (Backward compatible)
    photo_path: str = ""
    photo_fit: str = "cover"
    panel_side: str = "right"
    panel_width_ratio: float = 0.42
    panel_opacity: float = 0.92

    # Color Palette
    bg_color: List[int] = field(default_factory=lambda: [7, 16, 38])
    panel_top_color: List[int] = field(default_factory=lambda: [10, 24, 54])
    panel_bottom_color: List[int] = field(default_factory=lambda: [5, 12, 28])
    accent_color: List[int] = field(default_factory=lambda: [223, 255, 60])        # Neon Lime / Yellow
    secondary_accent: List[int] = field(default_factory=lambda: [0, 102, 255])    # Blue
    highlight_color: List[int] = field(default_factory=lambda: [223, 255, 60])
    bar_track_color: List[int] = field(default_factory=lambda: [30, 48, 80])
    title_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    label_color: List[int] = field(default_factory=lambda: [215, 228, 245])

    # Typography Font Sizes (Base scale for 1920x1080)
    title_font_size: int = 42
    label_font_size: int = 22
    value_font_size: int = 34
    font_bold_path: str = ""
    font_regular_path: str = ""

    # Mode 1: H2H Categorized Stats (Image 1 Style)
    h2h_rows: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"category": "SERVE", "label": "QUALITY", "val1": "7.7", "val2": "8.8", "max_val": "10.0"},
        {"category": "SERVE", "label": "UNRETURNED %", "val1": "23%", "val2": "41%", "max_val": "100"},
        {"category": "FIRST SERVE", "label": "IN %", "val1": "57%", "val2": "72%", "max_val": "100"},
        {"category": "FIRST SERVE", "label": "POINTS WON %", "val1": "58%", "val2": "82%", "max_val": "100"},
        {"category": "SECOND SERVE", "label": "POINTS WON %", "val1": "35%", "val2": "82%", "max_val": "100"},
        {"category": "SECOND SERVE", "label": "AVERAGE SPEED (km/h)", "val1": "164", "val2": "139", "max_val": "220"},
        {"category": "RETURN", "label": "QUALITY", "val1": "7.7", "val2": "8.8", "max_val": "10.0"},
        {"category": "RETURN", "label": "BREAK POINTS WON", "val1": "0/0", "val2": "6/6", "max_val": "6"},
    ])

    # Mode 2: Service Metrics & Summary Grid (Image 2 Style)
    service_cards: List[Dict[str, str]] = field(default_factory=lambda: [
        {"label": "1ST SERVE IN", "val1": "59%", "val2": "44%"},
        {"label": "1ST SERVE WON", "val1": "88%", "val2": "86%"},
        {"label": "2ND SERVE WON", "val1": "55%", "val2": "65%"},
    ])
    match_grid: List[Dict[str, str]] = field(default_factory=lambda: [
        {"col": "ACES", "val1": "8", "val2": "3"},
        {"col": "DOUBLE FAULTS", "val1": "1", "val2": "0"},
        {"col": "BREAK POINTS", "val1": "0/1", "val2": "1/2"},
        {"col": "SET 1", "val1": "0/0", "val2": "1/2"},
        {"col": "SET 2", "val1": "0/1", "val2": "0/0"},
    ])

    # Mode 3: Winners & Unforced Errors Breakdown (Image 3 Style)
    winners: Dict[str, Any] = field(default_factory=lambda: {
        "p1_total": "8", "p2_total": "24",
        "fh": {"p1": "2", "p2": "18"},
        "bh": {"p1": "3", "p2": "5"},
        "serve": {"p1": "3", "p2": "1"},
    })
    unforced_errors: Dict[str, Any] = field(default_factory=lambda: {
        "p1_total": "18", "p2_total": "29",
        "fh": {"p1": "9", "p2": "16"},
        "bh": {"p1": "7", "p2": "10"},
        "serve": {"p1": "2", "p2": "3"},
    })
    points_matrix: List[Dict[str, str]] = field(default_factory=lambda: [
        {"label": "UNRETURNED SERVES", "p1": "12/45", "p2": "12/77"},
        {"label": "SERVE POINTS WON", "p1": "25/47", "p2": "48/80"},
        {"label": "BASELINE POINTS WON", "p1": "34/73", "p2": "39/73"},
        {"label": "NET POINTS WON", "p1": "3/7", "p2": "15/19"},
        {"label": "TOTAL POINTS WON", "p1": "57/127", "p2": "70/127"},
    ])

    # Mode 4: Classic Rows (Backward compatibility)
    rows: List[Dict[str, str]] = field(default_factory=lambda: [
        {"label": "1st Serve %", "value": "72 %", "max_value": "100"},
        {"label": "2nd Serve win %", "value": "71 %", "max_value": "100"},
        {"label": "1st Serve Return win %", "value": "54 %", "max_value": "100"},
        {"label": "Short Rallies Won (1-4 shots)", "value": "66 %", "max_value": "100"},
    ])

    # Export configuration
    aspect_ratio: str = "16:9 Broadcast (1920x1080)"
    export_format: str = "PNG"
    export_quality: int = 95
    export_scale: int = 1

    # Interactive PPT-Style Element Offsets [dx, dy] in 1920x1080 coordinate space
    element_offsets: Dict[str, List[int]] = field(default_factory=lambda: {
        "header": [0, 0],
        "player1": [0, 0],
        "player2": [0, 0],
        "stats": [0, 0],
    })

    def get_offset(self, element_name: str) -> Tuple[int, int]:
        val = self.element_offsets.get(element_name, [0, 0])
        return (int(val[0]), int(val[1])) if len(val) >= 2 else (0, 0)

    def set_offset(self, element_name: str, dx: int, dy: int) -> None:
        self.element_offsets[element_name] = [int(dx), int(dy)]

    def reset_offsets(self) -> None:
        for k in list(self.element_offsets.keys()):
            self.element_offsets[k] = [0, 0]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoreboardConfig":
        valid_keys = set(cls().__dict__.keys())
        filtered = {}
        for k, v in data.items():
            if k in valid_keys:
                if k in ("player1", "player2") and isinstance(v, dict):
                    filtered[k] = PlayerData(**v)
                else:
                    filtered[k] = v
        return cls(**filtered)

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "ScoreboardConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

# ------------------------------------------------------------------------------
# GraphicsKit: Procedural Broadcast Aesthetics & Primitives
# ------------------------------------------------------------------------------
class GraphicsKit:
    """
    High-fidelity procedural graphics rendering tools for broadcast overlays.
    """
    _font_cache: Dict[Tuple[str, int], ImageFont.ImageFont] = {}

    @classmethod
    def load_font(cls, path: str, size: int) -> ImageFont.ImageFont:
        cache_key = (path, size)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        font = None
        if path and os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
            except Exception as e:
                logger.warning(f"Failed loading font '{path}': {e}")

        if font is None:
            sys_fonts = [
                "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/Library/Fonts/Arial.ttf"
            ]
            for candidate in sys_fonts:
                if os.path.exists(candidate):
                    try:
                        font = ImageFont.truetype(candidate, size)
                        break
                    except Exception:
                        continue

        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()

        cls._font_cache[cache_key] = font
        return font

    @staticmethod
    def extract_number(text: str) -> Optional[float]:
        if not text:
            return None
        frac_match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
        if frac_match:
            try:
                num = float(frac_match.group(1))
                den = float(frac_match.group(2))
                return (num / den) * 100.0 if den > 0 else 0.0
            except Exception:
                pass
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
        return float(match.group(0).replace(",", ".")) if match else None

    @classmethod
    def calculate_percent(cls, value_text: str, max_value: Any) -> float:
        num = cls.extract_number(value_text)
        if num is None:
            return 0.0
        try:
            max_val = float(max_value)
        except (TypeError, ValueError):
            max_val = 100.0
        if max_val <= 0:
            max_val = 100.0
        return max(0.0, min(100.0, (num / max_val) * 100.0))

    @staticmethod
    def create_procedural_arena_bg(W: int, H: int, base_rgb: Tuple[int, int, int]) -> Image.Image:
        """
        Generates an authentic sports broadcast stadium backdrop with
        radial lighting, court illumination, and subtle corner vignettes.
        """
        img = Image.new("RGBA", (W, H), base_rgb + (255,))
        draw = ImageDraw.Draw(img)

        # 1. Subtle top arena floodlight gradient
        spot_top = Image.new("RGBA", (W, H // 2), (0, 0, 0, 0))
        draw_spot = ImageDraw.Draw(spot_top)
        # Center glow
        cx, cy = W // 2, int(H * 0.1)
        r = int(W * 0.6)
        glow_color = (base_rgb[0] + 25, base_rgb[1] + 35, base_rgb[2] + 55, 80)
        draw_spot.ellipse([cx - r, cy - int(r * 0.4), cx + r, cy + int(r * 0.4)], fill=glow_color)
        spot_top = spot_top.filter(ImageFilter.GaussianBlur(radius=int(W * 0.04)))
        img.paste(spot_top, (0, 0), spot_top)

        # 2. Bottom court floor sheen
        court_h = int(H * 0.28)
        court_overlay = Image.new("RGBA", (W, court_h), (0, 0, 0, 0))
        draw_court = ImageDraw.Draw(court_overlay)
        court_col = (base_rgb[0] + 15, base_rgb[1] + 20, base_rgb[2] + 30, 60)
        draw_court.rectangle([0, 0, W, court_h], fill=court_col)
        court_overlay = court_overlay.filter(ImageFilter.GaussianBlur(radius=int(H * 0.02)))
        img.paste(court_overlay, (0, H - court_h), court_overlay)

        # 3. Corner vignette for high-contrast broadcast focus
        vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_vig = ImageDraw.Draw(vignette)
        # Top-left and Top-right subtle dark corners
        draw_vig.ellipse([-int(W * 0.2), -int(H * 0.2), int(W * 0.4), int(H * 0.4)], fill=(0, 0, 0, 90))
        draw_vig.ellipse([W - int(W * 0.4), -int(H * 0.2), W + int(W * 0.2), int(H * 0.4)], fill=(0, 0, 0, 90))
        vignette = vignette.filter(ImageFilter.GaussianBlur(radius=int(W * 0.05)))
        img.paste(vignette, (0, 0), vignette)

        return img

    @staticmethod
    def draw_glass_card(draw: ImageDraw.Draw, xy, radius: int,
                        fill_rgba: Tuple[int, int, int, int],
                        border_rgba: Tuple[int, int, int, int] = (60, 90, 140, 180),
                        border_width: int = 1):
        """Draws a modern translucent glassmorphic card with subtle depth."""
        x0, y0, x1, y1 = xy
        # Main glass body
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill_rgba,
                               outline=border_rgba, width=border_width)
        # Subtle top specular highlight line
        specular_y = y0 + 1
        spec_x0 = x0 + radius
        spec_x1 = x1 - radius
        if spec_x1 > spec_x0:
            draw.line([spec_x0, specular_y, spec_x1, specular_y], fill=(255, 255, 255, 60), width=1)

    @staticmethod
    def draw_flag_badge(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
                        country_code: str, font: ImageFont.ImageFont):
        """Draws an authentic national flag pill badge with vector colors."""
        draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                               fill=(15, 28, 50, 240), outline=(60, 95, 145), width=1)
        code = country_code.upper()[:3]
        swatch_w = int(h * 0.85)
        swatch_x = x + 3
        swatch_y = y + 2
        swatch_h = h - 4

        # Real flag colors palette for tennis nations
        flag_palettes = {
            "AUS": [(0, 35, 110), (200, 25, 45)],
            "USA": [(190, 25, 45), (255, 255, 255), (20, 45, 120)],
            "FRA": [(0, 85, 190), (255, 255, 255), (220, 35, 45)],
            "ESP": [(200, 25, 35), (250, 195, 20), (200, 25, 35)],
            "GBR": [(0, 35, 110), (255, 255, 255), (200, 25, 45)],
            "ITA": [(0, 145, 65), (255, 255, 255), (200, 35, 45)],
            "GER": [(20, 20, 20), (210, 25, 35), (250, 195, 20)],
            "SRB": [(190, 25, 45), (20, 45, 120), (255, 255, 255)],
            "SUI": [(210, 25, 35), (255, 255, 255)],
            "CAN": [(210, 25, 35), (255, 255, 255), (210, 25, 35)],
            "GRE": [(0, 90, 190), (255, 255, 255)],
            "POL": [(255, 255, 255), (210, 25, 45)],
            "JPN": [(255, 255, 255), (190, 25, 40)],
            "ARG": [(115, 175, 240), (255, 255, 255), (115, 175, 240)],
            "BRA": [(0, 150, 60), (250, 200, 20), (0, 40, 130)],
        }
        cols = flag_palettes.get(code, [(50, 90, 150), (25, 50, 90)])
        n = len(cols)
        seg_w = max(1, swatch_w // n)
        for i, col in enumerate(cols):
            draw.rectangle([swatch_x + i * seg_w, swatch_y,
                            min(swatch_x + (i + 1) * seg_w, swatch_x + swatch_w),
                            swatch_y + swatch_h], fill=col)

        # Country code text
        bbox = draw.textbbox((0, 0), code, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = swatch_x + swatch_w + (w - swatch_w - tw) // 2
        ty = y + (h - th) // 2 - 1
        draw.text((tx, ty), code, font=font, fill=(245, 250, 255))

    @classmethod
    def draw_player_avatar(cls, img: Image.Image, x: int, y: int, size: int,
                           photo_path: str, player_name: str, border_color: Tuple[int, int, int]):
        """Render circular or rounded player cutout photo or stylized broadcast avatar."""
        avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        mask = Image.new("L", (size, size), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([2, 2, size - 2, size - 2], radius=int(size * 0.16), fill=255)

        loaded = False
        if photo_path and os.path.exists(photo_path):
            try:
                p_img = Image.open(photo_path).convert("RGBA")
                p_img = ImageOps.fit(p_img, (size, size), method=Image.LANCZOS)
                avatar.paste(p_img, (0, 0), mask)
                loaded = True
            except Exception as e:
                logger.warning(f"Failed to load player photo '{photo_path}': {e}")

        if not loaded:
            # Stylized Broadcast Silhouette Avatar
            bg_grad = Image.new("RGBA", (size, size), (16, 28, 50, 255))
            draw_bg = ImageDraw.Draw(bg_grad)
            cx, cy = size // 2, int(size * 0.40)
            head_r = int(size * 0.22)
            draw_bg.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=(55, 80, 120, 255))
            draw_bg.pieslice([cx - int(size * 0.44), int(size * 0.54),
                              cx + int(size * 0.44), int(size * 1.25)],
                             180, 360, fill=(55, 80, 120, 255))

            initials = "".join([part[0] for part in player_name.split() if part])[:2].upper() or "P"
            init_font = cls.load_font("", int(size * 0.22))
            draw_bg.text((cx, int(size * 0.78)), initials, font=init_font, fill=(210, 230, 255), anchor="mm")
            avatar.paste(bg_grad, (0, 0), mask)

        # Glow Border
        draw_border = ImageDraw.Draw(avatar)
        draw_border.rounded_rectangle([2, 2, size - 2, size - 2], radius=int(size * 0.16),
                                     outline=border_color, width=3)
        img.paste(avatar, (x, y), avatar)

    @staticmethod
    def draw_comparison_bar(draw: ImageDraw.Draw, x0: int, y0: int, w: int, h: int,
                            pct: float, is_leader: bool,
                            accent_col: Tuple[int, int, int],
                            track_col: Tuple[int, int, int],
                            align_right: bool = False):
        """Draws comparative progress meter with leader neon highlight and glow edge."""
        # Background Track
        draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h // 2, fill=track_col)
        fill_w = max(0, min(w, int(w * (pct / 100.0))))
        if fill_w > 0:
            fill_col = accent_col if is_leader else (160, 185, 220)
            if align_right:
                bx0 = x0 + w - fill_w
                bx1 = x0 + w
            else:
                bx0 = x0
                bx1 = x0 + fill_w
            draw.rounded_rectangle([bx0, y0, bx1, y0 + h], radius=h // 2, fill=fill_col)

# ------------------------------------------------------------------------------
# ScoreboardRenderer & Layout Engines
# ------------------------------------------------------------------------------
class ScoreboardRenderer:
    """
    High-Performance Multi-Layout Broadcast Scoreboard Renderer.
    Supports interactive PPT-style mouse drag-and-drop repositioning via element_offsets.
    """
    @classmethod
    def get_element_bounds(cls, config: ScoreboardConfig) -> Dict[str, Dict[str, Any]]:
        """
        Returns normalized bounding boxes in 1920x1080 coordinates for interactive mouse hit-testing.
        Format: {element_id: {"bounds": (x0, y0, x1, y1), "label": display_name}}
        """
        mode = config.layout_mode
        off_h = config.get_offset("header")
        off_p1 = config.get_offset("player1")
        off_p2 = config.get_offset("player2")
        off_st = config.get_offset("stats")

        if mode == "service_table":
            return {
                "header": {
                    "bounds": (60 + off_h[0], 20 + off_h[1], 1860 + off_h[0], 115 + off_h[1]),
                    "label": "Tournament Header Bar"
                },
                "player1": {
                    "bounds": (60 + off_p1[0], 140 + off_p1[1], 800 + off_p1[0], 520 + off_p1[1]),
                    "label": f"Player Scores ({config.player1.name} / {config.player2.name})"
                },
                "player2": {
                    "bounds": (820 + off_p2[0], 140 + off_p2[1], 1860 + off_p2[0], 520 + off_p2[1]),
                    "label": "Service 3-Column Cards"
                },
                "stats": {
                    "bounds": (60 + off_st[0], 540 + off_st[1], 1860 + off_st[0], 1030 + off_st[1]),
                    "label": "Match Stats & Sets Grid"
                },
            }
        elif mode == "shot_breakdown":
            return {
                "header": {
                    "bounds": (60 + off_h[0], 15 + off_h[1], 1860 + off_h[0], 110 + off_h[1]),
                    "label": "Tournament Header Bar"
                },
                "player1": {
                    "bounds": (60 + off_p1[0], 130 + off_p1[1], 700 + off_p1[0], 560 + off_p1[1]),
                    "label": f"Player Profiles ({config.player1.name} / {config.player2.name})"
                },
                "player2": {
                    "bounds": (720 + off_p2[0], 130 + off_p2[1], 1270 + off_p2[0], 560 + off_p2[1]),
                    "label": "Winners Breakdown Card"
                },
                "stats": {
                    "bounds": (1290 + off_st[0], 130 + off_st[1], 1860 + off_st[0], 560 + off_st[1]),
                    "label": "Unforced Errors Card"
                },
            }
        elif mode == "classic_sidebar":
            panel_w = int(1920 * config.panel_width_ratio)
            x_start = 1920 - panel_w if config.panel_side == "right" else 0
            return {
                "header": {
                    "bounds": (x_start + 30 + off_h[0], 30 + off_h[1], x_start + panel_w - 30 + off_h[0], 210 + off_h[1]),
                    "label": "Title & Subtitle Header"
                },
                "stats": {
                    "bounds": (x_start + 30 + off_st[0], 230 + off_st[1], x_start + panel_w - 30 + off_st[0], 1040 + off_st[1]),
                    "label": "Classic Metrics Rows"
                },
            }
        else:  # h2h_broadcast
            return {
                "header": {
                    "bounds": (35 + off_h[0], 24 + off_h[1], 1885 + off_h[0], 129 + off_h[1]),
                    "label": "Top Header Banner"
                },
                "player1": {
                    "bounds": (65 + off_p1[0], 175 + off_p1[1], 370 + off_p1[0], 620 + off_p1[1]),
                    "label": f"Player 1: {config.player1.name}"
                },
                "player2": {
                    "bounds": (1550 + off_p2[0], 175 + off_p2[1], 1855 + off_p2[0], 620 + off_p2[1]),
                    "label": f"Player 2: {config.player2.name}"
                },
                "stats": {
                    "bounds": (470 + off_st[0], 150 + off_st[1], 1450 + off_st[0], 1040 + off_st[1]),
                    "label": "Center Comparison Stats"
                },
            }

    @classmethod
    def render(cls, config: ScoreboardConfig, multiplier: int = 1) -> Image.Image:
        base_w, base_h = ASPECT_RATIOS.get(config.aspect_ratio, (1920, 1080))
        W, H = base_w * multiplier, base_h * multiplier

        if config.layout_mode == "service_table":
            return cls.render_service_table(config, W, H)
        elif config.layout_mode == "shot_breakdown":
            return cls.render_shot_breakdown(config, W, H)
        elif config.layout_mode == "classic_sidebar":
            return cls.render_classic_sidebar(config, W, H)
        else:
            return cls.render_h2h_broadcast(config, W, H)

    # --------------------------------------------------------------------------
    # Layout 1: ATP Head-to-Head Broadcast (Image 1 Style)
    # --------------------------------------------------------------------------
    @classmethod
    def render_h2h_broadcast(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
        # Base background: Procedural Arena Lighting or Custom Photo
        if config.show_bg_photo and config.photo_path and os.path.exists(config.photo_path):
            try:
                bg = Image.open(config.photo_path).convert("RGBA")
                img = ImageOps.fit(bg, (W, H), method=Image.LANCZOS)
                if config.dark_overlay:
                    overlay = Image.new("RGBA", (W, H), tuple(config.bg_color) + (210,))
                    img = Image.alpha_composite(img, overlay)
            except Exception as e:
                logger.error(f"Failed to load background photo: {e}")
                img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))
        else:
            img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))

        draw = ImageDraw.Draw(img)
        s = W / 1920.0

        accent = tuple(config.accent_color)
        sec_accent = tuple(config.secondary_accent)
        track_col = tuple(config.bar_track_color)
        title_col = tuple(config.title_color)
        label_col = tuple(config.label_color)

        # Offsets for PPT Drag & Drop
        off_hdr = config.get_offset("header")
        off_p1 = config.get_offset("player1")
        off_p2 = config.get_offset("player2")
        off_st = config.get_offset("stats")

        # 1. Top Header Banner
        header_h = int(105 * s)
        header_y = int(24 * s) + int(off_hdr[1] * s)
        header_x0 = int(35 * s) + int(off_hdr[0] * s)
        header_x1 = W - int(35 * s) + int(off_hdr[0] * s)

        GraphicsKit.draw_glass_card(draw, [header_x0, header_y, header_x1, header_y + header_h],
                                    radius=int(12 * s), fill_rgba=(10, 22, 48, 245),
                                    border_rgba=(35, 70, 125, 220), border_width=1)

        f_title = GraphicsKit.load_font(config.font_bold_path, int(config.title_font_size * s * 0.8))
        f_sub = GraphicsKit.load_font(config.font_regular_path, int(18 * s))
        f_badge = GraphicsKit.load_font(config.font_bold_path, int(20 * s))
        f_score = GraphicsKit.load_font(config.font_bold_path, int(26 * s))
        f_name = GraphicsKit.load_font(config.font_bold_path, int(24 * s))

        draw.text((header_x0 + int(30 * s), header_y + int(18 * s)), config.title_text.upper(), font=f_title, fill=title_col)
        sub_info = f"{config.round_text.upper()}  |  ⏱ {config.match_time}"
        draw.text((header_x0 + int(32 * s), header_y + int(62 * s)), sub_info, font=f_sub, fill=(160, 190, 225))

        center_x = (header_x0 + header_x1) // 2
        p1 = config.player1
        p2 = config.player2

        # Player 1 Header Row
        p1_text = p1.name.upper()
        draw.text((center_x - int(80 * s), header_y + int(18 * s)), p1_text, font=f_name, fill=title_col, anchor="ra")
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, center_x - int(72 * s), header_y + int(18 * s), int(64 * s), int(26 * s), p1.country, f_sub)
        p1_sets = "  ".join(p1.sets)
        draw.text((center_x + int(40 * s), header_y + int(18 * s)), p1_sets, font=f_score, fill=title_col)

        # Player 2 Header Row
        p2_text = p2.name.upper()
        draw.text((center_x - int(80 * s), header_y + int(56 * s)), p2_text, font=f_name, fill=title_col, anchor="ra")
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, center_x - int(72 * s), header_y + int(56 * s), int(64 * s), int(26 * s), p2.country, f_sub)
        p2_sets = "  ".join(p2.sets)
        draw.text((center_x + int(40 * s), header_y + int(56 * s)), p2_sets, font=f_score, fill=accent)

        # Right Header: Tournament Brand
        brand_w = int(220 * s)
        brand_x = header_x1 - brand_w - int(25 * s)
        brand_y = header_y + int(20 * s)
        draw.text((brand_x, brand_y), config.tournament_badge, font=f_badge, fill=(255, 255, 255))
        draw.text((brand_x, brand_y + int(28 * s)), config.tournament_name, font=f_sub, fill=(170, 200, 240))

        # 2. Player Left & Right Cutout Cards
        side_margin = int(45 * s)
        card_y = int(153 * s)
        center_w = int(980 * s)

        if config.show_player_photos:
            photo_size = int(240 * s)
            # Player 1
            p1_card_x = side_margin + int(20 * s) + int(off_p1[0] * s)
            p1_card_y = card_y + int(50 * s) + int(off_p1[1] * s)
            GraphicsKit.draw_player_avatar(img, p1_card_x, p1_card_y, photo_size, p1.photo_path, p1.name, sec_accent)

            if config.show_ratings:
                r_box_y = p1_card_y + photo_size + int(20 * s)
                draw.text((p1_card_x, r_box_y), p1.name.upper(), font=f_sub, fill=label_col)
                draw.text((p1_card_x, r_box_y + int(22 * s)), "PERFORMANCE RATING", font=GraphicsKit.load_font("", int(14 * s)), fill=(150, 175, 210))
                f_rating = GraphicsKit.load_font(config.font_bold_path, int(60 * s))
                draw.text((p1_card_x, r_box_y + int(44 * s)), str(p1.rating), font=f_rating, fill=title_col)

            # Player 2
            p2_card_x = W - side_margin - photo_size - int(20 * s) + int(off_p2[0] * s)
            p2_card_y = card_y + int(50 * s) + int(off_p2[1] * s)
            GraphicsKit.draw_player_avatar(img, p2_card_x, p2_card_y, photo_size, p2.photo_path, p2.name, accent)

            if config.show_ratings:
                r_box_y2 = p2_card_y + photo_size + int(20 * s)
                draw.text((p2_card_x + photo_size, r_box_y2), p2.name.upper(), font=f_sub, fill=label_col, anchor="ra")
                draw.text((p2_card_x + photo_size, r_box_y2 + int(22 * s)), "PERFORMANCE RATING", font=GraphicsKit.load_font("", int(14 * s)), fill=(150, 175, 210), anchor="ra")
                draw.text((p2_card_x + photo_size, r_box_y2 + int(44 * s)), str(p2.rating), font=f_rating, fill=accent, anchor="ra")

        # 3. Center Categorized Comparison Rows
        center_x0 = (W - center_w) // 2 + int(off_st[0] * s)
        cur_y = card_y + int(off_st[1] * s)

        rows = config.h2h_rows or []
        categories = {}
        for r in rows:
            cat = r.get("category", "MATCH STATS").upper()
            categories.setdefault(cat, []).append(r)

        f_cat = GraphicsKit.load_font(config.font_bold_path, int(19 * s))
        f_lbl = GraphicsKit.load_font(config.font_bold_path, int(config.label_font_size * s))
        f_val = GraphicsKit.load_font(config.font_bold_path, int(config.value_font_size * s))

        bar_h = max(4, int(6 * s))
        half_bar_w = int(center_w * 0.38)

        for cat_title, cat_rows in categories.items():
            cat_banner_h = int(28 * s)
            GraphicsKit.draw_glass_card(draw, [center_x0, cur_y, center_x0 + center_w, cur_y + cat_banner_h],
                                        radius=int(6 * s), fill_rgba=sec_accent + (230,),
                                        border_rgba=(70, 130, 240, 200), border_width=1)
            draw.text((center_x0 + center_w // 2, cur_y + cat_banner_h // 2), cat_title, font=f_cat, fill=(255, 255, 255), anchor="mm")
            cur_y += cat_banner_h + int(14 * s)

            for row in cat_rows:
                lbl = row.get("label", "").upper()
                v1_str = str(row.get("val1", "0"))
                v2_str = str(row.get("val2", "0"))
                max_v = row.get("max_val", "100")

                num1 = GraphicsKit.extract_number(v1_str) or 0.0
                num2 = GraphicsKit.extract_number(v2_str) or 0.0

                p1_leads = num1 > num2
                p2_leads = num2 > num1

                c1 = accent if (p1_leads and config.auto_highlight_leader) else title_col
                c2 = accent if (p2_leads and config.auto_highlight_leader) else title_col

                draw.text((center_x0 + center_w // 2, cur_y + int(6 * s)), lbl, font=f_lbl, fill=label_col, anchor="mm")
                draw.text((center_x0 + int(70 * s), cur_y + int(6 * s)), v1_str, font=f_val, fill=c1, anchor="lm")
                draw.text((center_x0 + center_w - int(70 * s), cur_y + int(6 * s)), v2_str, font=f_val, fill=c2, anchor="rm")

                cur_y += int(26 * s)

                if config.show_comparison_bars:
                    pct1 = GraphicsKit.calculate_percent(v1_str, max_v)
                    pct2 = GraphicsKit.calculate_percent(v2_str, max_v)

                    lb_x1 = center_x0 + center_w // 2 - int(120 * s)
                    lb_x0 = lb_x1 - half_bar_w
                    GraphicsKit.draw_comparison_bar(draw, lb_x0, cur_y, half_bar_w, bar_h, pct1, p1_leads and config.auto_highlight_leader, accent, track_col, align_right=True)

                    rb_x0 = center_x0 + center_w // 2 + int(120 * s)
                    GraphicsKit.draw_comparison_bar(draw, rb_x0, cur_y, half_bar_w, bar_h, pct2, p2_leads and config.auto_highlight_leader, accent, track_col, align_right=False)

                    cur_y += bar_h + int(18 * s)
                else:
                    cur_y += int(14 * s)

            cur_y += int(10 * s)

        return img.convert("RGB")

    # --------------------------------------------------------------------------
    # Layout 2: Compact Service & Match Grid Table (Image 2 Style)
    # --------------------------------------------------------------------------
    @classmethod
    def render_service_table(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
        img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))
        draw = ImageDraw.Draw(img)
        s = W / 1920.0

        accent = tuple(config.accent_color)
        track_col = tuple(config.bar_track_color)
        title_col = tuple(config.title_color)

        off_hdr = config.get_offset("header")
        off_p1 = config.get_offset("player1")
        off_p2 = config.get_offset("player2")
        off_st = config.get_offset("stats")

        header_y = int(30 * s) + int(off_hdr[1] * s)
        margin_x = int(60 * s) + int(off_hdr[0] * s)
        f_badge = GraphicsKit.load_font(config.font_bold_path, int(32 * s))
        f_title = GraphicsKit.load_font(config.font_bold_path, int(28 * s))
        f_sub = GraphicsKit.load_font(config.font_regular_path, int(22 * s))

        draw.text((margin_x, header_y), config.tournament_badge, font=f_badge, fill=(255, 255, 255))
        draw.text((W // 2, header_y), config.title_text.upper(), font=f_title, fill=title_col, anchor="ma")
        draw.text((W // 2, header_y + int(38 * s)), f"MATCH ⏱ {config.match_time}", font=f_sub, fill=(160, 185, 215), anchor="ma")

        tourn_box_w = int(320 * s)
        tourn_box_h = int(65 * s)
        tourn_box_x = W - margin_x - tourn_box_w
        GraphicsKit.draw_glass_card(draw, [tourn_box_x, header_y, tourn_box_x + tourn_box_w, header_y + tourn_box_h],
                                    radius=int(8 * s), fill_rgba=(20, 30, 48, 240),
                                    border_rgba=(220, 180, 50, 200), border_width=2)
        draw.text((tourn_box_x + tourn_box_w // 2, header_y + int(18 * s)), config.tournament_name.upper(),
                  font=GraphicsKit.load_font(config.font_bold_path, int(18 * s)), fill=(240, 240, 240), anchor="mm")

        # Main Match Card Base
        base_margin_x = int(60 * s)
        card_y = int(140 * s)
        card_w = W - base_margin_x * 2
        card_h = H - card_y - int(50 * s)

        GraphicsKit.draw_glass_card(draw, [base_margin_x, card_y, base_margin_x + card_w, card_y + card_h],
                                    radius=int(16 * s), fill_rgba=(18, 29, 48, 250),
                                    border_rgba=(35, 55, 88, 200), border_width=1)

        p1 = config.player1
        p2 = config.player2
        p_left_w = int(card_w * 0.42)
        p_start_y = card_y + int(45 * s) + int(off_p1[1] * s)
        p1_mx = base_margin_x + int(off_p1[0] * s)
        f_pname = GraphicsKit.load_font(config.font_bold_path, int(30 * s))
        f_setnum = GraphicsKit.load_font(config.font_bold_path, int(34 * s))

        # Player 1 Row
        draw.text((p1_mx + int(40 * s), p_start_y), p1.name.upper(), font=f_pname, fill=title_col)
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, p1_mx + int(420 * s), p_start_y + int(2 * s), int(64 * s), int(28 * s), p1.country, f_sub)

        p1_scores_y = p_start_y + int(45 * s)
        GraphicsKit.draw_glass_card(draw, [p1_mx + int(120 * s), p1_scores_y, p1_mx + int(320 * s), p1_scores_y + int(50 * s)],
                                    radius=int(6 * s), fill_rgba=(25, 42, 70, 220))
        for i, st in enumerate(p1.sets[:3]):
            draw.text((p1_mx + int(160 * s + i * 65 * s), p1_scores_y + int(25 * s)), st, font=f_setnum, fill=title_col, anchor="mm")

        # Player 2 Row
        p2_start_y = p_start_y + int(170 * s)
        draw.text((p1_mx + int(40 * s), p2_start_y), p2.name.upper(), font=f_pname, fill=title_col)
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, p1_mx + int(420 * s), p2_start_y + int(2 * s), int(64 * s), int(28 * s), p2.country, f_sub)

        p2_scores_y = p2_start_y + int(45 * s)
        GraphicsKit.draw_glass_card(draw, [p1_mx + int(120 * s), p2_scores_y, p1_mx + int(320 * s), p2_scores_y + int(50 * s)],
                                    radius=int(6 * s), fill_rgba=(25, 42, 70, 220))
        for i, st in enumerate(p2.sets[:3]):
            draw.text((p1_mx + int(160 * s + i * 65 * s), p2_scores_y + int(25 * s)), st, font=f_setnum, fill=accent, anchor="mm")

        # Service 3-Column Card
        srv_x0 = base_margin_x + p_left_w + int(off_p2[0] * s)
        srv_w = card_w - p_left_w - int(30 * s)
        srv_y0 = card_y + int(30 * s) + int(off_p2[1] * s)
        srv_h = int(340 * s)

        GraphicsKit.draw_glass_card(draw, [srv_x0, srv_y0, srv_x0 + srv_w, srv_y0 + srv_h],
                                    radius=int(12 * s), fill_rgba=(14, 22, 38, 240),
                                    border_rgba=(40, 65, 100, 200), border_width=1)
        draw.text((srv_x0 + srv_w // 2, srv_y0 + int(20 * s)), "SERVICE", font=f_sub, fill=(180, 205, 235), anchor="mm")

        cards = config.service_cards or []
        col_w = srv_w // max(1, len(cards))
        f_statval = GraphicsKit.load_font(config.font_bold_path, int(46 * s))
        f_midbar = GraphicsKit.load_font(config.font_bold_path, int(18 * s))

        for idx, sc in enumerate(cards):
            cx = srv_x0 + idx * col_w + col_w // 2
            v1_str = sc.get("val1", "0%")
            v2_str = sc.get("val2", "0%")
            lbl = sc.get("label", "")

            n1 = GraphicsKit.extract_number(v1_str) or 0.0
            n2 = GraphicsKit.extract_number(v2_str) or 0.0
            p1_win = n1 >= n2
            p2_win = n2 > n1

            c1 = accent if (p1_win and config.auto_highlight_leader) else (230, 240, 255)
            c2 = accent if (p2_win and config.auto_highlight_leader) else (230, 240, 255)

            draw.text((cx, srv_y0 + int(80 * s)), v1_str, font=f_statval, fill=c1, anchor="mm")
            b_w = int(col_w * 0.55)
            draw.rounded_rectangle([cx - b_w // 2, srv_y0 + int(115 * s), cx + b_w // 2, srv_y0 + int(123 * s)], radius=4, fill=track_col)
            if p1_win:
                draw.rounded_rectangle([cx - b_w // 2, srv_y0 + int(115 * s), cx + b_w // 2, srv_y0 + int(123 * s)], radius=4, fill=accent)

            lbl_pill_y = srv_y0 + int(155 * s)
            pill_color = accent if ((p1_win or p2_win) and config.auto_highlight_leader) else (40, 60, 95)
            pill_text_color = (15, 23, 42) if pill_color == accent else (255, 255, 255)
            draw.rectangle([cx - col_w // 2 + 5, lbl_pill_y, cx + col_w // 2 - 5, lbl_pill_y + int(38 * s)], fill=pill_color)
            draw.text((cx, lbl_pill_y + int(19 * s)), lbl, font=f_midbar, fill=pill_text_color, anchor="mm")

            draw.text((cx, srv_y0 + int(240 * s)), v2_str, font=f_statval, fill=c2, anchor="mm")
            draw.rounded_rectangle([cx - b_w // 2, srv_y0 + int(275 * s), cx + b_w // 2, srv_y0 + int(283 * s)], radius=4, fill=track_col)
            if p2_win:
                draw.rounded_rectangle([cx - b_w // 2, srv_y0 + int(275 * s), cx + b_w // 2, srv_y0 + int(283 * s)], radius=4, fill=accent)

        # Bottom Grid Table
        tbl_y = card_y + int(400 * s) + int(off_st[1] * s)
        tbl_h = card_h - int(430 * s)
        tbl_x0 = base_margin_x + int(20 * s) + int(off_st[0] * s)
        tbl_x1 = base_margin_x + card_w - int(20 * s) + int(off_st[0] * s)
        GraphicsKit.draw_glass_card(draw, [tbl_x0, tbl_y, tbl_x1, tbl_y + tbl_h],
                                    radius=int(10 * s), fill_rgba=(13, 20, 35, 240),
                                    border_rgba=(30, 50, 80, 200), border_width=1)

        grid_items = config.match_grid or []
        col_count = len(grid_items) + 1
        cell_w = (card_w - int(40 * s)) // col_count

        f_tbl_head = GraphicsKit.load_font(config.font_bold_path, int(20 * s))
        f_tbl_val = GraphicsKit.load_font(config.font_bold_path, int(24 * s))

        head_y = tbl_y + int(22 * s)
        draw.text((tbl_x0 + int(40 * s), head_y), "METRIC / SET", font=f_tbl_head, fill=(150, 175, 205))
        for i, item in enumerate(grid_items):
            cell_x = tbl_x0 + int(20 * s) + (i + 1) * cell_w + cell_w // 2
            draw.text((cell_x, head_y), item.get("col", "").upper(), font=f_tbl_head, fill=(150, 175, 205), anchor="mm")

        r1_y = tbl_y + int(65 * s)
        draw.text((tbl_x0 + int(40 * s), r1_y), p1.name.upper(), font=f_tbl_head, fill=title_col)
        for i, item in enumerate(grid_items):
            cell_x = tbl_x0 + int(20 * s) + (i + 1) * cell_w + cell_w // 2
            v = item.get("val1", "0")
            n1 = GraphicsKit.extract_number(v) or 0
            n2 = GraphicsKit.extract_number(item.get("val2", "0")) or 0
            c = accent if (n1 > n2 and config.auto_highlight_leader) else title_col
            draw.text((cell_x, r1_y), v, font=f_tbl_val, fill=c, anchor="mm")

        r2_y = tbl_y + int(115 * s)
        draw.text((tbl_x0 + int(40 * s), r2_y), p2.name.upper(), font=f_tbl_head, fill=title_col)
        for i, item in enumerate(grid_items):
            cell_x = tbl_x0 + int(20 * s) + (i + 1) * cell_w + cell_w // 2
            v = item.get("val2", "0")
            n1 = GraphicsKit.extract_number(item.get("val1", "0")) or 0
            n2 = GraphicsKit.extract_number(v) or 0
            c = accent if (n2 > n1 and config.auto_highlight_leader) else title_col
            draw.text((cell_x, r2_y), v, font=f_tbl_val, fill=c, anchor="mm")

        return img.convert("RGB")

    # --------------------------------------------------------------------------
    # Layout 3: Shot Breakdown & Winners / Errors (Image 3 Style)
    # --------------------------------------------------------------------------
    @classmethod
    def render_shot_breakdown(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
        if config.show_bg_photo and config.photo_path and os.path.exists(config.photo_path):
            try:
                bg = Image.open(config.photo_path).convert("RGBA")
                img = ImageOps.fit(bg, (W, H), method=Image.LANCZOS)
                if config.dark_overlay:
                    overlay = Image.new("RGBA", (W, H), tuple(config.bg_color) + (200,))
                    img = Image.alpha_composite(img, overlay)
            except Exception as e:
                logger.error(f"Failed to load background photo: {e}")
                img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))
        else:
            img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))

        draw = ImageDraw.Draw(img)
        s = W / 1920.0

        accent = tuple(config.accent_color)
        track_col = tuple(config.bar_track_color)
        title_col = tuple(config.title_color)
        label_col = tuple(config.label_color)

        off_hdr = config.get_offset("header")
        off_p1 = config.get_offset("player1")
        off_p2 = config.get_offset("player2")
        off_st = config.get_offset("stats")

        header_y = int(24 * s) + int(off_hdr[1] * s)
        margin_x = int(60 * s) + int(off_hdr[0] * s)
        f_badge = GraphicsKit.load_font(config.font_bold_path, int(30 * s))
        f_title = GraphicsKit.load_font(config.font_bold_path, int(26 * s))
        f_sub = GraphicsKit.load_font(config.font_regular_path, int(20 * s))

        draw.text((margin_x, header_y), config.tournament_badge, font=f_badge, fill=(255, 255, 255))
        draw.text((W // 2, header_y), config.title_text.upper(), font=f_title, fill=title_col, anchor="ma")
        draw.text((W // 2, header_y + int(34 * s)), f"MATCH ⏱ {config.match_time}", font=f_sub, fill=(160, 185, 215), anchor="ma")

        draw.text((W - margin_x, header_y + int(10 * s)), config.tournament_name.upper(),
                  font=GraphicsKit.load_font(config.font_bold_path, int(20 * s)), fill=(180, 220, 255), anchor="ra")

        base_margin_x = int(60 * s)
        card_y = int(114 * s)
        card_w = W - base_margin_x * 2
        card_h = H - card_y - int(40 * s)

        GraphicsKit.draw_glass_card(draw, [base_margin_x, card_y, base_margin_x + card_w, card_y + card_h],
                                    radius=int(14 * s), fill_rgba=(12, 22, 38, 245),
                                    border_rgba=(32, 54, 86, 200), border_width=1)

        p1 = config.player1
        p2 = config.player2
        left_col_w = int(card_w * 0.35)
        p_card_h = int(190 * s)

        f_pname = GraphicsKit.load_font(config.font_bold_path, int(28 * s))
        f_setnum = GraphicsKit.load_font(config.font_bold_path, int(30 * s))

        # Player 1 Card
        p1_y = card_y + int(30 * s) + int(off_p1[1] * s)
        p_card_x = base_margin_x + int(off_p1[0] * s)
        avatar_size = int(140 * s)
        GraphicsKit.draw_player_avatar(img, p_card_x + int(30 * s), p1_y + int(10 * s), avatar_size, p1.photo_path, p1.name, (40, 80, 140))

        info_x = p_card_x + int(190 * s)
        draw.text((info_x, p1_y + int(20 * s)), p1.name.upper(), font=f_pname, fill=title_col)
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, info_x, p1_y + int(60 * s), int(64 * s), int(26 * s), p1.country, f_sub)

        sets_x = info_x + int(100 * s)
        GraphicsKit.draw_glass_card(draw, [sets_x, p1_y + int(55 * s), sets_x + int(120 * s), p1_y + int(95 * s)],
                                    radius=int(6 * s), fill_rgba=(25, 42, 70, 220))
        draw.text((sets_x + int(60 * s), p1_y + int(75 * s)), "  ".join(p1.sets), font=f_setnum, fill=title_col, anchor="mm")

        # Player 2 Card
        p2_y = p1_y + p_card_h + int(15 * s)
        GraphicsKit.draw_player_avatar(img, p_card_x + int(30 * s), p2_y + int(10 * s), avatar_size, p2.photo_path, p2.name, accent)

        draw.text((info_x, p2_y + int(20 * s)), p2.name.upper(), font=f_pname, fill=accent)
        if config.show_flags:
            GraphicsKit.draw_flag_badge(draw, info_x, p2_y + int(60 * s), int(64 * s), int(26 * s), p2.country, f_sub)

        GraphicsKit.draw_glass_card(draw, [sets_x, p2_y + int(55 * s), sets_x + int(120 * s), p2_y + int(95 * s)],
                                    radius=int(6 * s), fill_rgba=(25, 42, 70, 220))
        draw.text((sets_x + int(60 * s), p2_y + int(75 * s)), "  ".join(p2.sets), font=f_setnum, fill=accent, anchor="mm")

        # WINNERS & UNFORCED ERRORS Breakdown Cards
        right_x0 = base_margin_x + left_col_w + int(20 * s)
        right_w = card_w - left_col_w - int(40 * s)
        card_half_w = (right_w - int(25 * s)) // 2

        f_card_head = GraphicsKit.load_font(config.font_bold_path, int(20 * s))
        f_big_val = GraphicsKit.load_font(config.font_bold_path, int(64 * s))
        f_breakdown_lbl = GraphicsKit.load_font(config.font_bold_path, int(18 * s))
        f_breakdown_val = GraphicsKit.load_font(config.font_bold_path, int(22 * s))

        breakdown_y = card_y + int(30 * s)
        breakdown_h = int(390 * s)

        # Card 1: WINNERS
        w_card_x = right_x0 + int(off_p2[0] * s)
        w_card_y = breakdown_y + int(off_p2[1] * s)
        GraphicsKit.draw_glass_card(draw, [w_card_x, w_card_y, w_card_x + card_half_w, w_card_y + breakdown_h],
                                    radius=int(12 * s), fill_rgba=(16, 26, 44, 240),
                                    border_rgba=(35, 60, 95, 200), border_width=1)
        draw.text((w_card_x + card_half_w // 2, w_card_y + int(20 * s)), "WINNERS", font=f_card_head, fill=(200, 225, 255), anchor="mm")

        win_data = config.winners or {}
        w_p1 = win_data.get("p1_total", "0")
        w_p2 = win_data.get("p2_total", "0")
        w_p1_n = GraphicsKit.extract_number(w_p1) or 0
        w_p2_n = GraphicsKit.extract_number(w_p2) or 0

        draw.text((w_card_x + int(70 * s), w_card_y + int(100 * s)), w_p1, font=f_big_val,
                  fill=accent if (w_p1_n > w_p2_n and config.auto_highlight_leader) else title_col, anchor="mm")
        draw.text((w_card_x + int(70 * s), w_card_y + int(190 * s)), "TOTAL", font=f_breakdown_lbl, fill=title_col, anchor="mm")
        draw.text((w_card_x + int(70 * s), w_card_y + int(280 * s)), w_p2, font=f_big_val,
                  fill=accent if (w_p2_n > w_p1_n and config.auto_highlight_leader) else title_col, anchor="mm")

        shots = [("FH", win_data.get("fh", {})), ("BH", win_data.get("bh", {})), ("SERVE", win_data.get("serve", {}))]
        bx = w_card_x + int(160 * s)
        bw = card_half_w - int(190 * s)
        bar_track_w = int(bw * 0.45)

        for si, (s_lbl, s_dict) in enumerate(shots):
            sy1 = w_card_y + int(70 * s + si * 35 * s)
            sy2 = w_card_y + int(250 * s + si * 35 * s)
            val1 = str(s_dict.get("p1", "0"))
            val2 = str(s_dict.get("p2", "0"))
            v1_n = GraphicsKit.extract_number(val1) or 0
            v2_n = GraphicsKit.extract_number(val2) or 0

            draw.text((bx, sy1), val1, font=f_breakdown_val, fill=accent if v1_n > v2_n else title_col)
            draw.text((bx + int(120 * s), sy1), s_lbl, font=f_breakdown_lbl, fill=label_col)
            draw.rounded_rectangle([bx + int(35 * s), sy1 + int(8 * s), bx + int(35 * s) + bar_track_w, sy1 + int(14 * s)], radius=3, fill=track_col)
            if v1_n > 0:
                draw.rounded_rectangle([bx + int(35 * s), sy1 + int(8 * s), bx + int(35 * s) + min(bar_track_w, int(v1_n * 6 * s)), sy1 + int(14 * s)],
                                       radius=3, fill=accent if v1_n > v2_n else (150, 180, 220))

            draw.text((bx, sy2), val2, font=f_breakdown_val, fill=accent if v2_n > v1_n else title_col)
            draw.text((bx + int(120 * s), sy2), s_lbl, font=f_breakdown_lbl, fill=label_col)
            draw.rounded_rectangle([bx + int(35 * s), sy2 + int(8 * s), bx + int(35 * s) + bar_track_w, sy2 + int(14 * s)], radius=3, fill=track_col)
            if v2_n > 0:
                draw.rounded_rectangle([bx + int(35 * s), sy2 + int(8 * s), bx + int(35 * s) + min(bar_track_w, int(v2_n * 6 * s)), sy2 + int(14 * s)],
                                       radius=3, fill=accent if v2_n > v1_n else (150, 180, 220))

        # Card 2: UNFORCED ERRORS
        e_card_x = right_x0 + card_half_w + int(25 * s) + int(off_st[0] * s)
        e_card_y = breakdown_y + int(off_st[1] * s)
        GraphicsKit.draw_glass_card(draw, [e_card_x, e_card_y, e_card_x + card_half_w, e_card_y + breakdown_h],
                                    radius=int(12 * s), fill_rgba=(16, 26, 44, 240),
                                    border_rgba=(35, 60, 95, 200), border_width=1)
        draw.text((e_card_x + card_half_w // 2, e_card_y + int(20 * s)), "UNFORCED ERRORS", font=f_card_head, fill=(200, 225, 255), anchor="mm")

        err_data = config.unforced_errors or {}
        e_p1 = err_data.get("p1_total", "0")
        e_p2 = err_data.get("p2_total", "0")

        draw.text((e_card_x + int(70 * s), e_card_y + int(100 * s)), e_p1, font=f_big_val, fill=title_col, anchor="mm")
        draw.text((e_card_x + int(70 * s), e_card_y + int(190 * s)), "TOTAL", font=f_breakdown_lbl, fill=title_col, anchor="mm")
        draw.text((e_card_x + int(70 * s), e_card_y + int(280 * s)), e_p2, font=f_big_val, fill=title_col, anchor="mm")

        err_shots = [("FH", err_data.get("fh", {})), ("BH", err_data.get("bh", {})), ("SERVE", err_data.get("serve", {}))]
        ebx = e_card_x + int(160 * s)

        for si, (s_lbl, s_dict) in enumerate(err_shots):
            sy1 = e_card_y + int(70 * s + si * 35 * s)
            sy2 = e_card_y + int(250 * s + si * 35 * s)
            val1 = str(s_dict.get("p1", "0"))
            val2 = str(s_dict.get("p2", "0"))
            v1_n = GraphicsKit.extract_number(val1) or 0
            v2_n = GraphicsKit.extract_number(val2) or 0

            draw.text((ebx, sy1), val1, font=f_breakdown_val, fill=accent if v1_n > v2_n else title_col)
            draw.text((ebx + int(120 * s), sy1), s_lbl, font=f_breakdown_lbl, fill=label_col)
            draw.rounded_rectangle([ebx + int(35 * s), sy1 + int(8 * s), ebx + int(35 * s) + bar_track_w, sy1 + int(14 * s)], radius=3, fill=track_col)
            if v1_n > 0:
                draw.rounded_rectangle([ebx + int(35 * s), sy1 + int(8 * s), ebx + int(35 * s) + min(bar_track_w, int(v1_n * 6 * s)), sy1 + int(14 * s)],
                                       radius=3, fill=accent if v1_n > v2_n else (150, 180, 220))

            draw.text((ebx, sy2), val2, font=f_breakdown_val, fill=accent if v2_n > v1_n else title_col)
            draw.text((ebx + int(120 * s), sy2), s_lbl, font=f_breakdown_lbl, fill=label_col)
            draw.rounded_rectangle([ebx + int(35 * s), sy2 + int(8 * s), ebx + int(35 * s) + bar_track_w, sy2 + int(14 * s)], radius=3, fill=track_col)
            if v2_n > 0:
                draw.rounded_rectangle([ebx + int(35 * s), sy2 + int(8 * s), ebx + int(35 * s) + min(bar_track_w, int(v2_n * 6 * s)), sy2 + int(14 * s)],
                                       radius=3, fill=accent if v2_n > v1_n else (150, 180, 220))

        # Bottom Matrix
        matrix_y = card_y + int(450 * s) + int(off_st[1] * s)
        matrix_x = base_margin_x + int(off_st[0] * s)
        matrix_h = card_h - int(480 * s)
        items = config.points_matrix or []
        n_items = len(items)
        col_w = (card_w - int(400 * s)) // max(1, n_items)
        lbl_col_w = int(350 * s)

        f_mhead = GraphicsKit.load_font(config.font_bold_path, int(18 * s))
        f_mval = GraphicsKit.load_font(config.font_bold_path, int(26 * s))

        draw.text((matrix_x + int(40 * s), matrix_y + int(18 * s)), "METRIC", font=f_mhead, fill=(150, 175, 205))
        for mi, itm in enumerate(items):
            cx = matrix_x + lbl_col_w + mi * col_w + col_w // 2
            is_total = "TOTAL" in itm.get("label", "").upper()
            if is_total:
                draw.rounded_rectangle([cx - col_w // 2 + 5, matrix_y, cx + col_w // 2 - 5, matrix_y + matrix_h],
                                       radius=int(8 * s), fill=accent)
                draw.text((cx, matrix_y + int(22 * s)), itm.get("label", "").upper(), font=f_mhead, fill=(15, 23, 42), anchor="mm")
            else:
                draw.text((cx, matrix_y + int(22 * s)), itm.get("label", "").upper(), font=f_mhead, fill=(160, 185, 215), anchor="mm")

        r1_y = matrix_y + int(80 * s)
        draw.text((matrix_x + int(40 * s), r1_y), p1.name.upper(), font=f_mhead, fill=title_col)
        for mi, itm in enumerate(items):
            cx = matrix_x + lbl_col_w + mi * col_w + col_w // 2
            v = itm.get("p1", "")
            is_total = "TOTAL" in itm.get("label", "").upper()
            val_col = (15, 23, 42) if is_total else title_col
            draw.text((cx, r1_y), v, font=f_mval, fill=val_col, anchor="mm")

        r2_y = matrix_y + int(140 * s)
        draw.text((matrix_x + int(40 * s), r2_y), p2.name.upper(), font=f_mhead, fill=accent)
        for mi, itm in enumerate(items):
            cx = matrix_x + lbl_col_w + mi * col_w + col_w // 2
            v = itm.get("p2", "")
            is_total = "TOTAL" in itm.get("label", "").upper()
            val_col = (15, 23, 42) if is_total else accent
            draw.text((cx, r2_y), v, font=f_mval, fill=val_col, anchor="mm")

        return img.convert("RGB")

    # --------------------------------------------------------------------------
    # Layout 4: Classic Sidebar Presentation (Original Mode Preserved)
    # --------------------------------------------------------------------------
    @classmethod
    def render_classic_sidebar(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
        img = Image.new("RGB", (W, H), tuple(config.bg_color))

        if config.photo_path and os.path.exists(config.photo_path):
            try:
                photo = Image.open(config.photo_path).convert("RGB")
                fit = config.photo_fit
                if fit == "cover":
                    pw, ph = photo.size
                    target_ratio = W / H
                    src_ratio = pw / ph
                    if src_ratio > target_ratio:
                        new_h = H
                        new_w = int(src_ratio * new_h)
                    else:
                        new_w = W
                        new_h = int(new_w / src_ratio)
                    photo = photo.resize((new_w, new_h), Image.LANCZOS)
                    left = (new_w - W) // 2
                    top = (new_h - H) // 2
                    photo = photo.crop((left, top, left + W, top + H))
                    img.paste(photo, (0, 0))
                elif fit == "contain":
                    photo.thumbnail((W, H), Image.LANCZOS)
                    pw, ph = photo.size
                    img.paste(photo, ((W - pw) // 2, (H - ph) // 2))
                else:
                    photo = photo.resize((W, H), Image.LANCZOS)
                    img.paste(photo, (0, 0))
            except Exception as e:
                logger.error(f"Failed to load background photo: {e}")

        panel_w = int(W * config.panel_width_ratio)
        x_start = W - panel_w if config.panel_side == "right" else 0

        alpha = int(255 * config.panel_opacity)
        if HAS_NUMPY:
            t = np.linspace(0, 1, H, dtype=np.float32)[:, None]
            c_top = np.array(config.panel_top_color, dtype=np.float32)
            c_bot = np.array(config.panel_bottom_color, dtype=np.float32)
            rgb = (c_top * (1 - t) + c_bot * t).astype(np.uint8)
            arr = np.tile(rgb[:, None, :], (1, panel_w, 1))
            alpha_arr = np.full((H, panel_w, 1), alpha, dtype=np.uint8)
            rgba_arr = np.concatenate([arr, alpha_arr], axis=-1)
            panel_img = Image.fromarray(rgba_arr, mode="RGBA")
        else:
            base = Image.new("RGBA", (1, H))
            for y in range(H):
                t = y / max(1, H - 1)
                r = int(config.panel_top_color[0] + (config.panel_bottom_color[0] - config.panel_top_color[0]) * t)
                g = int(config.panel_top_color[1] + (config.panel_bottom_color[1] - config.panel_top_color[1]) * t)
                b = int(config.panel_top_color[2] + (config.panel_bottom_color[2] - config.panel_top_color[2]) * t)
                base.putpixel((0, y), (r, g, b, alpha))
            panel_img = base.resize((panel_w, H), Image.NEAREST)

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        overlay.paste(panel_img, (x_start, 0), panel_img)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(img, "RGBA")

        off_hdr = config.get_offset("header")
        off_st = config.get_offset("stats")
        multiplier = W / 1024.0
        s = W / 1920.0

        text_x = x_start + int(panel_w * 0.09) + int(off_hdr[0] * s)
        text_w = panel_w - int(panel_w * 0.18)

        sub_size = int(config.label_font_size * 0.8 * multiplier)
        sub_font = GraphicsKit.load_font(config.font_regular_path, sub_size)
        cur_y = int(H * 0.05) + int(off_hdr[1] * s)
        if config.subtitle_text.strip():
            draw.text((text_x, cur_y), config.subtitle_text.upper(), font=sub_font, fill=tuple(config.accent_color))
            bbox = draw.textbbox((0, 0), config.subtitle_text.upper(), font=sub_font)
            cur_y += (bbox[3] - bbox[1]) + int(H * 0.01)

        title_size = int(config.title_font_size * multiplier)
        title_font = GraphicsKit.load_font(config.font_bold_path, title_size)
        title_lines = config.title_text.splitlines()
        for line in title_lines:
            draw.text((text_x, cur_y), line, font=title_font, fill=tuple(config.title_color))
            bbox = draw.textbbox((0, 0), line, font=title_font)
            cur_y += (bbox[3] - bbox[1]) + int(title_size * 0.2)

        cur_y += int(H * 0.03) + int(off_st[1] * s)
        text_x = x_start + int(panel_w * 0.09) + int(off_st[0] * s)

        rows = config.rows or [{"label": "No Data", "value": "0", "max_value": "100"}]
        available_h = H - cur_y - int(H * 0.05)
        row_gap = available_h / len(rows)

        lbl_font = GraphicsKit.load_font(config.font_regular_path, int(config.label_font_size * multiplier))
        val_font = GraphicsKit.load_font(config.font_bold_path, int(config.value_font_size * multiplier))
        bar_h = max(4, int(H * 0.014))

        for row in rows:
            draw.text((text_x, cur_y), row.get("label", ""), font=lbl_font, fill=tuple(config.label_color))
            l_bbox = draw.textbbox((0, 0), row.get("label", ""), font=lbl_font)
            cur_y += (l_bbox[3] - l_bbox[1]) + int(H * 0.008)

            val_str = str(row.get("value", ""))
            draw.text((text_x, cur_y), val_str, font=val_font, fill=tuple(config.accent_color))
            v_bbox = draw.textbbox((0, 0), val_str, font=val_font)
            cur_y += (v_bbox[3] - v_bbox[1]) + int(H * 0.012)

            pct = GraphicsKit.calculate_percent(val_str, row.get("max_value", "100"))
            bar_y0 = cur_y
            bar_y1 = cur_y + bar_h
            draw.rounded_rectangle([text_x, bar_y0, text_x + text_w, bar_y1],
                                   radius=bar_h // 2, fill=tuple(config.bar_track_color))
            fill_w = int(text_w * (pct / 100.0))
            if fill_w > 0:
                draw.rounded_rectangle([text_x, bar_y0, text_x + max(fill_w, bar_h), bar_y1],
                                       radius=bar_h // 2, fill=tuple(config.accent_color))
            cur_y = bar_y1 + row_gap - (
                (l_bbox[3] - l_bbox[1]) + (v_bbox[3] - v_bbox[1]) +
                int(H * 0.02) + bar_h
            )

        return img

# ------------------------------------------------------------------------------
# Modern Custom Toggle Switch Widget (Light Theme)
# ------------------------------------------------------------------------------
class ToggleSwitch(tk.Canvas):
    """
    Animated iOS / Mac style toggle switch widget styled for light theme.
    """
    def __init__(self, parent, variable: Optional[tk.BooleanVar] = None,
                 command=None, width=54, height=28,
                 active_color="#0284c7", inactive_color="#cbd5e1",
                 knob_color="#ffffff", bg_parent="#ffffff", **kwargs):
        super().__init__(parent, width=width, height=height, bg=bg_parent,
                         highlightthickness=0, borderwidth=0, cursor="hand2", **kwargs)

        self.width = width
        self.height = height
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.knob_color = knob_color
        self.bg_parent = bg_parent
        self.command = command

        self.variable = variable or tk.BooleanVar(value=True)
        self.variable.trace_add("write", lambda *a: self._redraw())

        self.bind("<Button-1>", self._on_click)
        self.bind("<Return>", self._on_click)
        self.bind("<space>", self._on_click)

        self._redraw()

    def _on_click(self, event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _redraw(self):
        self.delete("all")
        is_on = bool(self.variable.get())
        pad = 2
        r = (self.height - pad * 2) // 2
        track_color = self.active_color if is_on else self.inactive_color

        # Track pill
        self.create_oval(pad, pad, pad + r * 2, pad + r * 2, fill=track_color, outline="")
        self.create_oval(self.width - pad - r * 2, pad, self.width - pad, pad + r * 2, fill=track_color, outline="")
        self.create_rectangle(pad + r, pad, self.width - pad - r, pad + r * 2, fill=track_color, outline="")

        # Circular knob
        knob_r = r - 2
        if is_on:
            knob_x = self.width - pad - r
            self.create_oval(knob_x - knob_r, self.height // 2 - knob_r,
                             knob_x + knob_r, self.height // 2 + knob_r,
                             fill=self.knob_color, outline="")
        else:
            knob_x = pad + r
            self.create_oval(knob_x - knob_r, self.height // 2 - knob_r,
                             knob_x + knob_r, self.height // 2 + knob_r,
                             fill=self.knob_color, outline="#94a3b8", width=1)


class SwitchRow(tk.Frame):
    """
    A labeled settings row containing a title, subtitle, and modern toggle switch (Light Theme).
    """
    def __init__(self, parent, title: str, subtitle: str = "",
                 variable: Optional[tk.BooleanVar] = None, command=None,
                 bg_color="#ffffff", active_color="#0284c7"):
        super().__init__(parent, bg=bg_color, pady=6, padx=8)

        text_frm = tk.Frame(self, bg=bg_color)
        text_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        lbl_title = tk.Label(text_frm, text=title, font=("Segoe UI", 10, "bold"), fg="#0f172a", bg=bg_color)
        lbl_title.pack(anchor="w")

        if subtitle:
            lbl_sub = tk.Label(text_frm, text=subtitle, font=("Segoe UI", 8), fg="#64748b", bg=bg_color)
            lbl_sub.pack(anchor="w")

        self.switch = ToggleSwitch(self, variable=variable, command=command,
                                   active_color=active_color, bg_parent=bg_color)
        self.switch.pack(side=tk.RIGHT, padx=4)

# ------------------------------------------------------------------------------
# ScoreboardStudioApp (Modern Desktop GUI with Light Theme Controls)
# ------------------------------------------------------------------------------
class ScoreboardStudioApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Match Stats & Scoreboard Graphics Studio (Broadcast Edition)")
        self.root.geometry("1560x960")
        self.root.minsize(1240, 780)

        # Software UI Light Theme Palette
        self.bg_light = "#f1f5f9"         # Off-white window canvas background
        self.card_light = "#ffffff"       # Pure white for cards, tabs, and panels
        self.border_light = "#e2e8f0"     # Light gray borders
        self.text_dark = "#0f172a"        # Deep slate primary text
        self.text_muted = "#64748b"       # Secondary text
        self.accent_blue = "#0284c7"      # Vibrant sports electric blue
        self.accent_hover = "#0369a1"     # Darker blue on hover
        self.btn_bg = "#ffffff"           # White button background
        self.btn_border = "#cbd5e1"       # Crisp button border
        self.btn_text = "#1e293b"         # Dark slate button text

        self.root.configure(bg=self.bg_light)

        self.config = ScoreboardConfig()
        self.current_config_path: Optional[str] = None
        self._tk_img: Optional[ImageTk.PhotoImage] = None

        # Interactive PPT Drag & Drop State
        self.ppt_mode_var = tk.BooleanVar(value=True)
        self._is_dragging = False
        self._selected_element: Optional[str] = None
        self._hovered_element: Optional[str] = None
        self._drag_start_mouse: Tuple[int, int] = (0, 0)
        self._drag_start_offset: Tuple[int, int] = (0, 0)
        self._preview_img_w = 1
        self._preview_img_h = 1
        self._preview_img_x = 0
        self._preview_img_y = 0

        self.render_queue: queue.Queue = queue.Queue()
        self._redraw_timer: Optional[str] = None

        self._init_ttk_style()
        self._build_ui()
        self._apply_config_to_ui()
        self._start_render_worker()
        self.schedule_redraw()

    def _init_ttk_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Global base styling in Light Theme
        style.configure(".", background=self.card_light, foreground=self.text_dark, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.card_light)
        style.configure("Card.TFrame", background=self.card_light, relief=tk.FLAT)
        style.configure("TLabel", background=self.card_light, foreground=self.text_dark)
        style.configure("Card.TLabel", background=self.card_light, foreground=self.text_dark)
        style.configure("Muted.TLabel", background=self.card_light, foreground=self.text_muted, font=("Segoe UI", 8))
        style.configure("Header.TLabel", background=self.card_light, foreground=self.accent_blue, font=("Segoe UI", 11, "bold"))

        # Light Notebook Tabs
        style.configure("TNotebook", background=self.bg_light, borderwidth=0)
        style.configure("TNotebook.Tab", background="#e2e8f0", foreground=self.text_muted, padding=[14, 8], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", self.card_light), ("active", "#eef2f6")],
                  foreground=[("selected", self.accent_blue), ("active", self.text_dark)])

        # Light Theme Buttons (White with crisp border)
        style.configure("TButton", background=self.btn_bg, foreground=self.btn_text,
                        bordercolor=self.btn_border, borderwidth=1, padding=[10, 6], font=("Segoe UI", 9))
        style.map("TButton",
                  background=[("active", "#f8fafc"), ("pressed", "#e2e8f0")],
                  foreground=[("active", self.text_dark)],
                  bordercolor=[("active", self.accent_blue)])

        # Accent Action Button (Vibrant Blue with white text)
        style.configure("Accent.TButton", background=self.accent_blue, foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"), borderwidth=0, padding=[12, 6])
        style.map("Accent.TButton",
                  background=[("active", self.accent_hover), ("pressed", "#075985")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

        # Light Inputs, Comboboxes & Spinboxes
        style.configure("TCombobox", fieldbackground="#ffffff", background="#ffffff", foreground=self.text_dark)
        style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], selectbackground=[("readonly", self.accent_blue)])
        style.configure("TEntry", fieldbackground="#ffffff", foreground=self.text_dark)
        style.configure("TSpinbox", fieldbackground="#ffffff", foreground=self.text_dark)

    def _build_ui(self):
        # 1. Top App Toolbar Header (Light Theme)
        top_bar = tk.Frame(self.root, bg="#ffffff", height=50, padx=16, pady=8)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        lbl_app = tk.Label(top_bar, text="🎾 MATCH STATS STUDIO", font=("Segoe UI", 13, "bold"), fg=self.accent_blue, bg="#ffffff")
        lbl_app.pack(side=tk.LEFT)

        lbl_desc = tk.Label(top_bar, text="— Broadcast TV Overlays & Leaderboard Generator", font=("Segoe UI", 9), fg=self.text_muted, bg="#ffffff")
        lbl_desc.pack(side=tk.LEFT, padx=(8, 0))

        # Preset Quick Switcher in Header
        tk.Label(top_bar, text="Theme Preset:", font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg="#ffffff").pack(side=tk.LEFT, padx=(30, 6))
        self.preset_combo = ttk.Combobox(top_bar, values=list(PRESET_THEMES.keys()), state="readonly", width=26)
        self.preset_combo.pack(side=tk.LEFT, padx=4)
        self.preset_combo.set("ATP Brisbane Blue (Image 1)")
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_theme_preset(self.preset_combo.get()))

        # Quick Export Button
        btn_exp = ttk.Button(top_bar, text="⚡ Export Image", style="Accent.TButton", command=self.export_image)
        btn_exp.pack(side=tk.RIGHT, padx=4)

        # Header border line
        sep_top = tk.Frame(self.root, height=1, bg=self.border_light)
        sep_top.pack(side=tk.TOP, fill=tk.X)

        # 2. Main Paned Layout
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.bg_light, sashwidth=6, bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Control Tabs (Pure White Container)
        left_container = tk.Frame(self.paned, bg=self.card_light, width=540, bd=1, relief=tk.SOLID, highlightthickness=0)
        self.paned.add(left_container, minsize=480, width=540)

        self.notebook = ttk.Notebook(left_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: 🎛️ Switches & Modes
        self.tab_switches = tk.Frame(self.notebook, bg=self.card_light, padx=14, pady=14)
        self.notebook.add(self.tab_switches, text="🎛️ Switches & Modes")
        self._build_tab_switches()

        # Tab 2: 👥 Players & Match
        self.tab_match = tk.Frame(self.notebook, bg=self.card_light, padx=14, pady=14)
        self.notebook.add(self.tab_match, text="👥 Players & Match")
        self._build_tab_match()

        # Tab 3: 📊 Stats & Metrics
        self.tab_stats = tk.Frame(self.notebook, bg=self.card_light, padx=14, pady=14)
        self.notebook.add(self.tab_stats, text="📊 Stats Editor")
        self._build_tab_stats()

        # Tab 4: 🎨 Styling & Colors
        self.tab_style = tk.Frame(self.notebook, bg=self.card_light, padx=14, pady=14)
        self.notebook.add(self.tab_style, text="🎨 Styling & Colors")
        self._build_tab_style()

        # Tab 5: 💾 Export & Save
        self.tab_export = tk.Frame(self.notebook, bg=self.card_light, padx=14, pady=14)
        self.notebook.add(self.tab_export, text="💾 Export & Presets")
        self._build_tab_export()

        # 3. Right Live Preview Panel (Workbench background that frames the dark canvas)
        right_container = tk.Frame(self.paned, bg=self.bg_light, bd=1, relief=tk.SOLID)
        self.paned.add(right_container, minsize=500)

        prev_bar = tk.Frame(right_container, bg="#ffffff", height=38, padx=12, pady=6)
        prev_bar.pack(fill=tk.X)

        tk.Label(prev_bar, text="LIVE BROADCAST CANVAS PREVIEW", font=("Segoe UI", 9, "bold"), fg=self.accent_blue, bg="#ffffff").pack(side=tk.LEFT)

        self.preview_res_lbl = tk.Label(prev_bar, text="1920 x 1080 (16:9)", font=("Segoe UI", 8, "bold"), fg=self.text_muted, bg="#ffffff")
        self.preview_res_lbl.pack(side=tk.RIGHT, padx=4)

        ttk.Button(prev_bar, text="↺ Reset Positions", command=self.reset_element_positions).pack(side=tk.RIGHT, padx=6)

        self.drag_status_lbl = tk.Label(prev_bar, text="🖱️ PPT Mode Active • Drag any element with mouse", font=("Segoe UI", 8), fg="#0284c7", bg="#ffffff")
        self.drag_status_lbl.pack(side=tk.RIGHT, padx=(10, 10))

        sep_prev = tk.Frame(right_container, height=1, bg=self.border_light)
        sep_prev.pack(fill=tk.X)

        # Interactive PPT-Style Canvas Preview
        self.preview_canvas = tk.Canvas(right_container, bg="#070d17", highlightthickness=0, borderwidth=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.preview_canvas.bind("<Configure>", lambda e: self.schedule_redraw())
        self.preview_canvas.bind("<Motion>", self._on_canvas_motion)
        self.preview_canvas.bind("<Button-1>", self._on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.preview_canvas.bind("<Leave>", self._on_canvas_leave)
        self.root.bind("<Key>", self._on_key_press)

        # 4. Bottom Status Bar (Light Theme)
        self.status_var = tk.StringVar(value="Ready • Broadcast Engine Loaded")
        status_bar = tk.Frame(self.root, bg="#ffffff", height=26, padx=12, pady=3)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        sep_bot = tk.Frame(self.root, height=1, bg=self.border_light)
        sep_bot.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(status_bar, textvariable=self.status_var, font=("Segoe UI", 8), fg=self.text_muted, bg="#ffffff", anchor="w").pack(side=tk.LEFT)

    # --------------------------------------------------------------------------
    # Tab 1: Switches & Layout Modes (Light Theme)
    # --------------------------------------------------------------------------
    def _build_tab_switches(self):
        f = self.tab_switches

        lbl_mode = tk.Label(f, text="BROADCAST LAYOUT TEMPLATE", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_mode.pack(anchor="w", pady=(0, 6))

        mode_frm = tk.Frame(f, bg=self.card_light)
        mode_frm.pack(fill=tk.X, pady=(0, 10))

        self.mode_var = tk.StringVar(value=self.config.layout_mode)
        modes = [
            ("h2h_broadcast", "🎾 ATP Head-to-Head (Image 1)"),
            ("service_table", "📊 Service & Match Table (Image 2)"),
            ("shot_breakdown", "🎯 Winners & Errors (Image 3)"),
            ("classic_sidebar", "📋 Classic Sidebar Card (Original)"),
        ]
        for mode_key, mode_title in modes:
            rb = tk.Radiobutton(mode_frm, text=mode_title, value=mode_key, variable=self.mode_var,
                                font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_light,
                                selectcolor="#ffffff", activebackground=self.card_light,
                                command=self._on_layout_mode_changed)
            rb.pack(anchor="w", pady=2)

        # Quick Match Loaders
        lbl_sample = tk.Label(f, text="1-CLICK DEMO MATCH LOADERS:", font=("Segoe UI", 8, "bold"), fg=self.text_muted, bg=self.card_light)
        lbl_sample.pack(anchor="w", pady=(4, 4))

        sm_frm = tk.Frame(f, bg=self.card_light)
        sm_frm.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(sm_frm, text="🎾 Vukic vs Tiafoe (Img 1)", command=lambda: self.load_sample_match("h2h")).pack(side=tk.LEFT, padx=2)
        ttk.Button(sm_frm, text="📊 Rinderknech vs Kumar (Img 2)", command=lambda: self.load_sample_match("service")).pack(side=tk.LEFT, padx=2)
        ttk.Button(sm_frm, text="🎯 Draper vs Alcaraz (Img 3)", command=lambda: self.load_sample_match("shots")).pack(side=tk.LEFT, padx=2)

        sep = tk.Frame(f, height=1, bg=self.border_light)
        sep.pack(fill=tk.X, pady=8)

        lbl_sw = tk.Label(f, text="FEATURE TOGGLE SWITCHES", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_sw.pack(anchor="w", pady=(4, 8))

        sw_container = tk.Frame(f, bg=self.card_light)
        sw_container.pack(fill=tk.BOTH, expand=True)

        SwitchRow(sw_container, title="🖱️ PPT Mouse Drag & Move",
                  subtitle="Click & drag any element with mouse on live preview canvas",
                  variable=self.ppt_mode_var, command=self._draw_overlay_handles,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_photos_var = tk.BooleanVar(value=self.config.show_player_photos)
        SwitchRow(sw_container, title="Player Portrait Photos",
                  subtitle="Show left and right player photo cutouts or avatar badges",
                  variable=self.sw_photos_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_ratings_var = tk.BooleanVar(value=self.config.show_ratings)
        SwitchRow(sw_container, title="Performance Ratings",
                  subtitle="Display performance rating badges (e.g. 6.5 vs 8.8)",
                  variable=self.sw_ratings_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_flags_var = tk.BooleanVar(value=self.config.show_flags)
        SwitchRow(sw_container, title="Country Flag Badges",
                  subtitle="Display country code flag badges (e.g. AUS, USA, FRA)",
                  variable=self.sw_flags_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_lead_var = tk.BooleanVar(value=self.config.auto_highlight_leader)
        SwitchRow(sw_container, title="Auto-Highlight Stat Leaders",
                  subtitle="Highlight higher statistic in bright neon lime/yellow on canvas",
                  variable=self.sw_lead_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_bars_var = tk.BooleanVar(value=self.config.show_comparison_bars)
        SwitchRow(sw_container, title="Comparative Progress Bars",
                  subtitle="Render dual visual indicator bars for each metric",
                  variable=self.sw_bars_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_bg_var = tk.BooleanVar(value=self.config.show_bg_photo)
        SwitchRow(sw_container, title="Background Photo Overlay",
                  subtitle="Render uploaded court or stadium photo behind the scorecard",
                  variable=self.sw_bg_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

        self.sw_overlay_var = tk.BooleanVar(value=self.config.dark_overlay)
        SwitchRow(sw_container, title="Dark Broadcast Vignette / Glass",
                  subtitle="Dark translucent broadcast tint over background image",
                  variable=self.sw_overlay_var, command=self.schedule_redraw,
                  bg_color=self.card_light, active_color=self.accent_blue).pack(fill=tk.X, pady=2)

    def _on_layout_mode_changed(self):
        self.config.layout_mode = self.mode_var.get()
        self.schedule_redraw()

    def load_sample_match(self, sample_type: str):
        if sample_type == "h2h":
            self.apply_theme_preset("ATP Brisbane Blue (Image 1)")
            self.config.player1 = PlayerData(name="ALEKSANDAR VUKIC", country="AUS", rating="6.5", sets=["2", "2"])
            self.config.player2 = PlayerData(name="FRANCES TIAFOE", country="USA", rating="8.8", sets=["6", "6"])
            self.config.tournament_name = "BRISBANE INTERNATIONAL"
            self.config.tournament_badge = "ATP 250"
            self.config.round_text = "ROUND 1"
            self.config.match_time = "0:59'"
        elif sample_type == "service":
            self.apply_theme_preset("Winston-Salem Dark (Image 2)")
            self.config.player1 = PlayerData(name="ARTHUR RINDERKNECH", country="FRA", rating="7.5", sets=["3", "6³"])
            self.config.player2 = PlayerData(name="OMNI KUMAR", country="USA", rating="8.2", sets=["6", "7"])
            self.config.tournament_name = "WINSTON-SALEM OPEN"
            self.config.tournament_badge = "ATP 250"
            self.config.round_text = "MATCH"
            self.config.match_time = "01:35"
        elif sample_type == "shots":
            self.apply_theme_preset("Rome Masters 1000 (Image 3)")
            self.config.player1 = PlayerData(name="JACK DRAPER", country="GBR", rating="7.0", sets=["4", "4"])
            self.config.player2 = PlayerData(name="CARLOS ALCARAZ", country="ESP", rating="9.1", sets=["6", "6"])
            self.config.tournament_name = "INTERNAZIONALI BNL D'ITALIA"
            self.config.tournament_badge = "ATP MASTERS 1000"
            self.config.round_text = "MATCH"
            self.config.match_time = "01:37"

        self._apply_config_to_ui()
        self.schedule_redraw()
        self.status_var.set(f"Loaded demo match: {sample_type.upper()}")

    # --------------------------------------------------------------------------
    # Tab 2: Players & Match Info (Light Theme)
    # --------------------------------------------------------------------------
    def _build_tab_match(self):
        f = self.tab_match

        lbl_tourn = tk.Label(f, text="TOURNAMENT & MATCH INFO", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_tourn.pack(anchor="w", pady=(0, 4))

        t_frm = tk.Frame(f, bg=self.card_light)
        t_frm.pack(fill=tk.X, pady=(0, 10))

        r1 = tk.Frame(t_frm, bg=self.card_light)
        r1.pack(fill=tk.X, pady=3)
        tk.Label(r1, text="Tournament:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.e_tourn_name = ttk.Entry(r1)
        self.e_tourn_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Label(r1, text="Badge:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(6, 2))
        self.e_tourn_badge = ttk.Entry(r1, width=12)
        self.e_tourn_badge.pack(side=tk.LEFT)

        r2 = tk.Frame(t_frm, bg=self.card_light)
        r2.pack(fill=tk.X, pady=3)
        tk.Label(r2, text="Round:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.e_round = ttk.Entry(r2, width=14)
        self.e_round.pack(side=tk.LEFT, padx=4)

        tk.Label(r2, text="Time:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(6, 2))
        self.e_time = ttk.Entry(r2, width=10)
        self.e_time.pack(side=tk.LEFT)

        tk.Label(r2, text="Title:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(6, 2))
        self.e_title = ttk.Entry(r2)
        self.e_title.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        for w in (self.e_tourn_name, self.e_tourn_badge, self.e_round, self.e_time, self.e_title):
            w.bind("<KeyRelease>", lambda e: self.schedule_redraw())

        sep = tk.Frame(f, height=1, bg=self.border_light)
        sep.pack(fill=tk.X, pady=10)

        # Player 1 Section
        lbl_p1 = tk.Label(f, text="PLAYER 1 (LEFT / TOP)", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_p1.pack(anchor="w", pady=(0, 4))

        p1_frm = tk.Frame(f, bg=self.card_light)
        p1_frm.pack(fill=tk.X, pady=(0, 10))

        p1_r1 = tk.Frame(p1_frm, bg=self.card_light)
        p1_r1.pack(fill=tk.X, pady=3)
        tk.Label(p1_r1, text="Name:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.e_p1_name = ttk.Entry(p1_r1)
        self.e_p1_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Label(p1_r1, text="Country:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 2))
        self.e_p1_country = ttk.Entry(p1_r1, width=6)
        self.e_p1_country.pack(side=tk.LEFT)

        p1_r2 = tk.Frame(p1_frm, bg=self.card_light)
        p1_r2.pack(fill=tk.X, pady=3)
        tk.Label(p1_r2, text="Set Scores:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.e_p1_sets = ttk.Entry(p1_r2, width=14)
        self.e_p1_sets.pack(side=tk.LEFT, padx=4)

        tk.Label(p1_r2, text="Rating:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 2))
        self.e_p1_rating = ttk.Entry(p1_r2, width=6)
        self.e_p1_rating.pack(side=tk.LEFT)

        ttk.Button(p1_r2, text="Browse Photo...", command=lambda: self._choose_player_photo(1)).pack(side=tk.LEFT, padx=(10, 0))
        self.lbl_p1_photo = tk.Label(p1_r2, text="", font=("Segoe UI", 8), fg=self.text_muted, bg=self.card_light)
        self.lbl_p1_photo.pack(side=tk.LEFT, padx=4)

        # Player 2 Section
        sep2 = tk.Frame(f, height=1, bg=self.border_light)
        sep2.pack(fill=tk.X, pady=10)

        lbl_p2 = tk.Label(f, text="PLAYER 2 (RIGHT / BOTTOM)", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_p2.pack(anchor="w", pady=(0, 4))

        p2_frm = tk.Frame(f, bg=self.card_light)
        p2_frm.pack(fill=tk.X, pady=(0, 10))

        p2_r1 = tk.Frame(p2_frm, bg=self.card_light)
        p2_r1.pack(fill=tk.X, pady=3)
        tk.Label(p2_r1, text="Name:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.e_p2_name = ttk.Entry(p2_r1)
        self.e_p2_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Label(p2_r1, text="Country:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 2))
        self.e_p2_country = ttk.Entry(p2_r1, width=6)
        self.e_p2_country.pack(side=tk.LEFT)

        p2_r2 = tk.Frame(p2_frm, bg=self.card_light)
        p2_r2.pack(fill=tk.X, pady=3)
        tk.Label(p2_r2, text="Set Scores:", width=12, anchor="w", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.e_p2_sets = ttk.Entry(p2_r2, width=14)
        self.e_p2_sets.pack(side=tk.LEFT, padx=4)

        tk.Label(p2_r2, text="Rating:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 2))
        self.e_p2_rating = ttk.Entry(p2_r2, width=6)
        self.e_p2_rating.pack(side=tk.LEFT)

        ttk.Button(p2_r2, text="Browse Photo...", command=lambda: self._choose_player_photo(2)).pack(side=tk.LEFT, padx=(10, 0))
        self.lbl_p2_photo = tk.Label(p2_r2, text="", font=("Segoe UI", 8), fg=self.text_muted, bg=self.card_light)
        self.lbl_p2_photo.pack(side=tk.LEFT, padx=4)

        for w in (self.e_p1_name, self.e_p1_country, self.e_p1_sets, self.e_p1_rating,
                  self.e_p2_name, self.e_p2_country, self.e_p2_sets, self.e_p2_rating):
            w.bind("<KeyRelease>", lambda e: self.schedule_redraw())

        # Background Stadium Photo
        sep3 = tk.Frame(f, height=1, bg=self.border_light)
        sep3.pack(fill=tk.X, pady=10)

        bg_frm = tk.Frame(f, bg=self.card_light)
        bg_frm.pack(fill=tk.X)
        tk.Label(bg_frm, text="Backdrop Image:", font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_light).pack(side=tk.LEFT)
        ttk.Button(bg_frm, text="Browse Stadium Image...", command=self._choose_bg_image).pack(side=tk.LEFT, padx=8)
        self.lbl_bg_photo = tk.Label(bg_frm, text="Procedural Lighting Active", font=("Segoe UI", 8, "italic"), fg=self.accent_blue, bg=self.card_light)
        self.lbl_bg_photo.pack(side=tk.LEFT)

    def _choose_player_photo(self, player_num: int):
        path = filedialog.askopenfilename(title=f"Select Player {player_num} Photo",
                                          filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            if player_num == 1:
                self.config.player1.photo_path = path
                self.lbl_p1_photo.config(text=os.path.basename(path))
            else:
                self.config.player2.photo_path = path
                self.lbl_p2_photo.config(text=os.path.basename(path))
            self.schedule_redraw()

    def _choose_bg_image(self):
        path = filedialog.askopenfilename(title="Select Stadium / Court Photo",
                                          filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.config.photo_path = path
            self.config.show_bg_photo = True
            self.sw_bg_var.set(True)
            self.lbl_bg_photo.config(text=os.path.basename(path), fg=self.text_dark)
            self.schedule_redraw()

    # --------------------------------------------------------------------------
    # Tab 3: Stats Editor (Light Theme)
    # --------------------------------------------------------------------------
    def _build_tab_stats(self):
        f = self.tab_stats

        lbl_head = tk.Label(f, text="DYNAMIC MATCH METRICS & ROWS", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_head.pack(anchor="w", pady=(0, 4))

        self.stats_canvas = tk.Canvas(f, bg=self.card_light, borderwidth=0, highlightthickness=0)
        stats_vscroll = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.stats_canvas.yview)
        self.stats_rows_frm = tk.Frame(self.stats_canvas, bg=self.card_light)

        self.stats_rows_frm.bind("<Configure>", lambda e: self.stats_canvas.configure(scrollregion=self.stats_canvas.bbox("all")))
        self.stats_canvas.create_window((0, 0), window=self.stats_rows_frm, anchor="nw", width=490)
        self.stats_canvas.configure(yscrollcommand=stats_vscroll.set)

        self.stats_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stats_vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.stats_canvas.bind_all("<MouseWheel>", lambda e: self.stats_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units") if e.delta else None)

    def _populate_stats_rows(self):
        for child in self.stats_rows_frm.winfo_children():
            child.destroy()

        rows = self.config.h2h_rows or []

        btn_bar = tk.Frame(self.stats_rows_frm, bg=self.card_light)
        btn_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btn_bar, text="+ Add Metric Row", command=self._add_h2h_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="Reset Template Stats", command=self._reset_stats_to_mode_default).pack(side=tk.LEFT, padx=4)

        # Light table header
        h_frm = tk.Frame(self.stats_rows_frm, bg="#f1f5f9", pady=4, padx=4, bd=1, relief=tk.SOLID)
        h_frm.pack(fill=tk.X, pady=(2, 4))
        tk.Label(h_frm, text="Category", width=12, font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#f1f5f9").grid(row=0, column=0, padx=2)
        tk.Label(h_frm, text="Metric Name", width=14, font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#f1f5f9").grid(row=0, column=1, padx=2)
        tk.Label(h_frm, text="P1 Val", width=6, font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#f1f5f9").grid(row=0, column=2, padx=2)
        tk.Label(h_frm, text="P2 Val", width=6, font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#f1f5f9").grid(row=0, column=3, padx=2)
        tk.Label(h_frm, text="Max", width=5, font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg="#f1f5f9").grid(row=0, column=4, padx=2)

        for idx, row in enumerate(rows):
            rf = tk.Frame(self.stats_rows_frm, bg=self.card_light, pady=2)
            rf.pack(fill=tk.X)

            e_cat = ttk.Entry(rf, width=12)
            e_cat.insert(0, row.get("category", "SERVE"))
            e_cat.grid(row=0, column=0, padx=2)

            e_lbl = ttk.Entry(rf, width=14)
            e_lbl.insert(0, row.get("label", "QUALITY"))
            e_lbl.grid(row=0, column=1, padx=2)

            e_v1 = ttk.Entry(rf, width=6)
            e_v1.insert(0, row.get("val1", "0"))
            e_v1.grid(row=0, column=2, padx=2)

            e_v2 = ttk.Entry(rf, width=6)
            e_v2.insert(0, row.get("val2", "0"))
            e_v2.grid(row=0, column=3, padx=2)

            e_max = ttk.Entry(rf, width=5)
            e_max.insert(0, row.get("max_val", "100"))
            e_max.grid(row=0, column=4, padx=2)

            def make_updater(i, c, l, v1, v2, m):
                def updater(*args):
                    if i < len(self.config.h2h_rows):
                        self.config.h2h_rows[i] = {
                            "category": c.get(), "label": l.get(),
                            "val1": v1.get(), "val2": v2.get(), "max_val": m.get()
                        }
                        self.schedule_redraw()
                return updater

            u_func = make_updater(idx, e_cat, e_lbl, e_v1, e_v2, e_max)
            for entry in (e_cat, e_lbl, e_v1, e_v2, e_max):
                entry.bind("<KeyRelease>", u_func)

            ttk.Button(rf, text="✕", width=2, command=lambda i=idx: self._delete_h2h_row(i)).grid(row=0, column=5, padx=2)

    def _add_h2h_row(self):
        self.config.h2h_rows.append({"category": "SERVE", "label": "NEW STAT", "val1": "50%", "val2": "50%", "max_val": "100"})
        self._populate_stats_rows()
        self.schedule_redraw()

    def _delete_h2h_row(self, index: int):
        if len(self.config.h2h_rows) > 1:
            self.config.h2h_rows.pop(index)
            self._populate_stats_rows()
            self.schedule_redraw()

    def _reset_stats_to_mode_default(self):
        self.apply_theme_preset(self.preset_combo.get())

    # --------------------------------------------------------------------------
    # Tab 4: Styling & Colors (Light Theme UI)
    # --------------------------------------------------------------------------
    def _build_tab_style(self):
        f = self.tab_style

        lbl_head = tk.Label(f, text="CANVAS COLOR PALETTE & VISUAL STYLING", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_head.pack(anchor="w", pady=(0, 6))

        lbl_hint = tk.Label(f, text="Customize the dark broadcast canvas colors below:", font=("Segoe UI", 8), fg=self.text_muted, bg=self.card_light)
        lbl_hint.pack(anchor="w", pady=(0, 6))

        color_items = [
            ("Canvas Background", "bg_color"),
            ("Card Top Header", "panel_top_color"),
            ("Card Bottom Frame", "panel_bottom_color"),
            ("Primary Accent (Neon)", "accent_color"),
            ("Secondary Accent (Blue)", "secondary_accent"),
            ("Progress Track Color", "bar_track_color"),
            ("Primary Title Text", "title_color"),
            ("Metrics / Label Text", "label_color"),
        ]

        self.color_buttons: Dict[str, tk.Button] = {}
        grid_frm = tk.Frame(f, bg=self.card_light)
        grid_frm.pack(fill=tk.X, pady=(0, 10))

        for idx, (lbl, key) in enumerate(color_items):
            r = idx // 2
            c = (idx % 2) * 2

            tk.Label(grid_frm, text=lbl + ":", font=("Segoe UI", 8, "bold"), fg=self.text_dark, bg=self.card_light).grid(row=r, column=c, sticky="w", padx=4, pady=4)
            btn = tk.Button(grid_frm, width=6, height=1, relief=tk.SOLID, bd=1,
                            command=lambda k=key: self._pick_color(k))
            btn.grid(row=r, column=c + 1, padx=4, pady=4)
            self.color_buttons[key] = btn

        sep = tk.Frame(f, height=1, bg=self.border_light)
        sep.pack(fill=tk.X, pady=8)

        lbl_font = tk.Label(f, text="TYPOGRAPHY & FONT SIZES", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_font.pack(anchor="w", pady=(0, 4))

        f_frm = tk.Frame(f, bg=self.card_light)
        f_frm.pack(fill=tk.X, pady=4)

        tk.Label(f_frm, text="Title Size:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.sp_title = ttk.Spinbox(f_frm, from_=20, to=90, width=4, command=self.schedule_redraw)
        self.sp_title.pack(side=tk.LEFT, padx=4)

        tk.Label(f_frm, text="Label Size:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.sp_label = ttk.Spinbox(f_frm, from_=12, to=50, width=4, command=self.schedule_redraw)
        self.sp_label.pack(side=tk.LEFT, padx=4)

        tk.Label(f_frm, text="Value Size:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.sp_val = ttk.Spinbox(f_frm, from_=18, to=80, width=4, command=self.schedule_redraw)
        self.sp_val.pack(side=tk.LEFT, padx=4)

        sep2 = tk.Frame(f, height=1, bg=self.border_light)
        sep2.pack(fill=tk.X, pady=8)

        lbl_ar = tk.Label(f, text="CANVAS RATIO & DIMENSIONS", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_ar.pack(anchor="w", pady=(0, 4))

        ar_frm = tk.Frame(f, bg=self.card_light)
        ar_frm.pack(fill=tk.X, pady=2)
        self.ar_combo = ttk.Combobox(ar_frm, values=list(ASPECT_RATIOS.keys()), state="readonly")
        self.ar_combo.pack(fill=tk.X, pady=2)
        self.ar_combo.set(self.config.aspect_ratio)
        self.ar_combo.bind("<<ComboboxSelected>>", lambda e: self._on_aspect_ratio_changed())

    def _on_aspect_ratio_changed(self):
        self.config.aspect_ratio = self.ar_combo.get()
        self.preview_res_lbl.config(text=self.config.aspect_ratio)
        self.schedule_redraw()

    @staticmethod
    def _rgb_to_hex(rgb: List[int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _pick_color(self, key: str):
        current = getattr(self.config, key, [255, 255, 255])
        color = colorchooser.askcolor(title=f"Choose Color for {key}", initialcolor=tuple(current))
        if color and color[0]:
            rgb = [int(c) for c in color[0]]
            setattr(self.config, key, rgb)
            if key in self.color_buttons:
                self.color_buttons[key].config(bg=self._rgb_to_hex(rgb))
            self.schedule_redraw()

    # --------------------------------------------------------------------------
    # Tab 5: Export & Presets (Light Theme)
    # --------------------------------------------------------------------------
    def _build_tab_export(self):
        f = self.tab_export

        lbl_head = tk.Label(f, text="EXPORT GRAPHIC & PRESETS", font=("Segoe UI", 10, "bold"), fg=self.accent_blue, bg=self.card_light)
        lbl_head.pack(anchor="w", pady=(0, 6))

        lbl_pr = tk.Label(f, text="Broadcast Presets:", font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_light)
        lbl_pr.pack(anchor="w", pady=(2, 4))

        pr_frm = tk.Frame(f, bg=self.card_light)
        pr_frm.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(pr_frm, text="Image 1: Brisbane H2H", command=lambda: self.apply_theme_preset("ATP Brisbane Blue (Image 1)")).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(pr_frm, text="Image 2: Winston-Salem", command=lambda: self.apply_theme_preset("Winston-Salem Dark (Image 2)")).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(pr_frm, text="Image 3: Rome Masters", command=lambda: self.apply_theme_preset("Rome Masters 1000 (Image 3)")).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(pr_frm, text="US Open Night", command=lambda: self.apply_theme_preset("US Open Night Session")).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        pr_frm.columnconfigure(0, weight=1)
        pr_frm.columnconfigure(1, weight=1)

        sep = tk.Frame(f, height=1, bg=self.border_light)
        sep.pack(fill=tk.X, pady=8)

        lbl_io = tk.Label(f, text="Configuration Files:", font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_light)
        lbl_io.pack(anchor="w", pady=(2, 4))

        io_frm = tk.Frame(f, bg=self.card_light)
        io_frm.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(io_frm, text="Load JSON Config...", command=self.load_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(io_frm, text="Save JSON Config...", command=self.save_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(io_frm, text="Reset Defaults", command=self.reset_defaults).pack(side=tk.LEFT, padx=2)

        sep2 = tk.Frame(f, height=1, bg=self.border_light)
        sep2.pack(fill=tk.X, pady=8)

        lbl_exp = tk.Label(f, text="High-Resolution Image Export:", font=("Segoe UI", 9, "bold"), fg=self.text_dark, bg=self.card_light)
        lbl_exp.pack(anchor="w", pady=(2, 4))

        exp_frm = tk.Frame(f, bg=self.card_light)
        exp_frm.pack(fill=tk.X, pady=4)

        tk.Label(exp_frm, text="Format:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.exp_fmt_combo = ttk.Combobox(exp_frm, values=["PNG", "JPEG", "WebP"], state="readonly", width=6)
        self.exp_fmt_combo.pack(side=tk.LEFT, padx=4)
        self.exp_fmt_combo.set(self.config.export_format)

        tk.Label(exp_frm, text="Resolution Scale:", fg=self.text_dark, bg=self.card_light, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(8, 0))
        self.exp_scale_combo = ttk.Combobox(exp_frm, values=["1x (1080p)", "2x (4K Ultra HD)", "4x (8K Print)"], state="readonly", width=14)
        self.exp_scale_combo.pack(side=tk.LEFT, padx=4)
        self.exp_scale_combo.set("1x (1080p)")

        btn_big_exp = ttk.Button(f, text="⚡ EXPORT BROADCAST GRAPHIC NOW", style="Accent.TButton", command=self.export_image)
        btn_big_exp.pack(fill=tk.X, pady=(14, 6))

    # --------------------------------------------------------------------------
    # State Synchronization
    # --------------------------------------------------------------------------
    def _update_config_from_ui(self):
        self.config.layout_mode = self.mode_var.get()

        self.config.show_player_photos = self.sw_photos_var.get()
        self.config.show_ratings = self.sw_ratings_var.get()
        self.config.show_flags = self.sw_flags_var.get()
        self.config.auto_highlight_leader = self.sw_lead_var.get()
        self.config.show_comparison_bars = self.sw_bars_var.get()
        self.config.show_bg_photo = self.sw_bg_var.get()
        self.config.dark_overlay = self.sw_overlay_var.get()

        self.config.tournament_name = self.e_tourn_name.get()
        self.config.tournament_badge = self.e_tourn_badge.get()
        self.config.round_text = self.e_round.get()
        self.config.match_time = self.e_time.get()
        self.config.title_text = self.e_title.get()

        self.config.player1.name = self.e_p1_name.get()
        self.config.player1.country = self.e_p1_country.get()
        self.config.player1.sets = [s.strip() for s in self.e_p1_sets.get().split() if s.strip()] or ["0"]
        self.config.player1.rating = self.e_p1_rating.get()

        self.config.player2.name = self.e_p2_name.get()
        self.config.player2.country = self.e_p2_country.get()
        self.config.player2.sets = [s.strip() for s in self.e_p2_sets.get().split() if s.strip()] or ["0"]
        self.config.player2.rating = self.e_p2_rating.get()

        try:
            self.config.title_font_size = int(self.sp_title.get())
            self.config.label_font_size = int(self.sp_label.get())
            self.config.value_font_size = int(self.sp_val.get())
        except Exception:
            pass
        self.config.aspect_ratio = self.ar_combo.get()

    def _apply_config_to_ui(self):
        self.mode_var.set(self.config.layout_mode)

        self.sw_photos_var.set(self.config.show_player_photos)
        self.sw_ratings_var.set(self.config.show_ratings)
        self.sw_flags_var.set(self.config.show_flags)
        self.sw_lead_var.set(self.config.auto_highlight_leader)
        self.sw_bars_var.set(self.config.show_comparison_bars)
        self.sw_bg_var.set(self.config.show_bg_photo)
        self.sw_overlay_var.set(self.config.dark_overlay)

        self.e_tourn_name.delete(0, tk.END)
        self.e_tourn_name.insert(0, self.config.tournament_name)

        self.e_tourn_badge.delete(0, tk.END)
        self.e_tourn_badge.insert(0, self.config.tournament_badge)

        self.e_round.delete(0, tk.END)
        self.e_round.insert(0, self.config.round_text)

        self.e_time.delete(0, tk.END)
        self.e_time.insert(0, self.config.match_time)

        self.e_title.delete(0, tk.END)
        self.e_title.insert(0, self.config.title_text)

        self.e_p1_name.delete(0, tk.END)
        self.e_p1_name.insert(0, self.config.player1.name)
        self.e_p1_country.delete(0, tk.END)
        self.e_p1_country.insert(0, self.config.player1.country)
        self.e_p1_sets.delete(0, tk.END)
        self.e_p1_sets.insert(0, "  ".join(self.config.player1.sets))
        self.e_p1_rating.delete(0, tk.END)
        self.e_p1_rating.insert(0, self.config.player1.rating)

        self.e_p2_name.delete(0, tk.END)
        self.e_p2_name.insert(0, self.config.player2.name)
        self.e_p2_country.delete(0, tk.END)
        self.e_p2_country.insert(0, self.config.player2.country)
        self.e_p2_sets.delete(0, tk.END)
        self.e_p2_sets.insert(0, "  ".join(self.config.player2.sets))
        self.e_p2_rating.delete(0, tk.END)
        self.e_p2_rating.insert(0, self.config.player2.rating)

        for k, btn in self.color_buttons.items():
            val = getattr(self.config, k, [255, 255, 255])
            btn.config(bg=self._rgb_to_hex(val))

        self.sp_title.delete(0, tk.END)
        self.sp_title.insert(0, str(self.config.title_font_size))
        self.sp_label.delete(0, tk.END)
        self.sp_label.insert(0, str(self.config.label_font_size))
        self.sp_val.delete(0, tk.END)
        self.sp_val.insert(0, str(self.config.value_font_size))

        self.ar_combo.set(self.config.aspect_ratio)
        self.preview_res_lbl.config(text=self.config.aspect_ratio)

        self._populate_stats_rows()
        self._draw_overlay_handles()

    def apply_theme_preset(self, preset_name: str):
        if preset_name in PRESET_THEMES:
            p = PRESET_THEMES[preset_name]
            for k, val in p.items():
                if hasattr(self.config, k):
                    setattr(self.config, k, val)
            self._apply_config_to_ui()
            self.schedule_redraw()
            self.status_var.set(f"Applied preset: {preset_name}")

    # --------------------------------------------------------------------------
    # Threaded Asynchronous Redraw Pipeline
    # --------------------------------------------------------------------------
    def schedule_redraw(self, *args):
        if self._redraw_timer:
            self.root.after_cancel(self._redraw_timer)
        self._redraw_timer = self.root.after(100, self._push_render_job)

    def _push_render_job(self):
        self._update_config_from_ui()
        self.render_queue.put(self.config)

    def _start_render_worker(self):
        def worker():
            while True:
                cfg = self.render_queue.get()
                while not self.render_queue.empty():
                    cfg = self.render_queue.get_nowait()
                try:
                    img = ScoreboardRenderer.render(cfg, multiplier=1)
                    self.root.after(0, lambda i=img: self._update_preview_ui(i))
                except Exception as e:
                    logger.error(f"Render Error: {e}", exc_info=True)
                finally:
                    self.render_queue.task_done()

        threading.Thread(target=worker, daemon=True).start()

    def _update_preview_ui(self, img: Image.Image):
        canv_w = max(400, self.preview_canvas.winfo_width())
        canv_h = max(300, self.preview_canvas.winfo_height())
        w, h = img.size

        scale = min((canv_w - 20) / w, (canv_h - 20) / h, 1.0)
        self._preview_img_w = max(1, int(w * scale))
        self._preview_img_h = max(1, int(h * scale))

        self._preview_img_x = (canv_w - self._preview_img_w) // 2
        self._preview_img_y = (canv_h - self._preview_img_h) // 2

        preview_img = img.resize((self._preview_img_w, self._preview_img_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(preview_img)

        self.preview_canvas.delete("preview_img")
        self.preview_canvas.create_image(
            self._preview_img_x, self._preview_img_y,
            image=self._tk_img, anchor="nw", tags="preview_img"
        )
        self._draw_overlay_handles()

    # --------------------------------------------------------------------------
    # PPT-Style Mouse Drag & Drop Element Repositioning
    # --------------------------------------------------------------------------
    def _hit_test_element(self, mx: int, my: int) -> Optional[str]:
        if not hasattr(self, "_preview_img_w") or self._preview_img_w <= 0:
            return None
        bounds_map = ScoreboardRenderer.get_element_bounds(self.config)
        # Check elements in reverse order so topmost visual element is hit-tested
        for elem_id, info in reversed(list(bounds_map.items())):
            b = info["bounds"]
            cx0 = self._preview_img_x + int(b[0] * (self._preview_img_w / 1920.0))
            cy0 = self._preview_img_y + int(b[1] * (self._preview_img_h / 1080.0))
            cx1 = self._preview_img_x + int(b[2] * (self._preview_img_w / 1920.0))
            cy1 = self._preview_img_y + int(b[3] * (self._preview_img_h / 1080.0))
            if cx0 <= mx <= cx1 and cy0 <= my <= cy1:
                return elem_id
        return None

    def _draw_overlay_handles(self):
        self.preview_canvas.delete("ppt_overlay")
        if not self.ppt_mode_var.get():
            return

        bounds_map = ScoreboardRenderer.get_element_bounds(self.config)

        # 1. Hover indicator (subtle cyan dashed box)
        if self._hovered_element and self._hovered_element != self._selected_element:
            info = bounds_map.get(self._hovered_element)
            if info:
                b = info["bounds"]
                cx0 = self._preview_img_x + int(b[0] * (self._preview_img_w / 1920.0))
                cy0 = self._preview_img_y + int(b[1] * (self._preview_img_h / 1080.0))
                cx1 = self._preview_img_x + int(b[2] * (self._preview_img_w / 1920.0))
                cy1 = self._preview_img_y + int(b[3] * (self._preview_img_h / 1080.0))
                self.preview_canvas.create_rectangle(
                    cx0, cy0, cx1, cy1,
                    outline="#38bdf8", width=1, dash=(3, 3), tags="ppt_overlay"
                )

        # 2. Selected element (PowerPoint-style active box with 8 circular handles and position tag)
        if self._selected_element:
            info = bounds_map.get(self._selected_element)
            if info:
                b = info["bounds"]
                label_text = info.get("label", self._selected_element.upper())
                cx0 = self._preview_img_x + int(b[0] * (self._preview_img_w / 1920.0))
                cy0 = self._preview_img_y + int(b[1] * (self._preview_img_h / 1080.0))
                cx1 = self._preview_img_x + int(b[2] * (self._preview_img_w / 1920.0))
                cy1 = self._preview_img_y + int(b[3] * (self._preview_img_h / 1080.0))

                # Primary Selection Box
                self.preview_canvas.create_rectangle(
                    cx0, cy0, cx1, cy1,
                    outline="#0284c7", width=2, tags="ppt_overlay"
                )

                # 8 Anchor handles
                mid_x = (cx0 + cx1) // 2
                mid_y = (cy0 + cy1) // 2
                handle_coords = [
                    (cx0, cy0), (mid_x, cy0), (cx1, cy0),
                    (cx0, mid_y),             (cx1, mid_y),
                    (cx0, cy1), (mid_x, cy1), (cx1, cy1)
                ]
                hr = 4
                for hx, hy in handle_coords:
                    self.preview_canvas.create_rectangle(
                        hx - hr, hy - hr, hx + hr, hy + hr,
                        fill="#ffffff", outline="#0284c7", width=1.5, tags="ppt_overlay"
                    )

                # Floating pill badge
                ox, oy = self.config.get_offset(self._selected_element)
                tag_text = f"✥ {label_text}  [X: {ox:+d}px, Y: {oy:+d}px]"
                tag_y = max(14, cy0 - 12)
                tag_w = len(tag_text) * 7 + 16
                self.preview_canvas.create_rectangle(
                    cx0, tag_y - 9, cx0 + tag_w, tag_y + 9,
                    fill="#0284c7", outline="#ffffff", width=1, tags="ppt_overlay"
                )
                self.preview_canvas.create_text(
                    cx0 + 8, tag_y, text=tag_text, font=("Segoe UI", 8, "bold"),
                    fill="#ffffff", anchor="w", tags="ppt_overlay"
                )

    def _on_canvas_motion(self, event):
        if not self.ppt_mode_var.get() or self._is_dragging:
            return
        elem_id = self._hit_test_element(event.x, event.y)
        if elem_id != self._hovered_element:
            self._hovered_element = elem_id
            if elem_id:
                self.preview_canvas.config(cursor="fleur")
            else:
                self.preview_canvas.config(cursor="")
            self._draw_overlay_handles()

    def _on_canvas_press(self, event):
        if not self.ppt_mode_var.get():
            return
        elem_id = self._hit_test_element(event.x, event.y)
        if elem_id:
            self._is_dragging = True
            self._selected_element = elem_id
            self._drag_start_mouse = (event.x, event.y)
            self._drag_start_offset = self.config.get_offset(elem_id)
            self.preview_canvas.config(cursor="fleur")
            self._draw_overlay_handles()
        else:
            self._selected_element = None
            self._draw_overlay_handles()

    def _on_canvas_drag(self, event):
        if not self._is_dragging or not self._selected_element:
            return
        dx_mouse = event.x - self._drag_start_mouse[0]
        dy_mouse = event.y - self._drag_start_mouse[1]

        scale_x = 1920.0 / max(1, self._preview_img_w)
        scale_y = 1080.0 / max(1, self._preview_img_h)

        dx_canvas = int(dx_mouse * scale_x)
        dy_canvas = int(dy_mouse * scale_y)

        new_ox = self._drag_start_offset[0] + dx_canvas
        new_oy = self._drag_start_offset[1] + dy_canvas

        self.config.set_offset(self._selected_element, new_ox, new_oy)
        self.drag_status_lbl.config(
            text=f"✥ Moving {self._selected_element.upper()}: X={new_ox:+d}px, Y={new_oy:+d}px"
        )
        self._draw_overlay_handles()
        self.schedule_redraw()

    def _on_canvas_release(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self.preview_canvas.config(cursor="fleur" if self._selected_element else "")
            self.schedule_redraw()
            if self._selected_element:
                ox, oy = self.config.get_offset(self._selected_element)
                self.drag_status_lbl.config(
                    text=f"✓ Placed {self._selected_element.upper()} at X={ox:+d}px, Y={oy:+d}px"
                )

    def _on_canvas_leave(self, event):
        if not self._is_dragging:
            self._hovered_element = None
            self.preview_canvas.config(cursor="")
            self._draw_overlay_handles()

    def _on_key_press(self, event):
        if not self._selected_element:
            return
        step = 10 if (event.state & 0x1) else 2
        ox, oy = self.config.get_offset(self._selected_element)
        if event.keysym == "Left":
            self.config.set_offset(self._selected_element, ox - step, oy)
        elif event.keysym == "Right":
            self.config.set_offset(self._selected_element, ox + step, oy)
        elif event.keysym == "Up":
            self.config.set_offset(self._selected_element, ox, oy - step)
        elif event.keysym == "Down":
            self.config.set_offset(self._selected_element, ox, oy + step)
        elif event.keysym == "Escape":
            self._selected_element = None
            self._draw_overlay_handles()
            return
        else:
            return
        ox, oy = self.config.get_offset(self._selected_element)
        self.drag_status_lbl.config(
            text=f"✥ {self._selected_element.upper()}: X={ox:+d}px, Y={oy:+d}px"
        )
        self._draw_overlay_handles()
        self.schedule_redraw()

    def reset_element_positions(self):
        self.config.reset_offsets()
        self._selected_element = None
        self._hovered_element = None
        self.drag_status_lbl.config(text="✓ Reset all element positions to default alignment")
        self._draw_overlay_handles()
        self.schedule_redraw()

    # --------------------------------------------------------------------------
    # File Actions
    # --------------------------------------------------------------------------
    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Configuration", "*.json")])
        if path:
            try:
                self.config = ScoreboardConfig.load_from_file(path)
                self.current_config_path = path
                self._apply_config_to_ui()
                self.schedule_redraw()
                self.status_var.set(f"Loaded config: {path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load JSON config: {e}")

    def save_config(self):
        if not self.current_config_path:
            self.current_config_path = filedialog.asksaveasfilename(
                defaultextension=".json", filetypes=[("JSON Configuration", "*.json")]
            )
        if self.current_config_path:
            self._update_config_from_ui()
            self.config.save_to_file(self.current_config_path)
            self.status_var.set(f"Saved configuration to: {self.current_config_path}")

    def reset_defaults(self):
        if messagebox.askyesno("Reset Configuration", "Reset all match settings and switches to original broadcast defaults?"):
            self.config = ScoreboardConfig()
            self.current_config_path = None
            self._apply_config_to_ui()
            self.schedule_redraw()
            self.status_var.set("Reset to defaults")

    def export_image(self):
        self._update_config_from_ui()
        fmt = self.exp_fmt_combo.get().lower()
        ext = "jpg" if fmt == "jpeg" else fmt

        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(f"{fmt.upper()} Image", f"*.{ext}")]
        )
        if path:
            try:
                scale_str = self.exp_scale_combo.get()
                multiplier = 4 if "4x" in scale_str else (2 if "2x" in scale_str else 1)

                high_res_img = ScoreboardRenderer.render(self.config, multiplier=multiplier)
                save_args = {}
                if fmt in ("jpeg", "webp"):
                    save_args["quality"] = self.config.export_quality
                high_res_img.save(path, format=fmt.upper(), **save_args)
                messagebox.showinfo("Export Successful", f"Broadcast graphic saved to:\n{path}\nResolution: {high_res_img.size[0]}x{high_res_img.size[1]}")
                self.status_var.set(f"Exported graphic: {path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export graphic: {e}")

# ------------------------------------------------------------------------------
# Entry Point & CLI Automation
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Match Stats & Scoreboard Graphics Studio (Broadcast Edition)")
    parser.add_argument("--config", type=str, default="", help="Path to JSON configuration file")
    parser.add_argument("--preset", type=str, default="", help="Apply a theme preset by name")
    parser.add_argument("--mode", type=str, default="", choices=list(LAYOUT_MODES.keys()), help="Layout mode")
    parser.add_argument("--export", type=str, default="", help="Export output image path (enables headless mode)")
    parser.add_argument("--scale", type=int, default=1, choices=[1, 2, 4], help="Resolution multiplier (1=1080p, 2=4K, 4=8K)")
    parser.add_argument("--format", type=str, default="PNG", choices=["PNG", "JPEG", "WebP"], help="Export file format")
    parser.add_argument("--quality", type=int, default=95, help="JPEG / WebP quality (1-100)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode without GUI")

    args = parser.parse_args()

    # Headless / Automation Mode
    if args.headless or args.export:
        logger.info("Running in headless automation mode...")
        config = ScoreboardConfig()
        if args.config and os.path.exists(args.config):
            config = ScoreboardConfig.load_from_file(args.config)
        if args.preset and args.preset in PRESET_THEMES:
            p = PRESET_THEMES[args.preset]
            for k, v in p.items():
                if hasattr(config, k):
                    setattr(config, k, v)
        if args.mode:
            config.layout_mode = args.mode

        out_path = args.export or "output.png"
        img = ScoreboardRenderer.render(config, multiplier=args.scale)
        save_args = {}
        if args.format.lower() in ("jpeg", "webp"):
            save_args["quality"] = args.quality
        img.save(out_path, format=args.format.upper(), **save_args)
        logger.info(f"Successfully generated graphic: {out_path} ({img.size[0]}x{img.size[1]})")
        return

    # Interactive GUI Mode
    root = tk.Tk()
    app = ScoreboardStudioApp(root)
    if args.preset and args.preset in PRESET_THEMES:
        app.apply_theme_preset(args.preset)
    if args.config and os.path.exists(args.config):
        app.config = ScoreboardConfig.load_from_file(args.config)
        app._apply_config_to_ui()
    root.mainloop()


if __name__ == "__main__":
    main()