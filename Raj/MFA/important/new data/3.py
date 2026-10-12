"""
Pro Thumbnail Generator (v7 — Canva-style editing tools)
=========================================================
Everything from v6 is preserved:
  - Individual top/bottom text line items with +/- controls
  - Draggable, selectable text + flag items, mirrored flag dragging
  - Auto flag-by-country-name (flagcdn.com + pycountry)
  - Presets (save/load full canvas state as JSON)
  - Reset-to-template, PNG/JPEG export at 1920x1080

New in v7 (see task list this was built from):
  1. Flag resizing: 8 drag handles (corners + edges) on the selected flag,
     width/height spin boxes, aspect-ratio lock, min/max clamps,
     rectangular-by-default flags, full undo/redo support.
  2. Canvas grid + snapping: show/hide grid, configurable spacing,
     snap-to-grid / canvas-center / canvas-edges / other-elements,
     live alignment guides while dragging, grid is NEVER exported.
  3. Font search: searchable font picker dialog (filters as you type,
     "No fonts found" state, preserves current selection).
  4. Text properties panel: family, size incr/decr, bold/italic/underline,
     color, alignment (L/C/R/justify), line spacing, letter spacing,
     text transform, live-updating, direct in-place text edit, undo/redo.
  5. Background effects: blur / gradient / color overlay / vignette
     ("shadow") / glow / pattern / transparency, each with an intensity
     slider, live preview before committing, remove/reset.
  6. Global undo/redo (Ctrl+Z / Ctrl+Shift+Z) covering every action above,
     implemented as a full-state snapshot stack (reuses the existing
     preset serialize/apply code, so it is guaranteed to stay in sync
     with whatever fields presets already track).

Requirements:
    pip install PyQt6 pycountry
"""

import os
import sys
import json
import copy
import uuid
import urllib.error
import urllib.request

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QColorDialog,
    QScrollArea, QGroupBox, QGraphicsScene, QGraphicsView, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsLineItem, QGraphicsItem, QSlider,
    QMessageBox, QDockWidget, QStatusBar, QInputDialog, QDialog, QListWidget,
    QSpinBox, QCheckBox, QComboBox, QToolButton, QTabWidget,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QPainter, QImage, QBrush, QPen, QShortcut,
    QKeySequence, QTextOption, QTextCursor, QTextBlockFormat, QFontDatabase,
    QLinearGradient, QRadialGradient, QCursor, QPainterPath,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, QEvent

try:
    import pycountry
    HAVE_PYCOUNTRY = True
except ImportError:
    HAVE_PYCOUNTRY = False

CANVAS_W, CANVAS_H = 1920, 1080
BASE_FLAG_W, BASE_FLAG_H = 500, 350          # rectangular by default (10:7)
FLAG_MIN_W, FLAG_MIN_H = 120, 70
FLAG_MAX_W, FLAG_MAX_H = 1200, 900
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FLAG_CACHE_DIR = os.path.join(SCRIPT_DIR, "flag_cache")
PRESETS_DIR = os.path.join(SCRIPT_DIR, "presets")

DEMO_BG_CANDIDATES = [
    "/mnt/data/ghostwriter_images/context/710909d7-bb83-51f4-b781-f574cc8816f7.png",
    "/mnt/data/ghostwriter_images/context/0f6e9f02-5b0d-5440-a400-b534e5678897.png",
]

LEFT_X = CANVAS_W * 0.25
CENTER_X = CANVAS_W * 0.50
RIGHT_X = CANVAS_W * 0.75

GRID_DEFAULT_SPACING = 40
SNAP_THRESHOLD = 10
UNDO_LIMIT = 80

ASPECT_RATIOS = {
    "Custom": None, "1:1 - Square": 1.0, "4:3": 4 / 3,
    "3:2": 3 / 2, "16:9": 16 / 9, "9:16": 9 / 16, "2:3": 2 / 3,
}
SHAPES = ["Rectangle", "Square", "Circle", "Oval", "Rounded Rectangle"]
SHADOW_DIRECTIONS = {
    "Left": (-1, 0), "Right": (1, 0), "Top": (0, -1), "Bottom": (0, 1),
    "Top-Left": (-0.707, -0.707), "Top-Right": (0.707, -0.707),
    "Bottom-Left": (-0.707, 0.707), "Bottom-Right": (0.707, 0.707),
}
DEFAULT_SHADOW = {
    "enabled": False, "color_mode": "Grey", "custom_color": "#777777",
    "direction": "Bottom-Right", "distance": 24, "blur": 30,
    "opacity": 55, "spread": 20, "intensity": 70,
}

DEFAULT_LAYOUT = {
    "top_lines": [
        {"text": "Davis Cup", "size": 72, "weight": int(QFont.Weight.Black)},
        {"text": "Quarter Finals 2026", "size": 46, "weight": int(QFont.Weight.Bold)},
        {"text": "3rd Round 2", "size": 40, "weight": int(QFont.Weight.Bold)},
    ],
    "bottom_lines": [
        {"text": "18-19 Sep 2026", "size": 42, "weight": int(QFont.Weight.Bold)},
        {"text": "Seol Park", "size": 34, "weight": int(QFont.Weight.Bold)},
    ],
    "left_team": "Australia",
    "right_team": "Poland",
    "top_start_y": 78,
    "top_gap": 74,
    "bottom_start_y": 845,
    "bottom_gap": 56,
    "flag_y": 485,
    "name_y": 705,
    "vs_y": 500,
}

DEFAULT_BG_EFFECTS = {
    "blur": 0,          # 0-100 -> px radius scaled
    "gradient": 0,       # 0-100 alpha
    "overlay": 0,        # 0-100 alpha
    "overlay_color": "#000000",
    "shadow": 0,         # vignette 0-100
    "glow": 0,           # 0-100
    "pattern": 0,        # 0-100
    "transparency": 100, # 100 = fully opaque
}


# ---------------------------------------------------------------------------
# Country / flag helpers
# ---------------------------------------------------------------------------

def resolve_country_code(name):
    if not HAVE_PYCOUNTRY or not name or not name.strip():
        return None
    name = name.strip()
    try:
        return pycountry.countries.lookup(name).alpha_2.lower()
    except LookupError:
        pass
    try:
        results = pycountry.countries.search_fuzzy(name)
        if results:
            return results[0].alpha_2.lower()
    except LookupError:
        pass
    return None


def fetch_flag_image(country_code, size="w320"):
    os.makedirs(FLAG_CACHE_DIR, exist_ok=True)
    local_path = os.path.join(FLAG_CACHE_DIR, f"{country_code}_{size}.png")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path
    url = f"https://flagcdn.com/{size}/{country_code}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


# ---------------------------------------------------------------------------
# Preset helpers
# ---------------------------------------------------------------------------

def list_presets():
    if not os.path.isdir(PRESETS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.lower().endswith(".json"))


def preset_path(name):
    return os.path.join(PRESETS_DIR, f"{name}.json")


def save_preset_json(name, state):
    os.makedirs(PRESETS_DIR, exist_ok=True)
    with open(preset_path(name), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_preset_json(name):
    with open(preset_path(name), "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Background effects compositor
# ---------------------------------------------------------------------------

def blur_qimage(image, radius_px):
    """Render an image through QGraphicsBlurEffect off-screen."""
    if radius_px <= 0:
        return image
    from PyQt6.QtWidgets import QGraphicsBlurEffect
    scene = QGraphicsScene()
    pix_item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius_px)
    pix_item.setGraphicsEffect(effect)
    scene.addItem(pix_item)
    result = QImage(image.size(), QImage.Format.Format_ARGB32)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()),
                 QRectF(0, 0, image.width(), image.height()))
    painter.end()
    return result


def compose_background(base_image, effects):
    """Apply the effects dict (see DEFAULT_BG_EFFECTS) to a copy of base_image."""
    img = QImage(base_image)
    if img.format() != QImage.Format.Format_ARGB32:
        img = img.convertToFormat(QImage.Format.Format_ARGB32)

    blur = effects.get("blur", 0)
    if blur > 0:
        img = blur_qimage(img, blur / 100.0 * 24)

    w, h = img.width(), img.height()
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient_amt = effects.get("gradient", 0)
    if gradient_amt > 0:
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, int(255 * gradient_amt / 100.0)))
        painter.fillRect(0, 0, w, h, QBrush(grad))

    overlay_amt = effects.get("overlay", 0)
    if overlay_amt > 0:
        c = QColor(effects.get("overlay_color", "#000000"))
        c.setAlpha(int(255 * overlay_amt / 100.0))
        painter.fillRect(0, 0, w, h, QBrush(c))

    shadow_amt = effects.get("shadow", 0)
    if shadow_amt > 0:
        rad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.75)
        rad.setColorAt(0.55, QColor(0, 0, 0, 0))
        rad.setColorAt(1.0, QColor(0, 0, 0, int(255 * shadow_amt / 100.0)))
        painter.fillRect(0, 0, w, h, QBrush(rad))

    glow_amt = effects.get("glow", 0)
    if glow_amt > 0:
        rad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.55)
        rad.setColorAt(0.0, QColor(255, 255, 255, int(255 * glow_amt / 100.0)))
        rad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(0, 0, w, h, QBrush(rad))

    pattern_amt = effects.get("pattern", 0)
    if pattern_amt > 0:
        alpha = max(10, int(90 * pattern_amt / 100.0))
        pen = QPen(QColor(255, 255, 255, alpha))
        pen.setWidth(2)
        painter.setPen(pen)
        step = 28
        for x in range(-h, w, step):
            painter.drawLine(x, 0, x + h, h)
    painter.end()

    transparency = effects.get("transparency", 100)
    if transparency < 100:
        alpha_img = QImage(img.size(), QImage.Format.Format_ARGB32)
        alpha_img.fill(Qt.GlobalColor.transparent)
        p2 = QPainter(alpha_img)
        p2.setOpacity(max(0.0, transparency / 100.0))
        p2.drawImage(0, 0, img)
        p2.end()
        img = alpha_img

    return img


# ---------------------------------------------------------------------------
# Text item
# ---------------------------------------------------------------------------

