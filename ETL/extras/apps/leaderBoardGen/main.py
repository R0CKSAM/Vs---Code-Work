#!/usr/bin/env python3
"""
Scoreboard / Match Stats Card Generator (Pro Edition)
Features:
- Native Drag & Drop Images (tkinterdnd2) or File Browser
- Broadcast-Quality Rendering (Horizontal Fades, Overlays)
- Dropdown Font Selection 
- Independent Title & Subtitle Styling
- Draggable Player Overlay
- Full Dynamic Rows & Export Options
"""

import json
import logging
import os
import queue
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("ScoreboardGenerator")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ------------------------------------------------------------------------------
# Constants, Fonts & Theme Presets
# ------------------------------------------------------------------------------
ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "1:1 Square (1024x1024)": (1024, 1024),
    "16:9 Landscape (1024x576)": (1024, 576),
    "9:16 Story (576x1024)": (576, 1024),
    "4:5 Social (1024x1280)": (1024, 1280),
}

SYSTEM_FONTS = [
    "Arial", "Helvetica", "Verdana", "Tahoma", "Trebuchet MS", 
    "Impact", "Times New Roman", "Courier New", "Consolas"
]

PRESET_THEMES: Dict[str, Dict[str, Any]] = {
    "Pro Performance (Reference)": {
        "bg_color": [10, 30, 48], "panel_top_color": [0, 0, 0], "panel_bottom_color": [0, 0, 0],
        "panel_gradient_dir": "horizontal_fade", "panel_opacity": 0.95,
        "accent_color": [223, 255, 0], "bar_track_color": [40, 50, 60],
        "title_color": [255, 255, 255], "subtitle_color": [223, 255, 0], "label_color": [255, 255, 255],
        "font_family": "Arial", "title_font_size": 42, "subtitle_font_size": 18, 
        "value_font_size": 28, "label_font_size": 16,
    },
    "Broadcast Dark": {
        "bg_color": [10, 30, 48], "panel_top_color": [8, 10, 14], "panel_bottom_color": [14, 34, 52],
        "panel_gradient_dir": "vertical", "panel_opacity": 0.90,
        "accent_color": [223, 255, 60], "bar_track_color": [70, 90, 105],
        "title_color": [255, 255, 255], "subtitle_color": [200, 200, 200], "label_color": [225, 230, 232],
    }
}

# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------
@dataclass
class ScoreboardConfig:
    photo_path: str = ""
    photo_fit: str = "cover"
    
    overlay_path: str = ""
    overlay_x: float = 0.0  
    overlay_y: float = 0.0  
    overlay_scale: float = 100.0 

    panel_side: str = "right"
    panel_width_ratio: float = 0.45
    panel_opacity: float = 0.95
    panel_gradient_dir: str = "horizontal_fade"
    
    margin_x: float = 9.0
    margin_y: float = 10.0
    spacing_title: float = 6.0
    spacing_rows: float = 4.0
    spacing_items: float = 1.0

    bg_color: List[int] = field(default_factory=lambda: [10, 30, 48])
    panel_top_color: List[int] = field(default_factory=lambda: [0, 0, 0])
    panel_bottom_color: List[int] = field(default_factory=lambda: [0, 0, 0])
    accent_color: List[int] = field(default_factory=lambda: [223, 255, 0])
    bar_track_color: List[int] = field(default_factory=lambda: [40, 50, 60])
    title_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    subtitle_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    label_color: List[int] = field(default_factory=lambda: [255, 255, 255])
    
    title_text: str = "Performance"
    subtitle_text: str = ""
    font_family: str = "Arial"
    title_font_size: int = 42
    subtitle_font_size: int = 18
    label_font_size: int = 16
    value_font_size: int = 28
    
    rows: List[Dict[str, str]] = field(default_factory=lambda: [
        {"label": "FOREHANDS IN %", "value": "91 %", "max_value": "100"},
        {"label": "SHOT DEPTH", "value": "8.8 M", "max_value": "20"},
        {"label": "BACKHAND SPEED", "value": "109 KMH", "max_value": "150"},
        {"label": "NET CLEARANCE", "value": "1.1 M", "max_value": "3"},
    ])
    
    aspect_ratio: str = "1:1 Square (1024x1024)"
    export_format: str = "PNG"
    export_quality: int = 95
    export_scale: int = 1

