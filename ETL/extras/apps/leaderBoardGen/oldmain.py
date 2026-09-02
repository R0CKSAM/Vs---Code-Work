#!/usr/bin/env python3
"""
Scoreboard / Match Stats Card Generator (Pro Edition)
---------------------------------------------------------
Features:
- Modern UI (CustomTkinter)
- Native Drag & Drop Images (tkinterdnd2)
- Broadcast-Quality Rendering (Glassmorphism, Shadows)
- Background Caching & Threaded Rendering Pipeline
- Advanced Padding & Spacing Controls
- Draggable Player/Subject Overlay (Drop a PNG!)
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
from tkinter import colorchooser, filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ------------------------------------------------------------------------------
# Logging & System Setup
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("ScoreboardGenerator")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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
        "bg_color": [10, 30, 48], "panel_top_color": [8, 10, 14], "panel_bottom_color": [14, 34, 52],
        "accent_color": [223, 255, 60], "bar_track_color": [70, 90, 105],
        "title_color": [255, 255, 255], "label_color": [225, 230, 232],
    },
    "Cyberpunk Neon": {
        "bg_color": [15, 5, 25], "panel_top_color": [20, 10, 35], "panel_bottom_color": [5, 2, 10],
        "accent_color": [255, 0, 128], "bar_track_color": [60, 20, 80],
        "title_color": [0, 255, 240], "label_color": [240, 240, 240],
    },
    "Emerald Pitch": {
        "bg_color": [5, 25, 15], "panel_top_color": [10, 30, 20], "panel_bottom_color": [2, 12, 8],
        "accent_color": [46, 213, 115], "bar_track_color": [30, 60, 45],
        "title_color": [255, 255, 255], "label_color": [200, 230, 210],
    },
    "Minimal Light": {
        "bg_color": [240, 242, 245], "panel_top_color": [255, 255, 255], "panel_bottom_color": [235, 238, 242],
        "accent_color": [0, 102, 255], "bar_track_color": [200, 210, 220],
        "title_color": [20, 25, 30], "label_color": [60, 70, 80],
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
    photo_fit: str = "cover"
    
    # Overlay Properties
    overlay_path: str = ""
    overlay_x: float = 0.0  
    overlay_y: float = 0.0  
    overlay_scale: float = 100.0 

    panel_side: str = "right"
    panel_width_ratio: float = 0.42
    panel_opacity: float = 0.90
    
    # Spacing and Margins (Percentages of Canvas Height/Width)
    margin_x: float = 9.0
    margin_y: float = 5.0
    spacing_title: float = 3.0
    spacing_rows: float = 3.0
    spacing_items: float = 1.0

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
            return cls.from_dict(json.load(f))

# ------------------------------------------------------------------------------
# High-Performance Rendering Engine
# ------------------------------------------------------------------------------
class ScoreboardRenderer:
    _font_cache: Dict[Tuple[str, int], ImageFont.ImageFont] = {}
    _cached_bg: Optional[Image.Image] = None
    _cached_bg_key: Optional[Tuple] = None

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
                "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc"
            ]
            for candidate in sys_fonts:
                if os.path.exists(candidate):
                    try:
                        font = ImageFont.truetype(candidate, size)
                        break
                    except Exception:
                        continue
        if font is None:
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
        if num is None: return 0.0
        try: max_val = float(max_value)
        except (TypeError, ValueError): max_val = 100.0
        return max(0.0, min(100.0, (num / max_val) * 100.0)) if max_val > 0 else 0.0

    @classmethod
    def get_background(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
        cache_key = (config.photo_path, W, H, config.photo_fit, tuple(config.bg_color))
        if cls._cached_bg_key == cache_key and cls._cached_bg:
            return cls._cached_bg.copy()

        img = Image.new("RGB", (W, H), tuple(config.bg_color))
        if config.photo_path and os.path.exists(config.photo_path):
            try:
                photo = Image.open(config.photo_path).convert("RGB")
                fit = config.photo_fit
                if fit == "cover":
                    pw, ph = photo.size
                    src_ratio, target_ratio = pw / ph, W / H
                    new_h = H if src_ratio > target_ratio else int(W / src_ratio)
                    new_w = int(src_ratio * new_h) if src_ratio > target_ratio else W
                    photo = photo.resize((new_w, new_h), Image.LANCZOS)
                    left, top = (new_w - W) // 2, (new_h - H) // 2
                    photo = photo.crop((left, top, left + W, top + H))
                    img.paste(photo, (0, 0))
                elif fit == "contain":
                    photo.thumbnail((W, H), Image.LANCZOS)
                    img.paste(photo, ((W - photo.size[0]) // 2, (H - photo.size[1]) // 2))
                else:
                    img.paste(photo.resize((W, H), Image.LANCZOS), (0, 0))
            except Exception as e:
                logger.error(f"Failed loading photo: {e}")

        cls._cached_bg = img
        cls._cached_bg_key = cache_key
        return img.copy()

    @staticmethod
    def create_gradient_panel(width: int, height: int, top_color: Tuple, bottom_color: Tuple, opacity: float) -> Image.Image:
        alpha = int(255 * opacity)
        if HAS_NUMPY:
            t = np.linspace(0, 1, height, dtype=np.float32)[:, None]
            c_top, c_bot = np.array(top_color, dtype=np.float32), np.array(bottom_color, dtype=np.float32)
            rgb = (c_top * (1 - t) + c_bot * t).astype(np.uint8)
            arr = np.tile(rgb[:, None, :], (1, width, 1))
            alpha_arr = np.full((height, width, 1), alpha, dtype=np.uint8)
            return Image.fromarray(np.concatenate([arr, alpha_arr], axis=-1), mode="RGBA")
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
        
        img = cls.get_background(config, W, H)
        
        # Apply Overlay Image (Drag & Drop PNG)
        if config.overlay_path and os.path.exists(config.overlay_path):
            try:
                overlay = Image.open(config.overlay_path).convert("RGBA")
                target_h = int(H * (config.overlay_scale / 100.0) * multiplier)
                aspect = overlay.width / overlay.height
                target_w = int(target_h * aspect)
                
                if target_w > 0 and target_h > 0:
                    overlay = overlay.resize((target_w, target_h), Image.LANCZOS)
                    pos_x = int(W * (config.overlay_x / 100.0))
                    pos_y = int(H * (config.overlay_y / 100.0))
                    
                    temp_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    temp_canvas.paste(overlay, (pos_x, pos_y), overlay)
                    img = Image.alpha_composite(img.convert("RGBA"), temp_canvas).convert("RGB")
            except Exception as e:
                logger.error(f"Failed rendering overlay: {e}")

        panel_w = int(W * config.panel_width_ratio)
        if panel_w <= 0: return img

        x_start = W - panel_w if config.panel_side == "right" else 0

        # Glassmorphism Blur Effect
        panel_box = (x_start, 0, x_start + panel_w, H)
        under_panel = img.crop(panel_box).filter(ImageFilter.GaussianBlur(radius=15 * multiplier))
        img.paste(under_panel, panel_box)

        # Drop Shadow Effect
        shadow_w = 25 * multiplier
        shadow = Image.new("RGBA", (panel_w + shadow_w, H), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rectangle([0, 0, panel_w, H], fill=(0, 0, 0, 160))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=12 * multiplier))
        
        overlay_ui = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow_x = x_start - (shadow_w // 2) if config.panel_side == "right" else 0
        overlay_ui.paste(shadow, (shadow_x, 0), shadow)

        # Apply Gradient Panel
        panel_img = cls.create_gradient_panel(panel_w, H, tuple(config.panel_top_color), tuple(config.panel_bottom_color), config.panel_opacity)
        overlay_ui.paste(panel_img, (x_start, 0), panel_img)
        img = Image.alpha_composite(img.convert("RGBA"), overlay_ui).convert("RGB")

        # Typography & Data Elements
        draw = ImageDraw.Draw(img, "RGBA")
        
        margin_x_px = int(panel_w * (config.margin_x / 100.0))
        margin_y_px = int(H * (config.margin_y / 100.0))
        spacing_title_px = int(H * (config.spacing_title / 100.0))
        spacing_rows_px = int(H * (config.spacing_rows / 100.0))
        spacing_items_px = int(H * (config.spacing_items / 100.0))
        
        text_x = x_start + margin_x_px
        text_w = panel_w - (margin_x_px * 2)
        cur_y = margin_y_px
        
        # Subtitle
        if config.subtitle_text.strip():
            sub_size = int(config.label_font_size * 0.8 * multiplier)
            sub_font = cls.load_font(config.font_regular_path, sub_size)
            draw.text((text_x, cur_y), config.subtitle_text.upper(), font=sub_font, fill=tuple(config.accent_color))
            bbox = draw.textbbox((0, 0), config.subtitle_text.upper(), font=sub_font)
            cur_y += (bbox[3] - bbox[1]) + spacing_items_px

        # Title
        title_size = int(config.title_font_size * multiplier)
        title_font = cls.load_font(config.font_bold_path, title_size)
        for line in config.title_text.splitlines():
            draw.text((text_x, cur_y), line, font=title_font, fill=tuple(config.title_color))
            bbox = draw.textbbox((0, 0), line, font=title_font)
            cur_y += (bbox[3] - bbox[1]) + int(title_size * 0.2)

        cur_y += spacing_title_px

        # Stat Rows
        rows = config.rows or [{"label": "No Data", "value": "0", "max_value": "100"}]
        lbl_font = cls.load_font(config.font_regular_path, int(config.label_font_size * multiplier))
        val_font = cls.load_font(config.font_bold_path, int(config.value_font_size * multiplier))
        bar_h = max(4 * multiplier, int(H * 0.014))

        for row in rows:
            # Label
            draw.text((text_x, cur_y), row["label"], font=lbl_font, fill=tuple(config.label_color))
            l_bbox = draw.textbbox((0, 0), row["label"], font=lbl_font)
            cur_y += (l_bbox[3] - l_bbox[1]) + spacing_items_px

            # Value
            val_str = str(row["value"])
            draw.text((text_x, cur_y), val_str, font=val_font, fill=tuple(config.accent_color))
            v_bbox = draw.textbbox((0, 0), val_str, font=val_font)
            cur_y += (v_bbox[3] - v_bbox[1]) + spacing_items_px

            # Bar
            pct = cls.calculate_percent(val_str, row.get("max_value", "100"))
            bar_y0, bar_y1 = cur_y, cur_y + bar_h
            draw.rounded_rectangle([text_x, bar_y0, text_x + text_w, bar_y1], radius=bar_h // 2, fill=tuple(config.bar_track_color))
            
            fill_w = int(text_w * (pct / 100.0))
            if fill_w > 0:
                draw.rounded_rectangle([text_x, bar_y0, text_x + max(fill_w, bar_h), bar_y1], radius=bar_h // 2, fill=tuple(config.accent_color))
            
            cur_y = bar_y1 + spacing_rows_px

        return img

# ------------------------------------------------------------------------------
# Embedded Row Controls Widget (CustomTkinter)
# ------------------------------------------------------------------------------
class StatRowWidget(ctk.CTkFrame):
    def __init__(self, parent, row_index: int, row_data: RowData, on_change_cb, on_delete_cb, on_move_cb):
        super().__init__(parent, fg_color="transparent")
        self.row_data = row_data
        self.on_change_cb = on_change_cb
        self.on_delete_cb = on_delete_cb
        self.on_move_cb = on_move_cb

        self.label_var = ctk.StringVar(value=row_data.label)
        self.value_var = ctk.StringVar(value=row_data.value)
        self.max_var = ctk.StringVar(value=row_data.max_value)

        self._build_ui()
        for var in (self.label_var, self.value_var, self.max_var):
            var.trace_add("write", lambda *a: self._notify_change())

    def _build_ui(self):
        ctk.CTkLabel(self, text="Lbl:").grid(row=0, column=0, padx=(0, 4))
        ctk.CTkEntry(self, textvariable=self.label_var, width=140).grid(row=0, column=1, padx=2)
        ctk.CTkLabel(self, text="Val:").grid(row=0, column=2, padx=(8, 4))
        ctk.CTkEntry(self, textvariable=self.value_var, width=70).grid(row=0, column=3, padx=2)
        ctk.CTkLabel(self, text="Max:").grid(row=0, column=4, padx=(8, 4))
        ctk.CTkEntry(self, textvariable=self.max_var, width=50).grid(row=0, column=5, padx=2)
        
        btn_args = {"width": 30, "height": 28, "fg_color": "#444", "hover_color": "#666"}
        ctk.CTkButton(self, text="▲", command=lambda: self.on_move_cb(self, -1), **btn_args).grid(row=0, column=6, padx=(8, 2))
        ctk.CTkButton(self, text="▼", command=lambda: self.on_move_cb(self, 1), **btn_args).grid(row=0, column=7, padx=2)
        ctk.CTkButton(self, text="⎘", command=lambda: self.on_move_cb(self, 0, True), **btn_args).grid(row=0, column=8, padx=2)
        
        del_args = btn_args.copy()
        del_args.update({"fg_color": "#A33", "hover_color": "#D44"})
        ctk.CTkButton(self, text="✕", command=lambda: self.on_delete_cb(self), **del_args).grid(row=0, column=9, padx=(8, 0))

    def _notify_change(self):
        self.row_data.label, self.row_data.value, self.row_data.max_value = self.label_var.get(), self.value_var.get(), self.max_var.get()
        self.on_change_cb()

    def get_config(self) -> RowData:
        return RowData(label=self.label_var.get(), value=self.value_var.get(), max_value=self.max_var.get())

# ------------------------------------------------------------------------------
# Main Application Interface (TkinterDnD + CustomTkinter)
# ------------------------------------------------------------------------------
class ScoreboardApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Match Stats Studio (Pro)")
        self.geometry("1500x950")
        self.minsize(1200, 750)

        # Drag and Drop setup
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_file_drop)

        self.app_config = ScoreboardConfig()
        self.current_config_path: Optional[str] = None
        self.row_widgets: List[StatRowWidget] = []
        self._tk_img: Optional[ImageTk.PhotoImage] = None

        self._drag_data = {"x": 0, "y": 0, "active": False}
        self._current_preview_scale = 1.0

        self.render_queue = queue.Queue()
        self._redraw_timer: Optional[str] = None

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        self._build_ui()
        self._apply_config_to_ui()
        self._start_render_worker()
        self.schedule_redraw()

    def on_file_drop(self, event):
        file_path = event.data.strip('{}')
        if not file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
            return

        # Simple logic: If it's a PNG, treat as overlay. Otherwise treat as background.
        if file_path.lower().endswith('.png'):
            self.app_config.overlay_path = file_path
            self.status_var.set(f"Loaded Overlay: {os.path.basename(file_path)}")
        else:
            self.app_config.photo_path = file_path
            self.img_path_lbl.configure(text=os.path.basename(file_path))
            self.status_var.set(f"Loaded Background: {os.path.basename(file_path)}")
            
        self.schedule_redraw()

    def _build_ui(self):
        # Left Panel (Scrollable Controls)
        self.controls_panel = ctk.CTkScrollableFrame(self.main_frame, width=540, corner_radius=0)
        self.controls_panel.pack(side="left", fill="y", padx=0, pady=0)

        # Right Panel (Preview)
        self.preview_panel = ctk.CTkFrame(self.main_frame, fg_color="#1a1a1a", corner_radius=0)
        self.preview_panel.pack(side="right", fill="both", expand=True)

        ctk.CTkLabel(self.preview_panel, text="Live Canvas Preview (Drag & Drop BG / Drop PNG for Overlay)\nDrag overlay with mouse", font=("Arial", 16, "bold"), text_color="#777").pack(pady=(20, 0))
        
        # Canvas for Preview & Interactivity
        self.preview_canvas = tk.Canvas(self.preview_panel, bg="#1a1a1a", highlightthickness=0)
        self.preview_canvas.pack(padx=20, pady=20, fill="both", expand=True)
        
        self.preview_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        self._build_preset_controls()
        self._build_file_controls()
        self._build_content_controls()
        self._build_image_controls()
        self._build_layout_controls()
        self._build_spacing_controls()
        self._build_color_controls()
        self._build_font_controls()
        self._build_rows_controls()
        self._build_export_controls()

        # Status Bar
        self.status_var = ctk.StringVar(value="Ready. Drop a JPG for Background or PNG for draggable Overlay.")
        status_bar = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w", fg_color="#222", corner_radius=0, padx=10, height=25)
        status_bar.pack(side="bottom", fill="x")

    def _make_section(self, title: str) -> ctk.CTkFrame:
        frm = ctk.CTkFrame(self.controls_panel, fg_color="#2b2b2b")
        frm.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(frm, text=title, font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        content = ctk.CTkFrame(frm, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(0, 10))
        return content

    def _build_preset_controls(self):
        sec = self._make_section("Quick Presets")
        preset_combo = ctk.CTkComboBox(sec, values=list(PRESET_THEMES.keys()), command=self.apply_preset, width=300)
        preset_combo.pack(side="left", padx=5)

    def _build_file_controls(self):
        sec = self._make_section("File & State")
        ctk.CTkButton(sec, text="Load JSON", command=self.load_config, width=100).pack(side="left", padx=5)
        ctk.CTkButton(sec, text="Save JSON", command=self.save_config, width=100).pack(side="left", padx=5)
        ctk.CTkButton(sec, text="Reset", command=self.reset_defaults, width=80, fg_color="#A33", hover_color="#D44").pack(side="left", padx=5)

    def _build_content_controls(self):
        sec = self._make_section("Titles & Headlines")
        ctk.CTkLabel(sec, text="Subtitle Header:").pack(anchor="w")
        self.sub_var = ctk.StringVar()
        ctk.CTkEntry(sec, textvariable=self.sub_var).pack(fill="x", pady=5)
        self.sub_var.trace_add("write", lambda *a: self.schedule_redraw())

        ctk.CTkLabel(sec, text="Main Title Text (Multiline):").pack(anchor="w", pady=(5, 0))
        self.title_text_widget = ctk.CTkTextbox(sec, height=70)
        self.title_text_widget.pack(fill="x", pady=5)
        self.title_text_widget.bind("<KeyRelease>", lambda e: self.schedule_redraw())

    def _build_image_controls(self):
        sec = self._make_section("Images & Background")
        frm = ctk.CTkFrame(sec, fg_color="transparent")
        frm.pack(fill="x")
        ctk.CTkButton(frm, text="Browse BG", command=self.choose_image, width=120).pack(side="left", padx=5)
        self.img_path_lbl = ctk.CTkLabel(frm, text="No background selected", text_color="#888")
        self.img_path_lbl.pack(side="left", padx=10)

        fit_frm = ctk.CTkFrame(sec, fg_color="transparent")
        fit_frm.pack(fill="x", pady=5)
        ctk.CTkLabel(fit_frm, text="BG Fit:").pack(side="left", padx=5)
        self.fit_var = ctk.StringVar(value="cover")
        ctk.CTkComboBox(fit_frm, variable=self.fit_var, values=["cover", "contain", "stretch"], command=lambda e: self.schedule_redraw(), width=100).pack(side="left", padx=10)
        
        # Overlay Control
        over_frm = ctk.CTkFrame(sec, fg_color="transparent")
        over_frm.pack(fill="x", pady=10)
        ctk.CTkButton(over_frm, text="Clear Overlay", command=self.clear_overlay, width=120, fg_color="#A33", hover_color="#D44").pack(side="left", padx=5)
        ctk.CTkLabel(over_frm, text="Overlay Scale:").pack(side="left", padx=(10, 5))
        self.overlay_scale_var = tk.DoubleVar(value=100.0)
        ctk.CTkSlider(over_frm, from_=10, to=200, variable=self.overlay_scale_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

    def _build_layout_controls(self):
        sec = self._make_section("Layout Geometry")
        
        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Canvas Ratio:").pack(side="left")
        self.aspect_var = ctk.StringVar(value=list(ASPECT_RATIOS.keys())[0])
        ctk.CTkComboBox(row1, variable=self.aspect_var, values=list(ASPECT_RATIOS.keys()), command=lambda e: self.schedule_redraw(), width=200).pack(side="left", padx=10)

        ctk.CTkLabel(row1, text="Panel Side:").pack(side="left", padx=(10,5))
        self.side_var = ctk.StringVar(value="right")
        ctk.CTkComboBox(row1, variable=self.side_var, values=["left", "right"], command=lambda e: self.schedule_redraw(), width=80).pack(side="left")

        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Panel Width:").pack(side="left")
        self.width_var = tk.DoubleVar(value=0.42)
        ctk.CTkSlider(row2, from_=0.20, to=0.70, variable=self.width_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True, padx=10)

        row3 = ctk.CTkFrame(sec, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Panel Opacity:").pack(side="left")
        self.opacity_var = tk.DoubleVar(value=0.92)
        ctk.CTkSlider(row3, from_=0.20, to=1.0, variable=self.opacity_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True, padx=10)

    def _build_spacing_controls(self):
        sec = self._make_section("Padding & Spacing (%)")
        
        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Side Margin:").pack(side="left", padx=(0,5))
        self.margin_x_var = tk.DoubleVar(value=9.0)
        ctk.CTkSlider(row1, from_=0, to=30, variable=self.margin_x_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(row1, text="Top Margin:").pack(side="left", padx=(10,5))
        self.margin_y_var = tk.DoubleVar(value=5.0)
        ctk.CTkSlider(row1, from_=0, to=30, variable=self.margin_y_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Title Space:").pack(side="left", padx=(0,5))
        self.spacing_title_var = tk.DoubleVar(value=3.0)
        ctk.CTkSlider(row2, from_=0, to=15, variable=self.spacing_title_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(row2, text="Row Space:").pack(side="left", padx=(10,5))
        self.spacing_rows_var = tk.DoubleVar(value=3.0)
        ctk.CTkSlider(row2, from_=0, to=20, variable=self.spacing_rows_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

        row3 = ctk.CTkFrame(sec, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Inner Gap:").pack(side="left", padx=(0,5))
        self.spacing_items_var = tk.DoubleVar(value=1.0)
        ctk.CTkSlider(row3, from_=0, to=10, variable=self.spacing_items_var, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True)

    def _build_color_controls(self):
        sec = self._make_section("Color Palette")
        colors = [("Background", "bg_color"), ("Panel Top", "panel_top_color"), ("Panel Bottom", "panel_bottom_color"), 
                  ("Accent", "accent_color"), ("Bar Track", "bar_track_color"), ("Title", "title_color"), ("Label Text", "label_color")]
        self.color_buttons: Dict[str, ctk.CTkButton] = {}
        
        for i, (label, key) in enumerate(colors):
            row, col = i // 2, (i % 2) * 2
            frm = ctk.CTkFrame(sec, fg_color="transparent")
            frm.grid(row=row, column=col, sticky="w", padx=10, pady=5)
            ctk.CTkLabel(frm, text=label + ":", width=90, anchor="w").pack(side="left")
            btn = ctk.CTkButton(frm, text="", width=30, height=20, border_width=1, border_color="#777", command=lambda k=key: self._pick_color(k))
            btn.pack(side="left")
            self.color_buttons[key] = btn

    def _build_font_controls(self):
        sec = self._make_section("Typography Settings")
        self.font_bold_path, self.font_regular_path = ctk.StringVar(), ctk.StringVar()

        for label, var, ftype in [("Bold Font:", self.font_bold_path, "bold"), ("Reg Font:", self.font_regular_path, "regular")]:
            frm = ctk.CTkFrame(sec, fg_color="transparent")
            frm.pack(fill="x", pady=5)
            ctk.CTkLabel(frm, text=label, width=70, anchor="w").pack(side="left")
            ctk.CTkEntry(frm, textvariable=var).pack(side="left", fill="x", expand=True, padx=5)
            ctk.CTkButton(frm, text="...", width=40, command=lambda t=ftype: self._browse_font(t)).pack(side="left")

        size_frm = ctk.CTkFrame(sec, fg_color="transparent")
        size_frm.pack(fill="x", pady=10)
        self.title_size_var, self.label_size_var, self.value_size_var = ctk.StringVar(value="36"), ctk.StringVar(value="18"), ctk.StringVar(value="30")
        
        for l, v in [("Title Size:", self.title_size_var), ("Label:", self.label_size_var), ("Value:", self.value_size_var)]:
            ctk.CTkLabel(size_frm, text=l).pack(side="left", padx=(10 if l != "Title Size:" else 0, 5))
            e = ctk.CTkEntry(size_frm, textvariable=v, width=50)
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda e: self.schedule_redraw())

    def _build_rows_controls(self):
        sec = self._make_section("Stat Metrics & Data Rows")
        self.rows_container = ctk.CTkFrame(sec, fg_color="transparent")
        self.rows_container.pack(fill="x", pady=5)

        btn_frm = ctk.CTkFrame(sec, fg_color="transparent")
        btn_frm.pack(fill="x", pady=5)
        ctk.CTkButton(btn_frm, text="+ Add Metric Row", command=self._add_row).pack(side="left", padx=5)
        ctk.CTkButton(btn_frm, text="Clear All", command=self._clear_rows, fg_color="#A33", hover_color="#D44").pack(side="left", padx=5)

    def _build_export_controls(self):
        sec = self._make_section("Export Options")
        frm = ctk.CTkFrame(sec, fg_color="transparent")
        frm.pack(fill="x", pady=5)

        ctk.CTkLabel(frm, text="Format:").pack(side="left")
        self.export_format_var = ctk.StringVar(value="PNG")
        ctk.CTkComboBox(frm, variable=self.export_format_var, values=["PNG", "JPEG", "WebP"], width=80).pack(side="left", padx=5)

        ctk.CTkLabel(frm, text="Scale:").pack(side="left", padx=(10, 0))
        self.export_scale_var = ctk.StringVar(value="1")
        ctk.CTkComboBox(frm, variable=self.export_scale_var, values=["1", "2", "4"], width=60).pack(side="left", padx=5)

        ctk.CTkLabel(frm, text="Quality:").pack(side="left", padx=(10, 0))
        self.quality_var = ctk.StringVar(value="95")
        ctk.CTkEntry(frm, textvariable=self.quality_var, width=50).pack(side="left", padx=5)

        ctk.CTkButton(sec, text="Export Final Graphic", command=self.export_image, height=40, font=("Arial", 14, "bold"), fg_color="#18844D", hover_color="#1FA560").pack(fill="x", pady=10)

    # --------------------------------------------------------------------------
    # Canvas Drag Events (Overlay Interactivity)
    # --------------------------------------------------------------------------
    def on_canvas_press(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["active"] = True

    def on_canvas_drag(self, event):
        if not self._drag_data["active"]: return
        
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        
        base_w, base_h = ASPECT_RATIOS.get(self.app_config.aspect_ratio, (1024, 576))
        
        pct_x = (dx / self._current_preview_scale) / base_w * 100.0
        pct_y = (dy / self._current_preview_scale) / base_h * 100.0
        
        self.app_config.overlay_x += pct_x
        self.app_config.overlay_y += pct_y
        
        self.schedule_redraw()

    def on_canvas_release(self, event):
        self._drag_data["active"] = False

    # --------------------------------------------------------------------------
    # Utilities & Actions
    # --------------------------------------------------------------------------
    @staticmethod
    def _rgb_to_hex(rgb: List[int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _pick_color(self, key: str):
        current = getattr(self.app_config, key)
        color = colorchooser.askcolor(title=f"Pick Color for {key}", initialcolor=tuple(current))
        if color and color[0]:
            rgb = [int(c) for c in color[0]]
            setattr(self.app_config, key, rgb)
            self.color_buttons[key].configure(fg_color=self._rgb_to_hex(rgb))
            self.schedule_redraw()

    def apply_preset(self, theme_name: str):
        if theme_name in PRESET_THEMES:
            for k, rgb in PRESET_THEMES[theme_name].items():
                setattr(self.app_config, k, rgb)
                if k in self.color_buttons:
                    self.color_buttons[k].configure(fg_color=self._rgb_to_hex(rgb))
            self.schedule_redraw()

    def _add_row(self, config: Optional[RowData] = None):
        widget = StatRowWidget(self.rows_container, len(self.row_widgets), config or RowData(), self.schedule_redraw, self._delete_row, self._move_row)
        widget.pack(fill="x", pady=3)
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
        for w in self.row_widgets: w.destroy()
        self.row_widgets.clear()
        self._add_row()

    def _move_row(self, widget: StatRowWidget, delta: int, duplicate: bool = False):
        if widget not in self.row_widgets: return
        idx = self.row_widgets.index(widget)
        if duplicate:
            cfg = widget.get_config()
            new_w = StatRowWidget(self.rows_container, idx + 1, RowData(cfg.label, cfg.value, cfg.max_value), self.schedule_redraw, self._delete_row, self._move_row)
            self.row_widgets.insert(idx + 1, new_w)
        else:
            new_idx = idx + delta
            if 0 <= new_idx < len(self.row_widgets):
                self.row_widgets[idx], self.row_widgets[new_idx] = self.row_widgets[new_idx], self.row_widgets[idx]
        for w in self.row_widgets: w.pack_forget()
        for w in self.row_widgets: w.pack(fill="x", pady=3)
        self.schedule_redraw()

    def _safe_int(self, val: str, default: int) -> int:
        try: return int(val)
        except ValueError: return default

    def _update_config_from_ui(self):
        self.app_config.photo_fit = self.fit_var.get()
        self.app_config.overlay_scale = self.overlay_scale_var.get()
        self.app_config.panel_side = self.side_var.get()
        self.app_config.panel_width_ratio = self.width_var.get()
        self.app_config.panel_opacity = self.opacity_var.get()
        
        self.app_config.margin_x = self.margin_x_var.get()
        self.app_config.margin_y = self.margin_y_var.get()
        self.app_config.spacing_title = self.spacing_title_var.get()
        self.app_config.spacing_rows = self.spacing_rows_var.get()
        self.app_config.spacing_items = self.spacing_items_var.get()
        
        self.app_config.aspect_ratio = self.aspect_var.get()
        self.app_config.subtitle_text = self.sub_var.get()
        self.app_config.title_text = self.title_text_widget.get("1.0", "end-1c")
        self.app_config.title_font_size = self._safe_int(self.title_size_var.get(), 36)
        self.app_config.label_font_size = self._safe_int(self.label_size_var.get(), 18)
        self.app_config.value_font_size = self._safe_int(self.value_size_var.get(), 30)
        self.app_config.font_bold_path = self.font_bold_path.get()
        self.app_config.font_regular_path = self.font_regular_path.get()
        self.app_config.export_format = self.export_format_var.get()
        self.app_config.export_quality = self._safe_int(self.quality_var.get(), 95)
        self.app_config.export_scale = self._safe_int(self.export_scale_var.get(), 1)
        self.app_config.rows = [asdict(w.get_config()) for w in self.row_widgets]

    def _apply_config_to_ui(self):
        self.fit_var.set(self.app_config.photo_fit)
        self.overlay_scale_var.set(self.app_config.overlay_scale)
        self.side_var.set(self.app_config.panel_side)
        self.width_var.set(self.app_config.panel_width_ratio)
        self.opacity_var.set(self.app_config.panel_opacity)
        
        self.margin_x_var.set(self.app_config.margin_x)
        self.margin_y_var.set(self.app_config.margin_y)
        self.spacing_title_var.set(self.app_config.spacing_title)
        self.spacing_rows_var.set(self.app_config.spacing_rows)
        self.spacing_items_var.set(self.app_config.spacing_items)
        
        self.aspect_var.set(self.app_config.aspect_ratio)
        self.sub_var.set(self.app_config.subtitle_text)

        self.title_text_widget.delete("1.0", tk.END)
        self.title_text_widget.insert("1.0", self.app_config.title_text)

        self.title_size_var.set(str(self.app_config.title_font_size))
        self.label_size_var.set(str(self.app_config.label_font_size))
        self.value_size_var.set(str(self.app_config.value_font_size))
        self.font_bold_path.set(self.app_config.font_bold_path)
        self.font_regular_path.set(self.app_config.font_regular_path)
        self.export_format_var.set(self.app_config.export_format)
        self.quality_var.set(str(self.app_config.export_quality))
        self.export_scale_var.set(str(self.app_config.export_scale))

        if self.app_config.photo_path and os.path.exists(self.app_config.photo_path):
            self.img_path_lbl.configure(text=os.path.basename(self.app_config.photo_path))
        
        for k, btn in self.color_buttons.items():
            btn.configure(fg_color=self._rgb_to_hex(getattr(self.app_config, k)))

        for w in self.row_widgets: w.destroy()
        self.row_widgets.clear()
        for r in self.app_config.rows: self._add_row(RowData(**r))

    def _browse_font(self, font_type: str):
        path = filedialog.askopenfilename(title=f"Select {font_type} font", filetypes=[("Fonts", "*.ttf *.otf")])
        if path:
            (self.font_bold_path if font_type == "bold" else self.font_regular_path).set(path)
            self.schedule_redraw()

    def choose_image(self):
        path = filedialog.askopenfilename(title="Select Background Photo", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self.app_config.photo_path = path
            self.img_path_lbl.configure(text=os.path.basename(path))
            self.schedule_redraw()

    def clear_overlay(self):
        self.app_config.overlay_path = ""
        self.app_config.overlay_x = 0.0
        self.app_config.overlay_y = 0.0
        self.status_var.set("Overlay cleared.")
        self.schedule_redraw()

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            try:
                self.app_config = ScoreboardConfig.load_from_file(path)
                self.current_config_path = path
                self._apply_config_to_ui()
                self.schedule_redraw()
                self.status_var.set(f"Loaded config: {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not load JSON config: {e}")

    def save_config(self):
        if not self.current_config_path:
            self.current_config_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if self.current_config_path:
            self._update_config_from_ui()
            self.app_config.save_to_file(self.current_config_path)
            self.status_var.set(f"Saved configuration to {os.path.basename(self.current_config_path)}")

    def reset_defaults(self):
        if messagebox.askyesno("Reset", "Reset UI and settings to original defaults?"):
            self.app_config = ScoreboardConfig()
            self.current_config_path = None
            self._apply_config_to_ui()
            self.schedule_redraw()

    # --------------------------------------------------------------------------
    # Threaded Redraw Pipeline
    # --------------------------------------------------------------------------
    def schedule_redraw(self, *args):
        if self._redraw_timer: self.after_cancel(self._redraw_timer)
        self._redraw_timer = self.after(150, self._push_render_job)

    def _push_render_job(self):
        self._update_config_from_ui()
        self.render_queue.put(self.app_config)

    def _start_render_worker(self):
        def worker():
            while True:
                cfg = self.render_queue.get()
                while not self.render_queue.empty(): cfg = self.render_queue.get_nowait()
                try:
                    img = ScoreboardRenderer.render(cfg, multiplier=1)
                    self.after(0, lambda i=img: self._update_preview_ui(i))
                except Exception as e: logger.error(f"Render Error: {e}")
                finally: self.render_queue.task_done()
        threading.Thread(target=worker, daemon=True).start()

    def _update_preview_ui(self, img: Image.Image):
        max_w = max(500, self.preview_panel.winfo_width() - 40)
        max_h = max(400, self.preview_panel.winfo_height() - 80)
        w, h = img.size

        self._current_preview_scale = min(max_w / w, max_h / h, 1.0)
        new_w, new_h = int(w * self._current_preview_scale), int(h * self._current_preview_scale)
        
        preview_img = img.resize((new_w, new_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(preview_img)
        
        self.preview_canvas.delete("all")
        c_w = self.preview_canvas.winfo_width()
        c_h = self.preview_canvas.winfo_height()
        
        x = c_w // 2
        y = c_h // 2
        
        self.preview_canvas.create_image(x, y, image=self._tk_img, anchor="center")

    def export_image(self):
        self._update_config_from_ui()
        fmt = self.app_config.export_format.lower()
        ext = "jpg" if fmt == "jpeg" else fmt
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}", filetypes=[(f"{fmt.upper()} Image", f"*.{ext}")])

        if path:
            try:
                self.status_var.set("Exporting high-resolution graphic... Please wait.")
                self.update()
                
                high_res_img = ScoreboardRenderer.render(self.app_config, multiplier=self.app_config.export_scale)
                save_args = {"quality": self.app_config.export_quality} if fmt in ("jpeg", "webp") else {}
                high_res_img.save(path, format=fmt.upper(), **save_args)
                
                self.status_var.set(f"Successfully exported to {os.path.basename(path)}")
                messagebox.showinfo("Success", f"Graphics exported successfully.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export graphic: {e}")
                self.status_var.set("Export failed.")

if __name__ == "__main__":
    app = ScoreboardApp()
    app.mainloop()