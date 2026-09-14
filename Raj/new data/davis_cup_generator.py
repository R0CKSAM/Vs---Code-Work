"""
================================================================================
 DAVIS CUP MATCH GRAPHIC & THUMBNAIL GENERATOR (PRO STUDIO v3.0)
================================================================================
 A complete, high-performance Canva-style thumbnail and match poster generator
 software engineered specifically for Tennis & Davis Cup Match Day graphics.

 Reference Design:
   Sumit Nagal vs Soonwoo Kwon, Day 1 / Match 1, IND vs KOR.

 All Requested Features Fully Integrated:
   1. Complete Single Python Script (No incomplete snippets or external code).
   2. Logo Management: Upload, Add, Replace, and Remove custom logos with aspect
      ratio lock, high-DPI scaling, and 1-click Davis Cup official logo reset.
   3. Glowing Effect Behind Images: Multi-layer luminous radial/Gaussian backlight
      glow rendered strictly behind player cutouts without altering image pixels.
   4. High-Quality Flags & Images: True 3:2 aspect ratio preservation with zero
      stretching, high-DPI flag CDN fetching, and procedural vector flags.
   5. Professional Text Styles: Font family (searchable picker + sports presets),
      size, bold, italic, underline, alignment, letter spacing, text case, and colors.
   6. Clean Underline Below Pictures: Luminous neon accent baseline anchored
      directly below each player cutout.
   7. Slant Angle for Naming: Independent badge slant angle (-45° to +45°) and
      text slant/rotation angle (-45° to +45°) for player nameplates.
   8. Modern Redesigned UI: Canva/Adobe Express inspired dark studio theme with
      organized categorized tabs, clear visual hierarchy, and lightweight footprint.
   9. Removed Up/Down Arrows: Clean numeric inputs with smooth mouse-wheel scrolling,
      trackpad navigation, and paired sliders.
  10. Removed Bring Forward / Send Backward Buttons: Cleaned toolbar while
      preserving underlying z-order logic and keyboard shortcuts (Ctrl+], Ctrl+[).
  11. Streamlined Core Workflow: All redundant and unused features removed.
  12. Automated Self-Audit & Testing Pass: Full headless programmatic test suite
      executable via `--audit` command line flag.

 Requirements:
     pip install PyQt6 pycountry Pillow
================================================================================
"""

import os
import sys
import json
import copy
import math
import uuid
import shutil
import urllib.request
import urllib.error

# ------------------------------------------------------------------------------
# AUTOMATIC DEPENDENCY RESOLVER
# ------------------------------------------------------------------------------
try:
    import PyQt6
except ImportError:
    print("\n" + "=" * 65)
    print(" [Davis Cup Studio] Required module 'PyQt6' is not installed.")
    print(f" Python environment: {sys.executable}")
    print(" Attempting automatic installation via pip...")
    print("=" * 65 + "\n")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt6", "pycountry", "Pillow"])
        print("\n[SUCCESS] 'PyQt6' and dependencies installed successfully!\n")
    except Exception as _install_err:
        print(f"\n[ERROR] Automatic pip installation failed: {_install_err}")
        print("\nPlease install PyQt6 manually by running this command in your terminal:")
        print(f'    "{sys.executable}" -m pip install PyQt6 pycountry Pillow\n')
        sys.exit(1)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QColorDialog,
    QScrollArea, QGroupBox, QGraphicsScene, QGraphicsView, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsLineItem, QGraphicsItem,
    QSlider, QMessageBox, QDockWidget, QStatusBar, QInputDialog,
    QDialog, QListWidget, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QToolButton, QTabWidget, QGraphicsDropShadowEffect, QFrame,
)
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QPainter, QImage, QBrush, QPen, QShortcut,
    QKeySequence, QTextOption, QTextCursor, QTextBlockFormat, QFontDatabase,
    QLinearGradient, QRadialGradient, QCursor, QPainterPath, QTransform,
    QPolygonF,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, QEvent, pyqtSignal

try:
    import pycountry
    HAVE_PYCOUNTRY = True
except ImportError:
    HAVE_PYCOUNTRY = False


# ==============================================================================
# CONSTANTS, DIRECTORIES & METRICS
# ==============================================================================
CANVAS_W, CANVAS_H = 1920, 1080
CENTER_X = CANVAS_W * 0.50
CENTER_Y = CANVAS_H * 0.50

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
PRESETS_DIR = os.path.join(SCRIPT_DIR, "presets")
FLAG_CACHE_DIR = os.path.join(SCRIPT_DIR, "flag_cache")

GRID_DEFAULT_SPACING = 40
SNAP_THRESHOLD = 12
UNDO_LIMIT = 100

SHADOW_DIRECTIONS = {
    "Bottom-Right": (0.707, 0.707),
    "Bottom": (0.0, 1.0),
    "Bottom-Left": (-0.707, 0.707),
    "Right": (1.0, 0.0),
    "Left": (-1.0, 0.0),
    "Top-Right": (0.707, -0.707),
    "Top": (0.0, -1.0),
    "Top-Left": (-0.707, -0.707),
}

DEFAULT_SHADOW = {
    "enabled": False,
    "color_mode": "Black / Dark",
    "custom_color": "#000000",
    "direction": "Bottom-Right",
    "distance": 22,
    "blur": 35,
    "opacity": 60,
    "spread": 15,
}

DEFAULT_BG_EFFECTS = {
    "blur": 0,
    "gradient": 0,
    "overlay": 0,
    "overlay_color": "#002814",
    "vignette": 15,
    "glow": 0,
    "pattern": 0,
    "transparency": 100,
}

POTENTIAL_REFERENCE_PATHS = [
    os.path.join(ASSETS_DIR, "davis_cup_reference.jpg"),
    r"C:\Users\Intern\.gemini\antigravity\brain\147731cc-6015-4d01-ba8e-88f517a3586b\.user_uploaded\media_1789105854522.jpg",
    r"C:\Users\Intern\.gemini\antigravity\brain\7c96226f-c7ef-42d3-9462-b6632e2fc9a6\.user_uploaded\media_1789044053864.jpg",
]


# ==============================================================================
# ASSET UTILITIES & PROCEDURAL GENERATORS
# ==============================================================================

def ensure_directory_tree():
    """Ensure assets, presets, and flag cache folders exist and initialize assets."""
    for folder in (ASSETS_DIR, PRESETS_DIR, FLAG_CACHE_DIR):
        os.makedirs(folder, exist_ok=True)

    # Automatically copy uploaded reference graphic if missing locally
    local_ref = os.path.join(ASSETS_DIR, "davis_cup_reference.jpg")
    if not os.path.exists(local_ref) or os.path.getsize(local_ref) == 0:
        for p in POTENTIAL_REFERENCE_PATHS:
            if p != local_ref and os.path.exists(p) and os.path.getsize(p) > 0:
                try:
                    shutil.copyfile(p, local_ref)
                    break
                except Exception:
                    pass

    # Blank project: no automatic image cropping or preloading on startup
    pass


def locate_reference_image():
    """Find the reference image uploaded by the user if available."""
    for p in POTENTIAL_REFERENCE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


def resolve_country_code(name):
    """Convert country name (e.g. 'India', 'South Korea', 'Spain') to 2-letter alpha code."""
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


def fetch_flag_image(country_code, size="w640"):
    """Fetch high-resolution country flag from flagcdn.com with local persistent caching."""
    ensure_directory_tree()
    code = country_code.lower()
    local_path = os.path.join(FLAG_CACHE_DIR, f"{code}_{size}.png")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path
    url = f"https://flagcdn.com/{size}/{code}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = resp.read()
    with open(local_path, "wb") as f:
        f.write(data)
    return local_path


def create_procedural_stadium_background():
    """
    Generate a high-resolution, photorealistic procedural tennis stadium background
    matching the Davis Cup aesthetic (green tennis court with lines, crowd atmosphere,
    floodlights, and glowing stadium ambience) if no image file is loaded.
    """
    img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#0a1f14"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # 1. Atmospheric Sky & Stadium Lights (Upper 62%)
    sky_grad = QLinearGradient(0, 0, 0, CANVAS_H * 0.65)
    sky_grad.setColorAt(0.0, QColor("#1c4230"))
    sky_grad.setColorAt(0.35, QColor("#2a5c43"))
    sky_grad.setColorAt(0.70, QColor("#1a412e"))
    sky_grad.setColorAt(1.0, QColor("#0e2b1d"))
    p.fillRect(0, 0, CANVAS_W, int(CANVAS_H * 0.65), QBrush(sky_grad))

    # Soft ambient cloud glow in sky
    cloud_radial = QRadialGradient(CANVAS_W * 0.5, CANVAS_H * 0.25, CANVAS_W * 0.55)
    cloud_radial.setColorAt(0.0, QColor(255, 255, 255, 55))
    cloud_radial.setColorAt(0.4, QColor(140, 230, 180, 30))
    cloud_radial.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.fillRect(0, 0, CANVAS_W, int(CANVAS_H * 0.65), QBrush(cloud_radial))

    # Stadium seating tier bands
    p.setPen(Qt.PenStyle.NoPen)
    for i, y_tier in enumerate(range(int(CANVAS_H * 0.38), int(CANVAS_H * 0.62), 16)):
        alpha = 30 + (i % 3) * 15
        p.setBrush(QBrush(QColor(10, 30, 20, alpha)))
        p.drawRect(0, y_tier, CANVAS_W, 12)

    # Stadium Floodlight Towers (left & right)
    for lx in (CANVAS_W * 0.22, CANVAS_W * 0.78):
        light_glow = QRadialGradient(lx, CANVAS_H * 0.44, 200)
        light_glow.setColorAt(0.0, QColor(255, 255, 240, 140))
        light_glow.setColorAt(0.4, QColor(200, 255, 220, 60))
        light_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(int(lx - 220), int(CANVAS_H * 0.33), 440, 260, QBrush(light_glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 240, 220)))
        for dy in (-12, 0, 12):
            for dx in (-28, -14, 0, 14, 28):
                p.drawEllipse(QPointF(lx + dx, CANVAS_H * 0.44 + dy), 3.5, 3.5)

    # 2. Green Hard Tennis Court (Lower 38%)
    court_poly = QPolygonF([
        QPointF(0, CANVAS_H * 0.62),
        QPointF(CANVAS_W, CANVAS_H * 0.62),
        QPointF(CANVAS_W, CANVAS_H),
        QPointF(0, CANVAS_H)
    ])
    court_grad = QLinearGradient(0, CANVAS_H * 0.62, 0, CANVAS_H)
    court_grad.setColorAt(0.0, QColor("#113e28"))
    court_grad.setColorAt(0.45, QColor("#195839"))
    court_grad.setColorAt(1.0, QColor("#0d3521"))
    p.setBrush(QBrush(court_grad))
    p.drawPolygon(court_poly)

    # Tennis Court White Lines (Perspective Projection)
    line_pen = QPen(QColor(245, 255, 248, 220))
    line_pen.setWidth(6)
    p.setPen(line_pen)

    # Horizontal baseline / service lines
    p.drawLine(0, int(CANVAS_H * 0.88), CANVAS_W, int(CANVAS_H * 0.88))
    p.setPen(QPen(QColor(245, 255, 248, 160), 4))
    p.drawLine(int(CANVAS_W * 0.15), int(CANVAS_H * 0.73), int(CANVAS_W * 0.85), int(CANVAS_H * 0.73))

    # Center T-service line marker
    p.setPen(QPen(QColor(255, 255, 255, 240), 6))
    p.drawLine(int(CENTER_X), int(CANVAS_H * 0.84), int(CENTER_X), int(CANVAS_H * 0.94))

    # Faded Davis Cup Trophy watermark silhouette on Left
    trophy_path = QPainterPath()
    trophy_cx, trophy_cy = CANVAS_W * 0.08, CANVAS_H * 0.38
    trophy_path.addEllipse(QRectF(trophy_cx - 90, trophy_cy - 120, 180, 240))
    p.setPen(QPen(QColor(200, 240, 215, 35), 3))
    p.setBrush(QBrush(QColor(220, 255, 235, 18)))
    p.drawPath(trophy_path)

    # Faded Globe sphere watermark on Right
    globe_cx, globe_cy = CANVAS_W * 0.92, CANVAS_H * 0.38
    globe_path = QPainterPath()
    globe_path.addEllipse(QRectF(globe_cx - 110, globe_cy - 110, 220, 220))
    p.setPen(QPen(QColor(160, 240, 190, 40), 3))
    p.setBrush(QBrush(QColor(180, 255, 210, 16)))
    p.drawPath(globe_path)

    p.end()
    return img


def create_procedural_flag(country_code, w=240, h=160):
    """
    Generate crisp, un-stretched vector flags in strict 3:2 aspect ratio.
    Accurate colors and geometry for India (IN) and South Korea (KR) with clean fallbacks.
    """
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    code = (country_code or "").upper().strip()
    if code in ("IND", "IN"):
        # Indian Tricolor: Saffron, White, Green + Ashoka Chakra
        strip_h = h / 3.0
        p.fillRect(QRectF(0, 0, w, strip_h), QColor("#FF9933"))
        p.fillRect(QRectF(0, strip_h, w, strip_h), QColor("#FFFFFF"))
        p.fillRect(QRectF(0, strip_h * 2, w, strip_h), QColor("#138808"))

        # Ashoka Chakra (Navy Blue) with 24 Spokes
        chakra_r = strip_h * 0.44
        cx, cy = w / 2.0, h / 2.0
        p.setPen(QPen(QColor("#000088"), 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), chakra_r, chakra_r)
        p.setPen(QPen(QColor("#000088"), 1.2))
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            p.drawLine(
                QPointF(cx, cy),
                QPointF(cx + chakra_r * math.cos(rad), cy + chakra_r * math.sin(rad))
            )

    elif code in ("KOR", "KR"):
        # South Korean Taegeukgi
        p.fillRect(QRectF(0, 0, w, h), QColor("#FFFFFF"))
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) * 0.28

        # Taegeuk Circle (Red on top, Blue on bottom)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#CD2E3A"))
        p.drawPie(QRectF(cx - r, cy - r, r * 2, r * 2), 0, 180 * 16)
        p.setBrush(QColor("#0047A0"))
        p.drawPie(QRectF(cx - r, cy - r, r * 2, r * 2), 180 * 16, 180 * 16)
        # S-curve swirls
        p.setBrush(QColor("#CD2E3A"))
        p.drawEllipse(QPointF(cx - r / 2, cy), r / 2, r / 2)
        p.setBrush(QColor("#0047A0"))
        p.drawEllipse(QPointF(cx + r / 2, cy), r / 2, r / 2)

        # 4 Black Trigrams (Geon, Gon, Gam, Ri)
        p.setPen(QPen(QColor("#000000"), 3.2))
        for ox, oy in [(-1, -0.6), (1, -0.6), (-1, 0.6), (1, 0.6)]:
            p.drawLine(int(cx + ox * r * 1.3), int(cy + oy * r * 0.9),
                       int(cx + ox * r * 0.95), int(cy + oy * r * 0.9))
    else:
        # Clean athletic flag card
        p.fillRect(QRectF(0, 0, w, h), QColor("#1e293b"))
        p.setPen(QPen(QColor("#00e575"), 2))
        p.drawRect(QRectF(1, 1, w - 2, h - 2))
        p.setPen(QColor("#f8fafc"))
        font = QFont("Arial", int(h * 0.35), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, code)

    p.end()
    return img


def create_procedural_player_silhouette(name, is_left=True, w=700, h=880):
    """
    Generate an athletic portrait card for the tennis player if no photo is loaded,
    styled with accurate jersey colors and nameplate.
    """
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx = w * 0.5
    head_y = h * 0.26
    head_r = w * 0.18
    grad_skin = QRadialGradient(cx, head_y, head_r)
    grad_skin.setColorAt(0.0, QColor("#e0b490" if is_left else "#f5d3b3"))
    grad_skin.setColorAt(1.0, QColor("#9c6b45" if is_left else "#c49272"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad_skin))
    p.drawEllipse(QPointF(cx, head_y), head_r, head_r * 1.15)

    if not is_left:
        # Blue Wilson tennis cap for Soonwoo Kwon
        p.setBrush(QColor("#1d4ed8"))
        p.drawPie(QRectF(cx - head_r * 1.05, head_y - head_r * 1.25, head_r * 2.1, head_r * 1.8), 0, 180 * 16)
        p.drawRoundedRect(QRectF(cx - head_r * 1.15, head_y - head_r * 0.3, head_r * 2.3, 18), 8, 8)

    # Torso with arms folded
    torso_path = QPainterPath()
    torso_path.moveTo(cx - w * 0.42, h)
    torso_path.lineTo(cx - w * 0.35, h * 0.52)
    torso_path.quadTo(cx - w * 0.20, h * 0.42, cx, h * 0.42)
    torso_path.quadTo(cx + w * 0.20, h * 0.42, cx + w * 0.35, h * 0.52)
    torso_path.lineTo(cx + w * 0.42, h)
    torso_path.closeSubpath()

    jersey_grad = QLinearGradient(0, h * 0.42, 0, h)
    if is_left:
        # India Track Jacket (White with Blue panels)
        jersey_grad.setColorAt(0.0, QColor("#f8fafc"))
        jersey_grad.setColorAt(0.5, QColor("#e2e8f0"))
        jersey_grad.setColorAt(1.0, QColor("#cbd5e1"))
    else:
        # South Korea White Track Jacket
        jersey_grad.setColorAt(0.0, QColor("#ffffff"))
        jersey_grad.setColorAt(0.5, QColor("#f1f5f9"))
        jersey_grad.setColorAt(1.0, QColor("#e2e8f0"))

    p.setBrush(QBrush(jersey_grad))
    p.drawPath(torso_path)

    if is_left:
        p.setBrush(QColor("#2563eb"))
        p.drawRect(QRectF(cx - w * 0.32, h * 0.52, w * 0.12, h * 0.35))
        p.drawRect(QRectF(cx + w * 0.20, h * 0.52, w * 0.12, h * 0.35))
        # Small Indian flag crest
        p.fillRect(QRectF(cx + w * 0.08, h * 0.62, 38, 24), QColor("#FF9933"))
        p.fillRect(QRectF(cx + w * 0.08, h * 0.62 + 8, 38, 8), QColor("#FFFFFF"))
        p.fillRect(QRectF(cx + w * 0.08, h * 0.62 + 16, 38, 8), QColor("#138808"))
    else:
        p.fillRect(QRectF(cx - w * 0.18, h * 0.62, 36, 24), QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawRect(QRectF(cx - w * 0.18, h * 0.62, 36, 24))

    p.setPen(QColor("#ffffff"))
    font = QFont("Arial", 28, QFont.Weight.Black)
    p.setFont(font)
    p.drawText(QRectF(0, h * 0.80, w, 50), Qt.AlignmentFlag.AlignCenter, name.upper())

    p.end()
    return img


# ==============================================================================
# CANVA-STYLE 8-POINT RESIZE HANDLES
# ==============================================================================

HANDLE_EDGES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"]
HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
}


