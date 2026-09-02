#!/usr/bin/env python3
"""
Scoreboard / Match Stats Card Generator (Production-Ready)
---------------------------------------------------------
A modular desktop application to generate match statistics graphics.

Dependencies:
    pip install pillow numpy
"""

import json
import logging
import os
import queue
import re
import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

# Optional NumPy for ultra-fast gradient generation
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ------------------------------------------------------------------------------
# Logging & System Setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ScoreboardGenerator")

# ------------------------------------------------------------------------------
# Constants & Theme Presets
# ------------------------------------------------------------------------------
ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "16:9 Landscape (1024x576)": (1024, 576),
    "1:1 Square (1024x1024)": (1024, 1024),
    "9:16 Story (576x1024)": (576, 1024),
    "4:5 Social (1024x1280)": (1024, 1280),
    "Full HD (1920x1080)": (1920, 1080),
}

PRESET_THEMES: Dict[str, Dict[str, List[int]]] = {
    "Broadcast Dark": {
        "bg_color": [10, 30, 48],
        "panel_top_color": [8, 10, 14],
        "panel_bottom_color": [14, 34, 52],
        "accent_color": [223, 255, 60],
        "bar_track_color": [70, 90, 105],
        "title_color": [255, 255, 255],
        "label_color": [225, 230, 232],
    },
    "Cyberpunk Neon": {
        "bg_color": [15, 5, 25],
        "panel_top_color": [20, 10, 35],
        "panel_bottom_color": [5, 2, 10],
        "accent_color": [255, 0, 128],
        "bar_track_color": [60, 20, 80],
        "title_color": [0, 255, 240],
        "label_color": [240, 240, 240],
    },
    "Emerald Pitch": {
        "bg_color": [5, 25, 15],
        "panel_top_color": [10, 30, 20],
        "panel_bottom_color": [2, 12, 8],
        "accent_color": [46, 213, 115],
        "bar_track_color": [30, 60, 45],
        "title_color": [255, 255, 255],
        "label_color": [200, 230, 210],
    },
    "Minimal Light": {
        "bg_color": [240, 242, 245],
        "panel_top_color": [255, 255, 255],
        "panel_bottom_color": [235, 238, 242],
        "accent_color": [0, 102, 255],
        "bar_track_color": [200, 210, 220],
        "title_color": [20, 25, 30],
        "label_color": [60, 70, 80],
    },
}

# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------
@dataclass
class RowData:
    label: str = "New Stat"
    value: str = "0 %"
    max_value: str = "100"


@dataclass
class ScoreboardConfig:
    photo_path: str = ""
    photo_fit: str = "cover"            # cover, contain, stretch
    panel_side: str = "right"          # left, right
    panel_width_ratio: float = 0.42     # fraction of width
    panel_opacity: float = 0.92         # 0.0 .. 1.0
    bg_color: List[int] = field(default_factory=lambda: [10, 30, 48])
    panel_top_color: List[int] = field(default_factory=lambda: [8, 10, 14])
    panel_bottom_color: List[int] = field(default_factory=lambda: [14, 34, 52])
    accent_color: List[int] = field(default_factory=lambda: [223, 255, 60])
    bar_track_color: List[int] = field(default_factory=lambda: [70, 90, 105])
    title_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    label_color: List[int] = field(default_factory=lambda: [225, 230, 232])
    title_text: str = "Match\nStatistics"
    subtitle_text: str = "FINAL RESULTS"
    title_font_size: int = 36
    label_font_size: int = 18
    value_font_size: int = 30
    font_bold_path: str = ""
    font_regular_path: str = ""
    rows: List[Dict[str, str]] = field(default_factory=lambda: [
        {"label": "1st Serve %", "value": "72 %", "max_value": "100"},
        {"label": "2nd Serve win %", "value": "71 %", "max_value": "100"},
        {"label": "1st Serve Return win %", "value": "54 %", "max_value": "100"},
        {"label": "Short Rallies Won (1-4 shots)", "value": "66 %", "max_value": "100"},
    ])
    aspect_ratio: str = "16:9 Landscape (1024x576)"
    export_format: str = "PNG"
    export_quality: int = 95
    export_scale: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoreboardConfig":
        valid_keys = set(cls().__dict__.keys())
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "ScoreboardConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