class CenteredTextItem(QGraphicsTextItem):
    def __init__(self, text, font, color, center_x, center_y, home_x=None,
                 role="generic", app=None):
        super().__init__(" ".join(text.splitlines()))
        self._box_w = None
        self._box_h = None
        self.setFlags(
            QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsTextItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setFont(font)
        self.setDefaultTextColor(color)
        self._home_x = home_x if home_x is not None else center_x
        self._center = QPointF(center_x, center_y)
        self._suppress_move = False
        self.on_move = None
        self.role = role
        self.app = app                 # ref to ThumbnailGenerator, for snapping/undo
        self.align = "center"          # left / center / right / justify
        self.line_spacing_pct = 100
        self.letter_spacing_px = 0
        self._apply_alignment()
        self._recenter()

    # -- alignment / spacing -------------------------------------------------
    def _apply_alignment(self):
        doc = self.document()
        qt_align = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
            "justify": Qt.AlignmentFlag.AlignJustify,
        }.get(self.align, Qt.AlignmentFlag.AlignHCenter)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.NoWrap)
        opt.setAlignment(qt_align)
        doc.setDefaultTextOption(opt)
        doc.setTextWidth(self._box_w if self._box_w is not None else doc.idealWidth())

        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setAlignment(qt_align)
        if self.line_spacing_pct and self.line_spacing_pct != 100:
            fmt.setLineHeight(self.line_spacing_pct,
                               QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(fmt)

    def set_alignment(self, align):
        self.align = align
        self._apply_alignment()
        self._recenter()

    def set_line_spacing(self, pct):
        self.line_spacing_pct = pct
        self._apply_alignment()
        self._recenter()

    def set_letter_spacing(self, px):
        self.letter_spacing_px = px
        f = self.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
        self.setFont(f)
        self._apply_alignment()
        self._recenter()

    def apply_text_transform(self, mode):
        text = self.toPlainText()
        if mode == "UPPERCASE":
            text = text.upper()
        elif mode == "lowercase":
            text = text.lower()
        elif mode == "Capitalize":
            text = text.title()
        self.set_text(text)

    # -- geometry --------------------------------------------------------
    def _recenter(self):
        rect = self.boundingRect()
        self._suppress_move = True
        self.setPos(
            self._center.x() - rect.width() / 2,
            self._center.y() - rect.height() / 2,
        )
        self._suppress_move = False
        if self.app:
            self.app.reposition_handles()

    def set_text(self, text):
        self.setPlainText(" ".join(text.splitlines()))
        self._apply_alignment()
        self._recenter()

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setClipRect(self.boundingRect())
        super().paint(painter, option, widget)
        painter.restore()

    def boundingRect(self):
        natural = super().boundingRect()
        if self._box_w is None or self._box_h is None:
            return natural
        return QRectF(0, 0, self._box_w, self._box_h)

    def set_box_size(self, width, height):
        width = max(80, min(CANVAS_W, float(width)))
        height = max(35, min(CANVAS_H, float(height)))
        self.prepareGeometryChange()
        self._box_w, self._box_h = width, height
        self.document().setTextWidth(width)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self._recenter()

    def clear_box_size(self):
        self.prepareGeometryChange()
        self._box_w = self._box_h = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, False)
        self._apply_alignment()
        self._recenter()

    def box_size(self):
        rect = self.boundingRect()
        return rect.width(), rect.height()

    def set_style(self, font=None, color=None):
        if font is not None:
            self.setFont(font)
            self._apply_alignment()
        if color is not None:
            self.setDefaultTextColor(color)
        self._recenter()

    def set_center(self, x, y):
        self._center = QPointF(x, y)
        self._recenter()

    def set_home_x(self, x):
        self._home_x = x

    def center(self):
        return (self._center.x(), self._center.y())

    def half_size(self):
        rect = self.boundingRect()
        return rect.width() / 2, rect.height() / 2

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, event):
        if self.app:
            self.app.push_undo_snapshot()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.app:
            self.app.clear_guides()

    def itemChange(self, change, value):
        # Only run snapping for real user drags (_suppress_move is True for
        # programmatic repositioning like layout/preset-apply/undo) and only
        # once the sidebar (and its snap checkbox) actually exists.
        if (
            change == QGraphicsTextItem.GraphicsItemChange.ItemPositionChange
            and self.app and not self._suppress_move
            and hasattr(self.app, "snap_enabled_checkbox")
        ):
            hw, hh = self.half_size()
            proposed_center = QPointF(value.x() + hw, value.y() + hh)
            snapped = self.app.snap_center(self, proposed_center, hw, hh)
            return QPointF(snapped.x() - hw, snapped.y() - hh)
        if (
            change == QGraphicsTextItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._suppress_move
        ):
            rect = self.boundingRect()
            self._center = QPointF(
                self.x() + rect.width() / 2,
                self.y() + rect.height() / 2,
            )
            if self.on_move:
                self.on_move(self)
            if self.app:
                self.app.reposition_handles()
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# Flag item (now resizable via explicit width/height, not just uniform scale)
# ---------------------------------------------------------------------------

class CenteredFlagItem(QGraphicsPixmapItem):
    def __init__(self, center_x, center_y, label="Flag", app=None):
        super().__init__()
        self.setFlags(
            QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self._center = QPointF(center_x, center_y)
        self._source_path = None
        self._w = BASE_FLAG_W
        self._h = BASE_FLAG_H
        self._label = label
        self._aspect_locked = True
        self._aspect_ratio = BASE_FLAG_W / BASE_FLAG_H
        self._shape = "Rectangle"
        self._shadow = copy.deepcopy(DEFAULT_SHADOW)
        self._suppress_move = False
        self.on_move = None
        self.app = app
        self._set_placeholder()

    # -- rendering -----------------------------------------------------
    def _set_placeholder(self):
        w, h = int(self._w), int(self._h)
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        pen = QPen(QColor(180, 180, 180))
        pen.setWidth(3)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QBrush(QColor(20, 20, 20, 95)))
        p.drawRect(2, 2, w - 4, h - 4)   # always rectangular
        p.setPen(QColor(235, 235, 235))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()
        self.setPixmap(QPixmap.fromImage(img))
        self._recenter()

    def load_image(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._source_path = path
        # The uploaded image defines the natural ratio. Keeping width stable
        # avoids a surprising size jump while preventing initial distortion.
        self._aspect_ratio = pix.width() / max(1, pix.height())
        if self._aspect_locked:
            self._h = max(FLAG_MIN_H, min(FLAG_MAX_H, self._w / self._aspect_ratio))
        self._apply_size()
        self._apply_shadow()
        return True

    def _apply_size(self):
        w, h = int(self._w), int(self._h)
        if self._source_path:
            source = QPixmap(self._source_path)
            scaled = source.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - w) // 2)
            y = max(0, (scaled.height() - h) // 2)
            cropped = scaled.copy(x, y, w, h)
            output = QPixmap(w, h)
            output.fill(Qt.GlobalColor.transparent)
            painter = QPainter(output)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipPath(self._shape_path(w, h))
            painter.drawPixmap(0, 0, cropped)
            painter.end()
            self.setPixmap(output)
            self._recenter()
        else:
            self._set_placeholder()

    def set_size_px(self, w, h, keep_aspect=None):
        """Resize to an exact width/height in px, clamped to min/max."""
        if keep_aspect is None:
            keep_aspect = self._aspect_locked
        w = max(FLAG_MIN_W, min(FLAG_MAX_W, w))
        h = max(FLAG_MIN_H, min(FLAG_MAX_H, h))
        if keep_aspect and self._aspect_ratio:
            ratio = self._aspect_ratio
            # Adjust h to match w while respecting the locked ratio
            h = w / ratio
            h = max(FLAG_MIN_H, min(FLAG_MAX_H, h))
        self._w, self._h = w, h
        self._apply_size()

    def _shape_path(self, w, h):
        path = QPainterPath()
        rect = QRectF(0, 0, w, h)
        if self._shape == "Circle" or self._shape == "Oval":
            path.addEllipse(rect)
        elif self._shape == "Rounded Rectangle":
            path.addRoundedRect(rect, min(w, h) * 0.12, min(w, h) * 0.12)
        else:
            path.addRect(rect)
        return path

    def set_shape(self, shape):
        self._shape = shape if shape in SHAPES else "Rectangle"
        if self._shape in ("Square", "Circle"):
            self._aspect_ratio = 1.0
            self._aspect_locked = True
            side = min(self._w, self._h)
            self._w = self._h = side
        self._apply_size()

    def shape_name(self):
        return self._shape

    def shadow_settings(self):
        return copy.deepcopy(self._shadow)

    def set_shadow_settings(self, settings):
        self._shadow = {**DEFAULT_SHADOW, **(settings or {})}
        self._apply_shadow()

    def dominant_color(self):
        if not self._source_path:
            return QColor("#777777")
        image = QImage(self._source_path)
        if image.isNull():
            return QColor("#777777")
        totals = [0, 0, 0]; count = 0
        step_x, step_y = max(1, image.width() // 24), max(1, image.height() // 24)
        for y in range(0, image.height(), step_y):
            for x in range(0, image.width(), step_x):
                c = image.pixelColor(x, y)
                if c.alpha() > 40 and not (c.red() > 242 and c.green() > 242 and c.blue() > 242):
                    totals[0] += c.red(); totals[1] += c.green(); totals[2] += c.blue(); count += 1
        return QColor(*(int(v / count) for v in totals)) if count else QColor("#777777")

    def _apply_shadow(self):
        if not self._shadow.get("enabled"):
            self.setGraphicsEffect(None)
            return
        effect = QGraphicsDropShadowEffect()
        mode = self._shadow.get("color_mode", "Grey")
        color = (self.dominant_color() if mode == "Image Color" else
                 QColor(self._shadow.get("custom_color", "#777777")) if mode == "Custom" else QColor("#777777"))
        opacity = self._shadow.get("opacity", 55) / 100
        intensity = self._shadow.get("intensity", 70) / 100
        color.setAlpha(max(0, min(255, round(255 * opacity * intensity))))
        effect.setColor(color)
        distance = self._shadow.get("distance", 24)
        dx, dy = SHADOW_DIRECTIONS.get(self._shadow.get("direction"), (0.707, 0.707))
        effect.setOffset(dx * distance, dy * distance)
        # Qt has no separate spread control; a modest radius contribution
        # produces the same fuller, depth-like result without changing size.
        effect.setBlurRadius(self._shadow.get("blur", 30) + self._shadow.get("spread", 20) * 0.45)
        self.setGraphicsEffect(effect)

    def set_aspect_ratio(self, ratio):
        self._aspect_ratio = ratio if ratio and ratio > 0 else self._w / max(1, self._h)
        if ratio:
            self.set_size_px(self._w, self._w / ratio, keep_aspect=False)

    def set_aspect_locked(self, locked):
        self._aspect_locked = locked

    def aspect_locked(self):
        return self._aspect_locked

    def aspect_ratio(self):
        return self._aspect_ratio

    def size(self):
        return self._w, self._h

    # legacy alias kept so existing preset files with scale_pct still load
    def set_scale_pct(self, pct):
        self.set_size_px(BASE_FLAG_W * pct / 100.0, BASE_FLAG_H * pct / 100.0)

    def scale_pct(self):
        return round(100.0 * self._w / BASE_FLAG_W)

    def _recenter(self):
        rect = self.boundingRect()
        self._suppress_move = True
        self.setPos(
            self._center.x() - rect.width() / 2,
            self._center.y() - rect.height() / 2,
        )
        self._suppress_move = False

    def set_center(self, x, y):
        self._center = QPointF(x, y)
        self._recenter()

    def center(self):
        return (self._center.x(), self._center.y())

    def half_size(self):
        return self._w / 2, self._h / 2

    def source_path(self):
        return self._source_path

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, event):
        if self.app:
            self.app.push_undo_snapshot()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.app:
            self.app.clear_guides()

    def itemChange(self, change, value):
        if (
            change == QGraphicsPixmapItem.GraphicsItemChange.ItemPositionChange
            and self.app and not self._suppress_move
            and hasattr(self.app, "snap_enabled_checkbox")
        ):
            hw, hh = self.half_size()
            proposed_center = QPointF(value.x() + hw, value.y() + hh)
            snapped = self.app.snap_center(self, proposed_center, hw, hh)
            return QPointF(snapped.x() - hw, snapped.y() - hh)
        if (
            change == QGraphicsPixmapItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._suppress_move
        ):
            rect = self.boundingRect()
            self._center = QPointF(
                self.x() + rect.width() / 2,
                self.y() + rect.height() / 2,
            )
            if self.on_move:
                self.on_move(self)
            if self.app:
                self.app.reposition_handles()
        return super().itemChange(change, value)


class LogoItem(CenteredFlagItem):
    """A freely positioned image element with logo-specific properties."""
    def __init__(self, center_x, center_y, app=None):
        super().__init__(center_x, center_y, label="Logo", app=app)
        self._w, self._h = 260, 180
        self._aspect_ratio = self._w / self._h
        self._set_placeholder()
        self.setZValue(20)


# ---------------------------------------------------------------------------
# Resize handles for the selected flag (Canva-style corner/edge squares)
# ---------------------------------------------------------------------------

HANDLE_EDGES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"]
HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
}