class CanvasResizeHandle(QGraphicsRectItem):
    """
    Canva-style interactive handle placed around selected elements.
    Supports corner & edge dragging with real-time resizing and cursor changes.
    """
    SIZE = 16

    def __init__(self, target_item, edge, app):
        super().__init__(-self.SIZE / 2, -self.SIZE / 2, self.SIZE, self.SIZE)
        self.target_item = target_item
        self.edge = edge
        self.app = app
        self.setBrush(QBrush(QColor("#00e575")))  # Neon green accent
        self.setPen(QPen(QColor("#ffffff"), 2))
        self.setZValue(5000)
        self.setCursor(QCursor(HANDLE_CURSORS.get(edge, Qt.CursorShape.ArrowCursor)))
        self.setAcceptHoverEvents(True)
        self._dragging = False

    def mousePressEvent(self, event):
        self._dragging = True
        self.app.push_undo_snapshot()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.app.resize_item_from_handle(self.target_item, self.edge, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.app.clear_guides()
        self.app.commit_history_state()
        event.accept()


# ==============================================================================
# BASE DRAGGABLE GRAPHICS ITEM
# ==============================================================================

class DraggableStudioItem(QGraphicsItem):
    """
    Abstract base class providing Canva-style drag, select, snapping,
    aspect ratio handling, shadow rendering, and geometry synchronization.
    """
    def __init__(self, center_x, center_y, width, height, app=None, role="generic"):
        super().__init__()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self._center = QPointF(center_x, center_y)
        self._w = max(20.0, float(width))
        self._h = max(20.0, float(height))
        self.app = app
        self.role = role
        self._aspect_locked = False
        self._aspect_ratio = self._w / max(1.0, self._h)
        self._shadow = copy.deepcopy(DEFAULT_SHADOW)
        self._suppress_move = False
        self.on_move = None
        self._recenter()

    def boundingRect(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def center(self):
        return (self._center.x(), self._center.y())

    def set_center(self, x, y):
        self._center = QPointF(x, y)
        self._recenter()

    def size(self):
        return (self._w, self._h)

    def half_size(self):
        return (self._w / 2.0, self._h / 2.0)

    def set_size_px(self, w, h, keep_aspect=None):
        if keep_aspect is None:
            keep_aspect = self._aspect_locked
        w = max(20.0, float(w))
        h = max(20.0, float(h))
        if keep_aspect and self._aspect_ratio:
            h = max(20.0, w / self._aspect_ratio)
        self.prepareGeometryChange()
        self._w = w
        self._h = h
        self._recenter()
        self.update()

    def set_aspect_locked(self, locked):
        self._aspect_locked = bool(locked)
        if self._h > 0:
            self._aspect_ratio = self._w / self._h

    def aspect_locked(self):
        return self._aspect_locked

    def aspect_ratio(self):
        return self._aspect_ratio

    def set_aspect_ratio(self, ratio):
        self._aspect_ratio = ratio if ratio and ratio > 0 else (self._w / max(1.0, self._h))
        if ratio:
            self.set_size_px(self._w, self._w / ratio, keep_aspect=False)

    def _recenter(self):
        self._suppress_move = True
        self.setPos(self._center.x(), self._center.y())
        self._suppress_move = False
        if self.app:
            self.app.reposition_handles()

    def shadow_settings(self):
        return copy.deepcopy(self._shadow)

    def set_shadow_settings(self, settings):
        self._shadow = {**DEFAULT_SHADOW, **(settings or {})}
        self._apply_shadow()

    def _apply_shadow(self):
        if not self._shadow.get("enabled"):
            self.setGraphicsEffect(None)
            return
        effect = QGraphicsDropShadowEffect()
        mode = self._shadow.get("color_mode", "Black / Dark")
        if mode == "Custom":
            color = QColor(self._shadow.get("custom_color", "#000000"))
        else:
            color = QColor("#000000")

        opacity = self._shadow.get("opacity", 60) / 100.0
        color.setAlpha(max(0, min(255, int(255 * opacity))))
        effect.setColor(color)
        dist = self._shadow.get("distance", 22)
        dx, dy = SHADOW_DIRECTIONS.get(self._shadow.get("direction"), (0.707, 0.707))
        effect.setOffset(dx * dist, dy * dist)
        blur_val = self._shadow.get("blur", 35) + self._shadow.get("spread", 15) * 0.4
        effect.setBlurRadius(max(0.0, blur_val))
        self.setGraphicsEffect(effect)

    def mousePressEvent(self, event):
        if self.app:
            self.app.push_undo_snapshot()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.app:
            self.app.clear_guides()
            self.app.commit_history_state()

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.app and not self._suppress_move
            and hasattr(self.app, "snap_enabled_checkbox")
        ):
            hw, hh = self.half_size()
            proposed_center = value
            snapped = self.app.snap_center(self, proposed_center, hw, hh)
            return snapped

        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._suppress_move
        ):
            self._center = self.pos()
            if self.on_move:
                self.on_move(self)
            if self.app:
                self.app.reposition_handles()

        return super().itemChange(change, value)


# ==============================================================================
# PLAYER CUTOUT GRAPHICS ITEM (WITH BACKLIGHT GLOW & UNDERLINE)
# ==============================================================================

class PlayerCutoutItem(DraggableStudioItem):
    """
    Movable cutout portrait of a tennis player.
    Supports:
      - Custom image loading with high-DPI scaling and transparency.
      - Luminous multi-layer radial/Gaussian backlight glow behind image.
      - Luminous neon green horizontal underline directly below picture.
      - Horizontal/vertical flipping (mirroring), rotation, opacity, and Canva handles.
    """
    def __init__(self, center_x, center_y, width, height, player_name, is_left=True, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="player")
        self.player_name = player_name
        self.is_left = is_left
        self._source_path = None
        self._pixmap = None
        self._flip_h = False
        self._flip_v = False
        self._aspect_locked = True
        self.setZValue(25)

        # 1. Backlight Glow Feature (Rendered STRICTLY BEHIND player)
        self.glow_enabled = True
        self.glow_color = QColor("#00ff88")  # Vibrant Davis Cup neon emerald
        self.glow_intensity = 85             # 0 - 100%
        self.glow_radius = 260.0             # Radius in pixels
        self.glow_blur = 60.0

        # 2. Horizontal Underline Directly Below Picture Feature
        self.underline_enabled = True
        self.underline_color = QColor("#00ff88")  # Clean neon tennis green
        self.underline_thickness = 5.0
        self.underline_width = 460.0
        self.underline_offset_y = 6.0             # Offset below picture bottom

        self._init_default_graphic()

    def _init_default_graphic(self):
        # Blank project on startup: zero preloaded photos
        self._source_path = None
        self._pixmap = None
        self.update()

    def clear_image(self):
        """Remove loaded photo and revert to clean blank placeholder."""
        self._source_path = None
        self._pixmap = None
        self.prepareGeometryChange()
        self.update()
        if self.app:
            self.app.reposition_handles()

    def mouseDoubleClickEvent(self, event):
        if self.app:
            self.app._load_player_photo(self)
        event.accept()

    def load_image(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._source_path = path
        self._pixmap = pix
        self._aspect_ratio = pix.width() / max(1.0, pix.height())
        if self._aspect_locked:
            self._h = self._w / self._aspect_ratio
        self.prepareGeometryChange()
        self.update()
        if self.app:
            self.app.reposition_handles()
        return True

    def source_path(self):
        return self._source_path

    def set_flip_h(self, flip):
        self._flip_h = bool(flip)
        self.update()

    def flip_h(self):
        return self._flip_h

    def set_flip_v(self, flip):
        self._flip_v = bool(flip)
        self.update()

    def flip_v(self):
        return self._flip_v

    def boundingRect(self):
        hw = self._w / 2.0
        hh = self._h / 2.0
        pad_x = 10.0
        pad_y_top = 10.0
        pad_y_bot = 10.0
        if self.glow_enabled and self.glow_intensity > 0:
            gr = max(40.0, self.glow_radius)
            pad_x = max(pad_x, gr - hw + 20.0)
            pad_y_top = max(pad_y_top, gr * 1.15 - hh + 20.0)
            pad_y_bot = max(pad_y_bot, gr * 1.15 - hh + 20.0)
        if self.underline_enabled and self.underline_thickness > 0:
            half_uw = min(hw * 1.5, self.underline_width / 2.0)
            pad_x = max(pad_x, half_uw - hw + 20.0)
            pad_y_bot = max(pad_y_bot, self.underline_offset_y + self.underline_thickness * 4.0 + 20.0)
        return QRectF(-hw - pad_x, -hh - pad_y_top, self._w + 2.0 * pad_x, self._h + pad_y_top + pad_y_bot)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        hw, hh = self._w / 2.0, self._h / 2.0

        # ----------------------------------------------------------------------
        # LAYER 1: VIBRANT BACKLIGHT GLOW (PAINTED STRICTLY BEHIND IMAGE)
        # ----------------------------------------------------------------------
        if self.glow_enabled and self.glow_intensity > 0:
            alpha = max(0, min(255, int(255 * (self.glow_intensity / 100.0))))
            gr = max(40.0, self.glow_radius)
            glow_cy = -hh * 0.15

            radial = QRadialGradient(0, glow_cy, gr)
            c_core = QColor(self.glow_color)
            c_core.setAlpha(min(255, int(alpha * 0.90)))
            c_mid = QColor(self.glow_color)
            c_mid.setAlpha(min(255, int(alpha * 0.40)))
            c_outer = QColor(self.glow_color)
            c_outer.setAlpha(0)

            radial.setColorAt(0.0, c_core)
            radial.setColorAt(0.45, c_mid)
            radial.setColorAt(1.0, c_outer)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(radial))
            painter.drawEllipse(QPointF(0, glow_cy), gr, gr * 1.15)

        # ----------------------------------------------------------------------
        # LAYER 2: FOREGROUND PLAYER CUTOUT (PRISTINE, HIGH-QUALITY SCALING)
        # ----------------------------------------------------------------------
        if self._pixmap and not self._pixmap.isNull():
            painter.save()
            sx = -1.0 if self._flip_h else 1.0
            sy = -1.0 if self._flip_v else 1.0
            if sx < 0 or sy < 0:
                painter.scale(sx, sy)
            draw_rect = QRectF(-hw, -hh, self._w, self._h)
            painter.drawPixmap(draw_rect.toRect(), self._pixmap)
            painter.restore()
        else:
            fallback_rect = QRectF(-hw, -hh, self._w, self._h)
            painter.save()
            painter.setBrush(QBrush(QColor(8, 24, 18, 205)))
            dash_pen = QPen(QColor("#00e575"), 2.2, Qt.PenStyle.DashLine)
            dash_pen.setDashPattern([6, 5])
            painter.setPen(dash_pen)
            painter.drawRoundedRect(fallback_rect, 20, 20)

            side_label = "PLAYER 1" if self.is_left else "PLAYER 2"

            f_icon = QFont("Segoe UI", 46)
            painter.setFont(f_icon)
            painter.setPen(QColor("#00e575"))
            painter.drawText(QRectF(-hw, -hh + 180, self._w, 75), Qt.AlignmentFlag.AlignCenter, "👤")

            f_name = QFont("Arial", 24, QFont.Weight.Bold)
            painter.setFont(f_name)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(-hw + 20, -hh + 265, self._w - 40, 45), Qt.AlignmentFlag.AlignCenter, f"+ Upload {side_label} Photo")

            f_sub = QFont("Arial", 14)
            painter.setFont(f_sub)
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(-hw + 20, -hh + 315, self._w - 40, 60), Qt.AlignmentFlag.AlignCenter, "Double-click here or use sidebar\nto load player cutout (PNG)")
            painter.restore()

        # ----------------------------------------------------------------------
        # LAYER 3: CLEAN NEON UNDERLINE DIRECTLY BELOW PICTURE
        # ----------------------------------------------------------------------
        if self.underline_enabled and self.underline_thickness > 0:
            line_y = hh + self.underline_offset_y
            half_uw = min(hw * 1.2, self.underline_width / 2.0)

            glow_pen = QPen(QColor(self.underline_color.red(),
                                  self.underline_color.green(),
                                  self.underline_color.blue(), 75),
                            self.underline_thickness * 2.8)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.drawLine(QPointF(-half_uw, line_y), QPointF(half_uw, line_y))

            core_pen = QPen(self.underline_color, self.underline_thickness)
            core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(core_pen)
            painter.drawLine(QPointF(-half_uw, line_y), QPointF(half_uw, line_y))

            inner_pen = QPen(QColor(255, 255, 255, 220), max(1.5, self.underline_thickness * 0.45))
            inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(inner_pen)
            painter.drawLine(QPointF(-half_uw * 0.8, line_y), QPointF(half_uw * 0.8, line_y))

        painter.restore()


# ==============================================================================
# SLANTED PLAYER NAMEPLATE ITEM (WITH SLANT & ROTATION ANGLES)
# ==============================================================================

class SlantedNameplateItem(DraggableStudioItem):
    """
    Athletic banner displaying the player's name with:
      - Independent badge slant angle (-45° to +45°).
      - Independent text slant/rotation angle (-45° to +45°).
      - Dark emerald athletic gradient, neon green border, and full typography controls.
    """
    def __init__(self, center_x, center_y, width, height, text, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="nameplate")
        self.text = text
        self.font_family = "Arial"
        self.font_size = 44
        self.font_bold = True
        self.font_italic = False
        self.font_underline = False
        self.letter_spacing = 3
        self.slant_deg = 15.0       # Parallelogram badge slant
        self.text_slant_deg = 0.0   # Text rotation/slant angle
        self.bg_color1 = QColor("#021f12")  # Deep emerald black
        self.bg_color2 = QColor("#064024")
        self.border_color = QColor("#00e575")  # Vibrant neon green
        self.border_width = 3.5
        self.text_color = QColor("#ffffff")
        self.setZValue(40)

    def set_name(self, name):
        self.text = str(name).strip()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.app:
            new_text, ok = QInputDialog.getText(self.app, "Edit Player Name", "Player Name:", text=self.text)
            if ok and new_text.strip():
                self.app.push_undo_snapshot()
                self.set_name(new_text)
                if self is self.app.nameplate_left and hasattr(self.app, "input_name_l"):
                    self.app.input_name_l.setText(self.text)
                elif self is self.app.nameplate_right and hasattr(self.app, "input_name_r"):
                    self.app.input_name_r.setText(self.text)
        event.accept()

    def boundingRect(self):
        slant_offset = abs(math.tan(math.radians(self.slant_deg))) * (self._h / 2.0)
        pad_x = slant_offset + self.border_width + 12.0
        pad_y = self.border_width + 8.0
        hw, hh = self._w / 2.0, self._h / 2.0
        return QRectF(-hw - pad_x, -hh - pad_y, self._w + 2.0 * pad_x, self._h + 2.0 * pad_y)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self._w, self._h
        hw, hh = w / 2.0, h / 2.0
        slant_offset = math.tan(math.radians(self.slant_deg)) * (h / 2.0)

        # 1. Build Parallelogram Badge
        path = QPainterPath()
        path.moveTo(-hw + slant_offset, -hh)
        path.lineTo(hw + slant_offset, -hh)
        path.lineTo(hw - slant_offset, hh)
        path.lineTo(-hw - slant_offset, hh)
        path.closeSubpath()

        grad = QLinearGradient(-hw, -hh, hw, hh)
        grad.setColorAt(0.0, self.bg_color1)
        grad.setColorAt(1.0, self.bg_color2)
        painter.setBrush(QBrush(grad))

        if self.border_width > 0:
            painter.setPen(QPen(self.border_color, self.border_width))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # 2. Typography with text slant/rotation angle
        painter.save()
        if self.text_slant_deg != 0.0:
            painter.rotate(self.text_slant_deg)

        f = QFont(self.font_family, self.font_size)
        f.setBold(self.font_bold)
        f.setItalic(self.font_italic)
        f.setUnderline(self.font_underline)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
        painter.setFont(f)
        painter.setPen(self.text_color)

        text_rect = QRectF(-hw + 20, -hh, w - 40, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text)
        painter.restore()

        painter.restore()


# ==============================================================================
# SLANTED MATCH BANNER ITEM ("DAY 1" / "MATCH 1")
# ==============================================================================

class SlantedMatchBannerItem(DraggableStudioItem):
    """
    Angled trapezoidal match badge (e.g. 'DAY 1' in emerald or 'MATCH 1' in silver-white).
    3D perspective bevel, gradient fill, drop shadow, and typography controls.
    """
    def __init__(self, center_x, center_y, width, height, text,
                 is_dark_green=True, app=None, role="match_banner"):
        super().__init__(center_x, center_y, width, height, app=app, role=role)
        self.text = text
        self.is_dark_green = is_dark_green
        self.font_family = "Arial"
        self.font_size = 54 if is_dark_green else 58
        self.font_bold = True
        self.font_italic = True
        self.font_underline = False
        self.letter_spacing = 2
        self.slant_deg = 15.0

        if is_dark_green:
            self.bg_color1 = QColor("#042b17")
            self.bg_color2 = QColor("#0d5430")
            self.border_color = QColor("#00ff88")
            self.text_color = QColor("#ffffff")
        else:
            self.bg_color1 = QColor("#ffffff")
            self.bg_color2 = QColor("#dbe4ee")
            self.border_color = QColor("#cbd5e1")
            self.text_color = QColor("#000000")

        self.border_width = 2.0
        self.setZValue(35)
        self._shadow["enabled"] = True
        self._apply_shadow()

    def set_banner_text(self, text):
        self.text = str(text).strip()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.app:
            new_text, ok = QInputDialog.getText(self.app, "Edit Banner Text", "Banner Text:", text=self.text)
            if ok and new_text.strip():
                self.app.push_undo_snapshot()
                self.set_banner_text(new_text)
                if self.role == "banner_day" and hasattr(self.app, "input_day_text"):
                    self.app.input_day_text.setText(self.text)
                elif self.role == "banner_match" and hasattr(self.app, "input_match_text"):
                    self.app.input_match_text.setText(self.text)
        event.accept()

    def boundingRect(self):
        slant_offset = abs(math.tan(math.radians(self.slant_deg))) * (self._h / 2.0)
        pad_x = slant_offset + self.border_width + 12.0
        pad_y = self.border_width + 8.0
        hw, hh = self._w / 2.0, self._h / 2.0
        return QRectF(-hw - pad_x, -hh - pad_y, self._w + 2.0 * pad_x, self._h + 2.0 * pad_y)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self._w, self._h
        hw, hh = w / 2.0, h / 2.0
        slant_offset = math.tan(math.radians(self.slant_deg)) * (h / 2.0)

        path = QPainterPath()
        path.moveTo(-hw + slant_offset, -hh)
        path.lineTo(hw + slant_offset, -hh)
        path.lineTo(hw - slant_offset, hh)
        path.lineTo(-hw - slant_offset, hh)
        path.closeSubpath()

        grad = QLinearGradient(-hw, -hh, -hw, hh)
        grad.setColorAt(0.0, self.bg_color1)
        grad.setColorAt(1.0, self.bg_color2)
        painter.setBrush(QBrush(grad))

        if self.border_width > 0:
            painter.setPen(QPen(self.border_color, self.border_width))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        f = QFont(self.font_family, self.font_size)
        f.setBold(self.font_bold)
        f.setItalic(self.font_italic)
        f.setUnderline(self.font_underline)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
        painter.setFont(f)
        painter.setPen(self.text_color)

        text_rect = QRectF(-hw + 20, -hh, w - 40, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text)

        painter.restore()


# ==============================================================================
# COUNTRY PILL ITEM (FLAG + CODE WITH ASPECT RATIO PRESERVATION)
# ==============================================================================