# ------------------------------------------------------------------------------
# High-Performance Rendering Engine
# ------------------------------------------------------------------------------
class ScoreboardRenderer:
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
                logger.warning(f"Failed loading font from path '{path}': {e}")

        if font is None:
            sys_fonts = [
                "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"
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
    def create_gradient_panel(width: int, height: int, top_color: Tuple[int, int, int],
                               bottom_color: Tuple[int, int, int], opacity: float) -> Image.Image:
        alpha = int(255 * opacity)
        if HAS_NUMPY:
            t = np.linspace(0, 1, height, dtype=np.float32)[:, None]
            c_top = np.array(top_color, dtype=np.float32)
            c_bot = np.array(bottom_color, dtype=np.float32)
            rgb = (c_top * (1 - t) + c_bot * t).astype(np.uint8)
            arr = np.tile(rgb[:, None, :], (1, width, 1))
            alpha_arr = np.full((height, width, 1), alpha, dtype=np.uint8)
            rgba_arr = np.concatenate([arr, alpha_arr], axis=-1)
            return Image.fromarray(rgba_arr, mode="RGBA")
        else:
            base = Image.new("RGBA", (1, height))
            for y in range(height):
                t = y / max(1, height - 1)
                r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
                g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
                b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
                base.putpixel((0, y), (r, g, b, alpha))
            return base.resize((width, height), Image.NEAREST)

    @classmethod
    def render(cls, config: ScoreboardConfig, multiplier: int = 1) -> Image.Image:
        base_w, base_h = ASPECT_RATIOS.get(config.aspect_ratio, (1024, 576))
        W, H = base_w * multiplier, base_h * multiplier

        img = Image.new("RGB", (W, H), tuple(config.bg_color))

        # Photo rendering
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
                else:  # stretch
                    photo = photo.resize((W, H), Image.LANCZOS)
                    img.paste(photo, (0, 0))
            except Exception as e:
                logger.error(f"Failed to load user background photo: {e}")

        # Overlay Gradient Panel
        panel_w = int(W * config.panel_width_ratio)
        x_start = W - panel_w if config.panel_side == "right" else 0

        panel_img = cls.create_gradient_panel(
            panel_w, H,
            tuple(config.panel_top_color),
            tuple(config.panel_bottom_color),
            config.panel_opacity
        )

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        overlay.paste(panel_img, (x_start, 0), panel_img)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        # Typography & Data Rendering
        draw = ImageDraw.Draw(img, "RGBA")
        text_x = x_start + int(panel_w * 0.09)
        text_w = panel_w - int(panel_w * 0.18)

        # Draw Subtitle
        sub_size = int(config.label_font_size * 0.8 * multiplier)
        sub_font = cls.load_font(config.font_regular_path, sub_size)
        cur_y = int(H * 0.05)
        if config.subtitle_text.strip():
            draw.text((text_x, cur_y), config.subtitle_text.upper(), font=sub_font, fill=tuple(config.accent_color))
            bbox = draw.textbbox((0, 0), config.subtitle_text.upper(), font=sub_font)
            cur_y += (bbox[3] - bbox[1]) + int(H * 0.01)

        # Draw Title
        title_size = int(config.title_font_size * multiplier)
        title_font = cls.load_font(config.font_bold_path, title_size)
        title_lines = config.title_text.splitlines()
        for line in title_lines:
            draw.text((text_x, cur_y), line, font=title_font, fill=tuple(config.title_color))
            bbox = draw.textbbox((0, 0), line, font=title_font)
            cur_y += (bbox[3] - bbox[1]) + int(title_size * 0.2)

        cur_y += int(H * 0.03)

        # Draw Stats Rows
        rows = config.rows or [{"label": "No Data", "value": "0", "max_value": "100"}]
        available_h = H - cur_y - int(H * 0.05)
        row_gap = available_h / len(rows)

        lbl_font = cls.load_font(config.font_regular_path, int(config.label_font_size * multiplier))
        val_font = cls.load_font(config.font_bold_path, int(config.value_font_size * multiplier))
        bar_h = max(4 * multiplier, int(H * 0.014))

        for row in rows:
            # Row Label
            draw.text((text_x, cur_y), row["label"], font=lbl_font, fill=tuple(config.label_color))
            l_bbox = draw.textbbox((0, 0), row["label"], font=lbl_font)
            cur_y += (l_bbox[3] - l_bbox[1]) + int(H * 0.008)

            # Row Value
            val_str = str(row["value"])
            draw.text((text_x, cur_y), val_str, font=val_font, fill=tuple(config.accent_color))
            v_bbox = draw.textbbox((0, 0), val_str, font=val_font)
            cur_y += (v_bbox[3] - v_bbox[1]) + int(H * 0.012)

            # Progress Bar
            pct = cls.calculate_percent(val_str, row.get("max_value", "100"))
            bar_y0 = cur_y
            bar_y1 = cur_y + bar_h
            draw.rounded_rectangle(
                [text_x, bar_y0, text_x + text_w, bar_y1],
                radius=bar_h // 2, fill=tuple(config.bar_track_color)
            )
            fill_w = int(text_w * (pct / 100.0))
            if fill_w > 0:
                draw.rounded_rectangle(
                    [text_x, bar_y0, text_x + max(fill_w, bar_h), bar_y1],
                    radius=bar_h // 2, fill=tuple(config.accent_color)
                )
            cur_y = bar_y1 + row_gap - (
                (l_bbox[3] - l_bbox[1]) + (v_bbox[3] - v_bbox[1]) +
                int(H * 0.02) + bar_h
            )

        return img

# ------------------------------------------------------------------------------
# Embedded Row Controls Widget
# ------------------------------------------------------------------------------
class StatRowWidget(ttk.Frame):
    def __init__(self, parent, row_index: int, config: RowData,
                 on_change_cb, on_delete_cb, on_move_cb):
        super().__init__(parent)
        self.row_index = row_index
        self.config = config
        self.on_change_cb = on_change_cb
        self.on_delete_cb = on_delete_cb
        self.on_move_cb = on_move_cb

        self.label_var = tk.StringVar(value=config.label)
        self.value_var = tk.StringVar(value=config.value)
        self.max_var = tk.StringVar(value=config.max_value)

        self._build_ui()

        for var in (self.label_var, self.value_var, self.max_var):
            var.trace_add("write", lambda *a: self._notify_change())

    def _build_ui(self):
        ttk.Label(self, text="Label:").grid(row=0, column=0, sticky="w", padx=2)
        ttk.Entry(self, textvariable=self.label_var, width=16).grid(row=0, column=1, padx=2)

        ttk.Label(self, text="Val:").grid(row=0, column=2, sticky="w", padx=2)
        ttk.Entry(self, textvariable=self.value_var, width=8).grid(row=0, column=3, padx=2)

        ttk.Label(self, text="Max:").grid(row=0, column=4, sticky="w", padx=2)
        ttk.Entry(self, textvariable=self.max_var, width=5).grid(row=0, column=5, padx=2)

        ttk.Button(self, text="▲", width=2, command=lambda: self.on_move_cb(self, -1)).grid(row=0, column=6, padx=1)
        ttk.Button(self, text="▼", width=2, command=lambda: self.on_move_cb(self, 1)).grid(row=0, column=7, padx=1)
        ttk.Button(self, text="⎘", width=2, command=lambda: self.on_move_cb(self, 0, duplicate=True)).grid(row=0, column=8, padx=1)
        ttk.Button(self, text="✕", width=2, command=lambda: self.on_delete_cb(self)).grid(row=0, column=9, padx=1)

    def _notify_change(self):
        self.config.label = self.label_var.get()
        self.config.value = self.value_var.get()
        self.config.max_value = self.max_var.get()
        self.on_change_cb()

    def get_config(self) -> RowData:
        return RowData(
            label=self.label_var.get(),
            value=self.value_var.get(),
            max_value=self.max_var.get()
        )

# ------------------------------------------------------------------------------
# Main Application Interface
# ------------------------------------------------------------------------------
class ScoreboardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Match Stats & Scoreboard Graphics Studio")
        self.root.geometry("1480x920")
        self.root.minsize(1200, 750)

        self.config = ScoreboardConfig()
        self.current_config_path: Optional[str] = None
        self.row_widgets: List[StatRowWidget] = []
        self._tk_img: Optional[ImageTk.PhotoImage] = None

        # Threading Queue & Debounce
        self.render_queue: queue.Queue = queue.Queue()
        self._redraw_timer: Optional[str] = None

        self._build_ui()
        self._apply_config_to_ui()
        self._start_render_worker()
        self.schedule_redraw()

    def _build_ui(self):
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # Left Scrollable Controls
        left_container = ttk.Frame(self.paned, width=490)
        self.paned.add(left_container, weight=0)

        self.canvas = tk.Canvas(left_container, borderwidth=0, highlightthickness=0)
        v_scroll = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.controls_frame = ttk.Frame(self.canvas)

        self.controls_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.controls_frame, anchor="nw", width=470)
        self.canvas.configure(yscrollcommand=v_scroll.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Mousewheel Scrolling Bindings
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

        # Right Live Preview Panel
        right_container = ttk.Frame(self.paned)
        self.paned.add(right_container, weight=1)

        ttk.Label(right_container, text="Canvas Preview", font=("", 12, "bold")).pack(pady=(10, 2))
        self.preview_label = ttk.Label(right_container)
        self.preview_label.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Section Builders
        self._build_preset_controls()
        self._build_file_controls()
        self._build_content_controls()
        self._build_image_controls()
        self._build_layout_controls()
        self._build_color_controls()
        self._build_font_controls()
        self._build_rows_controls()
        self._build_export_controls()

        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_preset_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Quick Presets")
        box.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(box, text="Theme Preset:").pack(side=tk.LEFT, padx=6, pady=6)
        preset_combo = ttk.Combobox(box, values=list(PRESET_THEMES.keys()), state="readonly")
        preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)
        preset_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_preset(preset_combo.get()))

    def _build_file_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="File & State")
        box.pack(fill=tk.X, padx=8, pady=4)
        frm = ttk.Frame(box)
        frm.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(frm, text="Load JSON", command=self.load_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(frm, text="Save JSON", command=self.save_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(frm, text="Reset Defaults", command=self.reset_defaults).pack(side=tk.LEFT, padx=2)

    def _build_content_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Titles & Headlines")
        box.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(box, text="Subtitle Header:").pack(anchor="w", padx=6, pady=(4, 0))
        self.sub_var = tk.StringVar()
        e_sub = ttk.Entry(box, textvariable=self.sub_var)
        e_sub.pack(fill=tk.X, padx=6, pady=2)
        self.sub_var.trace_add("write", lambda *a: self.schedule_redraw())

        ttk.Label(box, text="Main Title Text (Multiline):").pack(anchor="w", padx=6, pady=(4, 0))
        self.title_text_widget = tk.Text(box, height=3, width=30)
        self.title_text_widget.pack(fill=tk.X, padx=6, pady=4)
        self.title_text_widget.bind("<KeyRelease>", lambda e: self.schedule_redraw())

    def _build_image_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Background Photo")
        box.pack(fill=tk.X, padx=8, pady=4)
        frm = ttk.Frame(box)
        frm.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(frm, text="Browse Image...", command=self.choose_image).pack(side=tk.LEFT, padx=2)
        self.img_path_lbl = ttk.Label(frm, text="No image selected", foreground="#777")
        self.img_path_lbl.pack(side=tk.LEFT, padx=6)

        fit_frm = ttk.Frame(box)
        fit_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(fit_frm, text="Photo Fit:").pack(side=tk.LEFT)
        self.fit_var = tk.StringVar(value="cover")
        cb = ttk.Combobox(fit_frm, textvariable=self.fit_var, values=["cover", "contain", "stretch"], state="readonly", width=10)
        cb.pack(side=tk.LEFT, padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.schedule_redraw())

    def _build_layout_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Layout Geometry")
        box.pack(fill=tk.X, padx=8, pady=4)

        # Aspect Ratio
        ar_frm = ttk.Frame(box)
        ar_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(ar_frm, text="Canvas Ratio:").pack(side=tk.LEFT)
        self.aspect_var = tk.StringVar(value=list(ASPECT_RATIOS.keys())[0])
        cb_ar = ttk.Combobox(ar_frm, textvariable=self.aspect_var, values=list(ASPECT_RATIOS.keys()), state="readonly")
        cb_ar.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        cb_ar.bind("<<ComboboxSelected>>", lambda e: self.schedule_redraw())

        # Panel Side
        side_frm = ttk.Frame(box)
        side_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(side_frm, text="Panel Position:").pack(side=tk.LEFT)
        self.side_var = tk.StringVar(value="right")
        cb_side = ttk.Combobox(side_frm, textvariable=self.side_var, values=["left", "right"], state="readonly", width=8)
        cb_side.pack(side=tk.LEFT, padx=4)
        cb_side.bind("<<ComboboxSelected>>", lambda e: self.schedule_redraw())

        # Panel Width Slider
        w_frm = ttk.Frame(box)
        w_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(w_frm, text="Panel Width:").pack(side=tk.LEFT)
        self.width_var = tk.DoubleVar(value=0.42)
        ttk.Scale(w_frm, from_=0.20, to=0.70, variable=self.width_var, command=lambda e: self.schedule_redraw()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.w_lbl = ttk.Label(w_frm, text="42%")
        self.w_lbl.pack(side=tk.LEFT)
        self.width_var.trace_add("write", lambda *a: self.w_lbl.config(text=f"{int(self.width_var.get()*100)}%"))

        # Opacity Slider
        op_frm = ttk.Frame(box)
        op_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(op_frm, text="Panel Opacity:").pack(side=tk.LEFT)
        self.opacity_var = tk.DoubleVar(value=0.92)
        ttk.Scale(op_frm, from_=0.20, to=1.0, variable=self.opacity_var, command=lambda e: self.schedule_redraw()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.op_lbl = ttk.Label(op_frm, text="92%")
        self.op_lbl.pack(side=tk.LEFT)
        self.opacity_var.trace_add("write", lambda *a: self.op_lbl.config(text=f"{int(self.opacity_var.get()*100)}%"))

    def _build_color_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Color Palette")
        box.pack(fill=tk.X, padx=8, pady=4)

        colors = [
            ("Background", "bg_color"), ("Panel Top", "panel_top_color"),
            ("Panel Bottom", "panel_bottom_color"), ("Accent", "accent_color"),
            ("Bar Track", "bar_track_color"), ("Title", "title_color"),
            ("Label Text", "label_color")
        ]

        self.color_buttons: Dict[str, tk.Button] = {}
        for i, (label, key) in enumerate(colors):
            row = i // 2
            col = (i % 2) * 2
            frm = ttk.Frame(box)
            frm.grid(row=row, column=col, columnspan=2, sticky="w", padx=4, pady=2)
            ttk.Label(frm, text=label + ":", width=11).pack(side=tk.LEFT)
            btn = tk.Button(frm, width=4, height=1, relief=tk.RAISED, command=lambda k=key: self._pick_color(k))
            btn.pack(side=tk.LEFT, padx=4)
            self.color_buttons[key] = btn

    def _build_font_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Typography Settings")
        box.pack(fill=tk.X, padx=8, pady=4)

        self.font_bold_path = tk.StringVar()
        self.font_regular_path = tk.StringVar()

        f_bold_frm = ttk.Frame(box)
        f_bold_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(f_bold_frm, text="Bold Font:").pack(side=tk.LEFT)
        ttk.Entry(f_bold_frm, textvariable=self.font_bold_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(f_bold_frm, text="...", width=3, command=lambda: self._browse_font("bold")).pack(side=tk.LEFT)

        f_reg_frm = ttk.Frame(box)
        f_reg_frm.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(f_reg_frm, text="Regular Font:").pack(side=tk.LEFT)
        ttk.Entry(f_reg_frm, textvariable=self.font_regular_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(f_reg_frm, text="...", width=3, command=lambda: self._browse_font("regular")).pack(side=tk.LEFT)

        size_frm = ttk.Frame(box)
        size_frm.pack(fill=tk.X, padx=6, pady=4)
        self.title_size_var = tk.IntVar(value=36)
        self.label_size_var = tk.IntVar(value=18)
        self.value_size_var = tk.IntVar(value=30)

        ttk.Label(size_frm, text="Title Size:").grid(row=0, column=0, padx=2)
        ttk.Spinbox(size_frm, from_=16, to=96, textvariable=self.title_size_var, width=4, command=self.schedule_redraw).grid(row=0, column=1, padx=2)
        ttk.Label(size_frm, text="Label:").grid(row=0, column=2, padx=2)
        ttk.Spinbox(size_frm, from_=10, to=48, textvariable=self.label_size_var, width=4, command=self.schedule_redraw).grid(row=0, column=3, padx=2)
        ttk.Label(size_frm, text="Value:").grid(row=0, column=4, padx=2)
        ttk.Spinbox(size_frm, from_=16, to=80, textvariable=self.value_size_var, width=4, command=self.schedule_redraw).grid(row=0, column=5, padx=2)

    def _build_rows_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Stat Metrics & Data Rows")
        box.pack(fill=tk.X, padx=8, pady=4)

        self.rows_container = ttk.Frame(box)
        self.rows_container.pack(fill=tk.X, padx=4, pady=4)

        btn_frm = ttk.Frame(box)
        btn_frm.pack(fill=tk.X, pady=4)
        ttk.Button(btn_frm, text="+ Add Metric Row", command=self._add_row).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frm, text="Clear All", command=self._clear_rows).pack(side=tk.LEFT, padx=4)

    def _build_export_controls(self):
        box = ttk.LabelFrame(self.controls_frame, text="Export Options")
        box.pack(fill=tk.X, padx=8, pady=4)

        frm = ttk.Frame(box)
        frm.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(frm, text="Format:").pack(side=tk.LEFT)
        self.export_format_var = tk.StringVar(value="PNG")
        cb_fmt = ttk.Combobox(frm, textvariable=self.export_format_var, values=["PNG", "JPEG", "WebP"], state="readonly", width=6)
        cb_fmt.pack(side=tk.LEFT, padx=4)

        ttk.Label(frm, text="Scale:").pack(side=tk.LEFT, padx=(6, 0))
        self.export_scale_var = tk.IntVar(value=1)
        cb_scale = ttk.Combobox(frm, textvariable=self.export_scale_var, values=[1, 2, 4], state="readonly", width=4)
        cb_scale.pack(side=tk.LEFT, padx=4)

        ttk.Label(frm, text="Quality:").pack(side=tk.LEFT, padx=(6, 0))
        self.quality_var = tk.IntVar(value=95)
        ttk.Spinbox(frm, from_=1, to=100, textvariable=self.quality_var, width=4).pack(side=tk.LEFT, padx=4)

        ttk.Button(box, text="Export Graphic", command=self.export_image).pack(padx=6, pady=6, fill=tk.X)

    # --------------------------------------------------------------------------
    # Color & Preset Helpers
    # --------------------------------------------------------------------------
    @staticmethod
    def _rgb_to_hex(rgb: List[int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _pick_color(self, key: str):
        current = getattr(self.config, key)
        color = colorchooser.askcolor(title=f"Pick Color for {key}", initialcolor=tuple(current))
        if color and color[0]:
            rgb = [int(c) for c in color[0]]
            setattr(self.config, key, rgb)
            self.color_buttons[key].config(bg=self._rgb_to_hex(rgb))
            self.schedule_redraw()

    def apply_preset(self, theme_name: str):
        if theme_name in PRESET_THEMES:
            for k, rgb in PRESET_THEMES[theme_name].items():
                setattr(self.config, k, rgb)
                if k in self.color_buttons:
                    self.color_buttons[k].config(bg=self._rgb_to_hex(rgb))
            self.schedule_redraw()

    # --------------------------------------------------------------------------
    # Dynamic Row Management
    # --------------------------------------------------------------------------
    def _add_row(self, config: Optional[RowData] = None):
        if config is None:
            config = RowData()
        widget = StatRowWidget(
            self.rows_container,
            row_index=len(self.row_widgets),
            config=config,
            on_change_cb=self.schedule_redraw,
            on_delete_cb=self._delete_row,
            on_move_cb=self._move_row
        )
        widget.pack(fill=tk.X, pady=2)
        self.row_widgets.append(widget)
        self.schedule_redraw()

    def _delete_row(self, widget: StatRowWidget):
        if len(self.row_widgets) <= 1:
            messagebox.showwarning("Warning", "At least one stat metric row is required.")
            return
        widget.destroy()
        self.row_widgets.remove(widget)
        self.schedule_redraw()

    def _clear_rows(self):
        for w in self.row_widgets:
            w.destroy()
        self.row_widgets.clear()
        self._add_row()

    def _move_row(self, widget: StatRowWidget, delta: int, duplicate: bool = False):
        if widget not in self.row_widgets:
            return
        idx = self.row_widgets.index(widget)

        if duplicate:
            current_cfg = widget.get_config()
            new_cfg = RowData(label=current_cfg.label, value=current_cfg.value, max_value=current_cfg.max_value)
            new_w = StatRowWidget(
                self.rows_container, row_index=idx + 1, config=new_cfg,
                on_change_cb=self.schedule_redraw, on_delete_cb=self._delete_row, on_move_cb=self._move_row
            )
            self.row_widgets.insert(idx + 1, new_w)
        else:
            new_idx = idx + delta
            if new_idx < 0 or new_idx >= len(self.row_widgets):
                return
            self.row_widgets[idx], self.row_widgets[new_idx] = self.row_widgets[new_idx], self.row_widgets[idx]

        for w in self.row_widgets:
            w.pack_forget()
        for w in self.row_widgets:
            w.pack(fill=tk.X, pady=2)
        self.schedule_redraw()

    # --------------------------------------------------------------------------
    # State Synchronization
    # --------------------------------------------------------------------------
    def _update_config_from_ui(self):
        self.config.photo_fit = self.fit_var.get()
        self.config.panel_side = self.side_var.get()
        self.config.panel_width_ratio = self.width_var.get()
        self.config.panel_opacity = self.opacity_var.get()
        self.config.aspect_ratio = self.aspect_var.get()
        self.config.subtitle_text = self.sub_var.get()
        self.config.title_text = self.title_text_widget.get("1.0", "end-1c")
        self.config.title_font_size = self.title_size_var.get()
        self.config.label_font_size = self.label_size_var.get()
        self.config.value_font_size = self.value_size_var.get()
        self.config.font_bold_path = self.font_bold_path.get()
        self.config.font_regular_path = self.font_regular_path.get()
        self.config.export_format = self.export_format_var.get()
        self.config.export_quality = self.quality_var.get()
        self.config.export_scale = self.export_scale_var.get()

        self.config.rows = [w.get_config().to_dict() if hasattr(w.get_config(), "to_dict") else asdict(w.get_config()) for w in self.row_widgets]

    def _apply_config_to_ui(self):
        self.fit_var.set(self.config.photo_fit)
        self.side_var.set(self.config.panel_side)
        self.width_var.set(self.config.panel_width_ratio)
        self.opacity_var.set(self.config.panel_opacity)
        self.aspect_var.set(self.config.aspect_ratio)
        self.sub_var.set(self.config.subtitle_text)

        self.title_text_widget.delete("1.0", tk.END)
        self.title_text_widget.insert("1.0", self.config.title_text)

        self.title_size_var.set(self.config.title_font_size)
        self.label_size_var.set(self.config.label_font_size)
        self.value_size_var.set(self.config.value_font_size)
        self.font_bold_path.set(self.config.font_bold_path)
        self.font_regular_path.set(self.config.font_regular_path)
        self.export_format_var.set(self.config.export_format)
        self.quality_var.set(self.config.export_quality)
        self.export_scale_var.set(self.config.export_scale)

        if self.config.photo_path and os.path.exists(self.config.photo_path):
            self.img_path_lbl.config(text=os.path.basename(self.config.photo_path), foreground="#000")
        else:
            self.img_path_lbl.config(text="No image selected", foreground="#777")

        for k, btn in self.color_buttons.items():
            btn.config(bg=self._rgb_to_hex(getattr(self.config, k)))

        for w in self.row_widgets:
            w.destroy()
        self.row_widgets.clear()
        for r in self.config.rows:
            self._add_row(RowData(**r))

    # --------------------------------------------------------------------------
    # Font & File IO Actions
    # --------------------------------------------------------------------------
    def _browse_font(self, font_type: str):
        path = filedialog.askopenfilename(title=f"Select {font_type} font", filetypes=[("Fonts", "*.ttf *.otf")])
        if path:
            if font_type == "bold":
                self.font_bold_path.set(path)
            else:
                self.font_regular_path.set(path)
            self.schedule_redraw()

    def choose_image(self):
        path = filedialog.askopenfilename(title="Select Photo", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.config.photo_path = path
            self.img_path_lbl.config(text=os.path.basename(path), foreground="#000")
            self.schedule_redraw()

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            try:
                self.config = ScoreboardConfig.load_from_file(path)
                self.current_config_path = path
                self._apply_config_to_ui()
                self.schedule_redraw()
                self.status_var.set(f"Loaded config: {path}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not load JSON config: {e}")

    def save_config(self):
        if not self.current_config_path:
            self.current_config_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if self.current_config_path:
            self._update_config_from_ui()
            self.config.save_to_file(self.current_config_path)
            self.status_var.set(f"Saved configuration to {self.current_config_path}")

    def reset_defaults(self):
        if messagebox.askyesno("Reset", "Reset UI and settings to original defaults?"):
            self.config = ScoreboardConfig()
            self.current_config_path = None
            self._apply_config_to_ui()
            self.schedule_redraw()

    # --------------------------------------------------------------------------
    # Threaded Asynchronous Redraw Pipeline
    # --------------------------------------------------------------------------
    def schedule_redraw(self, *args):
        if self._redraw_timer:
            self.root.after_cancel(self._redraw_timer)
        self._redraw_timer = self.root.after(150, self._push_render_job)

    def _push_render_job(self):
        self._update_config_from_ui()
        self.render_queue.put(self.config)

    def _start_render_worker(self):
        def worker():
            while True:
                cfg = self.render_queue.get()
                # Clear queue backlog to render only latest request
                while not self.render_queue.empty():
                    cfg = self.render_queue.get_nowait()
                try:
                    img = ScoreboardRenderer.render(cfg, multiplier=1)
                    self.root.after(0, lambda i=img: self._update_preview_ui(i))
                except Exception as e:
                    logger.error(f"Render Error: {e}")
                finally:
                    self.render_queue.task_done()

        threading.Thread(target=worker, daemon=True).start()

    def _update_preview_ui(self, img: Image.Image):
        max_w = max(500, self.preview_label.winfo_width() - 20)
        max_h = max(400, self.preview_label.winfo_height() - 20)
        w, h = img.size

        scale = min(max_w / w, max_h / h, 1.0)
        preview_img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        self._tk_img = ImageTk.PhotoImage(preview_img)
        self.preview_label.config(image=self._tk_img)

    # --------------------------------------------------------------------------
    # Image Export Engine
    # --------------------------------------------------------------------------
    def export_image(self):
        self._update_config_from_ui()
        fmt = self.config.export_format.lower()
        ext = "jpg" if fmt == "jpeg" else fmt
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}", filetypes=[(f"{fmt.upper()} Image", f"*.{ext}")])

        if path:
            try:
                high_res_img = ScoreboardRenderer.render(self.config, multiplier=self.config.export_scale)
                save_args = {}
                if fmt in ("jpeg", "webp"):
                    save_args["quality"] = self.config.export_quality
                high_res_img.save(path, format=fmt.upper(), **save_args)
                messagebox.showinfo("Success", f"Graphics exported successfully to:\n{path}")
                self.status_var.set(f"Exported graphics to {path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export graphic: {e}")

# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = ScoreboardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()