class FlagResizeHandle(QGraphicsRectItem):
    SIZE = 16

    def __init__(self, flag_item, edge, app):
        super().__init__(-self.SIZE / 2, -self.SIZE / 2, self.SIZE, self.SIZE)
        self.flag_item = flag_item
        self.edge = edge
        self.app = app
        self.setBrush(QBrush(QColor("#4da3ff")))
        self.setPen(QPen(QColor("white"), 2))
        self.setZValue(2000)
        self.setCursor(QCursor(HANDLE_CURSORS[edge]))
        self.setAcceptHoverEvents(True)
        self._dragging = False

    def mousePressEvent(self, event):
        self._dragging = True
        self.app.push_undo_snapshot()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.app.resize_flag_from_handle(self.flag_item, self.edge, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.app.clear_guides()
        event.accept()


class TextResizeHandle(FlagResizeHandle):
    def mouseMoveEvent(self, event):
        if self._dragging:
            self.app.resize_text_from_handle(self.flag_item, self.edge, event.scenePos())
        event.accept()


# ---------------------------------------------------------------------------
# Font picker dialog with live search
# ---------------------------------------------------------------------------

class FontPickerDialog(QDialog):
    def __init__(self, current_family, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Font")
        self.resize(340, 420)
        self.selected_family = current_family

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search fonts…")
        layout.addWidget(self.search)

        self.list = QListWidget()
        layout.addWidget(self.list)

        self.no_results = QLabel("No fonts found")
        self.no_results.setStyleSheet("color:#e6a23c;")
        self.no_results.setVisible(False)
        layout.addWidget(self.no_results)

        btn_row = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        self.all_families = list(QFontDatabase.families())
        self._populate(self.all_families)
        matches = self.list.findItems(current_family, Qt.MatchFlag.MatchExactly)
        if matches:
            self.list.setCurrentItem(matches[0])

        self.search.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())

    def _populate(self, families):
        self.list.clear()
        self.list.addItems(families)

    def _filter(self, text):
        needle = text.strip().lower()
        filtered = [f for f in self.all_families if needle in f.lower()] if needle else self.all_families
        self._populate(filtered)
        self.no_results.setVisible(len(filtered) == 0)

    def get_selected(self):
        item = self.list.currentItem()
        return item.text() if item else self.selected_family


# ---------------------------------------------------------------------------
# Background effects dialog with live preview
# ---------------------------------------------------------------------------

class BackgroundEffectsDialog(QDialog):
    def __init__(self, base_image, current_effects, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Background Effects")
        self.resize(420, 560)
        self.base_image = base_image
        self.effects = copy.deepcopy(current_effects)
        self.result_effects = None

        outer = QHBoxLayout(self)

        # -- preview ----------------------------------------------------
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(220, 124)
        self.preview_label.setStyleSheet("background:#111; border:1px solid #555;")
        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("Preview"))
        preview_col.addWidget(self.preview_label)
        preview_col.addStretch()
        outer.addLayout(preview_col)

        # -- controls -----------------------------------------------------
        controls = QVBoxLayout()
        self.sliders = {}

        def add_slider(key, title, max_val=100):
            controls.addWidget(QLabel(title))
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(0, max_val)
            s.setValue(self.effects.get(key, 0))
            s.valueChanged.connect(lambda v, k=key: self._on_change(k, v))
            controls.addWidget(s)
            self.sliders[key] = s

        add_slider("blur", "Blur")
        add_slider("gradient", "Gradient (fade to dark)")

        controls.addWidget(QLabel("Overlay"))
        overlay_row = QHBoxLayout()
        self.overlay_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlay_slider.setRange(0, 100)
        self.overlay_slider.setValue(self.effects.get("overlay", 0))
        self.overlay_slider.valueChanged.connect(lambda v: self._on_change("overlay", v))
        overlay_row.addWidget(self.overlay_slider)
        self.overlay_color_btn = QPushButton("Color")
        self.overlay_color_btn.clicked.connect(self._pick_overlay_color)
        overlay_row.addWidget(self.overlay_color_btn)
        controls.addLayout(overlay_row)
        self.sliders["overlay"] = self.overlay_slider

        add_slider("shadow", "Shadow (vignette)")
        add_slider("glow", "Glow")
        add_slider("pattern", "Pattern")
        add_slider("transparency", "Opacity", max_val=100)
        self.sliders["transparency"].setValue(self.effects.get("transparency", 100))

        controls.addStretch()
        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Remove All")
        reset_btn.clicked.connect(self._reset)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet("background:#2E8B57; color:white; font-weight:bold;")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        controls.addLayout(btn_row)

        outer.addLayout(controls)
        self._update_preview()

    def _on_change(self, key, value):
        self.effects[key] = value
        self._update_preview()

    def _pick_overlay_color(self):
        color = QColorDialog.getColor(QColor(self.effects.get("overlay_color", "#000000")), self)
        if color.isValid():
            self.effects["overlay_color"] = color.name()
            self._update_preview()

    def _reset(self):
        self.effects = copy.deepcopy(DEFAULT_BG_EFFECTS)
        for key, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(self.effects.get(key, 0))
            slider.blockSignals(False)
        self._update_preview()

    def _update_preview(self):
        composed = compose_background(self.base_image, self.effects)
        pix = QPixmap.fromImage(composed).scaled(
            self.preview_label.width(), self.preview_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pix)

    def _apply(self):
        self.result_effects = self.effects
        self.accept()


# ---------------------------------------------------------------------------
# Grid overlay — draws every grid line in a single paint() call instead of
# one QGraphicsLineItem per line, so the scene index only ever tracks one
# extra item for the whole grid, regardless of spacing.
# ---------------------------------------------------------------------------

class _GridOverlayItem(QGraphicsItem):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return QRectF(0, 0, CANVAS_W, CANVAS_H)

    def paint(self, painter, option, widget=None):
        if not self.app._grid_enabled:
            return
        spacing = max(5, self.app._grid_spacing)
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidth(1)
        painter.setPen(pen)
        x = 0
        while x <= CANVAS_W:
            painter.drawLine(int(x), 0, int(x), CANVAS_H)
            x += spacing
        y = 0
        while y <= CANVAS_H:
            painter.drawLine(0, int(y), CANVAS_W, int(y))
            y += spacing
        center_pen = QPen(QColor(255, 255, 255, 70))
        center_pen.setWidth(1)
        painter.setPen(center_pen)
        painter.drawLine(int(CENTER_X), 0, int(CENTER_X), CANVAS_H)
        painter.drawLine(0, int(CANVAS_H / 2), CANVAS_W, int(CANVAS_H / 2))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ThumbnailGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Thumbnail Generator")
        self.setGeometry(80, 80, 1560, 880)

        self._background_path = None
        self._background_base_image = None   # QImage before effects
        self._bg_effects = copy.deepcopy(DEFAULT_BG_EFFECTS)
        self._mirroring = False
        self._top_gap = DEFAULT_LAYOUT["top_gap"]
        self._bottom_gap = DEFAULT_LAYOUT["bottom_gap"]
        self._top_start_y = DEFAULT_LAYOUT["top_start_y"]
        self._bottom_start_y = DEFAULT_LAYOUT["bottom_start_y"]

        # undo/redo
        self._undo_stack = []
        self._redo_stack = []
        self._restoring = False

        # grid
        self._grid_enabled = False
        self._grid_spacing = GRID_DEFAULT_SPACING
        self._grid_lines = []      # holds the single _GridOverlayItem once created
        self._guide_v = None       # persistent reusable snap-guide line items
        self._guide_h = None

        self.scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setCentralWidget(self.view)

        self.bg_item = QGraphicsPixmapItem()
        self.bg_item.setZValue(-10)
        self.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene.addItem(self.bg_item)
        self._draw_default_background()

        self.top_lines = []
        self.bottom_lines = []
        self.flag_items = []
        self.logo_items = []
        self.fixed_text_items = {}
        self.named_items = {}
        self.active_handles = []

        self._build_template_items()
        self._build_sidebar()
        self._build_shortcuts()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")
        self.scene.selectionChanged.connect(self._on_selection_changed)
        for spin in self.findChildren(QSpinBox):
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            spin.setKeyboardTracking(False)
        self._fit_view()
        self._prompt_startup_preset()
        self.push_undo_snapshot(initial=True)
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._poll_history)
        self._history_timer.start(150)
        QApplication.instance().installEventFilter(self)
        self.text_edit.editingFinished.connect(self._commit_history)
        self._on_selection_changed()

    def eventFilter(self, obj, event):
        if isinstance(obj, QWidget) and obj.window() is self:
            if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
                ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                if ctrl and event.key() in (Qt.Key.Key_Z, Qt.Key.Key_Y):
                    if event.type() == QEvent.Type.ShortcutOverride:
                        event.accept()
                    elif event.key() == Qt.Key.Key_Y or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self.redo()
                    else:
                        self.undo()
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ shortcuts
    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Delete"), self.view, activated=self._delete_selected_elements,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # ------------------------------------------------------------------ background
    def _draw_default_background(self):
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        img.fill(QColor("#0d1117"))
        self._background_path = None
        self._background_base_image = img
        self._refresh_background_pixmap()

    def _try_load_demo_background(self):
        for path in DEMO_BG_CANDIDATES:
            if os.path.exists(path):
                self._set_background_image(path)
                return True
        return False

    def _set_background_image(self, path):
        src = QPixmap(path)
        if src.isNull():
            return False
        scaled = src.scaled(
            CANVAS_W, CANVAS_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x_off = max(0, (scaled.width() - CANVAS_W) // 2)
        y_off = max(0, (scaled.height() - CANVAS_H) // 2)
        cropped = scaled.copy(x_off, y_off, CANVAS_W, CANVAS_H)
        self._background_path = path
        self._background_base_image = cropped.toImage()
        self._refresh_background_pixmap()
        return True

    def _refresh_background_pixmap(self):
        if self._background_base_image is None:
            return
        composed = compose_background(self._background_base_image, self._bg_effects)
        self.bg_item.setPixmap(QPixmap.fromImage(composed))

    def _open_effects_dialog(self):
        if self._background_base_image is None:
            return
        dlg = BackgroundEffectsDialog(self._background_base_image, self._bg_effects, self)
        if dlg.exec() and dlg.result_effects is not None:
            self.push_undo_snapshot()
            self._bg_effects = dlg.result_effects
            self._refresh_background_pixmap()
            self.statusBar().showMessage("Background effects applied.", 3000)

    # ------------------------------------------------------------------ template
    def _clear_template_items(self):
        self._clear_handles()
        self._clear_guides()
        persistent = set(self._grid_lines)
        if self._guide_v is not None:
            persistent.add(self._guide_v)
        if self._guide_h is not None:
            persistent.add(self._guide_h)
        for item in list(self.scene.items()):
            if item is self.bg_item or item in persistent:
                continue
            self.scene.removeItem(item)
        self.top_lines = []
        self.bottom_lines = []
        self.flag_items = []
        self.logo_items = []
        self.fixed_text_items = {}
        self.named_items = {}

    def _make_text(self, text, size, weight, x, y, home_x=None, role="generic"):
        item = CenteredTextItem(
            text,
            QFont("Arial", size, QFont.Weight(weight)),
            QColor("white"),
            x, y,
            home_x=home_x if home_x is not None else x,
            role=role,
            app=self,
        )
        self.scene.addItem(item)
        return item

    def _build_template_items(self):
        self._clear_template_items()
        layout = DEFAULT_LAYOUT

        self._try_load_demo_background()

        self.left_flag = CenteredFlagItem(LEFT_X, layout["flag_y"], label="Left Flag", app=self)
        self.right_flag = CenteredFlagItem(RIGHT_X, layout["flag_y"], label="Right Flag", app=self)
        self.scene.addItem(self.left_flag)
        self.scene.addItem(self.right_flag)
        self.flag_items = [self.left_flag, self.right_flag]

        self.vs_text = self._make_text(
            "VS", 96, int(QFont.Weight.Black), CENTER_X, layout["vs_y"], home_x=CENTER_X, role="vs"
        )
        self.vs_text.setDefaultTextColor(QColor("#fff000"))

        self.left_name = self._make_text(
            layout["left_team"], 52, int(QFont.Weight.Black), LEFT_X, layout["name_y"], home_x=LEFT_X, role="team"
        )
        self.right_name = self._make_text(
            layout["right_team"], 52, int(QFont.Weight.Black), RIGHT_X, layout["name_y"], home_x=RIGHT_X, role="team"
        )

        self.fixed_text_items = {
            "vs_text": self.vs_text,
            "left_name": self.left_name,
            "right_name": self.right_name,
        }

        self._top_start_y = layout["top_start_y"]
        self._bottom_start_y = layout["bottom_start_y"]
        self._top_gap = layout["top_gap"]
        self._bottom_gap = layout["bottom_gap"]

        self.top_lines = []
        for line in layout["top_lines"]:
            item = self._make_text(
                line["text"], line["size"], line["weight"], CENTER_X, 0,
                home_x=CENTER_X, role="top_line"
            )
            self.top_lines.append(item)

        self.bottom_lines = []
        for line in layout["bottom_lines"]:
            item = self._make_text(
                line["text"], line["size"], line["weight"], CENTER_X, 0,
                home_x=CENTER_X, role="bottom_line"
            )
            self.bottom_lines.append(item)

        self._layout_top_lines()
        self._layout_bottom_lines()
        self.named_items = self._collect_named_items()
        self._rebuild_grid()

        if hasattr(self, "country_l_input"):
            self.country_l_input.setText(layout["left_team"])
            self.country_r_input.setText(layout["right_team"])

    def _collect_named_items(self):
        data = {
            "left_flag": self.left_flag,
            "right_flag": self.right_flag,
            "vs_text": self.vs_text,
            "left_name": self.left_name,
            "right_name": self.right_name,
        }
        for idx, item in enumerate(self.top_lines, 1):
            data[f"top_line_{idx}"] = item
        for idx, item in enumerate(self.bottom_lines, 1):
            data[f"bottom_line_{idx}"] = item
        return data

    def _layout_top_lines(self):
        y = self._top_start_y
        for item in self.top_lines:
            item.set_home_x(CENTER_X)
            item.set_center(CENTER_X, y)
            y += self._top_gap

    def _layout_bottom_lines(self):
        y = self._bottom_start_y
        for item in self.bottom_lines:
            item.set_home_x(CENTER_X)
            item.set_center(CENTER_X, y)
            y += self._bottom_gap

    # ------------------------------------------------------------------ mirroring
    # ------------------------------------------------------------------ GRID
    # A single item that paints every grid line in one paint() call, instead
    # of ~80 separate QGraphicsLineItems. Rebuilding the whole scene index
    # for 80 items on every toggle/spacing change was cheap; the real cost
    # was doing the equivalent of this every mouse-move (see snap_center).
    def _rebuild_grid(self):
        if not self._grid_lines:
            grid_item = _GridOverlayItem(self)
            grid_item.setZValue(-5)
            self.scene.addItem(grid_item)
            self._grid_lines = [grid_item]
        self._grid_lines[0].update()

    def _toggle_grid(self, checked):
        self._grid_enabled = checked
        self._rebuild_grid()

    def _set_grid_spacing(self, value):
        self._grid_spacing = value
        if self._grid_enabled:
            self._rebuild_grid()

    # -- snapping --------------------------------------------------------
    # Guide lines are two PERSISTENT items created once and reused every
    # drag frame (setLine + setVisible) instead of being added to / removed
    # from the scene on every pixel of mouse movement. That add/remove
    # churn — happening dozens of times a second while dragging — was the
    # actual cause of the lag.
    def _ensure_guide_items(self):
        if self._guide_v is not None:
            return
        pen = QPen(QColor("#ff5b5b"))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        self._guide_v = QGraphicsLineItem(0, 0, 0, CANVAS_H)
        self._guide_h = QGraphicsLineItem(0, 0, CANVAS_W, 0)
        for line in (self._guide_v, self._guide_h):
            line.setPen(pen)
            line.setZValue(1500)
            line.setVisible(False)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.scene.addItem(line)

    def _clear_guides(self):
        self._ensure_guide_items()
        self._guide_v.setVisible(False)
        self._guide_h.setVisible(False)

    def clear_guides(self):
        self._clear_guides()

    def _show_guide(self, orientation, coord):
        self._ensure_guide_items()
        if orientation == "v":
            self._guide_v.setLine(coord, 0, coord, CANVAS_H)
            self._guide_v.setVisible(True)
        else:
            self._guide_h.setLine(0, coord, CANVAS_W, coord)
            self._guide_h.setVisible(True)

    def snap_center(self, moving_item, proposed_center, hw, hh):
        if not self.snap_enabled_checkbox.isChecked():
            self._clear_guides()
            return proposed_center

        cx, cy = proposed_center.x(), proposed_center.y()

        x_candidates = [CENTER_X, hw, CANVAS_W - hw]
        y_candidates = [CANVAS_H / 2, hh, CANVAS_H - hh]

        for item in self._all_snappable_items():
            if item is moving_item:
                continue
            ocx, ocy = item.center()
            x_candidates.append(ocx)
            y_candidates.append(ocy)

        if self._grid_enabled:
            spacing = max(5, self._grid_spacing)
            x_candidates.append(round(cx / spacing) * spacing)
            y_candidates.append(round(cy / spacing) * spacing)

        best_x, best_x_dist = cx, SNAP_THRESHOLD
        for cand in x_candidates:
            d = abs(cand - cx)
            if d < best_x_dist:
                best_x, best_x_dist = cand, d
        best_y, best_y_dist = cy, SNAP_THRESHOLD
        for cand in y_candidates:
            d = abs(cand - cy)
            if d < best_y_dist:
                best_y, best_y_dist = cand, d

        if best_x != cx:
            self._show_guide("v", best_x)
        else:
            self._guide_v is not None and self._guide_v.setVisible(False)
        if best_y != cy:
            self._show_guide("h", best_y)
        else:
            self._guide_h is not None and self._guide_h.setVisible(False)

        return QPointF(best_x, best_y)

    def _all_snappable_items(self):
        items = list(self.flag_items) + list(self.logo_items) + self.top_lines + self.bottom_lines
        items += [self.vs_text, self.left_name, self.right_name]
        return [item for item in items if item.scene() is self.scene]

    # ------------------------------------------------------------------ UNDO/REDO
    # _undo_stack holds PAST states only (not the current live state).
    # push_undo_snapshot() is called right before a mutation, capturing the
    # pre-change state so undo() can restore it later.
    def push_undo_snapshot(self, initial=False):
        """Flush the previous action; record changes only after they happen."""
        if self._restoring:
            return
        if initial:
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._history_state = json.dumps(self._capture_state())
        elif hasattr(self, "_history_state"):
            if QApplication.mouseButtons() == Qt.MouseButton.NoButton:
                self._commit_history()
        self._update_undo_redo_buttons()

    def _commit_history(self):
        if self._restoring or not hasattr(self, "_history_state"):
            return
        current = json.dumps(self._capture_state())
        if current != self._history_state:
            self._undo_stack.append(self._history_state)
            self._undo_stack = self._undo_stack[-UNDO_LIMIT:]
            self._redo_stack.clear()
            self._history_state = current
        self._update_undo_redo_buttons()

    def _poll_history(self):
        if QApplication.mouseButtons() == Qt.MouseButton.NoButton:
            if self.text_edit.hasFocus() and self.text_edit.isModified():
                return
            self._commit_history()

    def _travel_history(self, backwards):
        self._commit_history()
        source = self._undo_stack if backwards else self._redo_stack
        target = self._redo_stack if backwards else self._undo_stack
        if not source:
            self._update_undo_redo_buttons()
            return
        current = json.dumps(self._capture_state())
        state = source[-1]
        try:
            self._apply_state(json.loads(state))
        except Exception as exc:
            self._apply_state(json.loads(current))
            QMessageBox.warning(self, "History", f"Could not restore this change: {exc}")
            return
        source.pop()
        target.append(current)
        self._history_state = json.dumps(self._capture_state())
        self._update_undo_redo_buttons()

    def undo(self):
        self._travel_history(True)

    def redo(self):
        self._travel_history(False)

    def _update_undo_redo_buttons(self):
        if hasattr(self, "btn_undo"):
            pending = (hasattr(self, "_history_state") and
                       json.dumps(self._capture_state()) != self._history_state)
            self.btn_undo.setEnabled(bool(self._undo_stack) or pending)
            self.btn_redo.setEnabled(bool(self._redo_stack))

    # ------------------------------------------------------------------ FLAG RESIZE
    def _clear_handles(self):
        for h in self.active_handles:
            self.scene.removeItem(h)
        self.active_handles = []

    def _spawn_handles_for(self, flag_item):
        self._clear_handles()
        handle_class = TextResizeHandle if isinstance(flag_item, CenteredTextItem) else FlagResizeHandle
        for edge in HANDLE_EDGES:
            h = handle_class(flag_item, edge, self)
            self.scene.addItem(h)
            self.active_handles.append(h)
        self.reposition_handles()

    def reposition_handles(self):
        if not self.active_handles:
            return
        flag_item = self.active_handles[0].flag_item
        cx, cy = flag_item.center()
        hw, hh = flag_item.half_size()
        positions = {
            "nw": (cx - hw, cy - hh), "n": (cx, cy - hh), "ne": (cx + hw, cy - hh),
            "e": (cx + hw, cy), "se": (cx + hw, cy + hh), "s": (cx, cy + hh),
            "sw": (cx - hw, cy + hh), "w": (cx - hw, cy),
        }
        for h in self.active_handles:
            x, y = positions[h.edge]
            h.setPos(x, y)

    def resize_flag_from_handle(self, flag_item, edge, scene_pos):
        cx, cy = flag_item.center()
        w, h = flag_item.size()
        keep_aspect = (self.flag_aspect_checkbox.isChecked()
                       if type(flag_item) is CenteredFlagItem else flag_item.aspect_locked())

        dx = abs(scene_pos.x() - cx) * 2
        dy = abs(scene_pos.y() - cy) * 2

        new_w, new_h = w, h
        if edge in ("nw", "ne", "se", "sw"):
            new_w, new_h = dx, dy
        elif edge in ("e", "w"):
            new_w = dx
            new_h = h
        elif edge in ("n", "s"):
            new_h = dy
            new_w = w

        flag_item.set_size_px(new_w, new_h, keep_aspect=keep_aspect)
        self.reposition_handles()
        if type(flag_item) is CenteredFlagItem:
            self._sync_flag_spinboxes(flag_item)
        elif hasattr(self, "logo_w_spin"):
            self._sync_logo_size_controls(flag_item)

    def _sync_flag_spinboxes(self, flag_item):
        if not hasattr(self, "flag_w_spin"):
            return
        w, h = flag_item.size()
        for spin, val in ((self.flag_w_spin, w), (self.flag_h_spin, h)):
            spin.blockSignals(True)
            spin.setValue(int(val))
            spin.blockSignals(False)

    def resize_text_from_handle(self, item, edge, scene_pos):
        cx, cy = item.center()
        width, height = item.box_size()
        dx, dy = abs(scene_pos.x() - cx) * 2, abs(scene_pos.y() - cy) * 2
        if edge in ("nw", "ne", "se", "sw"):
            width, height = dx, dy
        elif edge in ("e", "w"):
            width = dx
        elif edge in ("n", "s"):
            height = dy
        item.set_box_size(width, height)
        self.reposition_handles()
        self._sync_text_box_controls(item)

    def _sync_text_box_controls(self, item):
        if not hasattr(self, "text_box_w_spin"):
            return
        width, height = item.box_size()
        for spin, value in ((self.text_box_w_spin, width), (self.text_box_h_spin, height)):
            spin.blockSignals(True); spin.setValue(round(value)); spin.blockSignals(False)

    def _on_flag_spin_changed(self):
        flags = self._selected_flag_items_strict()
        if not flags:
            return
        self.push_undo_snapshot()
        w = self.flag_w_spin.value()
        h = self.flag_h_spin.value()
        keep_aspect = self.flag_aspect_checkbox.isChecked()
        for flag in flags:
            flag.set_size_px(w, h, keep_aspect=keep_aspect)
        self.reposition_handles()

    def _selected_flag_items_strict(self):
        return [i for i in self.scene.selectedItems() if type(i) is CenteredFlagItem]

    def _build_shadow_group(self, prefix):
        group = QGroupBox("Shadow / 3D Depth")
        grid = QGridLayout()
        controls = {}
        enabled = QCheckBox("Enable shadow")
        mode = QComboBox(); mode.addItems(["Grey", "Image Color", "Custom"])
        color = QPushButton("Choose Custom Color…")
        direction = QComboBox(); direction.addItems(SHADOW_DIRECTIONS.keys())
        direction.setCurrentText(DEFAULT_SHADOW["direction"])
        grid.addWidget(enabled, 0, 0, 1, 2)
        grid.addWidget(QLabel("Color mode"), 1, 0); grid.addWidget(mode, 1, 1)
        grid.addWidget(color, 2, 0, 1, 2)
        grid.addWidget(QLabel("Direction"), 3, 0); grid.addWidget(direction, 3, 1)
        controls.update(enabled=enabled, color_mode=mode, color_button=color, direction=direction,
                        custom_color=DEFAULT_SHADOW["custom_color"])
        row = 4
        for key, title, maximum in (("distance", "Distance", 200), ("blur", "Blur", 150),
                                    ("opacity", "Opacity", 100), ("spread", "Spread", 100)):
            spin = QSpinBox(); spin.setRange(0, maximum); spin.setValue(DEFAULT_SHADOW[key])
            grid.addWidget(QLabel(title), row, 0); grid.addWidget(spin, row, 1)
            controls[key] = spin; row += 1
        self.shadow_controls[prefix] = controls
        enabled.toggled.connect(lambda: self._shadow_controls_changed(prefix))
        mode.currentTextChanged.connect(lambda: self._shadow_controls_changed(prefix))
        direction.currentTextChanged.connect(lambda: self._shadow_controls_changed(prefix))
        color.clicked.connect(lambda: self._choose_shadow_color(prefix))
        for key in ("distance", "blur", "opacity", "spread"):
            controls[key].valueChanged.connect(lambda _, p=prefix: self._shadow_controls_changed(p))
        group.setLayout(grid)
        return group

    def _shadow_targets(self, prefix):
        if prefix == "flag":
            return self._selected_flag_items_strict()
        logo = self._selected_logo()
        return [logo] if logo else []

    def _shadow_controls_changed(self, prefix):
        if getattr(self, "_syncing_shadow", False):
            return
        targets = self._shadow_targets(prefix)
        if not targets:
            return
        c = self.shadow_controls[prefix]
        settings = {"enabled": c["enabled"].isChecked(), "color_mode": c["color_mode"].currentText(),
                    "custom_color": c["custom_color"], "direction": c["direction"].currentText(),
                    **{key: c[key].value() for key in ("distance", "blur", "opacity", "spread")}}
        self.push_undo_snapshot()
        for item in targets:
            item.set_shadow_settings(settings)

    def _choose_shadow_color(self, prefix):
        controls = self.shadow_controls[prefix]
        color = QColorDialog.getColor(QColor(controls["custom_color"]), self, "Choose Shadow Color")
        if color.isValid():
            controls["custom_color"] = color.name()
            controls["color_mode"].setCurrentText("Custom")
            self._shadow_controls_changed(prefix)

    def _sync_shadow_controls(self, prefix, item):
        if not item or prefix not in self.shadow_controls:
            return
        settings = item.shadow_settings(); c = self.shadow_controls[prefix]
        self._syncing_shadow = True
        c["enabled"].setChecked(settings["enabled"]); c["color_mode"].setCurrentText(settings["color_mode"])
        c["direction"].setCurrentText(settings["direction"]); c["custom_color"] = settings["custom_color"]
        for key in ("distance", "blur", "opacity", "spread"):
            c[key].setValue(settings[key])
        self._syncing_shadow = False

    def _set_selected_aspect_lock(self, checked):
        self.push_undo_snapshot()
        for item in self._selected_flag_items_strict():
            item.set_aspect_locked(checked)

    def _apply_flag_ratio(self, label):
        ratio = ASPECT_RATIOS.get(label)
        flags = self._selected_flag_items_strict()
        if not flags:
            return
        self.push_undo_snapshot()
        for item in flags:
            item.set_aspect_ratio(ratio)
            item.set_aspect_locked(ratio is not None or self.flag_aspect_checkbox.isChecked())
        if ratio is not None:
            self.flag_aspect_checkbox.blockSignals(True)
            self.flag_aspect_checkbox.setChecked(True)
            self.flag_aspect_checkbox.blockSignals(False)
        self._sync_flag_spinboxes(flags[0])
        self.reposition_handles()

    def _apply_flag_shape(self, shape):
        flags = self._selected_flag_items_strict()
        if not flags:
            return
        self.push_undo_snapshot()
        for item in flags:
            item.set_shape(shape)
        self._sync_flag_spinboxes(flags[0])
        self.reposition_handles()

    def _selected_logo(self):
        return next((i for i in self.scene.selectedItems() if isinstance(i, LogoItem)), None)

    def _add_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add Logo", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        logo = LogoItem(CENTER_X, CANVAS_H / 2, app=self)
        if not logo.load_image(path):
            QMessageBox.warning(self, "Load Failed", "Could not read that logo image.")
            return
        self.push_undo_snapshot()
        self.scene.addItem(logo)
        self.logo_items.append(logo)
        self.scene.clearSelection()
        logo.setSelected(True)

    def _apply_logo_shape(self, shape):
        logo = self._selected_logo()
        if logo:
            self.push_undo_snapshot(); logo.set_shape(shape); self._sync_logo_size_controls(logo); self.reposition_handles()

    def _sync_logo_size_controls(self, logo):
        w, h = logo.size()
        for spin, value in ((self.logo_w_spin, w), (self.logo_h_spin, h)):
            spin.blockSignals(True); spin.setValue(round(value)); spin.blockSignals(False)

    def _on_logo_size_changed(self):
        logo = self._selected_logo()
        if not logo:
            return
        self.push_undo_snapshot()
        w, h = self.logo_w_spin.value(), self.logo_h_spin.value()
        if logo.aspect_locked() and self.sender() is self.logo_h_spin:
            w = h * logo.aspect_ratio()
        logo.set_size_px(w, h, keep_aspect=logo.aspect_locked())
        self._sync_logo_size_controls(logo); self.reposition_handles()

    def _set_logo_aspect_lock(self, checked):
        logo = self._selected_logo()
        if logo:
            self.push_undo_snapshot()
            logo.set_aspect_locked(checked)

    def _apply_logo_ratio(self, label):
        logo = self._selected_logo()
        if not logo:
            return
        ratio = ASPECT_RATIOS.get(label); self.push_undo_snapshot(); logo.set_aspect_ratio(ratio)
        if ratio is not None:
            logo.set_aspect_locked(True)
            self.logo_aspect_checkbox.blockSignals(True); self.logo_aspect_checkbox.setChecked(True); self.logo_aspect_checkbox.blockSignals(False)
        self._sync_logo_size_controls(logo); self.reposition_handles()

    def _apply_logo_rotation(self, value):
        logo = self._selected_logo()
        if logo:
            self.push_undo_snapshot(); logo.setTransformOriginPoint(logo.boundingRect().center()); logo.setRotation(value)

    def _apply_logo_opacity(self, value):
        logo = self._selected_logo()
        if logo:
            self.push_undo_snapshot(); logo.setOpacity(value / 100.0)

    def _delete_logo(self):
        logo = self._selected_logo()
        if not logo:
            self.statusBar().showMessage("Select a logo first.", 2500); return
        self.push_undo_snapshot(); self._clear_handles(); self.scene.removeItem(logo); self.logo_items.remove(logo)

    def _remove_logo_background(self):
        logo = self._selected_logo()
        if not logo or not logo.source_path():
            self.statusBar().showMessage("Select an uploaded logo first.", 2500); return
        image = QImage(logo.source_path()).convertToFormat(QImage.Format.Format_ARGB32)
        if image.isNull(): return
        corners = [image.pixelColor(0, 0), image.pixelColor(image.width()-1, 0),
                   image.pixelColor(0, image.height()-1), image.pixelColor(image.width()-1, image.height()-1)]
        br = sum(c.red() for c in corners) / 4; bg = sum(c.green() for c in corners) / 4; bb = sum(c.blue() for c in corners) / 4
        for y in range(image.height()):
            for x in range(image.width()):
                c = image.pixelColor(x, y)
                distance = ((c.red()-br)**2 + (c.green()-bg)**2 + (c.blue()-bb)**2) ** 0.5
                if distance < 55: c.setAlpha(0)
                elif distance < 100: c.setAlpha(int(c.alpha() * (distance - 55) / 45))
                image.setPixelColor(x, y, c)
        dlg = QDialog(self); dlg.setWindowTitle("Background Removal Preview")
        lay = QVBoxLayout(dlg); preview = QLabel(); preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(QPixmap.fromImage(image).scaled(420, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(preview); buttons = QHBoxLayout(); cancel = QPushButton("Cancel"); apply = QPushButton("Apply")
        cancel.clicked.connect(dlg.reject); apply.clicked.connect(dlg.accept); buttons.addWidget(cancel); buttons.addWidget(apply); lay.addLayout(buttons)
        if not dlg.exec(): return
        stem = os.path.splitext(os.path.basename(logo.source_path()))[0]
        os.makedirs(FLAG_CACHE_DIR, exist_ok=True); output = os.path.join(FLAG_CACHE_DIR, stem + "_" + uuid.uuid4().hex + "_transparent.png")
        if image.save(output):
            self.push_undo_snapshot()
            size, ratio, locked = logo.size(), logo.aspect_ratio(), logo.aspect_locked()
            logo.load_image(output)
            logo.set_aspect_ratio(ratio)
            logo.set_aspect_locked(locked)
            logo.set_size_px(*size, keep_aspect=False)
            self._sync_logo_size_controls(logo)
            self.reposition_handles()
            self.statusBar().showMessage("Logo background removed. Use Undo to revert.", 3500)

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self):
        self.shadow_controls = {}
        self._syncing_shadow = False
        dock = QDockWidget("Properties", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(390)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Undo/redo row ---
        undo_row = QHBoxLayout()
        self.btn_undo = QPushButton("← Undo")
        self.btn_undo.setToolTip("Undo the last change (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("Redo →")
        self.btn_redo.setToolTip("Redo the last undone change (Ctrl+Shift+Z)")
        self.btn_redo.clicked.connect(self.redo)
        undo_row.addWidget(self.btn_undo)
        undo_row.addWidget(self.btn_redo)
        layout.addLayout(undo_row)
        delete_selection = QPushButton("Delete Selected Element")
        delete_selection.clicked.connect(lambda: self._delete_selected_elements())
        layout.addWidget(delete_selection)

        tabs = QTabWidget()
        edit_tab, assets_tab, logo_tab, more_tab = QWidget(), QWidget(), QWidget(), QWidget()
        edit_layout, assets_layout = QVBoxLayout(edit_tab), QVBoxLayout(assets_tab)
        logo_layout = QVBoxLayout(logo_tab)
        more_layout = QVBoxLayout(more_tab)
        for tab_layout in (edit_layout, assets_layout, logo_layout, more_layout):
            tab_layout.setContentsMargins(8, 10, 8, 10)
            tab_layout.setSpacing(8)
        for page, title in ((edit_tab, "Text"), (assets_tab, "Images"),
                            (logo_tab, "Logo"), (more_tab, "Save")):
            page_scroll = QScrollArea()
            page_scroll.setWidgetResizable(True)
            page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            page_scroll.setWidget(page)
            tabs.addTab(page_scroll, title)
        layout.addWidget(tabs, 1)

        # --- Text properties panel ---
        text_group = QGroupBox("Text Properties")
        text_lay = QVBoxLayout()

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Select text on the canvas to edit it")
        self.text_edit.textChanged.connect(self._apply_text_edit)
        text_lay.addWidget(self.text_edit)

        font_row = QHBoxLayout()
        self.font_family_label = QLabel("Font: Arial")
        self.font_family_label.setStyleSheet("color:#ccc;")
        btn_font_search = QPushButton("Search Font…")
        btn_font_search.clicked.connect(self._open_font_picker)
        font_row.addWidget(self.font_family_label)
        font_row.addWidget(btn_font_search)
        text_lay.addLayout(font_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Size"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 400)
        self.font_size_spin.setValue(40)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        size_row.addWidget(self.font_size_spin)
        btn_dec = QToolButton(); btn_dec.setText("−")
        btn_dec.clicked.connect(lambda: self.font_size_spin.setValue(self.font_size_spin.value() - 2))
        btn_inc = QToolButton(); btn_inc.setText("+")
        btn_inc.clicked.connect(lambda: self.font_size_spin.setValue(self.font_size_spin.value() + 2))
        size_row.addWidget(btn_dec)
        size_row.addWidget(btn_inc)
        text_lay.addLayout(size_row)

        style_row = QHBoxLayout()
        self.bold_btn = QPushButton("B"); self.bold_btn.setCheckable(True)
        self.italic_btn = QPushButton("I"); self.italic_btn.setCheckable(True)
        self.underline_btn = QPushButton("U"); self.underline_btn.setCheckable(True)
        for b in (self.bold_btn, self.italic_btn, self.underline_btn):
            b.setFixedWidth(34)
            b.toggled.connect(self._apply_font_style_toggles)
            style_row.addWidget(b)
        btn_color = QPushButton("Color")
        btn_color.clicked.connect(self._choose_color)
        style_row.addWidget(btn_color)
        text_lay.addLayout(style_row)

        spacing_row = QHBoxLayout()
        spacing_row.addWidget(QLabel("Letter px"))
        self.letter_spacing_spin = QSpinBox()
        self.letter_spacing_spin.setRange(-10, 60)
        self.letter_spacing_spin.setValue(0)
        self.letter_spacing_spin.valueChanged.connect(self._on_letter_spacing_changed)
        spacing_row.addWidget(self.letter_spacing_spin)
        text_lay.addLayout(spacing_row)

        transform_row = QHBoxLayout()
        transform_row.addWidget(QLabel("Transform"))
        self.transform_combo = QComboBox()
        self.transform_combo.addItems(["None", "UPPERCASE", "lowercase", "Capitalize"])
        transform_row.addWidget(self.transform_combo)
        btn_apply_transform = QPushButton("Apply")
        btn_apply_transform.clicked.connect(self._apply_text_transform)
        transform_row.addWidget(btn_apply_transform)
        text_lay.addLayout(transform_row)

        text_lay.addWidget(QLabel("Text Box Size"))
        box_size_row = QHBoxLayout()
        box_size_row.addWidget(QLabel("W"))
        self.text_box_w_spin = QSpinBox(); self.text_box_w_spin.setRange(80, CANVAS_W)
        box_size_row.addWidget(self.text_box_w_spin)
        box_size_row.addWidget(QLabel("H"))
        self.text_box_h_spin = QSpinBox(); self.text_box_h_spin.setRange(35, CANVAS_H)
        box_size_row.addWidget(self.text_box_h_spin)
        self.text_box_w_spin.valueChanged.connect(self._on_text_box_size_changed)
        self.text_box_h_spin.valueChanged.connect(self._on_text_box_size_changed)
        text_lay.addLayout(box_size_row)
        text_box_note = QLabel("Drag the blue handles or enter an exact box size. Font size stays unchanged.")
        text_box_note.setWordWrap(True); text_box_note.setStyleSheet("color:#9ca3af; font-size:11px;")
        text_lay.addWidget(text_box_note)
        

        text_group.setLayout(text_lay)
        edit_layout.addWidget(text_group)

        add_line = QPushButton("Add Line")
        add_line.clicked.connect(self._add_top_line)
        edit_layout.addWidget(add_line)
        edit_layout.addStretch()

        # --- Grid & snapping ---
        grid_group = QGroupBox("Canvas Grid && Snapping")
        grid_lay = QVBoxLayout()
        self.grid_checkbox = QCheckBox("Show Grid")
        self.grid_checkbox.toggled.connect(self._toggle_grid)
        grid_lay.addWidget(self.grid_checkbox)

        spacing_row2 = QHBoxLayout()
        spacing_row2.addWidget(QLabel("Grid spacing (px)"))
        self.grid_spacing_spin = QSpinBox()
        self.grid_spacing_spin.setRange(10, 300)
        self.grid_spacing_spin.setValue(GRID_DEFAULT_SPACING)
        self.grid_spacing_spin.valueChanged.connect(self._set_grid_spacing)
        spacing_row2.addWidget(self.grid_spacing_spin)
        grid_lay.addLayout(spacing_row2)

        self.snap_enabled_checkbox = QCheckBox("Snap to grid / center / edges / elements")
        self.snap_enabled_checkbox.setChecked(True)
        grid_lay.addWidget(self.snap_enabled_checkbox)

        note = QLabel("Grid lines are visual guides only — never included in the exported image.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8fbf8f; font-size:11px;")
        grid_lay.addWidget(note)

        grid_group.setLayout(grid_lay)
        more_layout.addWidget(grid_group)

        # --- Background ---
        bg_group = QGroupBox("Background")
        bg_lay = QVBoxLayout()
        btn_bg = QPushButton("Load Background Image")
        btn_bg.clicked.connect(self._load_background)
        bg_lay.addWidget(btn_bg)
        btn_effects = QPushButton("Effects…")
        btn_effects.clicked.connect(self._open_effects_dialog)
        bg_lay.addWidget(btn_effects)
        bg_group.setLayout(bg_lay)
        assets_layout.addWidget(bg_group)

        # --- Flags ---
        flag_group = QGroupBox("Flags")
        flag_lay = QVBoxLayout()
        flag_btn_row = QHBoxLayout()
        btn_left = QPushButton("Load Left Flag")
        btn_left.clicked.connect(lambda: self._load_flag(self.left_flag))
        btn_right = QPushButton("Load Right Flag")
        btn_right.clicked.connect(lambda: self._load_flag(self.right_flag))
        flag_btn_row.addWidget(btn_left)
        flag_btn_row.addWidget(btn_right)
        flag_lay.addLayout(flag_btn_row)

        flag_lay.addWidget(QLabel("Auto Flag by Country Name:"))
        country_row_l = QHBoxLayout()
        self.country_l_input = QLineEdit()
        self.country_l_input.setPlaceholderText("Left country e.g. Australia")
        self.country_l_input.setText(DEFAULT_LAYOUT["left_team"])
        btn_auto_l = QPushButton("Set")
        btn_auto_l.clicked.connect(lambda: self._auto_flag(self.country_l_input, self.left_flag))
        country_row_l.addWidget(self.country_l_input)
        country_row_l.addWidget(btn_auto_l)
        flag_lay.addLayout(country_row_l)

        country_row_r = QHBoxLayout()
        self.country_r_input = QLineEdit()
        self.country_r_input.setPlaceholderText("Right country e.g. Poland")
        self.country_r_input.setText(DEFAULT_LAYOUT["right_team"])
        btn_auto_r = QPushButton("Set")
        btn_auto_r.clicked.connect(lambda: self._auto_flag(self.country_r_input, self.right_flag))
        country_row_r.addWidget(self.country_r_input)
        country_row_r.addWidget(btn_auto_r)
        flag_lay.addLayout(country_row_r)

        if not HAVE_PYCOUNTRY:
            note2 = QLabel("Install 'pycountry' to enable this (pip install pycountry).")
            note2.setStyleSheet("color: #e6a23c;")
            note2.setWordWrap(True)
            flag_lay.addWidget(note2)

        flag_lay.addWidget(QLabel("Flag Size (drag handles on canvas, or set exactly):"))
        size_row2 = QHBoxLayout()
        size_row2.addWidget(QLabel("W"))
        self.flag_w_spin = QSpinBox()
        self.flag_w_spin.setRange(FLAG_MIN_W, FLAG_MAX_W)
        self.flag_w_spin.setValue(BASE_FLAG_W)
        self.flag_w_spin.valueChanged.connect(self._on_flag_spin_changed)
        size_row2.addWidget(self.flag_w_spin)
        size_row2.addWidget(QLabel("H"))
        self.flag_h_spin = QSpinBox()
        self.flag_h_spin.setRange(FLAG_MIN_H, FLAG_MAX_H)
        self.flag_h_spin.setValue(BASE_FLAG_H)
        self.flag_h_spin.valueChanged.connect(self._on_flag_spin_changed)
        size_row2.addWidget(self.flag_h_spin)
        flag_lay.addLayout(size_row2)

        self.flag_aspect_checkbox = QCheckBox("Lock aspect ratio")
        self.flag_aspect_checkbox.setChecked(True)
        self.flag_aspect_checkbox.toggled.connect(self._set_selected_aspect_lock)
        flag_lay.addWidget(self.flag_aspect_checkbox)

        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("Aspect ratio"))
        self.flag_ratio_combo = QComboBox()
        self.flag_ratio_combo.addItems(ASPECT_RATIOS.keys())
        self.flag_ratio_combo.setCurrentText("Custom")
        self.flag_ratio_combo.currentTextChanged.connect(self._apply_flag_ratio)
        ratio_row.addWidget(self.flag_ratio_combo)
        flag_lay.addLayout(ratio_row)

        shape_row = QHBoxLayout()
        shape_row.addWidget(QLabel("Shape"))
        self.flag_shape_combo = QComboBox()
        self.flag_shape_combo.addItems(SHAPES)
        self.flag_shape_combo.currentTextChanged.connect(self._apply_flag_shape)
        shape_row.addWidget(self.flag_shape_combo)
        flag_lay.addLayout(shape_row)

        flag_group.setLayout(flag_lay)
        assets_layout.addWidget(flag_group)
        assets_layout.addWidget(self._build_shadow_group("flag"))
        assets_layout.addStretch()

        # --- Logos (kept separate from flags/images) ---
        logo_group = QGroupBox("Logo")
        logo_lay = QVBoxLayout()
        add_logo_btn = QPushButton("Add Logo…")
        add_logo_btn.clicked.connect(self._add_logo)
        logo_lay.addWidget(add_logo_btn)
        self.logo_shape_combo = QComboBox()
        self.logo_shape_combo.addItems(SHAPES)
        self.logo_shape_combo.currentTextChanged.connect(self._apply_logo_shape)
        logo_lay.addWidget(QLabel("Logo shape"))
        logo_lay.addWidget(self.logo_shape_combo)
        logo_size_row = QHBoxLayout()
        logo_size_row.addWidget(QLabel("W")); self.logo_w_spin = QSpinBox()
        self.logo_w_spin.setRange(FLAG_MIN_W, FLAG_MAX_W); self.logo_w_spin.setValue(260)
        logo_size_row.addWidget(self.logo_w_spin); logo_size_row.addWidget(QLabel("H")); self.logo_h_spin = QSpinBox()
        self.logo_h_spin.setRange(FLAG_MIN_H, FLAG_MAX_H); self.logo_h_spin.setValue(180)
        logo_size_row.addWidget(self.logo_h_spin); logo_lay.addLayout(logo_size_row)
        self.logo_w_spin.valueChanged.connect(self._on_logo_size_changed)
        self.logo_h_spin.valueChanged.connect(self._on_logo_size_changed)
        self.logo_aspect_checkbox = QCheckBox("Lock aspect ratio")
        self.logo_aspect_checkbox.setChecked(True); self.logo_aspect_checkbox.toggled.connect(self._set_logo_aspect_lock)
        logo_lay.addWidget(self.logo_aspect_checkbox)
        logo_lay.addWidget(QLabel("Aspect ratio")); self.logo_ratio_combo = QComboBox()
        self.logo_ratio_combo.addItems(ASPECT_RATIOS.keys()); self.logo_ratio_combo.currentTextChanged.connect(self._apply_logo_ratio)
        logo_lay.addWidget(self.logo_ratio_combo)
        logo_lay.addWidget(QLabel("Rotation"))
        self.logo_rotation_spin = QSpinBox()
        self.logo_rotation_spin.setRange(-360, 360)
        self.logo_rotation_spin.setSuffix("°")
        self.logo_rotation_spin.valueChanged.connect(self._apply_logo_rotation)
        logo_lay.addWidget(self.logo_rotation_spin)
        logo_lay.addWidget(QLabel("Opacity"))
        self.logo_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.logo_opacity_slider.setRange(0, 100)
        self.logo_opacity_slider.setValue(100)
        self.logo_opacity_slider.valueChanged.connect(self._apply_logo_opacity)
        logo_lay.addWidget(self.logo_opacity_slider)
        
        remove_bg_btn = QPushButton("Remove Background…")
        remove_bg_btn.clicked.connect(self._remove_logo_background)
        logo_lay.addWidget(remove_bg_btn)
        logo_group.setLayout(logo_lay)
        logo_layout.addWidget(logo_group)
        logo_layout.addWidget(self._build_shadow_group("logo"))
        logo_layout.addStretch()

        # --- Presets ---
        preset_group = QGroupBox("Presets")
        preset_lay = QVBoxLayout()
        btn_save_preset = QPushButton("Save As Preset…")
        btn_save_preset.clicked.connect(self._save_preset_dialog)
        preset_lay.addWidget(btn_save_preset)
        btn_load_preset = QPushButton("Load Preset…")
        btn_load_preset.clicked.connect(self._load_preset_dialog)
        preset_lay.addWidget(btn_load_preset)
        preset_group.setLayout(preset_lay)
        more_layout.addWidget(preset_group)

        btn_reset = QPushButton("Reset Layout to Template")
        btn_reset.clicked.connect(self._reset_layout)
        btn_reset.setObjectName("dangerButton")
        more_layout.addWidget(btn_reset)
        more_layout.addStretch()

        btn_export = QPushButton("Export Thumbnail")
        btn_export.setText("Export Thumbnail  (1920 × 1080)")
        btn_export.setObjectName("primaryButton")
        btn_export.setToolTip("Save the finished thumbnail as PNG or JPEG")
        btn_export.clicked.connect(self._export_image)
        layout.addWidget(btn_export)

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._update_undo_redo_buttons()

    # ------------------------------------------------------------------ selection
    def _selected_text_item(self):
        for item in self.scene.selectedItems():
            if isinstance(item, CenteredTextItem):
                return item
        return None

    def _selected_flag_items(self):
        sel = [i for i in self.scene.selectedItems() if isinstance(i, CenteredFlagItem)]
        return sel if sel else list(self.flag_items)

    def _on_selection_changed(self):
        if self._restoring:
            return
        text_item = self._selected_text_item()
        for widget in (self.font_size_spin, self.text_box_w_spin, self.text_box_h_spin,
                       self.bold_btn, self.italic_btn, self.underline_btn, self.letter_spacing_spin):
            widget.setEnabled(text_item is not None)
        self.text_edit.blockSignals(True)
        if text_item:
            self.text_edit.setEnabled(True)
            self.text_edit.setText(text_item.toPlainText())
            f = text_item.font()
            self.font_family_label.setText(f"Font: {f.family()}")
            self.font_size_spin.blockSignals(True)
            self.font_size_spin.setValue(f.pointSize() if f.pointSize() > 0 else 40)
            self.font_size_spin.blockSignals(False)
            self.bold_btn.blockSignals(True); self.bold_btn.setChecked(f.bold()); self.bold_btn.blockSignals(False)
            self.italic_btn.blockSignals(True); self.italic_btn.setChecked(f.italic()); self.italic_btn.blockSignals(False)
            self.underline_btn.blockSignals(True); self.underline_btn.setChecked(f.underline()); self.underline_btn.blockSignals(False)
            self.letter_spacing_spin.blockSignals(True)
            self.letter_spacing_spin.setValue(text_item.letter_spacing_px)
            self.letter_spacing_spin.blockSignals(False)
            self._sync_text_box_controls(text_item)
        else:
            self.text_edit.clear()
            self.text_edit.setEnabled(False)
        self.text_edit.blockSignals(False)

        flags = self._selected_flag_items_strict()
        if len(flags) == 1:
            self._spawn_handles_for(flags[0])
            self._sync_flag_spinboxes(flags[0])
            self.flag_aspect_checkbox.blockSignals(True); self.flag_aspect_checkbox.setChecked(flags[0].aspect_locked()); self.flag_aspect_checkbox.blockSignals(False)
            self.flag_shape_combo.blockSignals(True); self.flag_shape_combo.setCurrentText(flags[0].shape_name()); self.flag_shape_combo.blockSignals(False)
            self._sync_shadow_controls("flag", flags[0])
        else:
            self._clear_handles()

        logo = self._selected_logo()
        if logo:
            self._spawn_handles_for(logo)
            self._sync_logo_size_controls(logo)
            self.logo_aspect_checkbox.blockSignals(True); self.logo_aspect_checkbox.setChecked(logo.aspect_locked()); self.logo_aspect_checkbox.blockSignals(False)
            self.logo_shape_combo.blockSignals(True); self.logo_shape_combo.setCurrentText(logo.shape_name()); self.logo_shape_combo.blockSignals(False)
            self.logo_rotation_spin.blockSignals(True); self.logo_rotation_spin.setValue(round(logo.rotation())); self.logo_rotation_spin.blockSignals(False)
            self.logo_opacity_slider.blockSignals(True); self.logo_opacity_slider.setValue(round(logo.opacity() * 100)); self.logo_opacity_slider.blockSignals(False)
            self._sync_shadow_controls("logo", logo)
        elif not flags and text_item:
            self._spawn_handles_for(text_item)

    def _apply_text_edit(self):
        item = self._selected_text_item()
        if item:
            item.set_text(self.text_edit.text())
            if item is self.left_name:
                self.country_l_input.setText(item.toPlainText())
            elif item is self.right_name:
                self.country_r_input.setText(item.toPlainText())
            self.reposition_handles()
            self._update_undo_redo_buttons()

    def _on_text_box_size_changed(self):
        item = self._selected_text_item()
        if not item:
            return
        self.push_undo_snapshot()
        item.set_box_size(self.text_box_w_spin.value(), self.text_box_h_spin.value())
        self.reposition_handles()

    def _delete_selected_text(self):
        self._delete_selected_elements(text_only=True)

    def _delete_selected_elements(self, text_only=False):
        selected = [i for i in self.scene.selectedItems()
                    if (isinstance(i, (CenteredTextItem, CenteredFlagItem)) or i is self.bg_item)
                    and (not text_only or isinstance(i, CenteredTextItem))]
        if not selected:
            return
        self.push_undo_snapshot()
        self.scene.blockSignals(True)
        try:
            self._clear_handles()
            for item in selected:
                if item is self.bg_item:
                    self._bg_effects = copy.deepcopy(DEFAULT_BG_EFFECTS)
                    self._draw_default_background()
                    self.bg_item.setSelected(False)
                    continue
                for group in (self.top_lines, self.bottom_lines, self.logo_items):
                    if item in group:
                        group.remove(item)
                self.scene.removeItem(item)
        finally:
            self.scene.blockSignals(False)
        self._on_selection_changed()

    def _open_font_picker(self):
        item = self._selected_text_item()
        if not item:
            self.statusBar().showMessage("Select a text line first.", 3000)
            return
        dlg = FontPickerDialog(item.font().family(), self)
        if dlg.exec():
            self.push_undo_snapshot()
            family = dlg.get_selected()
            f = item.font()
            f.setFamily(family)
            item.set_style(font=f)
            self.font_family_label.setText(f"Font: {family}")

    def _on_font_size_changed(self, value):
        item = self._selected_text_item()
        if not item:
            return
        self.push_undo_snapshot()
        f = item.font()
        f.setPointSize(value)
        item.set_style(font=f)

    def _apply_font_style_toggles(self):
        item = self._selected_text_item()
        if not item:
            return
        self.push_undo_snapshot()
        f = item.font()
        f.setBold(self.bold_btn.isChecked())
        f.setItalic(self.italic_btn.isChecked())
        f.setUnderline(self.underline_btn.isChecked())
        item.set_style(font=f)

    def _choose_color(self):
        item = self._selected_text_item()
        if not item:
            self.statusBar().showMessage("Select a text line first.", 3000)
            return
        self.push_undo_snapshot()
        color = QColorDialog.getColor(item.defaultTextColor(), self)
        if color.isValid():
            item.set_style(color=color)

    def _on_letter_spacing_changed(self, value):
        item = self._selected_text_item()
        if not item:
            return
        self.push_undo_snapshot()
        item.set_letter_spacing(value)

    def _apply_text_transform(self):
        item = self._selected_text_item()
        if not item:
            return
        mode = self.transform_combo.currentText()
        if mode == "None":
            return
        self.push_undo_snapshot()
        item.apply_text_transform(mode)
        self.text_edit.blockSignals(True)
        self.text_edit.setText(item.toPlainText())
        self.text_edit.blockSignals(False)

    # ------------------------------------------------------------------ line controls
    def _make_blank_line(self, role):
        size = 40 if role == "top_line" else 34
        return self._make_text("New Line", size, int(QFont.Weight.Bold), CENTER_X, 0, home_x=CENTER_X, role=role)

    def _remove_item_from_group(self, item, group):
        if item in group:
            group.remove(item)
            self.scene.removeItem(item)
            return True
        return False

    def _add_top_line(self):
        self.push_undo_snapshot()
        item = self._make_blank_line("top_line")
        self.top_lines.append(item)
        item.set_center(CENTER_X, CANVAS_H / 2)
        self.named_items = self._collect_named_items()
        self.scene.clearSelection()
        item.setSelected(True)
        self.statusBar().showMessage("Line added.", 3000)

    def _add_bottom_line(self):
        self.push_undo_snapshot()
        item = self._make_blank_line("bottom_line")
        self.bottom_lines.append(item)
        self._layout_bottom_lines()
        self.named_items = self._collect_named_items()
        self.statusBar().showMessage("Bottom line added.", 3000)

    # ------------------------------------------------------------------ bg / flag
    def _load_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if self._set_background_image(path):
            self.statusBar().showMessage(f"Background loaded: {path}", 4000)
        else:
            QMessageBox.warning(self, "Load Failed", "Could not read that image file.")

    def _load_flag(self, flag_item):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Flag Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if flag_item.load_image(path):
            if flag_item.scene() is None:
                self.scene.addItem(flag_item)
            # Cached country flags use names such as in_w320.png. Only infer
            # a country when the filename can be resolved unambiguously.
            code = os.path.splitext(os.path.basename(path))[0].split("_")[0]
            country = None
            if HAVE_PYCOUNTRY:
                try:
                    country = pycountry.countries.lookup(code)
                except LookupError:
                    pass
            if country:
                name_item = self.left_name if flag_item is self.left_flag else self.right_name
                name_input = self.country_l_input if flag_item is self.left_flag else self.country_r_input
                name_item.set_text(country.name)
                name_input.setText(country.name)
                if name_item.scene() is None:
                    self.scene.addItem(name_item)
            self.statusBar().showMessage(f"Flag loaded: {path}", 4000)
            self.reposition_handles()
        else:
            QMessageBox.warning(self, "Load Failed", "Could not read that image file.")

    def _auto_flag(self, country_input, flag_item):
        name = country_input.text().strip()
        if not name:
            self.statusBar().showMessage("Type a country name first.", 3000)
            return
        if not HAVE_PYCOUNTRY:
            QMessageBox.warning(
                self, "Missing Dependency",
                "This feature needs 'pycountry'.\n\npip install pycountry",
            )
            return
        code = resolve_country_code(name)
        if not code:
            QMessageBox.warning(
                self, "Country Not Found",
                f"Couldn't match '{name}' to a country.\n"
                f"Try the full official name (e.g. 'South Korea', 'United States').",
            )
            return
        self.statusBar().showMessage(f"Fetching flag for {name} ({code.upper()})…")
        QApplication.processEvents()
        try:
            path = fetch_flag_image(code)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            QMessageBox.critical(
                self, "Download Failed",
                f"Couldn't download the flag for {name}.\n\n{exc}",
            )
            self.statusBar().showMessage("Flag download failed.", 4000)
            return
        self.push_undo_snapshot()
        if flag_item.load_image(path):
            text_item = self.left_name if flag_item is self.left_flag else self.right_name
            text_item.set_text(name)
            if flag_item.scene() is None:
                self.scene.addItem(flag_item)
            if text_item.scene() is None:
                self.scene.addItem(text_item)
            self.statusBar().showMessage(f"Flag set for {name} ({code.upper()}).", 4000)
            self.reposition_handles()
        else:
            QMessageBox.warning(self, "Load Failed", "Downloaded flag image could not be read.")

    # ------------------------------------------------------------------ presets / state
    def _serialize_text_item(self, item):
        font = item.font()
        color = item.defaultTextColor()
        cx, cy = item.center()
        return {
            "text": item.toPlainText(),
            "font_family": font.family(),
            "font_size": font.pointSize(),
            "font_weight": int(font.weight()),
            "font_italic": font.italic(),
            "font_bold": font.bold(),
            "font_underline": font.underline(),
            "color": color.name(QColor.NameFormat.HexArgb),
            "center": [cx, cy],
            "role": item.role,
            "align": item.align,
            "line_spacing_pct": item.line_spacing_pct,
            "letter_spacing_px": item.letter_spacing_px,
            "z": item.zValue(),
            "box_size": list(item.box_size()) if item._box_w is not None else None,
            "in_scene": item.scene() is self.scene,
        }

    def _capture_state(self):
        state = {
            "background": self._background_path,
            "bg_effects": copy.deepcopy(self._bg_effects),
            "fixed_texts": {
                "vs_text": self._serialize_text_item(self.vs_text),
                "left_name": self._serialize_text_item(self.left_name),
                "right_name": self._serialize_text_item(self.right_name),
            },
            "top_lines": [self._serialize_text_item(i) for i in self.top_lines],
            "bottom_lines": [self._serialize_text_item(i) for i in self.bottom_lines],
            "flags": {
                "left_flag": {
                    "in_scene": self.left_flag.scene() is self.scene,
                    "path": self.left_flag.source_path(),
                    "size": list(self.left_flag.size()),
                    "center": list(self.left_flag.center()),
                    "aspect_locked": self.left_flag.aspect_locked(),
                    "aspect_ratio": self.left_flag.aspect_ratio(),
                    "shape": self.left_flag.shape_name(),
                    "z": self.left_flag.zValue(),
                    "shadow": self.left_flag.shadow_settings(),
                },
                "right_flag": {
                    "in_scene": self.right_flag.scene() is self.scene,
                    "path": self.right_flag.source_path(),
                    "size": list(self.right_flag.size()),
                    "center": list(self.right_flag.center()),
                    "aspect_locked": self.right_flag.aspect_locked(),
                    "aspect_ratio": self.right_flag.aspect_ratio(),
                    "shape": self.right_flag.shape_name(),
                    "z": self.right_flag.zValue(),
                    "shadow": self.right_flag.shadow_settings(),
                },
            },
            "logos": [{
                "path": item.source_path(), "size": list(item.size()), "center": list(item.center()),
                "aspect_locked": item.aspect_locked(), "aspect_ratio": item.aspect_ratio(),
                "shape": item.shape_name(), "rotation": item.rotation(), "opacity": item.opacity(),
                "z": item.zValue(),
                "shadow": item.shadow_settings(),
            } for item in self.logo_items],
            "layout": {
                "top_start_y": self._top_start_y,
                "top_gap": self._top_gap,
                "bottom_start_y": self._bottom_start_y,
                "bottom_gap": self._bottom_gap,
            },
            "grid": {
                "enabled": self._grid_enabled,
                "spacing": self._grid_spacing,
            },
        }
        return state

    def _apply_saved_text_style(self, item, data):
        font = QFont(data.get("font_family", "Arial"), data.get("font_size", 40))
        font.setWeight(QFont.Weight(data.get("font_weight", int(QFont.Weight.Bold))))
        font.setItalic(bool(data.get("font_italic", False)))
        # Weight already includes bold; setting bold again loses Black/Heavy.
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, data.get("letter_spacing_px", 0))
        font.setUnderline(bool(data.get("font_underline", False)))
        color = QColor(data.get("color", "#ffffffff"))
        item.align = data.get("align", "center")
        item.line_spacing_pct = data.get("line_spacing_pct", 100)
        item.letter_spacing_px = data.get("letter_spacing_px", 0)
        item.set_text(data.get("text", ""))
        item.set_style(font=font, color=color)
        cx, cy = data.get("center", list(item.center()))
        item.set_center(cx, cy)
        item.setZValue(data.get("z", item.zValue()))
        box_size = data.get("box_size")
        if box_size:
            item.set_box_size(box_size[0], box_size[1])

    def _apply_state(self, state):
        previous = self._restoring
        self._restoring = True
        self.scene.blockSignals(True)
        try:
            self._restore_state(state)
        finally:
            self.scene.blockSignals(False)
            self._restoring = previous
            self._on_selection_changed()

    def _restore_state(self, state):
        self._clear_template_items()

        bg_path = state.get("background")
        if bg_path and os.path.exists(bg_path):
            self._set_background_image(bg_path)
        else:
            self._draw_default_background()
        self._bg_effects = {**DEFAULT_BG_EFFECTS, **state.get("bg_effects", {})}
        self._refresh_background_pixmap()

        layout_cfg = state.get("layout", {})
        self._top_start_y = layout_cfg.get("top_start_y", DEFAULT_LAYOUT["top_start_y"])
        self._top_gap = layout_cfg.get("top_gap", DEFAULT_LAYOUT["top_gap"])
        self._bottom_start_y = layout_cfg.get("bottom_start_y", DEFAULT_LAYOUT["bottom_start_y"])
        self._bottom_gap = layout_cfg.get("bottom_gap", DEFAULT_LAYOUT["bottom_gap"])

        grid_cfg = state.get("grid", {})
        self._grid_enabled = grid_cfg.get("enabled", False)
        self._grid_spacing = grid_cfg.get("spacing", GRID_DEFAULT_SPACING)
        if hasattr(self, "grid_checkbox"):
            self.grid_checkbox.blockSignals(True)
            self.grid_checkbox.setChecked(self._grid_enabled)
            self.grid_checkbox.blockSignals(False)
            self.grid_spacing_spin.blockSignals(True)
            self.grid_spacing_spin.setValue(self._grid_spacing)
            self.grid_spacing_spin.blockSignals(False)
        self._rebuild_grid()

        self.left_flag = CenteredFlagItem(LEFT_X, DEFAULT_LAYOUT["flag_y"], label="Left Flag", app=self)
        self.right_flag = CenteredFlagItem(RIGHT_X, DEFAULT_LAYOUT["flag_y"], label="Right Flag", app=self)
        self.scene.addItem(self.left_flag)
        self.scene.addItem(self.right_flag)
        self.flag_items = [self.left_flag, self.right_flag]

        fixed = state.get("fixed_texts", {})
        self.vs_text = self._make_text("VS", 96, int(QFont.Weight.Black), CENTER_X, DEFAULT_LAYOUT["vs_y"], home_x=CENTER_X, role="vs")
        self.left_name = self._make_text("TEAM A", 52, int(QFont.Weight.Black), LEFT_X, DEFAULT_LAYOUT["name_y"], home_x=LEFT_X, role="team")
        self.right_name = self._make_text("TEAM B", 52, int(QFont.Weight.Black), RIGHT_X, DEFAULT_LAYOUT["name_y"], home_x=RIGHT_X, role="team")
        self.fixed_text_items = {
            "vs_text": self.vs_text,
            "left_name": self.left_name,
            "right_name": self.right_name,
        }
        for key, item in self.fixed_text_items.items():
            if key in fixed:
                self._apply_saved_text_style(item, fixed[key])
                if not fixed[key].get("in_scene", True):
                    self.scene.removeItem(item)

        self.top_lines = []
        for data in state.get("top_lines", []):
            item = self._make_text(
                data.get("text", ""), data.get("font_size", 40),
                data.get("font_weight", int(QFont.Weight.Bold)), CENTER_X, 0,
                home_x=CENTER_X, role="top_line"
            )
            self._apply_saved_text_style(item, data)
            self.top_lines.append(item)

        self.bottom_lines = []
        for data in state.get("bottom_lines", []):
            item = self._make_text(
                data.get("text", ""), data.get("font_size", 34),
                data.get("font_weight", int(QFont.Weight.Bold)), CENTER_X, 0,
                home_x=CENTER_X, role="bottom_line"
            )
            self._apply_saved_text_style(item, data)
            self.bottom_lines.append(item)

        flags = state.get("flags", {})
        for name, item in (("left_flag", self.left_flag), ("right_flag", self.right_flag)):
            data = flags.get(name, {})
            path = data.get("path")
            if path and os.path.exists(path):
                item.load_image(path)
            item.set_aspect_locked(data.get("aspect_locked", True))
            item.set_aspect_ratio(data.get("aspect_ratio"))
            item.set_shape(data.get("shape", "Rectangle"))
            size = data.get("size")
            if size:
                item.set_size_px(size[0], size[1], keep_aspect=False)
            elif "scale_pct" in data:  # legacy preset compatibility
                item.set_scale_pct(data.get("scale_pct", 100))
            cx, cy = data.get("center", list(item.center()))
            item.set_center(cx, cy)
            item.setZValue(data.get("z", item.zValue()))
            item.set_shadow_settings(data.get("shadow", DEFAULT_SHADOW))
            if not data.get("in_scene", True):
                self.scene.removeItem(item)

        self.logo_items = []
        for data in state.get("logos", []):
            cx, cy = data.get("center", [CENTER_X, CANVAS_H / 2])
            logo = LogoItem(cx, cy, app=self)
            path = data.get("path")
            if path and os.path.exists(path): logo.load_image(path)
            logo.set_aspect_locked(data.get("aspect_locked", True))
            logo.set_aspect_ratio(data.get("aspect_ratio"))
            size = data.get("size", [260, 180])
            logo.set_size_px(size[0], size[1], keep_aspect=False)
            logo.set_shape(data.get("shape", "Rectangle"))
            logo.setTransformOriginPoint(logo.boundingRect().center())
            logo.setRotation(data.get("rotation", 0)); logo.setOpacity(data.get("opacity", 1.0)); logo.setZValue(data.get("z", 20))
            logo.set_shadow_settings(data.get("shadow", DEFAULT_SHADOW))
            self.scene.addItem(logo); self.logo_items.append(logo)

        self.named_items = self._collect_named_items()
        self.country_l_input.setText(self.left_name.toPlainText())
        self.country_r_input.setText(self.right_name.toPlainText())
        self._clear_handles()

    def _save_preset_dialog(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in list_presets():
            confirm = QMessageBox.question(
                self, "Overwrite?",
                f"A preset named '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        try:
            save_preset_json(name, self._capture_state())
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not write preset.\n\n{exc}")
            return
        self.statusBar().showMessage(f"Preset '{name}' saved.", 5000)

    def _load_preset_dialog(self):
        presets = list_presets()
        if not presets:
            QMessageBox.information(self, "No Presets", "No saved presets yet.")
            return
        name, ok = QInputDialog.getItem(self, "Load Preset", "Choose:", presets, 0, False)
        if ok and name:
            self._load_preset_by_name(name)

    def _load_preset_by_name(self, name):
        try:
            state = load_preset_json(name)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Load Failed", f"Could not read preset '{name}'.\n\n{exc}")
            return
        current = copy.deepcopy(self._capture_state())
        self.push_undo_snapshot()
        try:
            if not isinstance(state, dict):
                raise ValueError("A preset must contain a design object.")
            self._apply_state(state)
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
            self._apply_state(current)
            QMessageBox.warning(self, "Invalid Preset", f"This preset could not be loaded. Your design was restored.\n{exc}")
            return
        self._commit_history()
        self.statusBar().showMessage(f"Preset '{name}' loaded.", 4000)

    def _prompt_startup_preset(self):
        presets = list_presets()
        if not presets:
            return
        options = ["Blank Template (default)"] + presets
        choice, ok = QInputDialog.getItem(
            self, "Start Thumbnail",
            "Start from blank template or load a preset:",
            options, 0, False,
        )
        if ok and choice != options[0]:
            self._load_preset_by_name(choice)

    # ------------------------------------------------------------------ reset / export
    def _reset_layout(self):
        confirm = QMessageBox.question(
            self, "Reset Layout",
            "Remove all items and restore the default template?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.push_undo_snapshot()
        self.scene.clearSelection()
        self._draw_default_background()
        self._bg_effects = copy.deepcopy(DEFAULT_BG_EFFECTS)
        self._refresh_background_pixmap()
        self._build_template_items()
        self.statusBar().showMessage("Layout reset.", 3000)

    def _export_image(self):
        self.scene.clearSelection()
        self._clear_handles()
        self._clear_guides()
        # Grid must never appear in the exported file.
        grid_was_on = self._grid_enabled
        for line in self._grid_lines:
            line.setVisible(False)

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Thumbnail", "thumbnail.png",
            "PNG Image (*.png);;JPEG Image (*.jpg)",
        )
        if not path:
            for line in self._grid_lines:
                line.setVisible(grid_was_on)
            return
        image = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.scene.render(
            painter,
            QRectF(0, 0, CANVAS_W, CANVAS_H),
            QRectF(0, 0, CANVAS_W, CANVAS_H),
        )
        painter.end()

        for line in self._grid_lines:
            line.setVisible(grid_was_on)

        if image.save(path):
            QMessageBox.information(self, "Success", f"Thumbnail exported to:\n{path}")
            self.statusBar().showMessage(f"Exported to {path}", 5000)
        else:
            QMessageBox.critical(self, "Error", "Failed to save the image.")

    # ------------------------------------------------------------------ view
    def _fit_view(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        self._fit_view()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_view()

    def closeEvent(self, event):
        self._history_timer.stop()
        QApplication.instance().removeEventFilter(self)
        self.scene.blockSignals(True)
        super().closeEvent(event)


# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow, QScrollArea, QDockWidget > QWidget { background: #17191d; }
        QDockWidget { color: #f4f5f7; font-weight: 600; }
        QTabWidget::pane { border: 1px solid #343943; border-radius: 7px; background: #202329; }
        QTabBar::tab { background: #292d34; color: #bfc4ce; padding: 9px 13px; margin-right: 2px; }
        QTabBar::tab:selected { background: #3b82f6; color: white; }
        QGroupBox { color: #f4f5f7; font-weight: 600; border: 1px solid #3b404a;
                    border-radius: 7px; margin-top: 12px; padding: 14px 8px 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLabel, QCheckBox { color: #d7dae0; }
        QPushButton, QToolButton { background: #343942; color: white; border: 1px solid #454b56;
                                  min-height: 30px; padding: 4px 10px; border-radius: 6px; }
        QPushButton:hover, QToolButton:hover { background: #414752; border-color: #606875; }
        QPushButton:pressed, QToolButton:pressed { background: #292d34; }
        QPushButton:checked { background: #2563eb; border-color: #60a5fa; }
        QPushButton:disabled { background: #292c31; color: #6f747d; border-color: #33363c; }
        QPushButton#primaryButton { background: #168451; border-color: #24a566; font-weight: 700;
                                    min-height: 42px; font-size: 14px; }
        QPushButton#primaryButton:hover { background: #1b9960; }
        QPushButton#dangerButton { color: #ffb4b4; }
        QLineEdit, QSpinBox, QComboBox { min-height: 29px; padding: 3px 7px; background: #15171b;
                                        color: white; border: 1px solid #454b56; border-radius: 5px; }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #60a5fa; }
        QListWidget { background: #15171b; color: white; border: 1px solid #454b56; }
        QStatusBar { color: #c4c7ce; background: #202329; }
    """)
    window = ThumbnailGenerator()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