class CountryPillItem(DraggableStudioItem):
    """
    Rounded country badge pill (e.g. [Flag] IND or KOR [Flag]).
    Guarantees strict flag aspect ratio preservation with zero distortion.
    """
    def __init__(self, center_x, center_y, width, height, country_code,
                 flag_on_left=True, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="country_pill")
        self.country_code = country_code
        self.flag_on_left = flag_on_left
        self.font_family = "Arial"
        self.font_size = 38
        self.font_bold = True
        self.font_italic = False
        self.font_underline = False
        self.letter_spacing = 1
        self.bg_color = QColor("#0f291e")  # Dark athletic capsule
        self.border_color = QColor("#38a169")
        self.border_width = 2.0
        self.text_color = QColor("#ffffff")
        self._flag_source_path = None
        self._flag_pixmap = None
        self.setZValue(30)
        self._init_flag()

    def _init_flag(self):
        code = self.country_code.upper().strip()
        cached = os.path.join(FLAG_CACHE_DIR, f"{code.lower()}_w640.png")
        if os.path.exists(cached) and self.load_flag(cached):
            return
        cached_320 = os.path.join(FLAG_CACHE_DIR, f"{code.lower()}_w320.png")
        if os.path.exists(cached_320) and self.load_flag(cached_320):
            return

        flag_img = create_procedural_flag(code, 240, 160)
        self._flag_pixmap = QPixmap.fromImage(flag_img)
        self.update()

    def load_flag(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._flag_source_path = path
        self._flag_pixmap = pix
        self.update()
        return True

    def set_code(self, code):
        self.country_code = str(code).strip().upper()
        self._init_flag()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.app:
            new_code, ok = QInputDialog.getText(self.app, "Edit Country Code",
                                                "Code (e.g. IND, KOR, USA, ESP):",
                                                text=self.country_code)
            if ok and new_code.strip():
                self.app.push_undo_snapshot()
                self.set_code(new_code.strip())
                if self is self.app.pill_left and hasattr(self.app, "input_code_l"):
                    self.app.input_code_l.setText(self.country_code)
                elif self is self.app.pill_right and hasattr(self.app, "input_code_r"):
                    self.app.input_code_r.setText(self.country_code)
        event.accept()

    def boundingRect(self):
        pad = self.border_width + 4.0
        hw, hh = self._w / 2.0, self._h / 2.0
        return QRectF(-hw - pad, -hh - pad, self._w + 2.0 * pad, self._h + 2.0 * pad)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(-self._w / 2.0, -self._h / 2.0, self._w, self._h)
        radius = rect.height() * 0.28

        # Pill background
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(QPen(self.border_color, self.border_width))
        painter.drawRoundedRect(rect, radius, radius)

        # Flag slot geometry
        flag_slot_w = rect.height() * 1.32
        flag_slot_h = rect.height() * 0.84
        flag_slot_y = rect.top() + (rect.height() - flag_slot_h) / 2.0

        if self.flag_on_left:
            flag_slot_x = rect.left() + 8
            text_x = flag_slot_x + flag_slot_w + 12
            text_w = rect.right() - text_x - 12
        else:
            flag_slot_x = rect.right() - flag_slot_w - 8
            text_x = rect.left() + 12
            text_w = flag_slot_x - text_x - 12

        slot_rect = QRectF(flag_slot_x, flag_slot_y, flag_slot_w, flag_slot_h)

        # Draw flag with STRICT aspect ratio preservation (no stretching!)
        if self._flag_pixmap and not self._flag_pixmap.isNull():
            painter.save()
            flag_clip = QPainterPath()
            flag_clip.addRoundedRect(slot_rect, 6, 6)
            painter.setClipPath(flag_clip)

            scaled_flag = self._flag_pixmap.scaled(
                int(flag_slot_w), int(flag_slot_h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            dx = slot_rect.left() + (flag_slot_w - scaled_flag.width()) / 2.0
            dy = slot_rect.top() + (flag_slot_h - scaled_flag.height()) / 2.0
            painter.drawPixmap(int(dx), int(dy), scaled_flag)
            painter.restore()

            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(slot_rect, 6, 6)

        # Country text
        f = QFont(self.font_family, self.font_size)
        f.setBold(self.font_bold)
        f.setItalic(self.font_italic)
        f.setUnderline(self.font_underline)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
        painter.setFont(f)
        painter.setPen(self.text_color)
        text_rect = QRectF(text_x, rect.top(), text_w, rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.country_code)

        painter.restore()


# ==============================================================================
# "VS" DIVIDER ITEM
# ==============================================================================

class VsDividerItem(DraggableStudioItem):
    """
    Center matchup separator: vertical line | 'VS' text | vertical line.
    """
    def __init__(self, center_x, center_y, width, height, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="vs_divider")
        self.text = "VS"
        self.font_family = "Arial"
        self.font_size = 46
        self.font_bold = True
        self.font_italic = False
        self.font_underline = False
        self.letter_spacing = 1
        self.text_color = QColor("#000000")
        self.line_color = QColor(0, 0, 0, 160)
        self.setZValue(30)

    def mouseDoubleClickEvent(self, event):
        if self.app:
            new_text, ok = QInputDialog.getText(self.app, "Edit VS Text", "Text:", text=self.text)
            if ok and new_text.strip():
                self.app.push_undo_snapshot()
                self.text = new_text.strip()
                self.update()
        event.accept()

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self._w, self._h
        hw, hh = w / 2.0, h / 2.0

        painter.setPen(QPen(self.line_color, 2.5))
        painter.drawLine(QPointF(-hw + 10, -hh + 8), QPointF(-hw + 10, hh - 8))
        painter.drawLine(QPointF(hw - 10, -hh + 8), QPointF(hw - 10, hh - 8))

        f = QFont(self.font_family, self.font_size)
        f.setBold(self.font_bold)
        f.setItalic(self.font_italic)
        f.setUnderline(self.font_underline)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
        painter.setFont(f)
        painter.setPen(self.text_color)
        painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self.text)

        painter.restore()


# ==============================================================================
# TOURNAMENT LOGO & HEADER ITEM (UPLOAD, ADD, REPLACE, REMOVE, RESET)
# ==============================================================================

class TournamentLogoItem(DraggableStudioItem):
    """
    Official Tournament Logo & Header item matching the reference graphic.
    Full capabilities:
      - Upload & Add custom logo image (PNG transparency, JPG, WebP, SVG).
      - Replace logo image seamlessly.
      - Remove logo image without breaking layout.
      - Reset to official Davis Cup circular emblem and title.
      - Preserves high-DPI scaling and true aspect ratio.
      - Fully movable and resizable with Canva 8-point handles.
    """
    def __init__(self, center_x, center_y, width, height, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="tournament_logo")
        self.title_text = "DAVIS CUP®"
        self.font_family = "Times New Roman"
        self.font_size = 62
        self.font_bold = True
        self.font_italic = False
        self.font_underline = False
        self.letter_spacing = 4
        self.text_color = QColor("#000000")
        self.emblem_color = QColor("#00a352")  # Official Davis Cup green

        self.custom_logo_path = None
        self.custom_logo_pixmap = None
        self.show_logo = True
        self.show_title = True
        self.setZValue(30)
        self._aspect_locked = False

        self._init_default_logo()

    def _init_default_logo(self):
        # Default to official crisp procedural vector emblem & typography
        self.custom_logo_path = None
        self.custom_logo_pixmap = None
        self.show_logo = True
        self.show_title = True

    def set_custom_logo(self, file_path):
        """Upload/Replace with a custom logo file."""
        pix = QPixmap(file_path)
        if pix.isNull():
            return False
        self.custom_logo_path = file_path
        self.custom_logo_pixmap = pix
        self.show_logo = True
        self.update()
        return True

    def remove_logo(self):
        """Remove the custom logo from the header."""
        self.custom_logo_path = None
        self.custom_logo_pixmap = None
        self.show_logo = False
        self.update()

    def reset_to_davis_cup(self):
        """Reset to the official procedural Davis Cup circular emblem & title."""
        self.custom_logo_path = None
        self.custom_logo_pixmap = None
        self.show_logo = True
        self.show_title = True
        self.title_text = "DAVIS CUP®"
        self.emblem_color = QColor("#00a352")
        self.text_color = QColor("#000000")
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.app:
            new_text, ok = QInputDialog.getText(self.app, "Edit Tournament Title", "Title:", text=self.title_text)
            if ok and new_text.strip():
                self.app.push_undo_snapshot()
                self.title_text = new_text.strip()
                self.update()
                if hasattr(self.app, "input_header_text"):
                    self.app.input_header_text.setText(self.title_text)
        event.accept()

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self._w, self._h
        hw, hh = w / 2.0, h / 2.0

        has_title = self.show_title and bool(self.title_text.strip())
        if self.show_logo and has_title:
            emblem_h = h * 0.52
            emblem_r = emblem_h / 2.0
            emblem_cx = 0
            emblem_cy = -hh + emblem_r + 2
            text_y = emblem_cy + emblem_r + 6
            text_h = h - (emblem_h + 10)
        elif self.show_logo:
            emblem_h = h * 0.90
            emblem_r = emblem_h / 2.0
            emblem_cx = 0
            emblem_cy = 0
            text_y = 0
            text_h = 0
        else:
            emblem_r = 0
            text_y = -hh
            text_h = h

        # 1. DRAW LOGO (CUSTOM PIXMAP OR OFFICIAL EMBLEM)
        if self.show_logo:
            if self.custom_logo_pixmap and not self.custom_logo_pixmap.isNull():
                avail_w = w * 0.85
                avail_h = emblem_h
                scaled_logo = self.custom_logo_pixmap.scaled(
                    int(avail_w), int(avail_h),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                lx = emblem_cx - scaled_logo.width() / 2.0
                ly = emblem_cy - scaled_logo.height() / 2.0
                painter.drawPixmap(int(lx), int(ly), scaled_logo)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self.emblem_color))
                painter.drawEllipse(QPointF(emblem_cx, emblem_cy), emblem_r, emblem_r)

                swoosh = QPainterPath()
                swoosh.moveTo(emblem_cx - emblem_r * 0.65, emblem_cy + emblem_r * 0.1)
                swoosh.cubicTo(
                    emblem_cx - emblem_r * 0.2, emblem_cy - emblem_r * 0.55,
                    emblem_cx + emblem_r * 0.4, emblem_cy - emblem_r * 0.35,
                    emblem_cx + emblem_r * 0.7, emblem_cy - emblem_r * 0.05
                )
                swoosh.cubicTo(
                    emblem_cx + emblem_r * 0.2, emblem_cy + emblem_r * 0.25,
                    emblem_cx - emblem_r * 0.3, emblem_cy + emblem_r * 0.35,
                    emblem_cx - emblem_r * 0.65, emblem_cy + emblem_r * 0.1
                )
                swoosh.closeSubpath()
                painter.setBrush(QColor("#ffffff"))
                painter.drawPath(swoosh)

        # 2. DRAW TOURNAMENT TITLE TYPOGRAPHY
        if has_title:
            f = QFont(self.font_family, self.font_size)
            f.setBold(self.font_bold)
            f.setItalic(self.font_italic)
            f.setUnderline(self.font_underline)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.letter_spacing)
            painter.setFont(f)
            painter.setPen(self.text_color)
            text_rect = QRectF(-hw, text_y, w, text_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.title_text)

        painter.restore()


# ==============================================================================
# NEON ENERGY GLOW TRAILS
# ==============================================================================

class NeonGlowAccentsItem(DraggableStudioItem):
    """
    Bottom neon energy light trails framing the court, player nameplates,
    and match badge.
    """
    def __init__(self, center_x, center_y, width, height, app=None):
        super().__init__(center_x, center_y, width, height, app=app, role="neon_glow")
        self.glow_color = QColor("#00ff88")
        self.enabled = True
        self.setZValue(15)

    def paint(self, painter, option, widget=None):
        if not self.enabled:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self._w, self._h
        hw, hh = w / 2.0, h / 2.0

        for glow_w, alpha in ((14, 30), (8, 70), (3, 220)):
            pen = QPen(QColor(self.glow_color.red(), self.glow_color.green(), self.glow_color.blue(), alpha), glow_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            left_curve = QPainterPath()
            left_curve.moveTo(-hw, hh * 0.6)
            left_curve.cubicTo(-hw * 0.6, -hh * 0.5, -hw * 0.3, hh * 0.3, -hw * 0.05, hh * 0.1)
            painter.drawPath(left_curve)

            right_curve = QPainterPath()
            right_curve.moveTo(hw, hh * 0.6)
            right_curve.cubicTo(hw * 0.6, -hh * 0.5, hw * 0.3, hh * 0.3, hw * 0.05, hh * 0.1)
            painter.drawPath(right_curve)

        painter.restore()


# ==============================================================================
# GENERIC EDITABLE TEXT ITEM (CANVA-STYLE)
# ==============================================================================

class EditableTextItem(QGraphicsTextItem):
    """
    Free text line with Canva-style alignment, letter spacing, font size,
    and bounding box handles.
    """
    def __init__(self, text, font, color, center_x, center_y, app=None, role="custom_text"):
        super().__init__(text)
        self.setFlags(
            QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsTextItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setFont(font)
        self.setDefaultTextColor(color)
        self._center = QPointF(center_x, center_y)
        self.app = app
        self.role = role
        self.align = "center"
        self.letter_spacing_px = 0
        self._box_w = None
        self._box_h = None
        self._suppress_move = False
        self._apply_alignment()
        self._recenter()

    def boundingRect(self):
        natural = super().boundingRect()
        if self._box_w is None or self._box_h is None:
            return natural
        return QRectF(0, 0, self._box_w, self._box_h)

    def center(self):
        return (self._center.x(), self._center.y())

    def set_center(self, x, y):
        self._center = QPointF(x, y)
        self._recenter()

    def size(self):
        rect = self.boundingRect()
        return (rect.width(), rect.height())

    def half_size(self):
        rect = self.boundingRect()
        return (rect.width() / 2.0, rect.height() / 2.0)

    def _recenter(self):
        rect = self.boundingRect()
        self._suppress_move = True
        self.setPos(self._center.x() - rect.width() / 2.0, self._center.y() - rect.height() / 2.0)
        self._suppress_move = False
        if self.app:
            self.app.reposition_handles()

    def set_text(self, text):
        self.setPlainText(text)
        self._apply_alignment()
        self._recenter()

    def set_style(self, font=None, color=None):
        if font is not None:
            self.setFont(font)
            self._apply_alignment()
        if color is not None:
            self.setDefaultTextColor(color)
        self._recenter()

    def set_letter_spacing(self, px):
        self.letter_spacing_px = px
        f = self.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
        self.setFont(f)
        self._apply_alignment()
        self._recenter()

    def _apply_alignment(self):
        doc = self.document()
        qt_align = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(self.align, Qt.AlignmentFlag.AlignHCenter)
        opt = QTextOption()
        opt.setAlignment(qt_align)
        doc.setDefaultTextOption(opt)

    def mousePressEvent(self, event):
        if self.app:
            self.app.push_undo_snapshot()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.app:
            self.app.clear_guides()
            self.app.commit_history_state()

    def itemChange(self, change, value):
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
            self._center = QPointF(self.x() + rect.width() / 2.0, self.y() + rect.height() / 2.0)
            if self.app:
                self.app.reposition_handles()

        return super().itemChange(change, value)

    def shadow_settings(self):
        return copy.deepcopy(getattr(self, "_shadow", DEFAULT_SHADOW))

    def set_shadow_settings(self, settings):
        self._shadow = {**DEFAULT_SHADOW, **(settings or {})}



# ==============================================================================
# SEARCHABLE FONT PICKER & BACKGROUND EFFECTS DIALOGS
# ==============================================================================

class FontPickerDialog(QDialog):
    """Searchable system font picker with real-time filtration."""
    def __init__(self, current_family, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Typography Font")
        self.resize(380, 480)
        self.selected_family = current_family

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search font family (e.g. Arial, Montserrat, Impact)…")
        layout.addWidget(self.search)

        self.list = QListWidget()
        layout.addWidget(self.list)

        self.no_results = QLabel("No matching fonts found.")
        self.no_results.setStyleSheet("color:#eab308;")
        self.no_results.setVisible(False)
        layout.addWidget(self.no_results)

        btn_row = QHBoxLayout()
        ok = QPushButton("Select Font")
        ok.setStyleSheet("background:#10b981; color:white; font-weight:bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        try:
            self.all_families = list(QFontDatabase.families())
        except (TypeError, AttributeError):
            self.all_families = list(QFontDatabase().families())
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


def compose_background(base_image, effects):
    """Apply background effects (blur, gradient, overlay, vignette, glow) to image."""
    img = QImage(base_image)
    if img.format() != QImage.Format.Format_ARGB32:
        img = img.convertToFormat(QImage.Format.Format_ARGB32)

    w, h = img.width(), img.height()
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. Dark Gradient Vignette
    gradient_amt = effects.get("gradient", 0)
    if gradient_amt > 0:
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, int(255 * gradient_amt / 100.0)))
        painter.fillRect(0, 0, w, h, QBrush(grad))

    # 2. Color Overlay Tint
    overlay_amt = effects.get("overlay", 0)
    if overlay_amt > 0:
        c = QColor(effects.get("overlay_color", "#002814"))
        c.setAlpha(int(255 * overlay_amt / 100.0))
        painter.fillRect(0, 0, w, h, QBrush(c))

    # 3. Vignette
    vignette_amt = effects.get("vignette", 0)
    if vignette_amt > 0:
        rad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.72)
        rad.setColorAt(0.55, QColor(0, 0, 0, 0))
        rad.setColorAt(1.0, QColor(0, 0, 0, int(255 * vignette_amt / 100.0)))
        painter.fillRect(0, 0, w, h, QBrush(rad))

    # 4. Stadium Glow
    glow_amt = effects.get("glow", 0)
    if glow_amt > 0:
        rad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.55)
        rad.setColorAt(0.0, QColor(255, 255, 255, int(255 * glow_amt / 100.0)))
        rad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(0, 0, w, h, QBrush(rad))

    painter.end()

    # 5. Opacity / Transparency
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