# ------------------------------------------------------------------------------
# High-Performance Rendering Engine
# ------------------------------------------------------------------------------
class ScoreboardRenderer:
    _font_cache: Dict[Tuple[str, int, str], ImageFont.ImageFont] = {}
    _cached_bg: Optional[Image.Image] = None
    _cached_bg_key: Optional[Tuple] = None

    @classmethod
    def load_font(cls, family: str, size: int, weight: str = "regular") -> ImageFont.ImageFont:
        cache_key = (family, size, weight)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        font = None
        is_bold = weight == "bold"
        font_map = {
            "arial": ("arialbd.ttf" if is_bold else "arial.ttf"),
            "helvetica": ("Helvetica-Bold.ttf" if is_bold else "Helvetica.ttf"),
            "verdana": ("verdanab.ttf" if is_bold else "verdana.ttf"),
            "tahoma": ("tahomabd.ttf" if is_bold else "tahoma.ttf"),
            "trebuchet ms": ("trebucbd.ttf" if is_bold else "trebuc.ttf"),
            "impact": ("impact.ttf", "impact.ttf"), 
            "times new roman": ("timesbd.ttf" if is_bold else "times.ttf"),
            "courier new": ("courbd.ttf" if is_bold else "cour.ttf"),
            "consolas": ("consolab.ttf" if is_bold else "consola.ttf"),
        }
        
        file_name = font_map.get(family.lower(), ("arialbd.ttf" if is_bold else "arial.ttf"))
        
        try:
            font = ImageFont.truetype(file_name, size)
        except Exception:
            try:
                fallback_paths = [
                    f"/Library/Fonts/{file_name}",
                    f"/System/Library/Fonts/Supplemental/{family}.ttf",
                    f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if is_bold else 'Regular'}.ttf"
                ]
                for path in fallback_paths:
                    if os.path.exists(path):
                        font = ImageFont.truetype(path, size)
                        break
            except Exception:
                pass

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
                if config.photo_fit == "cover":
                    pw, ph = photo.size
                    src_ratio, target_ratio = pw / ph, W / H
                    new_h = H if src_ratio > target_ratio else int(W / src_ratio)
                    new_w = int(src_ratio * new_h) if src_ratio > target_ratio else W
                    photo = photo.resize((new_w, new_h), Image.LANCZOS)
                    left, top = (new_w - W) // 2, (new_h - H) // 2
                    photo = photo.crop((left, top, left + W, top + H))
                    img.paste(photo, (0, 0))
            except Exception as e:
                logger.error(f"Failed loading photo: {e}")

        cls._cached_bg = img
        cls._cached_bg_key = cache_key
        return img.copy()

    @staticmethod
    def create_panel(width: int, height: int, config: ScoreboardConfig) -> Image.Image:
        alpha_max = int(255 * config.panel_opacity)
        base = Image.new("RGBA", (width, height))
        
        if config.panel_gradient_dir == "horizontal_fade":
            for x in range(width):
                t = x / max(1, width - 1)
                if config.panel_side == "right":
                    alpha = int(alpha_max * (t ** 1.5))
                else:
                    alpha = int(alpha_max * ((1 - t) ** 1.5))
                
                r, g, b = config.panel_top_color
                for y in range(height):
                    base.putpixel((x, y), (r, g, b, alpha))
        else:
            for y in range(height):
                t = y / max(1, height - 1)
                c_top, c_bot = config.panel_top_color, config.panel_bottom_color
                r = int(c_top[0] + (c_bot[0] - c_top[0]) * t)
                g = int(c_top[1] + (c_bot[1] - c_top[1]) * t)
                b = int(c_top[2] + (c_bot[2] - c_top[2]) * t)
                for x in range(width):
                    base.putpixel((x, y), (r, g, b, alpha_max))
                    
        return base

    @classmethod
    def render(cls, config: ScoreboardConfig, multiplier: int = 1) -> Image.Image:
        base_w, base_h = ASPECT_RATIOS.get(config.aspect_ratio, (1024, 1024))
        W, H = base_w * multiplier, base_h * multiplier
        
        img = cls.get_background(config, W, H)
        
        # Apply Draggable Overlay Image
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
            except Exception: pass

        panel_w = int(W * config.panel_width_ratio)
        if panel_w <= 0: return img
        x_start = W - panel_w if config.panel_side == "right" else 0

        # Apply Panel
        overlay_ui = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        panel_img = cls.create_panel(panel_w, H, config)
        overlay_ui.paste(panel_img, (x_start, 0), panel_img)
        img = Image.alpha_composite(img.convert("RGBA"), overlay_ui).convert("RGB")

        # Typography Setup
        draw = ImageDraw.Draw(img, "RGBA")
        margin_x_px = int(panel_w * (config.margin_x / 100.0))
        margin_y_px = int(H * (config.margin_y / 100.0))
        text_x = x_start + margin_x_px
        text_w = panel_w - (margin_x_px * 2)
        cur_y = margin_y_px
        
        # Subtitle
        if config.subtitle_text.strip():
            sub_size = int(config.subtitle_font_size * multiplier)
            sub_font = cls.load_font(config.font_family, sub_size, "bold")
            draw.text((text_x, cur_y), config.subtitle_text.upper(), font=sub_font, fill=tuple(config.subtitle_color))
            bbox = draw.textbbox((0, 0), config.subtitle_text.upper(), font=sub_font)
            cur_y += (bbox[3] - bbox[1]) + int(H * (config.spacing_items / 100.0))

        # Title
        if config.title_text.strip():
            title_size = int(config.title_font_size * multiplier)
            title_font = cls.load_font(config.font_family, title_size, "bold")
            for line in config.title_text.splitlines():
                draw.text((text_x, cur_y), line, font=title_font, fill=tuple(config.title_color))
                bbox = draw.textbbox((0, 0), line, font=title_font)
                cur_y += (bbox[3] - bbox[1]) + int(title_size * 0.2)

        cur_y += int(H * (config.spacing_title / 100.0))

        # Stat Rows Data
        rows = config.rows or [{"label": "No Data", "value": "0", "max_value": "100"}]
        lbl_font = cls.load_font(config.font_family, int(config.label_font_size * multiplier), "bold")
        val_font = cls.load_font(config.font_family, int(config.value_font_size * multiplier), "bold")
        bar_h = max(3 * multiplier, int(H * 0.008))

        for row in rows:
            # Label
            draw.text((text_x, cur_y), row["label"].upper(), font=lbl_font, fill=tuple(config.label_color))
            l_bbox = draw.textbbox((0, 0), row["label"].upper(), font=lbl_font)
            cur_y += (l_bbox[3] - l_bbox[1]) + int(H * (config.spacing_items / 100.0))

            # Value
            val_str = str(row["value"])
            draw.text((text_x, cur_y), val_str, font=val_font, fill=tuple(config.accent_color))
            v_bbox = draw.textbbox((0, 0), val_str, font=val_font)
            cur_y += (v_bbox[3] - v_bbox[1]) + int(H * (config.spacing_items / 100.0)) + (2 * multiplier)

            # Flat Progress Bar
            pct = cls.calculate_percent(val_str, row.get("max_value", "100"))
            bar_y0, bar_y1 = cur_y, cur_y + bar_h
            
            draw.rectangle([text_x, bar_y0, text_x + text_w, bar_y1], fill=tuple(config.bar_track_color))
            
            fill_w = int(text_w * (pct / 100.0))
            if fill_w > 0:
                draw.rectangle([text_x, bar_y0, text_x + fill_w, bar_y1], fill=tuple(config.accent_color))
            
            cur_y = bar_y1 + int(H * (config.spacing_rows / 100.0))

        return img