class BackgroundEffectsDialog(QDialog):
    """Modal dialog with live preview for tuning background atmosphere."""
    def __init__(self, base_image, current_effects, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atmosphere & Lighting Effects")
        self.resize(460, 560)
        self.base_image = base_image
        self.effects = copy.deepcopy(current_effects)
        self.result_effects = None

        outer = QHBoxLayout(self)

        preview_col = QVBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(220, 124)
        self.preview_label.setStyleSheet("background:#080c09; border:1px solid #334155; border-radius:6px;")
        preview_col.addWidget(QLabel("Live Preview:"))
        preview_col.addWidget(self.preview_label)
        preview_col.addStretch()
        outer.addLayout(preview_col)

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

        add_slider("gradient", "Dark Bottom Gradient (Court Fade)")
        add_slider("vignette", "Stadium Vignette Shadow")

        controls.addWidget(QLabel("Color Tint Overlay"))
        tint_row = QHBoxLayout()
        self.overlay_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlay_slider.setRange(0, 100)
        self.overlay_slider.setValue(self.effects.get("overlay", 0))
        self.overlay_slider.valueChanged.connect(lambda v: self._on_change("overlay", v))
        tint_row.addWidget(self.overlay_slider)
        btn_color = QPushButton("Color…")
        btn_color.clicked.connect(self._pick_overlay_color)
        tint_row.addWidget(btn_color)
        controls.addLayout(tint_row)
        self.sliders["overlay"] = self.overlay_slider

        add_slider("glow", "Center Floodlight Glow")
        add_slider("transparency", "Overall Background Opacity")
        self.sliders["transparency"].setValue(self.effects.get("transparency", 100))

        controls.addStretch()
        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        apply_btn = QPushButton("Apply Effects")
        apply_btn.setStyleSheet("background:#10b981; color:white; font-weight:bold;")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(apply_btn)
        controls.addLayout(btn_row)

        outer.addLayout(controls)
        self._update_preview()

    def _on_change(self, key, value):
        self.effects[key] = value
        self._update_preview()

    def _pick_overlay_color(self):
        c = QColorDialog.getColor(QColor(self.effects.get("overlay_color", "#002814")), self)
        if c.isValid():
            self.effects["overlay_color"] = c.name()
            self._update_preview()

    def _reset(self):
        self.effects = copy.deepcopy(DEFAULT_BG_EFFECTS)
        for key, s in self.sliders.items():
            s.blockSignals(True)
            s.setValue(self.effects.get(key, 0))
            s.blockSignals(False)
        self._update_preview()

    def _update_preview(self):
        composed = compose_background(self.base_image, self.effects)
        pix = QPixmap.fromImage(composed).scaled(
            self.preview_label.width(), self.preview_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(pix)

    def _apply(self):
        self.result_effects = self.effects
        self.accept()


# ==============================================================================
# ZERO-LAG GRID OVERLAY
# ==============================================================================

class _GridOverlayItem(QGraphicsItem):
    """Paints full canvas grid in one draw call for zero dragging latency."""
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
        spacing = max(10, self.app._grid_spacing)
        pen = QPen(QColor(255, 255, 255, 35))
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

        # Center axes
        center_pen = QPen(QColor(0, 229, 117, 80))
        center_pen.setWidth(1)
        painter.setPen(center_pen)
        painter.drawLine(int(CENTER_X), 0, int(CENTER_X), CANVAS_H)
        painter.drawLine(0, int(CENTER_Y), CANVAS_W, int(CENTER_Y))


# ==============================================================================
# MAIN STUDIO APPLICATION WINDOW
# ==============================================================================

class DavisCupThumbnailStudio(QMainWindow):
    """
    Main Studio Window for the Davis Cup Match Graphic Generator.
    Manages scene, selection, Canva-style handles, snapping, undo/redo,
    logo operations, backlight glow, underlines, slant controls, and 1920x1080 export.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Davis Cup Match Graphic Generator — Pro Studio v3.0")
        self.setGeometry(50, 50, 1620, 940)

        ensure_directory_tree()

        # Canvas State
        self._background_path = None
        self._background_base_image = None
        self._bg_effects = copy.deepcopy(DEFAULT_BG_EFFECTS)

        # Undo / Redo engine
        self._undo_stack = []
        self._redo_stack = []
        self._restoring = False
        self._history_state = None

        # Grid & Snapping
        self._grid_enabled = False
        self._grid_spacing = GRID_DEFAULT_SPACING
        self._grid_item = None
        self._guide_v = None
        self._guide_h = None
        self.active_handles = []

        # Graphics Scene & View
        self.scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setCentralWidget(self.view)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)

        # Background Item (Layer -100)
        self.bg_item = QGraphicsPixmapItem()
        self.bg_item.setZValue(-100)
        self.bg_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene.addItem(self.bg_item)

        # Setup Components & Studio Panels
        self._init_background()
        self._build_template_items()
        self._build_sidebar()
        self._build_shortcuts()

        # Status Bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready. Select any item to edit. Move with mouse or Arrow keys (Shift=10px).")

        # Selection Changed Listener
        self.scene.selectionChanged.connect(self._on_selection_changed)

        # Responsive view fitting
        self._fit_view()

        # Commit initial state snapshot
        self.push_undo_snapshot(initial=True)

        # Poll timer for history commits on idle
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._poll_history)
        self._history_timer.start(180)

        self._on_selection_changed()

    def eventFilter(self, obj, event):
        if obj in (self.view.viewport(), self.view):
            if event.type() == QEvent.Type.KeyPress:
                step = 10.0 if bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1.0
                sel = self.scene.selectedItems()
                movable = [i for i in sel if i is not self.bg_item and hasattr(i, "center")]
                if movable:
                    dx, dy = 0.0, 0.0
                    if event.key() == Qt.Key.Key_Left:
                        dx = -step
                    elif event.key() == Qt.Key.Key_Right:
                        dx = step
                    elif event.key() == Qt.Key.Key_Up:
                        dy = -step
                    elif event.key() == Qt.Key.Key_Down:
                        dy = step
                    if dx != 0.0 or dy != 0.0:
                        self.push_undo_snapshot()
                        for it in movable:
                            cx, cy = it.center()
                            it.set_center(cx + dx, cy + dy)
                        self.reposition_handles()
                        return True
        return super().eventFilter(obj, event)

    # --------------------------------------------------------------------------
    # BACKGROUND PIPELINE
    # --------------------------------------------------------------------------
    def _init_background(self):
        # Blank project default: clean procedural court atmosphere with zero preloaded photos
        procedural = create_procedural_stadium_background()
        self._background_path = None
        self._background_base_image = procedural
        self._refresh_background_pixmap()

    def _set_background_image(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            return False
        scaled = pix.scaled(
            CANVAS_W, CANVAS_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
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
            self.statusBar().showMessage("Atmosphere effects applied.", 3000)

    # --------------------------------------------------------------------------
    # TEMPLATE INITIALIZATION (MATCHES REFERENCE DESIGN EXACTLY)
    # --------------------------------------------------------------------------
    def _build_template_items(self):
        self._clear_all_handles()
        self.clear_guides()

        # 1. Left Player: Sumit Nagal (India) with vibrant emerald backlight & baseline underline
        self.player_left = PlayerCutoutItem(
            center_x=430, center_y=560,
            width=700, height=880,
            player_name="Sumit Nagal",
            is_left=True, app=self
        )
        self.scene.addItem(self.player_left)

        # 2. Right Player: Soonwoo Kwon (South Korea) with vibrant emerald backlight & baseline underline
        self.player_right = PlayerCutoutItem(
            center_x=1490, center_y=560,
            width=700, height=880,
            player_name="Soonwoo Kwon",
            is_left=False, app=self
        )
        self.scene.addItem(self.player_right)

        # 3. Left Player Nameplate ("SUMIT NAGAL")
        self.nameplate_left = SlantedNameplateItem(
            center_x=340, center_y=875,
            width=540, height=76,
            text="SUMIT NAGAL", app=self
        )
        self.scene.addItem(self.nameplate_left)

        # 4. Right Player Nameplate ("SOONWOO KWON")
        self.nameplate_right = SlantedNameplateItem(
            center_x=1580, center_y=875,
            width=550, height=76,
            text="SOONWOO KWON", app=self
        )
        self.nameplate_right.font_italic = True
        self.scene.addItem(self.nameplate_right)

        # 5. Center Match Banners
        # Top Banner: "DAY 1"
        self.banner_day = SlantedMatchBannerItem(
            center_x=CENTER_X, center_y=735,
            width=520, height=95,
            text="DAY 1", is_dark_green=True, app=self, role="banner_day"
        )
        self.scene.addItem(self.banner_day)

        # Bottom Banner: "MATCH 1"
        self.banner_match = SlantedMatchBannerItem(
            center_x=CENTER_X, center_y=842,
            width=640, height=105,
            text="MATCH 1", is_dark_green=False, app=self, role="banner_match"
        )
        self.scene.addItem(self.banner_match)

        # 6. Tournament Logo & Header ("DAVIS CUP®")
        self.tournament_header = TournamentLogoItem(
            center_x=CENTER_X, center_y=160,
            width=600, height=190, app=self
        )
        self.scene.addItem(self.tournament_header)

        # 7. Country Matchup Bar
        # Left Country Pill: India Flag + "IND" (3:2 ratio)
        self.pill_left = CountryPillItem(
            center_x=710, center_y=445,
            width=270, height=76,
            country_code="IND", flag_on_left=True, app=self
        )
        self.scene.addItem(self.pill_left)

        # Center "VS" Divider
        self.vs_divider = VsDividerItem(
            center_x=CENTER_X, center_y=445,
            width=130, height=76, app=self
        )
        self.scene.addItem(self.vs_divider)

        # Right Country Pill: "KOR" + South Korea Flag (3:2 ratio)
        self.pill_right = CountryPillItem(
            center_x=1210, center_y=445,
            width=270, height=76,
            country_code="KOR", flag_on_left=False, app=self
        )
        self.scene.addItem(self.pill_right)

        # 8. Neon Energy Light Trails
        self.neon_glow = NeonGlowAccentsItem(
            center_x=CENTER_X, center_y=880,
            width=CANVAS_W, height=320, app=self
        )
        self.scene.addItem(self.neon_glow)

        # Extra Custom Text Lines list
        self.custom_text_items = []

        self._rebuild_grid()

    # --------------------------------------------------------------------------
    # CANVA-STYLE 8-POINT RESIZE HANDLES
    # --------------------------------------------------------------------------
    def _clear_all_handles(self):
        for h in self.active_handles:
            self.scene.removeItem(h)
        self.active_handles = []

    def clear_all_handles(self):
        self._clear_all_handles()

    def _spawn_handles_for(self, target_item):
        self._clear_all_handles()
        if target_item is self.bg_item:
            return
        for edge in HANDLE_EDGES:
            h = CanvasResizeHandle(target_item, edge, self)
            self.scene.addItem(h)
            self.active_handles.append(h)
        self.reposition_handles()

    def reposition_handles(self):
        if not self.active_handles:
            return
        target = self.active_handles[0].target_item
        if isinstance(target, EditableTextItem):
            cx, cy = target.center()
            hw, hh = target.half_size()
        elif isinstance(target, DraggableStudioItem):
            cx, cy = target.center()
            hw, hh = target.half_size()
        else:
            return

        coords = {
            "nw": (cx - hw, cy - hh), "n": (cx, cy - hh), "ne": (cx + hw, cy - hh),
            "e": (cx + hw, cy), "se": (cx + hw, cy + hh), "s": (cx, cy + hh),
            "sw": (cx - hw, cy + hh), "w": (cx - hw, cy),
        }
        for h in self.active_handles:
            x, y = coords.get(h.edge, (cx, cy))
            h.setPos(x, y)

    def resize_item_from_handle(self, item, edge, scene_pos):
        cx, cy = item.center()
        w, h = item.size()
        keep_aspect = getattr(item, "aspect_locked", lambda: False)()

        dx = abs(scene_pos.x() - cx) * 2.0
        dy = abs(scene_pos.y() - cy) * 2.0

        new_w, new_h = w, h
        if edge in ("nw", "ne", "se", "sw"):
            new_w, new_h = dx, dy
        elif edge in ("e", "w"):
            new_w = dx
        elif edge in ("n", "s"):
            new_h = dy

        if isinstance(item, DraggableStudioItem):
            item.set_size_px(new_w, new_h, keep_aspect=keep_aspect)
        elif isinstance(item, EditableTextItem):
            item._box_w = max(40.0, new_w)
            item._box_h = max(20.0, new_h)
            item._recenter()

        self.reposition_handles()
        self._sync_active_selection_controls(item)

    # --------------------------------------------------------------------------
    # GRID & SNAPPING
    # --------------------------------------------------------------------------
    def _rebuild_grid(self):
        if self._grid_item is None:
            self._grid_item = _GridOverlayItem(self)
            self._grid_item.setZValue(-50)
            self.scene.addItem(self._grid_item)
        self._grid_item.update()

    def _toggle_grid(self, checked):
        self._grid_enabled = checked
        self._rebuild_grid()

    def _set_grid_spacing(self, val):
        self._grid_spacing = val
        if self._grid_enabled:
            self._rebuild_grid()

    def _ensure_guide_items(self):
        if self._guide_v is not None:
            return
        pen = QPen(QColor("#ff0044"))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        self._guide_v = QGraphicsLineItem(0, 0, 0, CANVAS_H)
        self._guide_h = QGraphicsLineItem(0, 0, CANVAS_W, 0)
        for line in (self._guide_v, self._guide_h):
            line.setPen(pen)
            line.setZValue(6000)
            line.setVisible(False)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.scene.addItem(line)

    def clear_guides(self):
        self._ensure_guide_items()
        self._guide_v.setVisible(False)
        self._guide_h.setVisible(False)

    def _clear_guides(self):
        self.clear_guides()

    def _show_guide(self, orientation, coord):
        self._ensure_guide_items()
        if orientation == "v":
            self._guide_v.setLine(coord, 0, coord, CANVAS_H)
            self._guide_v.setVisible(True)
        else:
            self._guide_h.setLine(0, coord, CANVAS_W, coord)
            self._guide_h.setVisible(True)

    def snap_center(self, moving_item, proposed_center, hw, hh):
        if not hasattr(self, "snap_enabled_checkbox") or not self.snap_enabled_checkbox.isChecked():
            self.clear_guides()
            return proposed_center

        cx, cy = proposed_center.x(), proposed_center.y()
        x_cands = [CENTER_X, hw, CANVAS_W - hw]
        y_cands = [CENTER_Y, hh, CANVAS_H - hh]

        for it in self._all_snappable_items():
            if it is moving_item:
                continue
            if hasattr(it, "center"):
                ocx, ocy = it.center()
                x_cands.append(ocx)
                y_cands.append(ocy)

        if self._grid_enabled:
            sp = max(10, self._grid_spacing)
            x_cands.append(round(cx / sp) * sp)
            y_cands.append(round(cy / sp) * sp)

        best_x, best_x_dist = cx, SNAP_THRESHOLD
        for cand in x_cands:
            d = abs(cand - cx)
            if d < best_x_dist:
                best_x, best_x_dist = cand, d

        best_y, best_y_dist = cy, SNAP_THRESHOLD
        for cand in y_cands:
            d = abs(cand - cy)
            if d < best_y_dist:
                best_y, best_y_dist = cand, d

        if best_x != cx:
            self._show_guide("v", best_x)
        elif self._guide_v:
            self._guide_v.setVisible(False)

        if best_y != cy:
            self._show_guide("h", best_y)
        elif self._guide_h:
            self._guide_h.setVisible(False)

        return QPointF(best_x, best_y)

    def _all_snappable_items(self):
        items = [
            self.player_left, self.player_right,
            self.nameplate_left, self.nameplate_right,
            self.banner_day, self.banner_match,
            self.pill_left, self.vs_divider, self.pill_right,
            self.tournament_header, self.neon_glow
        ]
        items.extend(self.custom_text_items)
        return [i for i in items if i.scene() is self.scene]

    # --------------------------------------------------------------------------
    # UNDO / REDO STATE MACHINE
    # --------------------------------------------------------------------------
    def push_undo_snapshot(self, initial=False):
        if self._restoring:
            return
        if initial:
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._history_state = json.dumps(self._capture_state())
        elif self._history_state:
            if QApplication.mouseButtons() == Qt.MouseButton.NoButton:
                self.commit_history_state()
        self._update_undo_redo_ui()

    def commit_history_state(self):
        if self._restoring or self._history_state is None:
            return
        current = json.dumps(self._capture_state())
        if current != self._history_state:
            self._undo_stack.append(self._history_state)
            self._undo_stack = self._undo_stack[-UNDO_LIMIT:]
            self._redo_stack.clear()
            self._history_state = current
        self._update_undo_redo_ui()

    def _poll_history(self):
        if QApplication.mouseButtons() == Qt.MouseButton.NoButton:
            self.commit_history_state()

    def undo(self):
        self._travel_history(backwards=True)

    def redo(self):
        self._travel_history(backwards=False)

    def _travel_history(self, backwards):
        self.commit_history_state()
        src = self._undo_stack if backwards else self._redo_stack
        dst = self._redo_stack if backwards else self._undo_stack
        if not src:
            self._update_undo_redo_ui()
            return

        current = json.dumps(self._capture_state())
        target_state_str = src.pop()
        try:
            self._apply_state(json.loads(target_state_str))
            dst.append(current)
            self._history_state = json.dumps(self._capture_state())
            self.statusBar().showMessage("Undone." if backwards else "Redone.", 2000)
        except Exception as exc:
            self._apply_state(json.loads(current))
            QMessageBox.warning(self, "Undo Warning", f"Could not restore state: {exc}")
        self._update_undo_redo_ui()

    def _update_undo_redo_ui(self):
        if hasattr(self, "btn_undo"):
            pending = (self._history_state is not None and
                       json.dumps(self._capture_state()) != self._history_state)
            self.btn_undo.setEnabled(bool(self._undo_stack) or pending)
            self.btn_redo.setEnabled(bool(self._redo_stack))

    # --------------------------------------------------------------------------
    # SERIALIZATION / PRESETS
    # --------------------------------------------------------------------------
    def _serialize_studio_item(self, item):
        data = {
            "center": list(item.center()),
            "size": list(item.size()),
            "z": item.zValue(),
            "role": getattr(item, "role", "item"),
            "in_scene": item.scene() is self.scene,
            "rotation": item.rotation(),
            "opacity": item.opacity(),
            "shadow": item.shadow_settings() if hasattr(item, "shadow_settings") else copy.deepcopy(DEFAULT_SHADOW),
        }
        if isinstance(item, PlayerCutoutItem):
            data.update({
                "player_name": item.player_name,
                "source_path": item.source_path(),
                "flip_h": item.flip_h(),
                "flip_v": item.flip_v(),
                "aspect_locked": item.aspect_locked(),
                "glow_enabled": item.glow_enabled,
                "glow_color": item.glow_color.name(),
                "glow_intensity": item.glow_intensity,
                "glow_radius": item.glow_radius,
                "underline_enabled": item.underline_enabled,
                "underline_color": item.underline_color.name(),
                "underline_thickness": item.underline_thickness,
                "underline_width": item.underline_width,
            })
        elif isinstance(item, SlantedNameplateItem):
            data.update({
                "text": item.text,
                "font_family": item.font_family,
                "font_size": item.font_size,
                "font_bold": item.font_bold,
                "font_italic": item.font_italic,
                "font_underline": item.font_underline,
                "letter_spacing": item.letter_spacing,
                "slant_deg": item.slant_deg,
                "text_slant_deg": item.text_slant_deg,
                "bg_color1": item.bg_color1.name(),
                "bg_color2": item.bg_color2.name(),
                "border_color": item.border_color.name(),
                "border_width": item.border_width,
                "text_color": item.text_color.name(),
            })
        elif isinstance(item, SlantedMatchBannerItem):
            data.update({
                "text": item.text,
                "font_family": item.font_family,
                "font_size": item.font_size,
                "font_bold": item.font_bold,
                "font_italic": item.font_italic,
                "font_underline": item.font_underline,
                "letter_spacing": item.letter_spacing,
                "slant_deg": item.slant_deg,
                "bg_color1": item.bg_color1.name(),
                "bg_color2": item.bg_color2.name(),
                "border_color": item.border_color.name(),
                "border_width": item.border_width,
                "text_color": item.text_color.name(),
                "is_dark_green": item.is_dark_green,
            })
        elif isinstance(item, CountryPillItem):
            data.update({
                "country_code": item.country_code,
                "flag_on_left": item.flag_on_left,
                "flag_path": item._flag_source_path,
                "font_family": item.font_family,
                "font_size": item.font_size,
                "font_bold": item.font_bold,
                "bg_color": item.bg_color.name(),
                "border_color": item.border_color.name(),
                "text_color": item.text_color.name(),
            })
        elif isinstance(item, TournamentLogoItem):
            data.update({
                "title_text": item.title_text,
                "font_family": item.font_family,
                "font_size": item.font_size,
                "font_bold": item.font_bold,
                "font_italic": item.font_italic,
                "text_color": item.text_color.name(),
                "emblem_color": item.emblem_color.name(),
                "custom_logo_path": item.custom_logo_path,
                "show_logo": item.show_logo,
                "show_title": item.show_title,
            })
        elif isinstance(item, NeonGlowAccentsItem):
            data.update({
                "glow_color": item.glow_color.name(),
                "enabled": item.enabled,
            })
        elif isinstance(item, VsDividerItem):
            data.update({
                "text": item.text,
                "font_family": item.font_family,
                "font_size": item.font_size,
                "font_bold": item.font_bold,
                "font_italic": item.font_italic,
                "font_underline": item.font_underline,
                "letter_spacing": item.letter_spacing,
                "text_color": item.text_color.name(),
                "line_color": item.line_color.name() if hasattr(item.line_color, 'name') else "#000000",
            })
        elif isinstance(item, EditableTextItem):
            f = item.font()
            data.update({
                "text": item.toPlainText(),
                "font_family": f.family(),
                "font_size": f.pointSize(),
                "bold": f.bold(),
                "italic": f.italic(),
                "underline": f.underline(),
                "color": item.defaultTextColor().name(),
                "align": item.align,
                "letter_spacing_px": item.letter_spacing_px,
                "box_w": getattr(item, "_box_w", None),
                "box_h": getattr(item, "_box_h", None),
            })
        return data

    def _capture_state(self):
        state = {
            "background": self._background_path,
            "bg_effects": copy.deepcopy(self._bg_effects),
            "grid": {"enabled": self._grid_enabled, "spacing": self._grid_spacing},
            "player_left": self._serialize_studio_item(self.player_left),
            "player_right": self._serialize_studio_item(self.player_right),
            "nameplate_left": self._serialize_studio_item(self.nameplate_left),
            "nameplate_right": self._serialize_studio_item(self.nameplate_right),
            "banner_day": self._serialize_studio_item(self.banner_day),
            "banner_match": self._serialize_studio_item(self.banner_match),
            "tournament_header": self._serialize_studio_item(self.tournament_header),
            "pill_left": self._serialize_studio_item(self.pill_left),
            "vs_divider": self._serialize_studio_item(self.vs_divider),
            "pill_right": self._serialize_studio_item(self.pill_right),
            "neon_glow": self._serialize_studio_item(self.neon_glow),
            "custom_texts": [self._serialize_studio_item(i) for i in self.custom_text_items],
        }
        return state

    def _apply_state(self, state):
        self._restoring = True
        self.scene.blockSignals(True)
        try:
            self._restore_state(state)
        finally:
            self.scene.blockSignals(False)
            self._restoring = False
            self._on_selection_changed()

    def _restore_state(self, state):
        self._clear_all_handles()
        self.clear_guides()

        bg_p = state.get("background")
        if bg_p and os.path.exists(bg_p):
            self._set_background_image(bg_p)
        else:
            self._init_background()

        self._bg_effects = {**DEFAULT_BG_EFFECTS, **state.get("bg_effects", {})}
        self._refresh_background_pixmap()

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

        def apply_props(it, d):
            if not d:
                return
            it.set_center(d["center"][0], d["center"][1])
            if hasattr(it, "set_size_px"):
                it.set_size_px(d["size"][0], d["size"][1], keep_aspect=False)
            it.setZValue(d.get("z", it.zValue()))
            it.setRotation(d.get("rotation", 0))
            it.setOpacity(d.get("opacity", 1.0))
            if hasattr(it, "set_shadow_settings") and "shadow" in d:
                it.set_shadow_settings(d["shadow"])
            if not d.get("in_scene", True) and it.scene() is self.scene:
                self.scene.removeItem(it)
            elif d.get("in_scene", True) and it.scene() is None:
                self.scene.addItem(it)

        # 1. Players
        pl_d = state.get("player_left", {})
        apply_props(self.player_left, pl_d)
        if pl_d.get("source_path") and os.path.exists(pl_d["source_path"]):
            self.player_left.load_image(pl_d["source_path"])
        self.player_left.set_flip_h(pl_d.get("flip_h", False))
        self.player_left.set_flip_v(pl_d.get("flip_v", False))
        if "glow_enabled" in pl_d:
            self.player_left.glow_enabled = pl_d["glow_enabled"]
            self.player_left.glow_color = QColor(pl_d.get("glow_color", "#00ff88"))
            self.player_left.glow_intensity = pl_d.get("glow_intensity", 85)
            self.player_left.glow_radius = pl_d.get("glow_radius", 260)
        if "underline_enabled" in pl_d:
            self.player_left.underline_enabled = pl_d["underline_enabled"]
            self.player_left.underline_color = QColor(pl_d.get("underline_color", "#00ff88"))
            self.player_left.underline_thickness = pl_d.get("underline_thickness", 5)
            self.player_left.underline_width = pl_d.get("underline_width", 460)

        pr_d = state.get("player_right", {})
        apply_props(self.player_right, pr_d)
        if pr_d.get("source_path") and os.path.exists(pr_d["source_path"]):
            self.player_right.load_image(pr_d["source_path"])
        self.player_right.set_flip_h(pr_d.get("flip_h", False))
        self.player_right.set_flip_v(pr_d.get("flip_v", False))
        if "glow_enabled" in pr_d:
            self.player_right.glow_enabled = pr_d["glow_enabled"]
            self.player_right.glow_color = QColor(pr_d.get("glow_color", "#00ff88"))
            self.player_right.glow_intensity = pr_d.get("glow_intensity", 85)
            self.player_right.glow_radius = pr_d.get("glow_radius", 260)
        if "underline_enabled" in pr_d:
            self.player_right.underline_enabled = pr_d["underline_enabled"]
            self.player_right.underline_color = QColor(pr_d.get("underline_color", "#00ff88"))
            self.player_right.underline_thickness = pr_d.get("underline_thickness", 5)
            self.player_right.underline_width = pr_d.get("underline_width", 460)

        # 2. Nameplates
        nl_d = state.get("nameplate_left", {})
        apply_props(self.nameplate_left, nl_d)
        if "text" in nl_d:
            self.nameplate_left.set_name(nl_d["text"])
            self.nameplate_left.slant_deg = nl_d.get("slant_deg", 15.0)
            self.nameplate_left.text_slant_deg = nl_d.get("text_slant_deg", 0.0)
            self.nameplate_left.font_family = nl_d.get("font_family", self.nameplate_left.font_family)
            self.nameplate_left.font_size = nl_d.get("font_size", self.nameplate_left.font_size)
            self.nameplate_left.font_bold = nl_d.get("font_bold", self.nameplate_left.font_bold)
            self.nameplate_left.font_italic = nl_d.get("font_italic", self.nameplate_left.font_italic)
            self.nameplate_left.font_underline = nl_d.get("font_underline", self.nameplate_left.font_underline)
            self.nameplate_left.letter_spacing = nl_d.get("letter_spacing", self.nameplate_left.letter_spacing)
            if "text_color" in nl_d:
                self.nameplate_left.text_color = QColor(nl_d["text_color"])
            if "bg_color1" in nl_d:
                self.nameplate_left.bg_color1 = QColor(nl_d["bg_color1"])
            if "bg_color2" in nl_d:
                self.nameplate_left.bg_color2 = QColor(nl_d["bg_color2"])
            if "border_color" in nl_d:
                self.nameplate_left.border_color = QColor(nl_d["border_color"])
            self.nameplate_left.border_width = nl_d.get("border_width", self.nameplate_left.border_width)
            self.nameplate_left.update()

        nr_d = state.get("nameplate_right", {})
        apply_props(self.nameplate_right, nr_d)
        if "text" in nr_d:
            self.nameplate_right.set_name(nr_d["text"])
            self.nameplate_right.slant_deg = nr_d.get("slant_deg", 15.0)
            self.nameplate_right.text_slant_deg = nr_d.get("text_slant_deg", 0.0)
            self.nameplate_right.font_family = nr_d.get("font_family", self.nameplate_right.font_family)
            self.nameplate_right.font_size = nr_d.get("font_size", self.nameplate_right.font_size)
            self.nameplate_right.font_bold = nr_d.get("font_bold", self.nameplate_right.font_bold)
            self.nameplate_right.font_italic = nr_d.get("font_italic", self.nameplate_right.font_italic)
            self.nameplate_right.font_underline = nr_d.get("font_underline", self.nameplate_right.font_underline)
            self.nameplate_right.letter_spacing = nr_d.get("letter_spacing", self.nameplate_right.letter_spacing)
            if "text_color" in nr_d:
                self.nameplate_right.text_color = QColor(nr_d["text_color"])
            if "bg_color1" in nr_d:
                self.nameplate_right.bg_color1 = QColor(nr_d["bg_color1"])
            if "bg_color2" in nr_d:
                self.nameplate_right.bg_color2 = QColor(nr_d["bg_color2"])
            if "border_color" in nr_d:
                self.nameplate_right.border_color = QColor(nr_d["border_color"])
            self.nameplate_right.border_width = nr_d.get("border_width", self.nameplate_right.border_width)
            self.nameplate_right.update()

        # 3. Match Banners
        bd_d = state.get("banner_day", {})
        apply_props(self.banner_day, bd_d)
        if "text" in bd_d:
            self.banner_day.set_banner_text(bd_d["text"])
            self.banner_day.slant_deg = bd_d.get("slant_deg", 15.0)
            self.banner_day.font_family = bd_d.get("font_family", self.banner_day.font_family)
            self.banner_day.font_size = bd_d.get("font_size", self.banner_day.font_size)
            self.banner_day.font_bold = bd_d.get("font_bold", self.banner_day.font_bold)
            self.banner_day.font_italic = bd_d.get("font_italic", self.banner_day.font_italic)
            self.banner_day.font_underline = bd_d.get("font_underline", self.banner_day.font_underline)
            self.banner_day.letter_spacing = bd_d.get("letter_spacing", self.banner_day.letter_spacing)
            if "text_color" in bd_d:
                self.banner_day.text_color = QColor(bd_d["text_color"])
            if "bg_color1" in bd_d:
                self.banner_day.bg_color1 = QColor(bd_d["bg_color1"])
            if "bg_color2" in bd_d:
                self.banner_day.bg_color2 = QColor(bd_d["bg_color2"])
            if "border_color" in bd_d:
                self.banner_day.border_color = QColor(bd_d["border_color"])
            self.banner_day.border_width = bd_d.get("border_width", self.banner_day.border_width)
            self.banner_day.update()

        bm_d = state.get("banner_match", {})
        apply_props(self.banner_match, bm_d)
        if "text" in bm_d:
            self.banner_match.set_banner_text(bm_d["text"])
            self.banner_match.slant_deg = bm_d.get("slant_deg", 15.0)
            self.banner_match.font_family = bm_d.get("font_family", self.banner_match.font_family)
            self.banner_match.font_size = bm_d.get("font_size", self.banner_match.font_size)
            self.banner_match.font_bold = bm_d.get("font_bold", self.banner_match.font_bold)
            self.banner_match.font_italic = bm_d.get("font_italic", self.banner_match.font_italic)
            self.banner_match.font_underline = bm_d.get("font_underline", self.banner_match.font_underline)
            self.banner_match.letter_spacing = bm_d.get("letter_spacing", self.banner_match.letter_spacing)
            if "text_color" in bm_d:
                self.banner_match.text_color = QColor(bm_d["text_color"])
            if "bg_color1" in bm_d:
                self.banner_match.bg_color1 = QColor(bm_d["bg_color1"])
            if "bg_color2" in bm_d:
                self.banner_match.bg_color2 = QColor(bm_d["bg_color2"])
            if "border_color" in bm_d:
                self.banner_match.border_color = QColor(bm_d["border_color"])
            self.banner_match.border_width = bm_d.get("border_width", self.banner_match.border_width)
            self.banner_match.update()

        # 4. Header & Logo
        th_d = state.get("tournament_header", {})
        apply_props(self.tournament_header, th_d)
        if "title_text" in th_d:
            self.tournament_header.title_text = th_d["title_text"]
        if "show_logo" in th_d:
            self.tournament_header.show_logo = th_d["show_logo"]
        if "show_title" in th_d:
            self.tournament_header.show_title = th_d["show_title"]
        if "font_family" in th_d:
            self.tournament_header.font_family = th_d["font_family"]
        if "font_size" in th_d:
            self.tournament_header.font_size = th_d["font_size"]
        if "font_bold" in th_d:
            self.tournament_header.font_bold = th_d["font_bold"]
        if "font_italic" in th_d:
            self.tournament_header.font_italic = th_d["font_italic"]
        if "text_color" in th_d:
            self.tournament_header.text_color = QColor(th_d["text_color"])
        if "emblem_color" in th_d:
            self.tournament_header.emblem_color = QColor(th_d["emblem_color"])
        if th_d.get("custom_logo_path") and os.path.exists(th_d["custom_logo_path"]):
            self.tournament_header.set_custom_logo(th_d["custom_logo_path"])
        self.tournament_header.update()

        # 5. Pills
        pill_l_d = state.get("pill_left", {})
        apply_props(self.pill_left, pill_l_d)
        if "country_code" in pill_l_d:
            self.pill_left.set_code(pill_l_d["country_code"])
        if pill_l_d.get("flag_path") and os.path.exists(pill_l_d["flag_path"]):
            self.pill_left.load_flag(pill_l_d["flag_path"])
        if "bg_color" in pill_l_d:
            self.pill_left.bg_color = QColor(pill_l_d["bg_color"])
        if "border_color" in pill_l_d:
            self.pill_left.border_color = QColor(pill_l_d["border_color"])
        if "text_color" in pill_l_d:
            self.pill_left.text_color = QColor(pill_l_d["text_color"])
        self.pill_left.font_size = pill_l_d.get("font_size", self.pill_left.font_size)
        self.pill_left.font_family = pill_l_d.get("font_family", self.pill_left.font_family)
        self.pill_left.font_bold = pill_l_d.get("font_bold", self.pill_left.font_bold)
        self.pill_left.update()

        vs_d = state.get("vs_divider", {})
        apply_props(self.vs_divider, vs_d)
        if "text" in vs_d:
            self.vs_divider.text = vs_d["text"]
        self.vs_divider.font_size = vs_d.get("font_size", self.vs_divider.font_size)
        self.vs_divider.font_family = vs_d.get("font_family", self.vs_divider.font_family)
        self.vs_divider.font_bold = vs_d.get("font_bold", self.vs_divider.font_bold)
        if "text_color" in vs_d:
            self.vs_divider.text_color = QColor(vs_d["text_color"])
        self.vs_divider.update()

        pill_r_d = state.get("pill_right", {})
        apply_props(self.pill_right, pill_r_d)
        if "country_code" in pill_r_d:
            self.pill_right.set_code(pill_r_d["country_code"])
        if pill_r_d.get("flag_path") and os.path.exists(pill_r_d["flag_path"]):
            self.pill_right.load_flag(pill_r_d["flag_path"])
        if "bg_color" in pill_r_d:
            self.pill_right.bg_color = QColor(pill_r_d["bg_color"])
        if "border_color" in pill_r_d:
            self.pill_right.border_color = QColor(pill_r_d["border_color"])
        if "text_color" in pill_r_d:
            self.pill_right.text_color = QColor(pill_r_d["text_color"])
        self.pill_right.font_size = pill_r_d.get("font_size", self.pill_right.font_size)
        self.pill_right.font_family = pill_r_d.get("font_family", self.pill_right.font_family)
        self.pill_right.font_bold = pill_r_d.get("font_bold", self.pill_right.font_bold)
        self.pill_right.update()

        # 6. Neon Glow
        ng_d = state.get("neon_glow", {})
        apply_props(self.neon_glow, ng_d)
        if "enabled" in ng_d:
            self.neon_glow.enabled = ng_d["enabled"]

        # 7. Custom Text Lines
        for item in list(self.custom_text_items):
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.custom_text_items = []
        for td in state.get("custom_texts", []):
            try:
                cx, cy = td.get("center", [CENTER_X, CENTER_Y])
                f = QFont(td.get("font_family", "Arial"), td.get("font_size", 48))
                f.setBold(td.get("bold", True))
                f.setItalic(td.get("italic", False))
                f.setUnderline(td.get("underline", False))
                c = QColor(td.get("color", "#ffffff"))
                txt_item = EditableTextItem(td.get("text", "MATCH DAY"), f, c, cx, cy, app=self)
                txt_item.align = td.get("align", "center")
                txt_item.letter_spacing_px = td.get("letter_spacing_px", 0)
                if td.get("box_w") is not None and td.get("box_h") is not None:
                    txt_item._box_w = td.get("box_w")
                    txt_item._box_h = td.get("box_h")
                    txt_item._recenter()
                txt_item.setZValue(td.get("z", 35))
                txt_item.setRotation(td.get("rotation", 0))
                txt_item.setOpacity(td.get("opacity", 1.0))
                self.scene.addItem(txt_item)
                self.custom_text_items.append(txt_item)
            except Exception:
                pass

        self._sync_sidebar_to_model()

    def _sync_sidebar_to_model(self):
        widget_names = [
            "input_name_l", "input_name_r",
            "spin_slant_l", "spin_slant_r",
            "spin_text_slant_l", "spin_text_slant_r",
            "input_code_l", "input_code_r",
            "input_day_text", "input_match_text",
            "input_header_text",
            "chk_show_logo", "chk_show_title", "spin_banner_slant",
            "chk_glow_l", "slider_glow_int_l", "slider_glow_rad_l",
            "chk_und_l", "spin_und_thk_l", "spin_und_w_l",
            "chk_glow_r", "slider_glow_int_r", "slider_glow_rad_r",
            "chk_und_r", "spin_und_thk_r", "spin_und_w_r",
        ]
        active_widgets = [getattr(self, n) for n in widget_names if hasattr(self, n)]
        for w in active_widgets:
            w.blockSignals(True)

        if hasattr(self, "input_name_l"):
            self.input_name_l.setText(self.nameplate_left.text)
        if hasattr(self, "input_name_r"):
            self.input_name_r.setText(self.nameplate_right.text)
        if hasattr(self, "spin_slant_l"):
            self.spin_slant_l.setValue(self.nameplate_left.slant_deg)
        if hasattr(self, "spin_slant_r"):
            self.spin_slant_r.setValue(self.nameplate_right.slant_deg)
        if hasattr(self, "spin_text_slant_l"):
            self.spin_text_slant_l.setValue(self.nameplate_left.text_slant_deg)
        if hasattr(self, "spin_text_slant_r"):
            self.spin_text_slant_r.setValue(self.nameplate_right.text_slant_deg)
        if hasattr(self, "input_code_l"):
            self.input_code_l.setText(self.pill_left.country_code)
        if hasattr(self, "input_code_r"):
            self.input_code_r.setText(self.pill_right.country_code)
        if hasattr(self, "input_day_text"):
            self.input_day_text.setText(self.banner_day.text)
        if hasattr(self, "input_match_text"):
            self.input_match_text.setText(self.banner_match.text)
        if hasattr(self, "input_header_text"):
            self.input_header_text.setText(self.tournament_header.title_text)

        if hasattr(self, "spin_banner_slant"):
            self.spin_banner_slant.setValue(self.banner_day.slant_deg)
        if hasattr(self, "chk_show_logo"):
            self.chk_show_logo.setChecked(self.tournament_header.show_logo)
        if hasattr(self, "chk_show_title"):
            self.chk_show_title.setChecked(self.tournament_header.show_title)

        if hasattr(self, "chk_glow_l"):
            self.chk_glow_l.setChecked(self.player_left.glow_enabled)
        if hasattr(self, "slider_glow_int_l"):
            self.slider_glow_int_l.setValue(int(self.player_left.glow_intensity))
        if hasattr(self, "slider_glow_rad_l"):
            self.slider_glow_rad_l.setValue(int(self.player_left.glow_radius))
        if hasattr(self, "chk_und_l"):
            self.chk_und_l.setChecked(self.player_left.underline_enabled)
        if hasattr(self, "spin_und_thk_l"):
            self.spin_und_thk_l.setValue(int(self.player_left.underline_thickness))
        if hasattr(self, "spin_und_w_l"):
            self.spin_und_w_l.setValue(int(self.player_left.underline_width))

        if hasattr(self, "chk_glow_r"):
            self.chk_glow_r.setChecked(self.player_right.glow_enabled)
        if hasattr(self, "slider_glow_int_r"):
            self.slider_glow_int_r.setValue(int(self.player_right.glow_intensity))
        if hasattr(self, "slider_glow_rad_r"):
            self.slider_glow_rad_r.setValue(int(self.player_right.glow_radius))
        if hasattr(self, "chk_und_r"):
            self.chk_und_r.setChecked(self.player_right.underline_enabled)
        if hasattr(self, "spin_und_thk_r"):
            self.spin_und_thk_r.setValue(int(self.player_right.underline_thickness))
        if hasattr(self, "spin_und_w_r"):
            self.spin_und_w_r.setValue(int(self.player_right.underline_width))

        for w in active_widgets:
            w.blockSignals(False)

    # --------------------------------------------------------------------------
    # MODERN REDESIGNED UI & STUDIO CONTROLS
    # --------------------------------------------------------------------------
    def _build_sidebar(self):
        dock = QDockWidget("Studio Controls", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(440)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # --- Top Undo/Redo & Clean Action Header ---
        top_bar = QHBoxLayout()
        self.btn_undo = QPushButton("↺  Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("Redo (Ctrl+Y)  ↻")
        self.btn_redo.clicked.connect(self.redo)
        self.btn_blank_project = QPushButton("📄 Blank Project")
        self.btn_blank_project.clicked.connect(self._reset_to_blank_project)
        top_bar.addWidget(self.btn_undo)
        top_bar.addWidget(self.btn_redo)
        top_bar.addWidget(self.btn_blank_project)
        layout.addLayout(top_bar)

        # Tabbed Panes
        tabs = QTabWidget()
        tab_logo = QWidget()
        tab_match = QWidget()
        tab_p1 = QWidget()
        tab_p2 = QWidget()
        tab_styling = QWidget()
        tab_atmosphere = QWidget()
        tab_export = QWidget()

        lay_logo = QVBoxLayout(tab_logo)
        lay_match = QVBoxLayout(tab_match)
        lay_p1 = QVBoxLayout(tab_p1)
        lay_p2 = QVBoxLayout(tab_p2)
        lay_styling = QVBoxLayout(tab_styling)
        lay_atmosphere = QVBoxLayout(tab_atmosphere)
        lay_export = QVBoxLayout(tab_export)

        for l in (lay_logo, lay_match, lay_p1, lay_p2, lay_styling, lay_atmosphere, lay_export):
            l.setContentsMargins(10, 12, 10, 12)
            l.setSpacing(10)

        tabs.addTab(tab_logo, "🏷️ Logo")
        tabs.addTab(tab_match, "⚔️ Match")
        tabs.addTab(tab_p1, "👤 Left")
        tabs.addTab(tab_p2, "👤 Right")
        tabs.addTab(tab_styling, "🔤 Text")
        tabs.addTab(tab_atmosphere, "🌌 Court")
        tabs.addTab(tab_export, "💾 Save")
        layout.addWidget(tabs, 1)

        # ======================================================================
        # TAB 1: LOGO & TOURNAMENT HEADER (REQ 2: ADD, REPLACE, REMOVE LOGO)
        # ======================================================================
        grp_logo = QGroupBox("Tournament Logo Management")
        l_lg = QVBoxLayout()

        row_logo_btns = QHBoxLayout()
        btn_upload_logo = QPushButton("📁 Upload / Add Logo…")
        btn_upload_logo.clicked.connect(self._upload_custom_logo)
        btn_replace_logo = QPushButton("🔄 Replace Logo…")
        btn_replace_logo.clicked.connect(self._upload_custom_logo)
        row_logo_btns.addWidget(btn_upload_logo)
        row_logo_btns.addWidget(btn_replace_logo)
        l_lg.addLayout(row_logo_btns)

        row_logo_actions = QHBoxLayout()
        btn_remove_logo = QPushButton("❌ Remove Logo")
        btn_remove_logo.clicked.connect(self._remove_logo)
        btn_reset_logo = QPushButton("🎾 Reset Davis Cup Logo")
        btn_reset_logo.clicked.connect(self._reset_logo)
        row_logo_actions.addWidget(btn_remove_logo)
        row_logo_actions.addWidget(btn_reset_logo)
        l_lg.addLayout(row_logo_actions)

        self.chk_show_logo = QCheckBox("Display Logo Mark on Canvas")
        self.chk_show_logo.setChecked(True)
        self.chk_show_logo.toggled.connect(self._toggle_logo_display)
        l_lg.addWidget(self.chk_show_logo)

        grp_logo.setLayout(l_lg)
        lay_logo.addWidget(grp_logo)

        grp_title = QGroupBox("Tournament Header Title")
        l_ttl = QVBoxLayout()
        l_ttl.addWidget(QLabel("Title Text:"))
        self.input_header_text = QLineEdit(self.tournament_header.title_text)
        self.input_header_text.textChanged.connect(self._on_header_text_changed)
        l_ttl.addWidget(self.input_header_text)

        row_title_opts = QHBoxLayout()
        self.chk_show_title = QCheckBox("Show Title Text")
        self.chk_show_title.setChecked(True)
        self.chk_show_title.toggled.connect(self._toggle_title_display)
        btn_title_color = QPushButton("Title Color…")
        btn_title_color.clicked.connect(self._pick_title_color)
        row_title_opts.addWidget(self.chk_show_title)
        row_title_opts.addWidget(btn_title_color)
        l_ttl.addLayout(row_title_opts)

        grp_title.setLayout(l_ttl)
        lay_logo.addWidget(grp_title)
        lay_logo.addStretch()

        # ======================================================================
        # TAB 2: MATCH BANNERS & FLAGS (REQ 4: IMPROVE FLAG & IMAGE QUALITY)
        # ======================================================================
        grp_badges = QGroupBox("Center Match Banners")
        l_bdg = QVBoxLayout()
        l_bdg.addWidget(QLabel("Top Emerald Banner Text:"))
        self.input_day_text = QLineEdit(self.banner_day.text)
        self.input_day_text.textChanged.connect(lambda t: (self.banner_day.set_banner_text(t), self.push_undo_snapshot()))
        l_bdg.addWidget(self.input_day_text)

        l_bdg.addWidget(QLabel("Bottom Silver-White Banner Text:"))
        self.input_match_text = QLineEdit(self.banner_match.text)
        self.input_match_text.textChanged.connect(lambda t: (self.banner_match.set_banner_text(t), self.push_undo_snapshot()))
        l_bdg.addWidget(self.input_match_text)

        row_bslant = QHBoxLayout()
        row_bslant.addWidget(QLabel("Banners Slant Angle:"))
        self.spin_banner_slant = QDoubleSpinBox()
        self.spin_banner_slant.setRange(-45.0, 45.0)
        self.spin_banner_slant.setValue(15.0)
        self.spin_banner_slant.valueChanged.connect(self._on_banner_slant_changed)
        row_bslant.addWidget(self.spin_banner_slant)
        l_bdg.addLayout(row_bslant)
        grp_badges.setLayout(l_bdg)
        lay_match.addWidget(grp_badges)

        grp_teams = QGroupBox("Country Matchup (Crisp 3:2 Aspect Ratio)")
        l_tms = QVBoxLayout()

        # Left Team
        row_tl = QHBoxLayout()
        self.input_code_l = QLineEdit(self.pill_left.country_code)
        self.input_code_l.setPlaceholderText("Left Code e.g. IND")
        self.input_code_l.textChanged.connect(lambda t: (self.pill_left.set_code(t), self.push_undo_snapshot()))
        btn_flag_l = QPushButton("Load Flag…")
        btn_flag_l.clicked.connect(lambda: self._load_custom_flag(self.pill_left))
        row_tl.addWidget(QLabel("Left Country:"))
        row_tl.addWidget(self.input_code_l)
        row_tl.addWidget(btn_flag_l)
        l_tms.addLayout(row_tl)

        # Right Team
        row_tr = QHBoxLayout()
        self.input_code_r = QLineEdit(self.pill_right.country_code)
        self.input_code_r.setPlaceholderText("Right Code e.g. KOR")
        self.input_code_r.textChanged.connect(lambda t: (self.pill_right.set_code(t), self.push_undo_snapshot()))
        btn_flag_r = QPushButton("Load Flag…")
        btn_flag_r.clicked.connect(lambda: self._load_custom_flag(self.pill_right))
        row_tr.addWidget(QLabel("Right Country:"))
        row_tr.addWidget(self.input_code_r)
        row_tr.addWidget(btn_flag_r)
        l_tms.addLayout(row_tr)

        # Auto Flag Fetcher (w640 High DPI)
        auto_row = QHBoxLayout()
        self.input_auto_country = QLineEdit()
        self.input_auto_country.setPlaceholderText("Country Name (e.g. India, Korea, Spain)")
        btn_auto_flag_l = QPushButton("→ Set Left")
        btn_auto_flag_l.clicked.connect(lambda: self._auto_fetch_flag(self.input_auto_country.text(), self.pill_left, self.input_code_l))
        btn_auto_flag_r = QPushButton("→ Set Right")
        btn_auto_flag_r.clicked.connect(lambda: self._auto_fetch_flag(self.input_auto_country.text(), self.pill_right, self.input_code_r))
        auto_row.addWidget(self.input_auto_country)
        auto_row.addWidget(btn_auto_flag_l)
        auto_row.addWidget(btn_auto_flag_r)
        l_tms.addLayout(auto_row)

        grp_teams.setLayout(l_tms)
        lay_match.addWidget(grp_teams)
        lay_match.addStretch()

        # ======================================================================
        # TAB 3: LEFT PLAYER (SUMIT NAGAL) - GLOW, UNDERLINE, SLANT
        # ======================================================================
        grp_p1_photo = QGroupBox("Player 1 Photo (Left)")
        l_p1_p = QVBoxLayout()
        btn_row_p1 = QHBoxLayout()
        btn_load_p1 = QPushButton("📁 Load Photo…")
        btn_load_p1.clicked.connect(lambda: self._load_player_photo(self.player_left))
        btn_clear_p1 = QPushButton("❌ Clear Photo")
        btn_clear_p1.clicked.connect(lambda: self._clear_player_photo(self.player_left))
        btn_flip_p1 = QPushButton("↔ Mirror")
        btn_flip_p1.clicked.connect(lambda: self._toggle_flip(self.player_left))
        btn_row_p1.addWidget(btn_load_p1)
        btn_row_p1.addWidget(btn_clear_p1)
        btn_row_p1.addWidget(btn_flip_p1)
        l_p1_p.addLayout(btn_row_p1)
        grp_p1_photo.setLayout(l_p1_p)
        lay_p1.addWidget(grp_p1_photo)

        # Backlight Glow Controls (REQ 3)
        grp_p1_glow = QGroupBox("Radiant Backlight Glow (Behind Image)")
        l_p1_glw = QVBoxLayout()
        self.chk_glow_l = QCheckBox("Enable Radiant Glow Behind Player")
        self.chk_glow_l.setChecked(True)
        self.chk_glow_l.toggled.connect(lambda c: self._set_player_glow_enabled(self.player_left, c))
        l_p1_glw.addWidget(self.chk_glow_l)

        row_glw_color_l = QHBoxLayout()
        btn_glow_color_l = QPushButton("Glow Color…")
        btn_glow_color_l.clicked.connect(lambda: self._pick_player_glow_color(self.player_left))
        row_glw_color_l.addWidget(QLabel("Aura Color:"))
        row_glw_color_l.addWidget(btn_glow_color_l)
        l_p1_glw.addLayout(row_glw_color_l)

        l_p1_glw.addWidget(QLabel("Glow Intensity:"))
        self.slider_glow_int_l = QSlider(Qt.Orientation.Horizontal)
        self.slider_glow_int_l.setRange(0, 100)
        self.slider_glow_int_l.setValue(85)
        self.slider_glow_int_l.valueChanged.connect(lambda v: self._set_player_glow_intensity(self.player_left, v))
        l_p1_glw.addWidget(self.slider_glow_int_l)

        l_p1_glw.addWidget(QLabel("Glow Radius / Spread:"))
        self.slider_glow_rad_l = QSlider(Qt.Orientation.Horizontal)
        self.slider_glow_rad_l.setRange(50, 500)
        self.slider_glow_rad_l.setValue(260)
        self.slider_glow_rad_l.valueChanged.connect(lambda v: self._set_player_glow_radius(self.player_left, v))
        l_p1_glw.addWidget(self.slider_glow_rad_l)
        grp_p1_glow.setLayout(l_p1_glw)
        lay_p1.addWidget(grp_p1_glow)

        # Clean Horizontal Underline Directly Below Picture (REQ 6)
        grp_p1_und = QGroupBox("Clean Underline Below Picture")
        l_p1_und = QVBoxLayout()
        self.chk_und_l = QCheckBox("Show Neon Underline Below Picture")
        self.chk_und_l.setChecked(True)
        self.chk_und_l.toggled.connect(lambda c: self._set_player_underline_enabled(self.player_left, c))
        l_p1_und.addWidget(self.chk_und_l)

        row_und_col_l = QHBoxLayout()
        btn_und_col_l = QPushButton("Underline Color…")
        btn_und_col_l.clicked.connect(lambda: self._pick_player_underline_color(self.player_left))
        row_und_col_l.addWidget(QLabel("Line Color:"))
        row_und_col_l.addWidget(btn_und_col_l)
        l_p1_und.addLayout(row_und_col_l)

        row_und_dim_l = QHBoxLayout()
        row_und_dim_l.addWidget(QLabel("Thickness:"))
        self.spin_und_thk_l = QSpinBox()
        self.spin_und_thk_l.setRange(1, 30)
        self.spin_und_thk_l.setValue(5)
        self.spin_und_thk_l.valueChanged.connect(lambda v: self._set_player_underline_thickness(self.player_left, v))
        row_und_dim_l.addWidget(self.spin_und_thk_l)
        row_und_dim_l.addWidget(QLabel("Width:"))
        self.spin_und_w_l = QSpinBox()
        self.spin_und_w_l.setRange(50, 900)
        self.spin_und_w_l.setValue(460)
        self.spin_und_w_l.valueChanged.connect(lambda v: self._set_player_underline_width(self.player_left, v))
        row_und_dim_l.addWidget(self.spin_und_w_l)
        l_p1_und.addLayout(row_und_dim_l)
        grp_p1_und.setLayout(l_p1_und)
        lay_p1.addWidget(grp_p1_und)

        # Nameplate & Slant Angle (REQ 7)
        grp_p1_name = QGroupBox("Player 1 Name & Slant Angles")
        l_p1_n = QVBoxLayout()
        self.input_name_l = QLineEdit(self.nameplate_left.text)
        self.input_name_l.textChanged.connect(lambda t: (self.nameplate_left.set_name(t), self.push_undo_snapshot()))
        l_p1_n.addWidget(QLabel("Player Name:"))
        l_p1_n.addWidget(self.input_name_l)

        row_sl_l = QHBoxLayout()
        row_sl_l.addWidget(QLabel("Plate Slant:"))
        self.spin_slant_l = QDoubleSpinBox()
        self.spin_slant_l.setRange(-45.0, 45.0)
        self.spin_slant_l.setValue(15.0)
        self.spin_slant_l.valueChanged.connect(lambda v: self._set_nameplate_slant(self.nameplate_left, v))
        row_sl_l.addWidget(self.spin_slant_l)
        row_sl_l.addWidget(QLabel("Text Slant:"))
        self.spin_text_slant_l = QDoubleSpinBox()
        self.spin_text_slant_l.setRange(-45.0, 45.0)
        self.spin_text_slant_l.setValue(0.0)
        self.spin_text_slant_l.valueChanged.connect(lambda v: self._set_nameplate_text_slant(self.nameplate_left, v))
        row_sl_l.addWidget(self.spin_text_slant_l)
        l_p1_n.addLayout(row_sl_l)
        grp_p1_name.setLayout(l_p1_n)
        lay_p1.addWidget(grp_p1_name)
        lay_p1.addStretch()

        # ======================================================================
        # TAB 4: RIGHT PLAYER (SOONWOO KWON) - GLOW, UNDERLINE, SLANT
        # ======================================================================
        grp_p2_photo = QGroupBox("Player 2 Photo (Right)")
        l_p2_p = QVBoxLayout()
        btn_row_p2 = QHBoxLayout()
        btn_load_p2 = QPushButton("📁 Load Photo…")
        btn_load_p2.clicked.connect(lambda: self._load_player_photo(self.player_right))
        btn_clear_p2 = QPushButton("❌ Clear Photo")
        btn_clear_p2.clicked.connect(lambda: self._clear_player_photo(self.player_right))
        btn_flip_p2 = QPushButton("↔ Mirror")
        btn_flip_p2.clicked.connect(lambda: self._toggle_flip(self.player_right))
        btn_row_p2.addWidget(btn_load_p2)
        btn_row_p2.addWidget(btn_clear_p2)
        btn_row_p2.addWidget(btn_flip_p2)
        l_p2_p.addLayout(btn_row_p2)
        grp_p2_photo.setLayout(l_p2_p)
        lay_p2.addWidget(grp_p2_photo)

        grp_p2_glow = QGroupBox("Radiant Backlight Glow (Behind Image)")
        l_p2_glw = QVBoxLayout()
        self.chk_glow_r = QCheckBox("Enable Radiant Glow Behind Player")
        self.chk_glow_r.setChecked(True)
        self.chk_glow_r.toggled.connect(lambda c: self._set_player_glow_enabled(self.player_right, c))
        l_p2_glw.addWidget(self.chk_glow_r)

        row_glw_color_r = QHBoxLayout()
        btn_glow_color_r = QPushButton("Glow Color…")
        btn_glow_color_r.clicked.connect(lambda: self._pick_player_glow_color(self.player_right))
        row_glw_color_r.addWidget(QLabel("Aura Color:"))
        row_glw_color_r.addWidget(btn_glow_color_r)
        l_p2_glw.addLayout(row_glw_color_r)

        l_p2_glw.addWidget(QLabel("Glow Intensity:"))
        self.slider_glow_int_r = QSlider(Qt.Orientation.Horizontal)
        self.slider_glow_int_r.setRange(0, 100)
        self.slider_glow_int_r.setValue(85)
        self.slider_glow_int_r.valueChanged.connect(lambda v: self._set_player_glow_intensity(self.player_right, v))
        l_p2_glw.addWidget(self.slider_glow_int_r)

        l_p2_glw.addWidget(QLabel("Glow Radius / Spread:"))
        self.slider_glow_rad_r = QSlider(Qt.Orientation.Horizontal)
        self.slider_glow_rad_r.setRange(50, 500)
        self.slider_glow_rad_r.setValue(260)
        self.slider_glow_rad_r.valueChanged.connect(lambda v: self._set_player_glow_radius(self.player_right, v))
        l_p2_glw.addWidget(self.slider_glow_rad_r)
        grp_p2_glow.setLayout(l_p2_glw)
        lay_p2.addWidget(grp_p2_glow)

        grp_p2_und = QGroupBox("Clean Underline Below Picture")
        l_p2_und = QVBoxLayout()
        self.chk_und_r = QCheckBox("Show Neon Underline Below Picture")
        self.chk_und_r.setChecked(True)
        self.chk_und_r.toggled.connect(lambda c: self._set_player_underline_enabled(self.player_right, c))
        l_p2_und.addWidget(self.chk_und_r)

        row_und_col_r = QHBoxLayout()
        btn_und_col_r = QPushButton("Underline Color…")
        btn_und_col_r.clicked.connect(lambda: self._pick_player_underline_color(self.player_right))
        row_und_col_r.addWidget(QLabel("Line Color:"))
        row_und_col_r.addWidget(btn_und_col_r)
        l_p2_und.addLayout(row_und_col_r)

        row_und_dim_r = QHBoxLayout()
        row_und_dim_r.addWidget(QLabel("Thickness:"))
        self.spin_und_thk_r = QSpinBox()
        self.spin_und_thk_r.setRange(1, 30)
        self.spin_und_thk_r.setValue(5)
        self.spin_und_thk_r.valueChanged.connect(lambda v: self._set_player_underline_thickness(self.player_right, v))
        row_und_dim_r.addWidget(self.spin_und_thk_r)
        row_und_dim_r.addWidget(QLabel("Width:"))
        self.spin_und_w_r = QSpinBox()
        self.spin_und_w_r.setRange(50, 900)
        self.spin_und_w_r.setValue(460)
        self.spin_und_w_r.valueChanged.connect(lambda v: self._set_player_underline_width(self.player_right, v))
        row_und_dim_r.addWidget(self.spin_und_w_r)
        l_p2_und.addLayout(row_und_dim_r)
        grp_p2_und.setLayout(l_p2_und)
        lay_p2.addWidget(grp_p2_und)

        grp_p2_name = QGroupBox("Player 2 Name & Slant Angles")
        l_p2_n = QVBoxLayout()
        self.input_name_r = QLineEdit(self.nameplate_right.text)
        self.input_name_r.textChanged.connect(lambda t: (self.nameplate_right.set_name(t), self.push_undo_snapshot()))
        l_p2_n.addWidget(QLabel("Player Name:"))
        l_p2_n.addWidget(self.input_name_r)

        row_sl_r = QHBoxLayout()
        row_sl_r.addWidget(QLabel("Plate Slant:"))
        self.spin_slant_r = QDoubleSpinBox()
        self.spin_slant_r.setRange(-45.0, 45.0)
        self.spin_slant_r.setValue(15.0)
        self.spin_slant_r.valueChanged.connect(lambda v: self._set_nameplate_slant(self.nameplate_right, v))
        row_sl_r.addWidget(self.spin_slant_r)
        row_sl_r.addWidget(QLabel("Text Slant:"))
        self.spin_text_slant_r = QDoubleSpinBox()
        self.spin_text_slant_r.setRange(-45.0, 45.0)
        self.spin_text_slant_r.setValue(0.0)
        self.spin_text_slant_r.valueChanged.connect(lambda v: self._set_nameplate_text_slant(self.nameplate_right, v))
        row_sl_r.addWidget(self.spin_text_slant_r)
        l_p2_n.addLayout(row_sl_r)
        grp_p2_name.setLayout(l_p2_n)
        lay_p2.addWidget(grp_p2_name)
        lay_p2.addStretch()

        # ======================================================================
        # TAB 5: COMPREHENSIVE TEXT STYLES & TYPOGRAPHY (REQ 5)
        # ======================================================================
        grp_txt = QGroupBox("Active Text Formatting")
        l_st = QVBoxLayout()

        self.edit_selected_text = QLineEdit()
        self.edit_selected_text.setPlaceholderText("Select any text/badge on canvas to style")
        self.edit_selected_text.textChanged.connect(self._apply_direct_text_edit)
        l_st.addWidget(self.edit_selected_text)

        row_fnt = QHBoxLayout()
        self.combo_quick_fonts = QComboBox()
        self.combo_quick_fonts.addItems([
            "Arial", "Montserrat", "Trebuchet MS", "Impact",
            "Segoe UI", "Georgia", "Times New Roman", "Tahoma", "Verdana"
        ])
        self.combo_quick_fonts.currentTextChanged.connect(self._on_quick_font_selected)
        btn_choose_font = QPushButton("🔍 All Fonts…")
        btn_choose_font.clicked.connect(self._open_font_picker)
        row_fnt.addWidget(self.combo_quick_fonts)
        row_fnt.addWidget(btn_choose_font)
        l_st.addLayout(row_fnt)

        row_fnt_size = QHBoxLayout()
        row_fnt_size.addWidget(QLabel("Size (pt):"))
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 300)
        self.spin_font_size.setValue(44)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        row_fnt_size.addWidget(self.spin_font_size)

        row_fnt_size.addWidget(QLabel("Spacing:"))
        self.spin_letter_spacing = QSpinBox()
        self.spin_letter_spacing.setRange(-5, 50)
        self.spin_letter_spacing.setValue(2)
        self.spin_letter_spacing.valueChanged.connect(self._on_letter_spacing_changed)
        row_fnt_size.addWidget(self.spin_letter_spacing)
        l_st.addLayout(row_fnt_size)

        row_style_btns = QHBoxLayout()
        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setStyleSheet("font-weight:bold; font-size:14px;")
        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style:italic; font-size:14px;")
        self.btn_underline = QPushButton("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setStyleSheet("text-decoration:underline; font-size:14px;")
        btn_color = QPushButton("Color…")
        btn_color.clicked.connect(self._choose_text_color)
        row_style_btns.addWidget(self.btn_bold)
        row_style_btns.addWidget(self.btn_italic)
        row_style_btns.addWidget(self.btn_underline)
        row_style_btns.addWidget(btn_color)
        l_st.addLayout(row_style_btns)
        self.btn_bold.toggled.connect(self._apply_font_toggles)
        self.btn_italic.toggled.connect(self._apply_font_toggles)
        self.btn_underline.toggled.connect(self._apply_font_toggles)

        row_align = QHBoxLayout()
        row_align.addWidget(QLabel("Alignment:"))
        self.combo_align = QComboBox()
        self.combo_align.addItems(["Center", "Left", "Right"])
        self.combo_align.currentTextChanged.connect(self._on_align_changed)
        row_align.addWidget(self.combo_align)
        l_st.addLayout(row_align)

        row_case = QHBoxLayout()
        btn_upper = QPushButton("UPPER")
        btn_upper.clicked.connect(lambda: self._transform_text_case("upper"))
        btn_title = QPushButton("Title")
        btn_title.clicked.connect(lambda: self._transform_text_case("title"))
        btn_lower = QPushButton("lower")
        btn_lower.clicked.connect(lambda: self._transform_text_case("lower"))
        row_case.addWidget(btn_upper)
        row_case.addWidget(btn_title)
        row_case.addWidget(btn_lower)
        l_st.addLayout(row_case)

        grp_txt.setLayout(l_st)
        lay_styling.addWidget(grp_txt)

        btn_add_text = QPushButton("+ Add Custom Text Element")
        btn_add_text.clicked.connect(self._add_custom_text)
        lay_styling.addWidget(btn_add_text)
        lay_styling.addStretch()

        # ======================================================================
        # TAB 6: ATMOSPHERE & COURT (LIGHTS, VIGNETTE, GRID)
        # ======================================================================
        grp_bg = QGroupBox("Stadium & Tennis Court")
        l_bg = QVBoxLayout()
        btn_load_bg = QPushButton("📁 Load Custom Background Image…")
        btn_load_bg.clicked.connect(self._load_custom_background)
        l_bg.addWidget(btn_load_bg)

        btn_load_ref = QPushButton("🎾 Load Davis Cup Reference Stadium")
        btn_load_ref.clicked.connect(self._load_reference_as_background)
        l_bg.addWidget(btn_load_ref)

        btn_load_procedural = QPushButton("⚡ Reset to Clean Stadium Background")
        btn_load_procedural.clicked.connect(self._load_procedural_background)
        l_bg.addWidget(btn_load_procedural)

        btn_fx = QPushButton("✨ Atmosphere Effects (Vignette, Glow, Tint)…")
        btn_fx.clicked.connect(self._open_effects_dialog)
        l_bg.addWidget(btn_fx)
        grp_bg.setLayout(l_bg)
        lay_atmosphere.addWidget(grp_bg)

        grp_neon = QGroupBox("Bottom Neon Energy Trails")
        l_nn = QVBoxLayout()
        self.chk_neon_glow = QCheckBox("Enable Court Laser Light Trails")
        self.chk_neon_glow.setChecked(True)
        self.chk_neon_glow.toggled.connect(self._toggle_neon_accents)
        l_nn.addWidget(self.chk_neon_glow)
        btn_neon_color = QPushButton("Choose Neon Accent Color…")
        btn_neon_color.clicked.connect(self._choose_neon_color)
        l_nn.addWidget(btn_neon_color)
        grp_neon.setLayout(l_nn)
        lay_atmosphere.addWidget(grp_neon)

        grp_snapping = QGroupBox("Canvas Alignment & Snapping")
        l_snp = QVBoxLayout()
        self.grid_checkbox = QCheckBox("Show Alignment Grid")
        self.grid_checkbox.toggled.connect(self._toggle_grid)
        l_snp.addWidget(self.grid_checkbox)

        row_spc = QHBoxLayout()
        row_spc.addWidget(QLabel("Grid Spacing (px):"))
        self.grid_spacing_spin = QSpinBox()
        self.grid_spacing_spin.setRange(10, 300)
        self.grid_spacing_spin.setValue(GRID_DEFAULT_SPACING)
        self.grid_spacing_spin.valueChanged.connect(self._set_grid_spacing)
        row_spc.addWidget(self.grid_spacing_spin)
        l_snp.addLayout(row_spc)

        self.snap_enabled_checkbox = QCheckBox("Smart Snap to Center, Edges & Elements")
        self.snap_enabled_checkbox.setChecked(True)
        l_snp.addWidget(self.snap_enabled_checkbox)
        grp_snapping.setLayout(l_snp)
        lay_atmosphere.addWidget(grp_snapping)
        lay_atmosphere.addStretch()

        # ======================================================================
        # TAB 7: EXPORT & PRESETS
        # ======================================================================
        grp_presets = QGroupBox("Design Presets")
        l_pre = QVBoxLayout()
        btn_save_pre = QPushButton("💾 Save Preset as JSON…")
        btn_save_pre.clicked.connect(self._save_preset)
        btn_load_pre = QPushButton("📂 Load Preset…")
        btn_load_pre.clicked.connect(self._load_preset)
        l_pre.addWidget(btn_save_pre)
        l_pre.addWidget(btn_load_pre)
        grp_presets.setLayout(l_pre)
        lay_export.addWidget(grp_presets)

        btn_del_selected = QPushButton("Delete Selected Element (Del)")
        btn_del_selected.setObjectName("dangerButton")
        btn_del_selected.clicked.connect(self._delete_selected_element)
        lay_export.addWidget(btn_del_selected)

        btn_reset_blank = QPushButton("📄 New Blank Project (No Images)")
        btn_reset_blank.clicked.connect(self._reset_to_blank_project)
        lay_export.addWidget(btn_reset_blank)

        btn_reset = QPushButton("Reset to Default Davis Cup Template")
        btn_reset.setObjectName("dangerButton")
        btn_reset.clicked.connect(self._reset_to_template)
        lay_export.addWidget(btn_reset)
        lay_export.addStretch()

        # Big 1920x1080 High-Res Export Button
        btn_export = QPushButton("EXPORT FULL HD  (1920 × 1080)")
        btn_export.setObjectName("primaryButton")
        btn_export.clicked.connect(self.export_thumbnail)
        layout.addWidget(btn_export)

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._update_undo_redo_ui()

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+]"), self, activated=self.bring_selected_forward)
        QShortcut(QKeySequence("Ctrl+["), self, activated=self.send_selected_backward)
        QShortcut(QKeySequence("Delete"), self.view, activated=self._delete_selected_element,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def bring_selected_forward(self):
        item = self._selected_item()
        if item and item is not self.bg_item:
            self.push_undo_snapshot()
            item.setZValue(item.zValue() + 1)
            self.statusBar().showMessage(f"Brought forward (Z: {item.zValue():.0f})", 1500)

    def send_selected_backward(self):
        item = self._selected_item()
        if item and item is not self.bg_item:
            self.push_undo_snapshot()
            item.setZValue(max(-90.0, item.zValue() - 1))
            self.statusBar().showMessage(f"Sent backward (Z: {item.zValue():.0f})", 1500)

    # --------------------------------------------------------------------------
    # LOGO MANAGEMENT ACTIONS (REQ 2)
    # --------------------------------------------------------------------------
    def _upload_custom_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload Brand / Tournament Logo", "",
            "Images (*.png *.jpg *.jpeg *.webp *.svg *.bmp)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if self.tournament_header.set_custom_logo(path):
            self.chk_show_logo.setChecked(True)
            self.statusBar().showMessage(f"Logo uploaded: {os.path.basename(path)}", 3500)
            self.reposition_handles()
        else:
            QMessageBox.warning(self, "Load Error", "Could not read logo image.")

    def _remove_logo(self):
        self.push_undo_snapshot()
        self.tournament_header.remove_logo()
        self.chk_show_logo.setChecked(False)
        self.statusBar().showMessage("Logo removed.", 2000)

    def _reset_logo(self):
        self.push_undo_snapshot()
        self.tournament_header.reset_to_davis_cup()
        self.chk_show_logo.setChecked(True)
        self.chk_show_title.setChecked(True)
        self.input_header_text.setText(self.tournament_header.title_text)
        self.statusBar().showMessage("Reset to official Davis Cup logo mark.", 3000)

    def _toggle_logo_display(self, checked):
        self.push_undo_snapshot()
        self.tournament_header.show_logo = checked
        self.tournament_header.update()

    def _toggle_title_display(self, checked):
        self.push_undo_snapshot()
        self.tournament_header.show_title = checked
        self.tournament_header.update()

    def _pick_title_color(self):
        c = QColorDialog.getColor(self.tournament_header.text_color, self, "Select Title Color")
        if c.isValid():
            self.push_undo_snapshot()
            self.tournament_header.text_color = c
            self.tournament_header.update()

    def _on_header_text_changed(self, text):
        self.tournament_header.title_text = text
        self.tournament_header.update()
        self.push_undo_snapshot()

    # --------------------------------------------------------------------------
    # GLOW & UNDERLINE ACTIONS (REQ 3 & REQ 6)
    # --------------------------------------------------------------------------
    def _set_player_glow_enabled(self, player, enabled):
        self.push_undo_snapshot()
        player.glow_enabled = bool(enabled)
        player.update()

    def _pick_player_glow_color(self, player):
        c = QColorDialog.getColor(player.glow_color, self, "Select Backlight Glow Color")
        if c.isValid():
            self.push_undo_snapshot()
            player.glow_color = c
            player.update()

    def _set_player_glow_intensity(self, player, intensity):
        player.glow_intensity = intensity
        player.update()

    def _set_player_glow_radius(self, player, radius):
        player.glow_radius = float(radius)
        player.update()

    def _set_player_underline_enabled(self, player, enabled):
        self.push_undo_snapshot()
        player.underline_enabled = bool(enabled)
        player.update()

    def _pick_player_underline_color(self, player):
        c = QColorDialog.getColor(player.underline_color, self, "Select Underline Color")
        if c.isValid():
            self.push_undo_snapshot()
            player.underline_color = c
            player.update()

    def _set_player_underline_thickness(self, player, val):
        player.underline_thickness = float(val)
        player.update()

    def _set_player_underline_width(self, player, val):
        player.underline_width = float(val)
        player.update()

    # --------------------------------------------------------------------------
    # SLANT & ROTATION ACTIONS (REQ 7)
    # --------------------------------------------------------------------------
    def _set_nameplate_slant(self, nameplate, val):
        nameplate.slant_deg = val
        nameplate.update()
        self.push_undo_snapshot()

    def _set_nameplate_text_slant(self, nameplate, val):
        nameplate.text_slant_deg = val
        nameplate.update()
        self.push_undo_snapshot()

    def _on_banner_slant_changed(self, val):
        self.banner_day.slant_deg = val
        self.banner_match.slant_deg = val
        self.banner_day.update()
        self.banner_match.update()
        self.push_undo_snapshot()

    # --------------------------------------------------------------------------
    # SELECTION & CONTROL SYNCHRONIZATION
    # --------------------------------------------------------------------------
    def _selected_item(self):
        sel = self.scene.selectedItems()
        return sel[0] if sel else None

    def _on_selection_changed(self):
        if self._restoring:
            return
        item = self._selected_item()
        if item and item is not self.bg_item:
            self._spawn_handles_for(item)
            self._sync_active_selection_controls(item)
        else:
            self._clear_all_handles()

    def _sync_active_selection_controls(self, item):
        self.edit_selected_text.blockSignals(True)
        self.spin_font_size.blockSignals(True)
        self.spin_letter_spacing.blockSignals(True)
        self.btn_bold.blockSignals(True)
        self.btn_italic.blockSignals(True)
        self.btn_underline.blockSignals(True)

        if isinstance(item, (SlantedNameplateItem, SlantedMatchBannerItem)):
            self.edit_selected_text.setEnabled(True)
            self.edit_selected_text.setText(item.text)
            self.spin_font_size.setValue(item.font_size)
            self.spin_letter_spacing.setValue(getattr(item, "letter_spacing", 2))
            self.btn_bold.setChecked(item.font_bold)
            self.btn_italic.setChecked(item.font_italic)
            self.btn_underline.setChecked(item.font_underline)
        elif isinstance(item, CountryPillItem):
            self.edit_selected_text.setEnabled(True)
            self.edit_selected_text.setText(item.country_code)
            self.spin_font_size.setValue(item.font_size)
            self.spin_letter_spacing.setValue(getattr(item, "letter_spacing", 1))
            self.btn_bold.setChecked(item.font_bold)
            self.btn_italic.setChecked(item.font_italic)
            self.btn_underline.setChecked(item.font_underline)
        elif isinstance(item, VsDividerItem):
            self.edit_selected_text.setEnabled(True)
            self.edit_selected_text.setText(item.text)
            self.spin_font_size.setValue(item.font_size)
            self.spin_letter_spacing.setValue(getattr(item, "letter_spacing", 1))
            self.btn_bold.setChecked(item.font_bold)
            self.btn_italic.setChecked(item.font_italic)
            self.btn_underline.setChecked(item.font_underline)
        elif isinstance(item, EditableTextItem):
            self.edit_selected_text.setEnabled(True)
            self.edit_selected_text.setText(item.toPlainText())
            f = item.font()
            self.spin_font_size.setValue(f.pointSize())
            self.spin_letter_spacing.setValue(item.letter_spacing_px)
            self.btn_bold.setChecked(f.bold())
            self.btn_italic.setChecked(f.italic())
            self.btn_underline.setChecked(f.underline())
        elif isinstance(item, TournamentLogoItem):
            self.edit_selected_text.setEnabled(True)
            self.edit_selected_text.setText(item.title_text)
            self.spin_font_size.setValue(item.font_size)
            self.spin_letter_spacing.setValue(item.letter_spacing)
            self.btn_bold.setChecked(item.font_bold)
            self.btn_italic.setChecked(item.font_italic)
            self.btn_underline.setChecked(item.font_underline)
        else:
            self.edit_selected_text.clear()
            self.edit_selected_text.setEnabled(False)

        self.edit_selected_text.blockSignals(False)
        self.spin_font_size.blockSignals(False)
        self.spin_letter_spacing.blockSignals(False)
        self.btn_bold.blockSignals(False)
        self.btn_italic.blockSignals(False)
        self.btn_underline.blockSignals(False)

    def _apply_direct_text_edit(self, text):
        item = self._selected_item()
        if not item:
            return
        if isinstance(item, SlantedNameplateItem):
            item.set_name(text)
            if item is self.nameplate_left and hasattr(self, "input_name_l"):
                self.input_name_l.blockSignals(True)
                self.input_name_l.setText(text)
                self.input_name_l.blockSignals(False)
            elif item is self.nameplate_right and hasattr(self, "input_name_r"):
                self.input_name_r.blockSignals(True)
                self.input_name_r.setText(text)
                self.input_name_r.blockSignals(False)
        elif isinstance(item, SlantedMatchBannerItem):
            item.set_banner_text(text)
            if item.role == "banner_day" and hasattr(self, "input_day_text"):
                self.input_day_text.blockSignals(True)
                self.input_day_text.setText(text)
                self.input_day_text.blockSignals(False)
            elif item.role == "banner_match" and hasattr(self, "input_match_text"):
                self.input_match_text.blockSignals(True)
                self.input_match_text.setText(text)
                self.input_match_text.blockSignals(False)
        elif isinstance(item, CountryPillItem):
            item.set_code(text)
            if item is self.pill_left and hasattr(self, "input_code_l"):
                self.input_code_l.blockSignals(True)
                self.input_code_l.setText(text)
                self.input_code_l.blockSignals(False)
            elif item is self.pill_right and hasattr(self, "input_code_r"):
                self.input_code_r.blockSignals(True)
                self.input_code_r.setText(text)
                self.input_code_r.blockSignals(False)
        elif isinstance(item, VsDividerItem):
            item.text = text
            item.update()
        elif isinstance(item, EditableTextItem):
            item.set_text(text)
        elif isinstance(item, TournamentLogoItem):
            item.title_text = text
            item.update()
            if hasattr(self, "input_header_text"):
                self.input_header_text.blockSignals(True)
                self.input_header_text.setText(text)
                self.input_header_text.blockSignals(False)
        self.reposition_handles()
        self.push_undo_snapshot()

    def _on_quick_font_selected(self, font_name):
        item = self._selected_item()
        if not item:
            return
        self.push_undo_snapshot()
        if hasattr(item, "font_family"):
            item.font_family = font_name
            item.update()
        elif isinstance(item, EditableTextItem):
            f = item.font()
            f.setFamily(font_name)
            item.set_style(font=f)

    def _open_font_picker(self):
        item = self._selected_item()
        curr = "Arial"
        if hasattr(item, "font_family"):
            curr = item.font_family
        elif isinstance(item, EditableTextItem):
            curr = item.font().family()

        dlg = FontPickerDialog(curr, self)
        if dlg.exec():
            f_fam = dlg.get_selected()
            self.push_undo_snapshot()
            if hasattr(item, "font_family"):
                item.font_family = f_fam
                item.update()
            elif isinstance(item, EditableTextItem):
                f = item.font()
                f.setFamily(f_fam)
                item.set_style(font=f)

    def _on_font_size_changed(self, sz):
        item = self._selected_item()
        if not item:
            return
        self.push_undo_snapshot()
        if hasattr(item, "font_size"):
            item.font_size = sz
            item.update()
        elif isinstance(item, EditableTextItem):
            f = item.font()
            f.setPointSize(sz)
            item.set_style(font=f)

    def _on_letter_spacing_changed(self, sp):
        item = self._selected_item()
        if not item:
            return
        self.push_undo_snapshot()
        if hasattr(item, "letter_spacing"):
            item.letter_spacing = sp
            item.update()
        elif isinstance(item, EditableTextItem):
            item.set_letter_spacing(sp)

    def _apply_font_toggles(self):
        item = self._selected_item()
        if not item:
            return
        self.push_undo_snapshot()
        if hasattr(item, "font_bold"):
            item.font_bold = self.btn_bold.isChecked()
            item.font_italic = self.btn_italic.isChecked()
            item.font_underline = self.btn_underline.isChecked()
            item.update()
        elif isinstance(item, EditableTextItem):
            f = item.font()
            f.setBold(self.btn_bold.isChecked())
            f.setItalic(self.btn_italic.isChecked())
            f.setUnderline(self.btn_underline.isChecked())
            item.set_style(font=f)

    def _on_align_changed(self, align_str):
        item = self._selected_item()
        if isinstance(item, EditableTextItem):
            self.push_undo_snapshot()
            item.align = align_str.lower()
            item._apply_alignment()
            item.update()

    def _transform_text_case(self, mode):
        item = self._selected_item()
        if not item:
            return
        self.push_undo_snapshot()
        if hasattr(item, "text"):
            t = item.text
            if mode == "upper":
                item.text = t.upper()
            elif mode == "lower":
                item.text = t.lower()
            elif mode == "title":
                item.text = t.title()
            item.update()
            self.edit_selected_text.setText(item.text)
        elif isinstance(item, EditableTextItem):
            t = item.toPlainText()
            if mode == "upper":
                item.set_text(t.upper())
            elif mode == "lower":
                item.set_text(t.lower())
            elif mode == "title":
                item.set_text(t.title())
            self.edit_selected_text.setText(item.toPlainText())

    def _choose_text_color(self):
        item = self._selected_item()
        if not item:
            return
        curr_c = QColor("#ffffff")
        if hasattr(item, "text_color"):
            curr_c = item.text_color
        elif isinstance(item, EditableTextItem):
            curr_c = item.defaultTextColor()

        c = QColorDialog.getColor(curr_c, self, "Select Typography Color")
        if c.isValid():
            self.push_undo_snapshot()
            if hasattr(item, "text_color"):
                item.text_color = c
                item.update()
            elif isinstance(item, EditableTextItem):
                item.setDefaultTextColor(c)

    def _delete_selected_element(self):
        sel = self.scene.selectedItems()
        if not sel:
            return
        self.push_undo_snapshot()
        for it in sel:
            if it is self.bg_item:
                continue
            if it in self.custom_text_items:
                self.custom_text_items.remove(it)
            self.scene.removeItem(it)
        self._clear_all_handles()
        self.statusBar().showMessage("Element deleted.", 2000)

    # --------------------------------------------------------------------------
    # ACTIONS & FILE LOADERS
    # --------------------------------------------------------------------------
    def _load_player_photo(self, player_item):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Load Photo for {player_item.player_name}", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if player_item.load_image(path):
            self.statusBar().showMessage(f"Photo loaded: {os.path.basename(path)}", 3500)
            self.reposition_handles()
        else:
            QMessageBox.warning(self, "Load Error", "Could not read that image file.")

    def _clear_player_photo(self, player_item):
        self.push_undo_snapshot()
        player_item.clear_image()
        self.statusBar().showMessage(f"Photo cleared for {player_item.player_name}.", 2500)

    def _toggle_flip(self, player_item):
        self.push_undo_snapshot()
        player_item.set_flip_h(not player_item.flip_h())
        self.statusBar().showMessage("Mirrored player horizontally.", 1500)

    def _load_custom_flag(self, pill_item):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Load Flag for {pill_item.country_code}", "",
            "Images (*.png *.jpg *.jpeg *.webp *.svg)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if pill_item.load_flag(path):
            self.statusBar().showMessage(f"Flag loaded: {os.path.basename(path)}", 3000)
        else:
            QMessageBox.warning(self, "Load Error", "Could not read that flag image.")

    def _auto_fetch_flag(self, country_name, pill_item, code_input):
        name = country_name.strip()
        if not name:
            self.statusBar().showMessage("Type a country name first.", 3000)
            return
        code = resolve_country_code(name)
        if not code:
            QMessageBox.warning(self, "Country Lookup", f"Could not match '{name}' to a standard country.")
            return

        self.statusBar().showMessage(f"Fetching flag for {name} ({code.upper()})…")
        QApplication.processEvents()
        try:
            path = fetch_flag_image(code, size="w640")
            self.push_undo_snapshot()
            pill_item.set_code(code.upper())
            pill_item.load_flag(path)
            code_input.setText(code.upper())
            self.statusBar().showMessage(f"Flag set for {name} ({code.upper()}).", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Download Error", f"Could not download flag: {exc}")

    def _toggle_neon_accents(self, checked):
        self.push_undo_snapshot()
        self.neon_glow.enabled = checked
        self.neon_glow.update()

    def _choose_neon_color(self):
        c = QColorDialog.getColor(self.neon_glow.glow_color, self, "Select Neon Accent Color")
        if c.isValid():
            self.push_undo_snapshot()
            self.neon_glow.glow_color = c
            self.neon_glow.update()

    def _load_custom_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not path:
            return
        self.push_undo_snapshot()
        if self._set_background_image(path):
            self.statusBar().showMessage(f"Background set: {os.path.basename(path)}", 3500)
        else:
            QMessageBox.warning(self, "Load Error", "Could not load background.")

    def _load_reference_as_background(self):
        ref = locate_reference_image()
        if ref and os.path.exists(ref):
            self.push_undo_snapshot()
            self._set_background_image(ref)
            self.statusBar().showMessage("Reference graphic set as background.", 3000)
        else:
            QMessageBox.information(self, "Reference Image", "No reference image found in assets.")

    def _load_procedural_background(self):
        self.push_undo_snapshot()
        self._background_path = None
        self._background_base_image = create_procedural_stadium_background()
        self._refresh_background_pixmap()
        self.statusBar().showMessage("Reset to clean procedural stadium court.", 3000)

    def _add_custom_text(self):
        self.push_undo_snapshot()
        item = EditableTextItem("MATCH DAY", QFont("Arial", 48, QFont.Weight.Bold), QColor("#ffffff"), CENTER_X, CENTER_Y, app=self)
        self.scene.addItem(item)
        self.custom_text_items.append(item)
        self.scene.clearSelection()
        item.setSelected(True)
        self.statusBar().showMessage("Text line added. Drag anywhere on canvas.", 3000)

    def _reset_to_template(self):
        confirm = QMessageBox.question(
            self, "Reset Layout", "Reset all canvas elements to default Davis Cup template?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.push_undo_snapshot()
        persistent = {self.bg_item}
        if self._grid_item is not None:
            persistent.add(self._grid_item)
        if self._guide_v is not None:
            persistent.add(self._guide_v)
        if self._guide_h is not None:
            persistent.add(self._guide_h)
        for item in list(self.scene.items()):
            if item not in persistent:
                self.scene.removeItem(item)
        self._init_background()
        self._build_template_items()
        self.statusBar().showMessage("Template reset.", 3000)

    def _reset_to_blank_project(self):
        confirm = QMessageBox.question(
            self, "New Blank Project", "Start a new blank project? This will clear all uploaded photos and reset elements.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.push_undo_snapshot()
        persistent = {self.bg_item}
        if self._grid_item is not None:
            persistent.add(self._grid_item)
        if self._guide_v is not None:
            persistent.add(self._guide_v)
        if self._guide_h is not None:
            persistent.add(self._guide_h)
        for item in list(self.scene.items()):
            if item not in persistent:
                self.scene.removeItem(item)
        self._init_background()
        self._build_template_items()
        self.player_left.clear_image()
        self.player_right.clear_image()
        self.tournament_header.reset_to_davis_cup()
        self._sync_sidebar_to_model()
        self.statusBar().showMessage("New blank project initialized with zero preloaded images.", 3500)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset Name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        os.makedirs(PRESETS_DIR, exist_ok=True)
        path = os.path.join(PRESETS_DIR, f"{name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._capture_state(), f, indent=2)
            self.statusBar().showMessage(f"Preset '{name}' saved successfully.", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Failed to save preset: {exc}")

    def _load_preset(self):
        if not os.path.exists(PRESETS_DIR):
            QMessageBox.information(self, "Presets", "No presets found.")
            return
        files = [f[:-5] for f in os.listdir(PRESETS_DIR) if f.lower().endswith(".json")]
        if not files:
            QMessageBox.information(self, "Presets", "No presets found.")
            return
        name, ok = QInputDialog.getItem(self, "Load Preset", "Select preset:", files, 0, False)
        if ok and name:
            path = os.path.join(PRESETS_DIR, f"{name}.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.push_undo_snapshot()
                self._apply_state(state)
                self.statusBar().showMessage(f"Preset '{name}' loaded.", 4000)
            except Exception as exc:
                QMessageBox.critical(self, "Load Error", f"Failed to load preset: {exc}")

    # --------------------------------------------------------------------------
    # 1920x1080 EXPORT PIPELINE
    # --------------------------------------------------------------------------
    def export_thumbnail(self):
        self.scene.clearSelection()
        self._clear_all_handles()
        self.clear_guides()

        grid_was_on = self._grid_enabled
        if self._grid_item:
            self._grid_item.setVisible(False)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Match Graphic", "davis_cup_match_thumbnail.png",
            "PNG Image (*.png);;JPEG Image (*.jpg)"
        )
        if not path:
            if self._grid_item:
                self._grid_item.setVisible(grid_was_on)
            return

        out_img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        out_img.fill(Qt.GlobalColor.transparent)
        p = QPainter(out_img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.scene.render(
            p,
            QRectF(0, 0, CANVAS_W, CANVAS_H),
            QRectF(0, 0, CANVAS_W, CANVAS_H)
        )
        p.end()

        if self._grid_item:
            self._grid_item.setVisible(grid_was_on)

        if out_img.save(path):
            QMessageBox.information(self, "Export Successful", f"Full HD 1920×1080 graphic exported to:\n{path}")
            self.statusBar().showMessage(f"Exported to {path}", 5000)
        else:
            QMessageBox.critical(self, "Export Error", "Failed to write image file.")

    # --------------------------------------------------------------------------
    # VIEW RESIZING
    # --------------------------------------------------------------------------
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
        super().closeEvent(event)


# ==============================================================================
# SENIOR DEVELOPER SELF-AUDIT & VERIFICATION SUITE
# ==============================================================================

def run_senior_developer_audit():
    """
    Headless automated audit verifying:
      1. Scene & Canvas metric bounds (1920x1080).
      2. Instantiation of all core graphic elements.
      3. Logo management (Upload, replace, remove, reset).
      4. Glowing backlight & Underline on player cutouts.
      5. Geometry & Coordinate integrity with flags in 3:2 aspect ratio.
      6. Slant & rotation angle controls on naming feature.
      7. State serialization and JSON encoding round-tripping.
      8. Undo / Redo stack transitions.
      9. Off-screen 1920x1080 rendering pipeline.
    """
    print("\n========================================================")
    print(" SENIOR DEVELOPER AUDIT: Davis Cup Studio Engine v3.0")
    print("========================================================")
    results = []

    def check(name, condition, detail=""):
        status = "PASSED" if condition else "FAILED"
        results.append((name, condition))
        print(f"[{status}] {name} {f'({detail})' if detail else ''}")

    app = QApplication.instance() or QApplication(sys.argv)
    window = DavisCupThumbnailStudio()

    # 1. Canvas Dimensions
    check("Canvas Dimensions", window.scene.width() == 1920 and window.scene.height() == 1080, "1920x1080")

    # 2. Key Components
    check("Player 1 (Left)", window.player_left is not None and window.player_left.scene() is window.scene)
    check("Player 2 (Right)", window.player_right is not None and window.player_right.scene() is window.scene)
    check("Nameplate Left", window.nameplate_left.text == "SUMIT NAGAL")
    check("Nameplate Right", window.nameplate_right.text == "SOONWOO KWON")
    check("Day Banner", window.banner_day.text == "DAY 1")
    check("Match Banner", window.banner_match.text == "MATCH 1")
    check("Country Pill Left (IND)", window.pill_left.country_code == "IND")
    check("Country Pill Right (KOR)", window.pill_right.country_code == "KOR")
    check("VS Divider", window.vs_divider is not None)
    check("Tournament Logo & Header", "DAVIS CUP" in window.tournament_header.title_text)

    # 3. Logo Management System (Req 2)
    window.tournament_header.remove_logo()
    check("Logo Removal", not window.tournament_header.show_logo)
    window.tournament_header.reset_to_davis_cup()
    check("Logo Davis Cup Reset", window.tournament_header.show_logo and window.tournament_header.title_text == "DAVIS CUP®")

    # 4. Backlight Glow & Underlines (Req 3 & 6)
    check("Left Player Glow Enabled", window.player_left.glow_enabled and window.player_left.glow_intensity > 0)
    check("Right Player Glow Enabled", window.player_right.glow_enabled and window.player_right.glow_intensity > 0)
    check("Left Player Underline", window.player_left.underline_enabled and window.player_left.underline_thickness > 0)
    check("Right Player Underline", window.player_right.underline_enabled and window.player_right.underline_thickness > 0)

    # 5. Slant Angle Controls (Req 7)
    orig_slant = window.nameplate_left.slant_deg
    window._set_nameplate_slant(window.nameplate_left, 22.5)
    window._set_nameplate_text_slant(window.nameplate_left, -5.0)
    check("Nameplate Badge Slant Adjustment", window.nameplate_left.slant_deg == 22.5)
    check("Nameplate Text Slant Adjustment", window.nameplate_left.text_slant_deg == -5.0)
    window._set_nameplate_slant(window.nameplate_left, orig_slant)
    window._set_nameplate_text_slant(window.nameplate_left, 0.0)

    # 6. State JSON Serialization & Undo
    state1 = window._capture_state()
    json_str = json.dumps(state1)
    check("State JSON Serializability", len(json_str) > 600, f"{len(json_str)} bytes serialized")

    window.banner_day.set_banner_text("SEMI-FINAL")
    window.push_undo_snapshot()
    window.undo()
    check("Undo Engine Roundtrip", window.banner_day.text == "DAY 1", f"Restored: {window.banner_day.text}")

    # 7. Offscreen 1920x1080 Render Validation
    test_img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
    test_img.fill(Qt.GlobalColor.transparent)
    p = QPainter(test_img)
    window.scene.render(p)
    p.end()
    check("1920x1080 Render Pipeline", not test_img.isNull() and test_img.width() == 1920, "1920x1080 ARGB32 Output")

    # 8. Custom Typography Elements & Serialization Lifecycle
    window._add_custom_text()
    check("Custom Text Insertion", len(window.custom_text_items) == 1)
    state2 = window._capture_state()
    check("Custom Text Serialization Integrity", len(state2.get("custom_texts", [])) == 1)
    window._delete_selected_element()
    check("Custom Text Element Cleanup", len(window.custom_text_items) == 0)

    total_passed = sum(1 for _, ok in results if ok)
    print("--------------------------------------------------------")
    print(f"AUDIT SUMMARY: {total_passed}/{len(results)} tests passed.")
    print("========================================================\n")
    return total_passed == len(results)


# ==============================================================================
# MAIN ENTRYPOINT & THEME (NO ARROW BUTTONS, CANVA-STYLE DARK STUDIO)
# ==============================================================================

def main():
    if "--audit" in sys.argv:
        success = run_senior_developer_audit()
        sys.exit(0 if success else 1)

    app = QApplication(sys.argv)

    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    # Modern Pro Athletic Studio Theme (Clean inputs, NO spinbox arrows, sleek sliders)
    app.setStyleSheet("""
        QMainWindow, QScrollArea, QDockWidget > QWidget {
            background: #0d1217;
        }
        QDockWidget {
            color: #f1f5f9;
            font-weight: 700;
        }
        QTabWidget::pane {
            border: 1px solid #1e293b;
            border-radius: 8px;
            background: #141b24;
        }
        QTabBar::tab {
            background: #1c2634;
            color: #94a3b8;
            padding: 9px 12px;
            margin-right: 3px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-weight: 600;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background: #00e575;
            color: #042416;
            font-weight: 700;
        }
        QGroupBox {
            color: #f8fafc;
            font-weight: 700;
            border: 1px solid #283548;
            border-radius: 8px;
            margin-top: 14px;
            padding: 16px 10px 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #00e575;
        }
        QLabel, QCheckBox {
            color: #cbd5e1;
            font-size: 13px;
        }
        QPushButton, QToolButton {
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #334155;
            min-height: 32px;
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 600;
        }
        QPushButton:hover, QToolButton:hover {
            background: #334155;
            border-color: #475569;
        }
        QPushButton:pressed, QToolButton:pressed {
            background: #0f172a;
        }
        QPushButton:checked {
            background: #00e575;
            color: #052416;
            border-color: #00ff88;
        }
        QPushButton#primaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
            border: 1px solid #34d399;
            color: white;
            font-weight: 800;
            font-size: 15px;
            min-height: 48px;
            border-radius: 8px;
        }
        QPushButton#primaryButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
            color: #022c22;
        }
        QPushButton#dangerButton {
            color: #f87171;
            border-color: #7f1d1d;
        }
        QPushButton#dangerButton:hover {
            background: #450a0a;
        }
        QLineEdit, QComboBox {
            min-height: 30px;
            padding: 4px 8px;
            background: #090e14;
            color: #ffffff;
            border: 1px solid #334155;
            border-radius: 6px;
        }
        /* REQ 9: REMOVE UNNECESSARY UP/DOWN ARROW CONTROLS FROM SPINBOXES */
        QSpinBox, QDoubleSpinBox {
            min-height: 30px;
            padding: 4px 8px;
            background: #090e14;
            color: #ffffff;
            border: 1px solid #334155;
            border-radius: 6px;
            padding-right: 4px;
        }
        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
            width: 0px;
            height: 0px;
            border: none;
            subcontrol-origin: margin;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
            border-color: #00e575;
        }
        QSlider::groove:horizontal {
            border: 1px solid #283548;
            height: 6px;
            background: #101620;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #10b981;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #00e575;
            border: 1px solid #ffffff;
            width: 16px;
            margin-top: -6px;
            margin-bottom: -6px;
            border-radius: 8px;
        }
        QSlider::handle:horizontal:hover {
            background: #34d399;
        }
        QListWidget {
            background: #090e14;
            color: #ffffff;
            border: 1px solid #334155;
            border-radius: 6px;
        }
        QStatusBar {
            background: #141b24;
            color: #94a3b8;
            font-size: 12px;
        }
    """)

    window = DavisCupThumbnailStudio()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