# ------------------------------------------------------------------------------
# UI Implementation 
# ------------------------------------------------------------------------------
class ScoreboardApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Match Stats Studio (Pro)")
        self.geometry("1500x950")
        
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_file_drop)

        self.app_config = ScoreboardConfig()
        self.row_widgets = []
        self._drag_data = {"x": 0, "y": 0, "active": False}
        self._current_preview_scale = 1.0
        self.render_queue = queue.Queue()
        self._redraw_timer = None

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        self._build_ui()
        self._apply_config_to_ui()
        self._start_render_worker()
        self.schedule_redraw()

    def on_file_drop(self, event):
        file_path = event.data.strip('{}')
        if not file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')): return
        if file_path.lower().endswith('.png'):
            self.app_config.overlay_path = file_path
        else:
            self.app_config.photo_path = file_path
        self.schedule_redraw()

    def _build_ui(self):
        self.controls = ctk.CTkScrollableFrame(self.main_frame, width=540, corner_radius=0)
        self.controls.pack(side="left", fill="y")
        
        self.preview_panel = ctk.CTkFrame(self.main_frame, fg_color="#1a1a1a", corner_radius=0)
        self.preview_panel.pack(side="right", fill="both", expand=True)
        self.preview_canvas = tk.Canvas(self.preview_panel, bg="#1a1a1a", highlightthickness=0)
        self.preview_canvas.pack(padx=20, pady=20, fill="both", expand=True)
        
        self.preview_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        self._build_preset_controls()
        self._build_image_controls()
        self._build_content_controls()
        self._build_font_controls()
        self._build_layout_controls()
        self._build_color_controls()
        self._build_rows_controls()
        self._build_export_controls()

    def _make_section(self, title: str) -> ctk.CTkFrame:
        frm = ctk.CTkFrame(self.controls, fg_color="#2b2b2b")
        frm.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(frm, text=title, font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        content = ctk.CTkFrame(frm, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(0, 10))
        return content

    def _build_preset_controls(self):
        sec = self._make_section("Quick Presets")
        ctk.CTkComboBox(sec, values=list(PRESET_THEMES.keys()), command=self.apply_preset, width=300).pack(side="left")

    def _build_image_controls(self):
        sec = self._make_section("Images (Drag & Drop or Browse)")
        
        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkButton(row1, text="Background Photo", command=self._browse_bg).pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(row1, text="Clear", width=50, fg_color="#8B0000", hover_color="#5c0000", command=lambda: self._clear_img("bg")).pack(side="left")
        
        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkButton(row2, text="Player Overlay (PNG)", command=self._browse_overlay).pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(row2, text="Clear", width=50, fg_color="#8B0000", hover_color="#5c0000", command=lambda: self._clear_img("overlay")).pack(side="left")
        
        scale_frm = ctk.CTkFrame(sec, fg_color="transparent")
        scale_frm.pack(fill="x", pady=5)
        ctk.CTkLabel(scale_frm, text="Overlay Scale:").pack(side="left")
        self.overlay_scale_var = tk.DoubleVar(value=100.0)
        ctk.CTkSlider(scale_frm, variable=self.overlay_scale_var, from_=10, to=300, command=lambda e: self.schedule_redraw()).pack(side="left", fill="x", expand=True, padx=10)

    def _browse_bg(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")])
        if path:
            self.app_config.photo_path = path
            self.schedule_redraw()

    def _browse_overlay(self):
        path = filedialog.askopenfilename(filetypes=[("PNG Images", "*.png")])
        if path:
            self.app_config.overlay_path = path
            self.schedule_redraw()
            
    def _clear_img(self, target: str):
        if target == "bg": self.app_config.photo_path = ""
        else: self.app_config.overlay_path = ""
        self.schedule_redraw()

    def _build_content_controls(self):
        sec = self._make_section("Titles & Text")
        self.sub_var = ctk.StringVar()
        ctk.CTkEntry(sec, textvariable=self.sub_var, placeholder_text="Subtitle").pack(fill="x", pady=5)
        self.sub_var.trace_add("write", lambda *a: self.schedule_redraw())
        self.title_var = ctk.StringVar()
        ctk.CTkEntry(sec, textvariable=self.title_var, placeholder_text="Main Title").pack(fill="x", pady=5)
        self.title_var.trace_add("write", lambda *a: self.schedule_redraw())

    def _build_font_controls(self):
        sec = self._make_section("Typography Choices")
        
        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=5)
        ctk.CTkLabel(row, text="Font Family:").pack(side="left")
        self.font_var = ctk.StringVar(value="Arial")
        ctk.CTkComboBox(row, variable=self.font_var, values=SYSTEM_FONTS, command=lambda e: self.schedule_redraw()).pack(side="left", padx=10)
        
        size_frm = ctk.CTkFrame(sec, fg_color="transparent")
        size_frm.pack(fill="x", pady=10)
        self.title_size_var, self.sub_size_var = ctk.StringVar(value="42"), ctk.StringVar(value="18")
        self.label_size_var, self.value_size_var = ctk.StringVar(value="16"), ctk.StringVar(value="28")
        
        for l, v in [("Title:", self.title_size_var), ("Sub:", self.sub_size_var), ("Lbl:", self.label_size_var), ("Val:", self.value_size_var)]:
            ctk.CTkLabel(size_frm, text=l).pack(side="left", padx=(5, 2))
            e = ctk.CTkEntry(size_frm, textvariable=v, width=40)
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda e: self.schedule_redraw())

    def _build_layout_controls(self):
        sec = self._make_section("Panel Style & Layout")
        
        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        self.aspect_var = ctk.StringVar(value=list(ASPECT_RATIOS.keys())[0])
        ctk.CTkComboBox(row1, variable=self.aspect_var, values=list(ASPECT_RATIOS.keys()), command=lambda e: self.schedule_redraw(), width=200).pack(side="left")
        
        self.grad_dir_var = ctk.StringVar(value="horizontal_fade")
        ctk.CTkComboBox(row1, variable=self.grad_dir_var, values=["horizontal_fade", "vertical"], command=lambda e: self.schedule_redraw(), width=130).pack(side="right")

    def _build_color_controls(self):
        sec = self._make_section("Color Palette")
        colors = [
            ("Panel Color", "panel_top_color"), ("Accent & Bars", "accent_color"), ("Track Base", "bar_track_color"), 
            ("Title", "title_color"), ("Subtitle", "subtitle_color"), ("Labels", "label_color")
        ]
        self.color_buttons = {}
        for i, (label, key) in enumerate(colors):
            frm = ctk.CTkFrame(sec, fg_color="transparent")
            frm.grid(row=i // 2, column=(i % 2), sticky="w", padx=10, pady=5)
            ctk.CTkLabel(frm, text=label + ":", width=90, anchor="w").pack(side="left")
            btn = ctk.CTkButton(frm, text="", width=30, height=20, border_width=1, border_color="#777", command=lambda k=key: self._pick_color(k))
            btn.pack(side="left")
            self.color_buttons[key] = btn

    def _build_rows_controls(self):
        sec = self._make_section("Statistics")
        header = ctk.CTkFrame(sec, fg_color="transparent")
        header.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header, text="Label").pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(header, text="Value").pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(header, text="Max").pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(header, text="", width=30).pack(side="right", padx=5)

        self.rows_container = ctk.CTkFrame(sec, fg_color="transparent")
        self.rows_container.pack(fill="x")
        
        ctk.CTkButton(sec, text="+ Add Row", command=self._add_row_ui).pack(pady=10)

    def _build_export_controls(self):
        sec = self._make_section("Export Options")
        ctk.CTkButton(sec, text="Generate Final Image", font=("Arial", 16, "bold"), fg_color="#1E90FF", hover_color="#0066CC", command=self.export_image, height=40).pack(fill="x", pady=10)

    def _add_row_ui(self, data: Optional[Dict] = None):
        if data is None: data = {"label": "New Stat", "value": "0", "max_value": "100"}
        frm = ctk.CTkFrame(self.rows_container, fg_color="transparent")
        frm.pack(fill="x", pady=2)
        
        l_var = ctk.StringVar(value=data["label"])
        v_var = ctk.StringVar(value=data["value"])
        m_var = ctk.StringVar(value=data.get("max_value", "100"))
        
        for var in (l_var, v_var, m_var):
            var.trace_add("write", lambda *args: self.schedule_redraw())
            
        ctk.CTkEntry(frm, textvariable=l_var).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkEntry(frm, textvariable=v_var).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkEntry(frm, textvariable=m_var).pack(side="left", padx=2, expand=True, fill="x")
        
        btn = ctk.CTkButton(frm, text="X", width=30, fg_color="#8B0000", hover_color="#5c0000", command=lambda f=frm: self._remove_row_ui(f))
        btn.pack(side="right", padx=2)
        
        self.row_widgets.append({"frame": frm, "vars": (l_var, v_var, m_var)})
        self.schedule_redraw()

    def _remove_row_ui(self, frm):
        for item in self.row_widgets:
            if item["frame"] == frm:
                self.row_widgets.remove(item)
                frm.destroy()
                self.schedule_redraw()
                break

    def apply_preset(self, theme_name: str):
        if theme_name in PRESET_THEMES:
            for k, val in PRESET_THEMES[theme_name].items():
                setattr(self.app_config, k, val)
                if k in self.color_buttons:
                    self.color_buttons[k].configure(fg_color=f"#{val[0]:02x}{val[1]:02x}{val[2]:02x}")
            self._apply_config_to_ui()
            self.schedule_redraw()

    def _pick_color(self, key: str):
        color = colorchooser.askcolor(initialcolor=tuple(getattr(self.app_config, key)))
        if color[0]:
            rgb = [int(c) for c in color[0]]
            setattr(self.app_config, key, rgb)
            self.color_buttons[key].configure(fg_color=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
            self.schedule_redraw()

    def _update_config_from_ui(self):
        self.app_config.aspect_ratio = self.aspect_var.get()
        self.app_config.panel_gradient_dir = self.grad_dir_var.get()
        self.app_config.font_family = self.font_var.get()
        self.app_config.title_text = self.title_var.get()
        self.app_config.subtitle_text = self.sub_var.get()
        self.app_config.overlay_scale = self.overlay_scale_var.get()
        try:
            self.app_config.title_font_size = int(self.title_size_var.get())
            self.app_config.subtitle_font_size = int(self.sub_size_var.get())
            self.app_config.label_font_size = int(self.label_size_var.get())
            self.app_config.value_font_size = int(self.value_size_var.get())
        except ValueError: pass
        
        self.app_config.rows = []
        for w in self.row_widgets:
            l, v, m = w["vars"]
            self.app_config.rows.append({"label": l.get(), "value": v.get(), "max_value": m.get()})

    def _apply_config_to_ui(self):
        self.aspect_var.set(self.app_config.aspect_ratio)
        self.grad_dir_var.set(self.app_config.panel_gradient_dir)
        self.font_var.set(self.app_config.font_family)
        self.title_var.set(self.app_config.title_text)
        self.sub_var.set(self.app_config.subtitle_text)
        self.overlay_scale_var.set(self.app_config.overlay_scale)
        self.title_size_var.set(str(self.app_config.title_font_size))
        self.sub_size_var.set(str(self.app_config.subtitle_font_size))
        self.label_size_var.set(str(self.app_config.label_font_size))
        self.value_size_var.set(str(self.app_config.value_font_size))
        
        for k, btn in self.color_buttons.items():
            btn.configure(fg_color=f"#{getattr(self.app_config, k)[0]:02x}{getattr(self.app_config, k)[1]:02x}{getattr(self.app_config, k)[2]:02x}")
            
        for w in list(self.row_widgets): w["frame"].destroy()
        self.row_widgets.clear()
        for row in self.app_config.rows: self._add_row_ui(row)

    def on_canvas_press(self, event):
        self._drag_data["x"], self._drag_data["y"], self._drag_data["active"] = event.x, event.y, True
        
    def on_canvas_drag(self, event):
        if not self._drag_data["active"]: return
        dx, dy = event.x - self._drag_data["x"], event.y - self._drag_data["y"]
        self._drag_data["x"], self._drag_data["y"] = event.x, event.y
        base_w, base_h = ASPECT_RATIOS.get(self.app_config.aspect_ratio, (1024, 1024))
        self.app_config.overlay_x += (dx / self._current_preview_scale) / base_w * 100.0
        self.app_config.overlay_y += (dy / self._current_preview_scale) / base_h * 100.0
        self.schedule_redraw()
        
    def on_canvas_release(self, event):
        self._drag_data["active"] = False

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
        self._tk_img = ImageTk.PhotoImage(img.resize((new_w, new_h), Image.LANCZOS))
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(self.preview_canvas.winfo_width()//2, self.preview_canvas.winfo_height()//2, image=self._tk_img, anchor="center")

    def export_image(self):
        self._update_config_from_ui()
        file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if not file_path: return
        try:
            final_img = ScoreboardRenderer.render(self.app_config, multiplier=2)
            final_img.save(file_path, quality=95)
            messagebox.showinfo("Success", f"Image exported successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export image:\n{e}")

if __name__ == "__main__":
    app = ScoreboardApp()
    app.mainloop()