
# -*- coding: utf-8 -*-
"""
Next Match Generator V1 — Davis Cup Band Editor
=========================================================

Requirements:
    pip install PyQt6 pycountry

Highlights:
- 1920x1080 scene and 3840x2160 export
- Exact Davis Cup inspired "COMING NEXT" band layout
- Editable header, country names, auto flag + country code via pycountry
- Click element -> selected element editor opens automatically
- Whole-band dragging, scaling, undo/redo, presets, and export
"""

import json
import os
import sys
import urllib.request

import pycountry
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QPixmap,
    QKeySequence,
    QShortcut,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

CANVAS_W = 1920
CANVAS_H = 1080
EXPORT_W = 3840
EXPORT_H = 2160
UNDO_LIMIT = 80
STYLE = {'name': 'V1', 'preset_dir': 'next_match_v1_presets', 'default_title': 'COMING NEXT', 'default_left': 'India', 'default_right': 'Korea', 'default_vs': 'VS', 'bg_mode': 'stadium', 'default_band_scale': 100, 'grid_spacing': 80, 'band_default_y': 250, 'header': {'text_y': 10, 'font': 68, 'line_y': 42, 'left_line_x': 205, 'left_line_w': 210, 'right_line_x': 980, 'right_line_w': 210}, 'band': {'x': 95, 'y': 120, 'flag_w': 170, 'flag_h': 110, 'code_w': 250, 'code_h': 112, 'vs_w': 180, 'vs_h': 112, 'gap': 16, 'left_flag_x': 0, 'left_code_x': 195, 'vs_x': 462, 'right_code_x': 660, 'right_flag_x': 930}, 'fonts': {'code': 64, 'vs': 72}, 'overall_width': 1100}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRESET_DIR = os.path.join(SCRIPT_DIR, STYLE["preset_dir"])
FLAG_CACHE_DIR = os.path.join(SCRIPT_DIR, "flag_cache")
os.makedirs(PRESET_DIR, exist_ok=True)
os.makedirs(FLAG_CACHE_DIR, exist_ok=True)

ALIASES = {
    "korea": ("KR", "KOR"),
    "south korea": ("KR", "KOR"),
    "republic of korea": ("KR", "KOR"),
    "india": ("IN", "IND"),
    "usa": ("US", "USA"),
    "u.s.a": ("US", "USA"),
    "united states": ("US", "USA"),
    "uk": ("GB", "GBR"),
    "great britain": ("GB", "GBR"),
    "britain": ("GB", "GBR"),
    "england": ("GB", "GBR"),
    "czechia": ("CZ", "CZE"),
    "czech republic": ("CZ", "CZE"),
    "uae": ("AE", "UAE"),
}

DEFAULTS = {
    "title": STYLE["default_title"],
    "left_country": STYLE["default_left"],
    "right_country": STYLE["default_right"],
    "vs_text": STYLE["default_vs"],
    "band_scale": STYLE["default_band_scale"],
    "background_color": "#FFFFFF",
    "grid_spacing": STYLE["grid_spacing"],
    "band_y": STYLE["band_default_y"],
    "panel_green": "#0A6B45",
    "panel_green_dark": "#074A30",
    "gold": "#D3B55C",
    "white": "#F4F5F1",
    "code_green": "#085839",
    "header_text": "#FFFFFF",
    "line_tint": "#A4D4A5",
}


def load_pixmap_original(path):
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        return QPixmap()
    return QPixmap.fromImage(img)


def resolve_country(text):
    raw = (text or "").strip()
    if not raw:
        return None, None
    key = raw.casefold()
    if key in ALIASES:
        return ALIASES[key]
    if len(raw) == 2:
        c = pycountry.countries.get(alpha_2=raw.upper())
        if c:
            return c.alpha_2, getattr(c, "alpha_3", c.alpha_2)
    if len(raw) == 3:
        c = pycountry.countries.get(alpha_3=raw.upper())
        if c:
            return c.alpha_2, c.alpha_3
    try:
        c = pycountry.countries.lookup(raw)
        return c.alpha_2, getattr(c, "alpha_3", c.alpha_2)
    except LookupError:
        q = raw.casefold()
        for c in pycountry.countries:
            names = [getattr(c, "name", ""), getattr(c, "official_name", ""), getattr(c, "common_name", "")]
            if any(q in n.casefold() for n in names if n):
                return c.alpha_2, getattr(c, "alpha_3", c.alpha_2)
    return None, raw[:3].upper() if raw else ""


def get_flag_cache_path(alpha2, width=320):
    return os.path.join(FLAG_CACHE_DIR, f"{alpha2.lower()}_w{width}.png")


def ensure_flag_pixmap(country_text, width=320):
    alpha2, alpha3 = resolve_country(country_text)
    if not alpha2:
        return QPixmap(), alpha3 or (country_text or "")[:3].upper()
    path = get_flag_cache_path(alpha2, width)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        url = f"https://flagcdn.com/w{width}/{alpha2.lower()}.png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r, open(path, "wb") as f:
                f.write(r.read())
        except Exception:
            pass
    if os.path.exists(path):
        return load_pixmap_original(path), alpha3
    return QPixmap(), alpha3


def rounded_flag_pixmap(pixmap, w, h, radius=22):
    out = QImage(max(2, w), max(2, h), QImage.Format.Format_ARGB32)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(path)
    if pixmap.isNull():
        p.fillPath(path, QColor("#F2F2F2"))
        p.setPen(QPen(QColor("#8A8A8A"), 2))
        p.drawPath(path)
    else:
        src = pixmap.toImage().scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawImage(0, 0, src)
    p.end()
    return QPixmap.fromImage(out)


def make_text(text, size, weight=QFont.Weight.Bold, color="#FFFFFF", italic=False, letter=0):
    item = QGraphicsTextItem(text)
    font = QFont("Arial", int(size))
    font.setWeight(weight)
    font.setItalic(italic)
    if letter:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter)
    item.setFont(font)
    item.setDefaultTextColor(QColor(color))
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    return item


def preserve_center_while_changing_text_size(item, new_size):
    old_center = item.mapToParent(item.boundingRect().center())
    font = item.font()
    font.setPointSize(max(4, int(new_size)))
    item.setFont(font)
    new_center = item.mapToParent(item.boundingRect().center())
    item.setPos(item.pos() + (old_center - new_center))


class BandView(QGraphicsView):
    def __init__(self, owner, scene):
        super().__init__(scene)
        self.owner = owner

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            item = self.scene().itemAt(scene_pos, self.transform())
            self.owner.handle_canvas_click(item)
        super().mousePressEvent(event)


class BandGroup(QGraphicsItemGroup):
    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.owner is not None:
            return self.owner._snap_band_position(value)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.owner is not None:
            self.owner.sync_position_controls_from_band()
        return result

    def mousePressEvent(self, event):
        if self.owner is not None:
            self.owner._begin_history_action()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.owner is not None:
            self.owner._commit_history_now()


class NextMatchGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Next Match Generator {STYLE['name']} — Davis Cup")
        self.resize(1600, 940)

        self.selected_edit_item = None
        self._undo_stack = []
        self._redo_stack = []
        self._history_state = None
        self._action_start_state = None
        self._restoring_history = False
        self._syncing_position = False
        self._grid_enabled = False
        self._snap_enabled = True
        self._grid_spacing = DEFAULTS["grid_spacing"]
        self._history_timer = QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(250)
        self._history_timer.timeout.connect(self._commit_history_now)

        self.background_color = QColor(DEFAULTS["background_color"])
        self.background_image_path = None
        self.background_source_pixmap = QPixmap()

        self.panel_green = QColor(DEFAULTS["panel_green"])
        self.panel_green_dark = QColor(DEFAULTS["panel_green_dark"])
        self.gold = QColor(DEFAULTS["gold"])
        self.white = QColor(DEFAULTS["white"])
        self.code_green = QColor(DEFAULTS["code_green"])
        self.header_text_color = QColor(DEFAULTS["header_text"])
        self.line_tint = QColor(DEFAULTS["line_tint"])

        self.band_scale_pct = DEFAULTS["band_scale"]
        self.editable = {}
        self.items_by_name = {}

        self.scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
        self.view = BandView(self, self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QBrush(QColor("#202226")))
        self.setCentralWidget(self.view)

        self.canvas_bg = QGraphicsPixmapItem()
        self.canvas_bg.setZValue(-300)
        self.canvas_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.canvas_bg)
        self._set_default_background()

        self.bg_image_item = QGraphicsPixmapItem()
        self.bg_image_item.setZValue(-290)
        self.bg_image_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.bg_image_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.bg_image_item)

        self.grid_item = QGraphicsPathItem()
        self.grid_item.setZValue(-275)
        self.grid_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.grid_item)
        self._rebuild_grid()

        self.band = BandGroup(self)
        self.scene.addItem(self.band)
        self._build_band()
        self._apply_band_scale()
        self._snap_band_to_default_position()

        self._build_sidebar()
        self.sync_position_controls_from_band()
        self._wire_history_tracking()
        self._history_state = self._capture_state()
        self._action_start_state = None
        self._update_history_buttons()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready — click any band element to edit it. Change countries to auto-update flags + codes.")
        self._fit_view()

    def _set_default_background(self):
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        img.fill(self.background_color)
        self.canvas_bg.setPixmap(QPixmap.fromImage(img))

    def _choose_background_color(self):
        color = QColorDialog.getColor(self.background_color, self, "Choose Background Color")
        if color.isValid():
            self._begin_history_action()
            self.background_color = QColor(color)
            self._set_default_background()
            self.canvas_bg.update()
            self.scene.update()
            self._update_background_color_button()
            self._commit_history_now()

    def _update_background_color_button(self):
        if not hasattr(self, "background_color_btn"):
            return
        c = self.background_color.name().upper()
        text_color = "#111111" if self.background_color.lightness() > 150 else "#FFFFFF"
        self.background_color_btn.setText(f"Background Color  {c}")
        self.background_color_btn.setStyleSheet(f"background:{c};color:{text_color};font-weight:800;")

    def _load_background(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Background", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        pix = load_pixmap_original(path)
        if pix.isNull():
            QMessageBox.warning(self, "Image Error", "Could not load background image.")
            return
        self._begin_history_action()
        self.background_image_path = path
        self._set_background_source(pix)
        self.bg_image_item.setVisible(True)
        self._commit_history_now()

    def _clear_background(self):
        self._begin_history_action()
        self.background_image_path = None
        self.background_source_pixmap = QPixmap()
        self.bg_image_item.setPixmap(QPixmap())
        self.bg_image_item.setVisible(False)
        self._commit_history_now()

    def _set_background_source(self, pixmap):
        self.background_source_pixmap = pixmap
        self.bg_image_item.setPixmap(pixmap)
        if pixmap.isNull():
            return
        scale = max(CANVAS_W / pixmap.width(), CANVAS_H / pixmap.height())
        self.bg_image_item.setScale(scale)
        self.bg_image_item.setPos((CANVAS_W - pixmap.width() * scale) / 2, (CANVAS_H - pixmap.height() * scale) / 2)

    def _rebuild_grid(self):
        path = QPainterPath()
        spacing = max(10, int(self._grid_spacing))
        for x in range(0, CANVAS_W+1, spacing):
            path.moveTo(x, 0)
            path.lineTo(x, CANVAS_H)
        for y in range(0, CANVAS_H+1, spacing):
            path.moveTo(0, y)
            path.lineTo(CANVAS_W, y)
        self.grid_item.setPath(path)
        pen = QPen(QColor(65, 130, 210, 105), 1)
        pen.setCosmetic(True)
        self.grid_item.setPen(pen)
        self.grid_item.setVisible(self._grid_enabled)

    def _toggle_grid(self, checked):
        self._grid_enabled = bool(checked)
        self._rebuild_grid()

    def _set_grid_spacing(self, value):
        self._grid_spacing = int(value)
        self._rebuild_grid()

    def _snap_band_position(self, value):
        if not self._grid_enabled or not self._snap_enabled or QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
            return value
        spacing = max(10, int(self._grid_spacing))
        return QPointF(round(value.x()/spacing)*spacing, round(value.y()/spacing)*spacing)

    def _register_editable(self, item, name, kind, logical_group=None):
        self.editable[item] = {"name": name, "kind": kind, "logical_group": logical_group}
        self.items_by_name[name] = item
        item.setData(100, 100)

    def _add_shape(self, path, brush, pen, z, name, logical_group=None):
        item = QGraphicsPathItem(path)
        item.setBrush(brush)
        item.setPen(pen)
        item.setZValue(z)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setTransformOriginPoint(item.boundingRect().center())
        self.band.addToGroup(item)
        self._register_editable(item, name, "shape", logical_group)
        return item

    def _add_line_rect(self, x, y, w, h, color, name):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), h/2, h/2)
        return self._add_shape(path, QBrush(color), QPen(Qt.PenStyle.NoPen), 2, name, "line_tint")

    def _slanted_panel_path(self, x, y, w, h, skew=22, reverse=False):
        path = QPainterPath()
        if not reverse:
            path.moveTo(x+skew, y)
            path.lineTo(x+w, y)
            path.lineTo(x+w-skew, y+h)
            path.lineTo(x, y+h)
        else:
            path.moveTo(x, y)
            path.lineTo(x+w-skew, y)
            path.lineTo(x+w, y+h)
            path.lineTo(x+skew, y+h)
        path.closeSubpath()
        return path

    def _hex_vs_path(self, x, y, w, h, inset=22):
        path = QPainterPath()
        path.moveTo(x+inset, y)
        path.lineTo(x+w-inset, y)
        path.lineTo(x+w, y+h/2)
        path.lineTo(x+w-inset, y+h)
        path.lineTo(x+inset, y+h)
        path.lineTo(x, y+h/2)
        path.closeSubpath()
        return path

    def _rounded_rect_path(self, x, y, w, h, radius):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), radius, radius)
        return path

    def _build_band(self):
        cfg_h = STYLE["header"]
        cfg = STYLE["band"]
        self.header_line_left = None
        self.header_line_right = None
        self.header_text = make_text(DEFAULTS["title"], cfg_h["font"], QFont.Weight.Black, self.header_text_color.name(), False, 3)
        self.header_text.setZValue(6)
        self.header_text.setTransformOriginPoint(self.header_text.boundingRect().center())
        self.band.addToGroup(self.header_text)
        self._register_editable(self.header_text, "Header Text", "text", "header_text")
        self._center_header_text(cfg_h["text_y"])

        y = cfg["y"]
        self.left_flag_border = self._add_shape(self._rounded_rect_path(cfg["left_flag_x"], y+2, cfg["flag_w"], cfg["flag_h"], 24), QBrush(Qt.GlobalColor.transparent), QPen(self.gold, 4), 4, "Left Flag Border", "gold")
        self.right_flag_border = self._add_shape(self._rounded_rect_path(cfg["right_flag_x"], y+2, cfg["flag_w"], cfg["flag_h"], 24), QBrush(Qt.GlobalColor.transparent), QPen(self.gold, 4), 4, "Right Flag Border", "gold")

        self.left_flag_item = QGraphicsPixmapItem()
        self.left_flag_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.left_flag_item.setZValue(3)
        self.band.addToGroup(self.left_flag_item)
        self.right_flag_item = QGraphicsPixmapItem()
        self.right_flag_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.right_flag_item.setZValue(3)
        self.band.addToGroup(self.right_flag_item)

        left_panel_path = self._rounded_rect_path(cfg["left_code_x"], y, cfg["code_w"], cfg["code_h"], 22)
        right_panel_path = self._rounded_rect_path(cfg["right_code_x"], y, cfg["code_w"], cfg["code_h"], 22)
        pen = QPen(self.gold, 4)
        self.left_code_panel = self._add_shape(left_panel_path, QBrush(self.white), pen, 3, "Left Code Panel", "white")
        self.right_code_panel = self._add_shape(right_panel_path, QBrush(self.white), pen, 3, "Right Code Panel", "white")
        self.left_panel_inner = self._add_shape(self._rounded_rect_path(cfg["left_code_x"]+10, y+10, cfg["code_w"]-20, cfg["code_h"]-20, 16), QBrush(Qt.GlobalColor.transparent), QPen(QColor(255,255,255,70), 1), 3, "Left Panel Inner", "white")
        self.right_panel_inner = self._add_shape(self._rounded_rect_path(cfg["right_code_x"]+10, y+10, cfg["code_w"]-20, cfg["code_h"]-20, 16), QBrush(Qt.GlobalColor.transparent), QPen(QColor(255,255,255,70), 1), 3, "Right Panel Inner", "white")

        vs_grad = QLinearGradient(cfg["vs_x"], y, cfg["vs_x"], y+cfg["vs_h"])
        vs_grad.setColorAt(0.0, QColor(18, 112, 67))
        vs_grad.setColorAt(0.55, QColor(7, 82, 47))
        vs_grad.setColorAt(1.0, QColor(8, 56, 35))
        self.vs_panel = self._add_shape(self._hex_vs_path(cfg["vs_x"], y, cfg["vs_w"], cfg["vs_h"], 22), QBrush(vs_grad), QPen(self.gold, 4), 3, "VS Panel", "panel_green")
        streak = QPainterPath()
        streak.addRoundedRect(QRectF(cfg["vs_x"]+cfg["vs_w"]*0.38, y+8, cfg["vs_w"]*0.24, cfg["vs_h"]-16), 18, 18)
        self.vs_streak = self._add_shape(streak, QBrush(QColor(255, 225, 120, 28)), QPen(Qt.PenStyle.NoPen), 3, "VS Glow", "gold")

        self.left_code_text = make_text("IND", STYLE["fonts"]["code"], QFont.Weight.Black, self.code_green.name(), True)
        self.right_code_text = make_text("KOR", STYLE["fonts"]["code"], QFont.Weight.Black, self.code_green.name(), True)
        self.vs_text_item = make_text(DEFAULTS["vs_text"], STYLE["fonts"]["vs"], QFont.Weight.Black, "#F0D06A", True)
        for item, name in ((self.left_code_text, "Left Code"), (self.right_code_text, "Right Code"), (self.vs_text_item, "VS Text")):
            item.setZValue(6)
            item.setTransformOriginPoint(item.boundingRect().center())
            self.band.addToGroup(item)
            self._register_editable(item, name, "text", "code_green" if "Code" in name else "gold")
        self._center_text_in_path(self.left_code_text, left_panel_path)
        self._center_text_in_path(self.right_code_text, right_panel_path)
        self._center_text_in_path(self.vs_text_item, self._hex_vs_path(cfg["vs_x"], y, cfg["vs_w"], cfg["vs_h"], 22))

        self.update_country_band()

    def _center_header_text(self, y):
        r = self.header_text.boundingRect()
        overall_w = max(STYLE["overall_width"], 1080)
        start_x = (overall_w - r.width())/2 + 115
        self.header_text.setPos(start_x, y)

    def _center_text_in_path(self, text_item, path):
        b = path.boundingRect()
        r = text_item.boundingRect()
        text_item.setPos(b.center().x() - r.width()/2, b.center().y() - r.height()/2 - 4)

    def update_country_band(self):
        cfg = STYLE["band"]
        left_name = self.left_country_edit.text() if hasattr(self, 'left_country_edit') else DEFAULTS['left_country']
        right_name = self.right_country_edit.text() if hasattr(self, 'right_country_edit') else DEFAULTS['right_country']
        left_pix, left_code = ensure_flag_pixmap(left_name, 320)
        right_pix, right_code = ensure_flag_pixmap(right_name, 320)
        self.left_code_text.setPlainText((left_code or "LFT")[:3].upper())
        self.right_code_text.setPlainText((right_code or "RGT")[:3].upper())
        self._center_text_in_path(self.left_code_text, self.left_code_panel.path())
        self._center_text_in_path(self.right_code_text, self.right_code_panel.path())

        left_round = rounded_flag_pixmap(left_pix, cfg["flag_w"], cfg["flag_h"], 23)
        right_round = rounded_flag_pixmap(right_pix, cfg["flag_w"], cfg["flag_h"], 23)
        self.left_flag_item.setPixmap(left_round)
        self.right_flag_item.setPixmap(right_round)
        self.left_flag_item.setPos(cfg["left_flag_x"], cfg["y"]+2)
        self.right_flag_item.setPos(cfg["right_flag_x"], cfg["y"]+2)

    def _resolve_editable(self, item):
        current = item
        while current is not None:
            if current in self.editable:
                return current
            if current is self.band:
                return self.band
            current = current.parentItem()
        return None

    def handle_canvas_click(self, item):
        target = self._resolve_editable(item)
        if target is not None:
            self.select_element_for_editing(target)

    def select_element_for_editing(self, item):
        self.selected_edit_item = item
        self._update_history_buttons()
        if not hasattr(self, "editor_tabs"):
            return
        self.editor_tabs.setCurrentIndex(0)
        if item is self.band:
            self.selected_name_label.setText("WHOLE BAND")
            self.selected_kind_label.setText("Band / match band")
            self.selected_content_edit.setEnabled(False)
            self.selected_content_edit.setText("")
            self.selected_size_spin.setRange(25, 300)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(self.band_scale_pct)
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(False)
            return
        meta = self.editable[item]
        self.selected_name_label.setText(meta["name"].upper())
        self.selected_kind_label.setText(meta["kind"].title())
        if meta["kind"] == "text":
            self.selected_content_edit.setEnabled(True)
            self.selected_content_edit.setText(item.toPlainText())
            self.selected_size_spin.setRange(4, 300)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(item.font().pointSize())
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(True)
        else:
            self.selected_content_edit.setEnabled(False)
            self.selected_content_edit.setText("")
            self.selected_size_spin.setRange(10, 400)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(int(item.data(100) or 100))
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(True)

    def _selected_size_changed(self, value):
        item = self.selected_edit_item
        if item is None:
            return
        if item is self.band:
            self.band_scale_spin.setValue(value)
            return
        meta = self.editable.get(item)
        if not meta:
            return
        if meta["kind"] == "text":
            preserve_center_while_changing_text_size(item, value)
            if item is self.header_text:
                self._center_header_text(self.header_text.y())
        else:
            item.setData(100, value)
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setScale(value / 100.0)

    def _selected_size_minus(self):
        self.selected_size_spin.setValue(self.selected_size_spin.value() - 5)

    def _selected_size_plus(self):
        self.selected_size_spin.setValue(self.selected_size_spin.value() + 5)

    def _selected_content_changed(self):
        item = self.selected_edit_item
        if item is None or item is self.band:
            return
        meta = self.editable.get(item)
        if not meta or meta["kind"] != "text":
            return
        text = self.selected_content_edit.text().upper()
        item.setPlainText(text)
        if item is self.header_text:
            self.title_edit.blockSignals(True)
            self.title_edit.setText(text)
            self.title_edit.blockSignals(False)
            self._center_header_text(self.header_text.y())
        elif item is self.vs_text_item:
            self.vs_edit.blockSignals(True)
            self.vs_edit.setText(text)
            self.vs_edit.blockSignals(False)
            self._center_text_in_path(self.vs_text_item, self.vs_panel.path())
        elif item in (self.left_code_text, self.right_code_text):
            panel = self.left_code_panel.path() if item is self.left_code_text else self.right_code_panel.path()
            self._center_text_in_path(item, panel)

    def _selected_change_color(self):
        item = self.selected_edit_item
        if item is None or item is self.band:
            return
        meta = self.editable.get(item)
        if meta is None:
            return
        current = item.defaultTextColor() if meta["kind"] == "text" else item.brush().color()
        color = QColorDialog.getColor(current, self, f"Color — {meta['name']}")
        if not color.isValid():
            return
        self._begin_history_action()
        group = meta.get("logical_group")
        if group == "panel_green":
            self.panel_green = color
            grad = QLinearGradient(self.vs_panel.boundingRect().topLeft(), self.vs_panel.boundingRect().bottomLeft())
            grad.setColorAt(0.0, color.lighter(130))
            grad.setColorAt(0.55, color)
            grad.setColorAt(1.0, color.darker(150))
            self.vs_panel.setBrush(QBrush(grad))
        elif group == "gold":
            self.gold = color
            for sh in (self.left_flag_border, self.right_flag_border, self.left_code_panel, self.right_code_panel, self.vs_panel):
                pen = sh.pen()
                pen.setColor(color)
                sh.setPen(pen)
            self.vs_text_item.setDefaultTextColor(color.lighter(125))
        elif group == "white":
            self.white = color
            self.left_code_panel.setBrush(QBrush(color))
            self.right_code_panel.setBrush(QBrush(color))
        elif group == "code_green":
            self.code_green = color
            self.left_code_text.setDefaultTextColor(color)
            self.right_code_text.setDefaultTextColor(color)
        elif group == "header_text":
            self.header_text_color = color
            self.header_text.setDefaultTextColor(color)
        elif group == "line_tint":
            self.line_tint = color
            self.header_line_left.setBrush(QBrush(color))
            self.header_line_right.setBrush(QBrush(color))
        else:
            if meta["kind"] == "text":
                item.setDefaultTextColor(color)
            else:
                item.setBrush(QBrush(color))
        self._commit_history_now()

    def _sync_match_controls(self):
        self.header_text.setPlainText(self.title_edit.text().upper())
        self._center_header_text(self.header_text.y())
        self.vs_text_item.setPlainText(self.vs_edit.text().upper())
        self._center_text_in_path(self.vs_text_item, self.vs_panel.path())
        self.update_country_band()

    def _make_spin(self, minimum, maximum, value, suffix="", prefix=""):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setPrefix(prefix)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setKeyboardTracking(False)
        return spin

    def _scroll_tab(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _build_sidebar(self):
        dock = QDockWidget("Band Editor", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(400)
        dock_body = QWidget()
        dock_layout = QVBoxLayout(dock_body)
        dock_layout.setContentsMargins(8, 8, 8, 8)
        dock_layout.setSpacing(8)
        action_row = QHBoxLayout()
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.clicked.connect(self.redo)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.clicked.connect(self.delete_selected)
        action_row.addWidget(self.btn_undo)
        action_row.addWidget(self.btn_redo)
        action_row.addWidget(self.btn_delete)
        dock_layout.addLayout(action_row)

        self.editor_tabs = QTabWidget()
        dock_layout.addWidget(self.editor_tabs, 1)

        selected_page = QWidget()
        selected_root = QVBoxLayout(selected_page)
        self.selected_name_label = QLabel("CLICK AN ELEMENT")
        self.selected_name_label.setStyleSheet("font-size:18px;font-weight:900;color:white;")
        self.selected_kind_label = QLabel("The correct editing controls will open here automatically.")
        self.selected_kind_label.setWordWrap(True)
        self.selected_kind_label.setStyleSheet("color:#9fa7b3;font-size:11px;")
        selected_root.addWidget(self.selected_name_label)
        selected_root.addWidget(self.selected_kind_label)
        selected_root.addWidget(QLabel("Text / content"))
        self.selected_content_edit = QLineEdit()
        self.selected_content_edit.setEnabled(False)
        self.selected_content_edit.textChanged.connect(self._selected_content_changed)
        selected_root.addWidget(self.selected_content_edit)
        size_group = QGroupBox("Size")
        size_layout = QHBoxLayout(size_group)
        minus_btn = QPushButton("−")
        minus_btn.setObjectName("sizeButton")
        minus_btn.clicked.connect(self._selected_size_minus)
        self.selected_size_spin = self._make_spin(1, 400, 100)
        self.selected_size_spin.valueChanged.connect(self._selected_size_changed)
        plus_btn = QPushButton("+")
        plus_btn.setObjectName("sizeButton")
        plus_btn.clicked.connect(self._selected_size_plus)
        size_layout.addWidget(minus_btn)
        size_layout.addWidget(self.selected_size_spin, 1)
        size_layout.addWidget(plus_btn)
        selected_root.addWidget(size_group)
        self.selected_color_btn = QPushButton("Change Selected Element Color")
        self.selected_color_btn.setEnabled(False)
        self.selected_color_btn.clicked.connect(self._selected_change_color)
        selected_root.addWidget(self.selected_color_btn)
        select_band_btn = QPushButton("Edit Whole Band Size")
        select_band_btn.clicked.connect(lambda: self.select_element_for_editing(self.band))
        selected_root.addWidget(select_band_btn)
        selected_root.addStretch()
        self.editor_tabs.addTab(self._scroll_tab(selected_page), "Element")

        match_page = QWidget()
        match_root = QVBoxLayout(match_page)
        form = QFormLayout()
        self.title_edit = QLineEdit(DEFAULTS["title"])
        self.vs_edit = QLineEdit(DEFAULTS["vs_text"])
        self.left_country_edit = QLineEdit(DEFAULTS["left_country"])
        self.right_country_edit = QLineEdit(DEFAULTS["right_country"])
        form.addRow("Header text", self.title_edit)
        form.addRow("VS text", self.vs_edit)
        form.addRow("Left country", self.left_country_edit)
        form.addRow("Right country", self.right_country_edit)
        match_root.addLayout(form)
        update_btn = QPushButton("Update Countries + Codes + Flags")
        update_btn.clicked.connect(self._sync_match_controls)
        match_root.addWidget(update_btn)
        auto_note = QLabel("Country fields use pycountry to resolve the flag and 3-letter country code automatically.")
        auto_note.setWordWrap(True)
        auto_note.setStyleSheet("color:#9fa7b3;font-size:11px;")
        match_root.addWidget(auto_note)
        match_root.addStretch()
        self.editor_tabs.addTab(self._scroll_tab(match_page), "Match")

        band_page = QWidget()
        band_root = QVBoxLayout(band_page)
        band_title = QLabel("CANVAS / POSITION")
        band_title.setStyleSheet("font-size:16px;font-weight:800;color:white;")
        band_root.addWidget(band_title)
        band_size_group = QGroupBox("Whole Band Size")
        band_size_layout = QHBoxLayout(band_size_group)
        band_minus = QPushButton("−")
        band_minus.setObjectName("sizeButton")
        self.band_scale_spin = self._make_spin(25, 300, DEFAULTS["band_scale"], " %")
        band_plus = QPushButton("+")
        band_plus.setObjectName("sizeButton")
        band_minus.clicked.connect(lambda: self.band_scale_spin.setValue(self.band_scale_spin.value() - 5))
        band_plus.clicked.connect(lambda: self.band_scale_spin.setValue(self.band_scale_spin.value() + 5))
        self.band_scale_spin.valueChanged.connect(self._change_band_scale)
        band_size_layout.addWidget(band_minus)
        band_size_layout.addWidget(self.band_scale_spin, 1)
        band_size_layout.addWidget(band_plus)
        band_root.addWidget(band_size_group)

        position_group = QGroupBox("Band Position")
        pos_form = QFormLayout(position_group)
        self.band_x_spin = self._make_spin(-2000, 3000, 0, " px")
        self.band_y_spin = self._make_spin(-1500, 2000, 0, " px")
        self.band_x_spin.valueChanged.connect(self._position_controls_changed)
        self.band_y_spin.valueChanged.connect(self._position_controls_changed)
        pos_form.addRow("X", self.band_x_spin)
        pos_form.addRow("Y", self.band_y_spin)
        band_root.addWidget(position_group)
        pos_buttons = QHBoxLayout()
        snap_btn = QPushButton("Default Position")
        snap_btn.clicked.connect(self._snap_band_to_default_position)
        center_btn = QPushButton("Center X")
        center_btn.clicked.connect(self._center_band_horizontally)
        pos_buttons.addWidget(snap_btn)
        pos_buttons.addWidget(center_btn)
        band_root.addLayout(pos_buttons)

        bg_group = QGroupBox("Background")
        bg_layout = QVBoxLayout(bg_group)
        bg_buttons = QHBoxLayout()
        load_bg = QPushButton("Load BG")
        load_bg.clicked.connect(self._load_background)
        clear_bg = QPushButton("Clear Image")
        clear_bg.clicked.connect(self._clear_background)
        bg_buttons.addWidget(load_bg)
        bg_buttons.addWidget(clear_bg)
        bg_layout.addLayout(bg_buttons)
        self.background_color_btn = QPushButton()
        self.background_color_btn.clicked.connect(self._choose_background_color)
        bg_layout.addWidget(self.background_color_btn)
        self._update_background_color_button()
        band_root.addWidget(bg_group)

        grid_group = QGroupBox("Grid Placement")
        grid_layout = QVBoxLayout(grid_group)
        grid_row = QHBoxLayout()
        self.grid_checkbox = QCheckBox("Show grid")
        self.grid_checkbox.toggled.connect(self._toggle_grid)
        self.grid_spacing_spin = self._make_spin(10, 300, DEFAULTS["grid_spacing"], " px")
        self.grid_spacing_spin.valueChanged.connect(self._set_grid_spacing)
        grid_row.addWidget(self.grid_checkbox)
        grid_row.addWidget(QLabel("Spacing"))
        grid_row.addWidget(self.grid_spacing_spin, 1)
        grid_layout.addLayout(grid_row)
        self.snap_checkbox = QCheckBox("Snap band to grid (hold Alt for free movement)")
        self.snap_checkbox.setChecked(True)
        self.snap_checkbox.toggled.connect(lambda checked: setattr(self, "_snap_enabled", bool(checked)))
        grid_layout.addWidget(self.snap_checkbox)
        band_root.addWidget(grid_group)

        preset_group = QGroupBox("Presets")
        preset_layout = QHBoxLayout(preset_group)
        save_preset = QPushButton("Save")
        save_preset.clicked.connect(self._save_preset)
        load_preset = QPushButton("Load")
        load_preset.clicked.connect(self._load_preset)
        preset_layout.addWidget(save_preset)
        preset_layout.addWidget(load_preset)
        band_root.addWidget(preset_group)

        export_with_bg = QPushButton("DOWNLOAD WITH BG — 4K PNG")
        export_with_bg.setObjectName("exportWithBg")
        export_with_bg.clicked.connect(self._export_with_bg)
        band_root.addWidget(export_with_bg)
        export_no_bg = QPushButton("DOWNLOAD WITHOUT BG — 4K PNG")
        export_no_bg.setObjectName("exportNoBg")
        export_no_bg.clicked.connect(self._export_without_bg)
        band_root.addWidget(export_no_bg)
        band_root.addStretch()
        self.editor_tabs.addTab(self._scroll_tab(band_page), "Canvas")

        dock.setWidget(dock_body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        for spin in dock.findChildren(QSpinBox):
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setKeyboardTracking(False)

        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_shortcut)

    def _apply_band_scale(self):
        self.band.setScale(self.band_scale_pct / 100.0)

    def _change_band_scale(self, value):
        old_center = self.band.sceneBoundingRect().center()
        self.band_scale_pct = int(value)
        self._apply_band_scale()
        new_center = self.band.sceneBoundingRect().center()
        self.band.setPos(self.band.pos() + (old_center - new_center))
        self.sync_position_controls_from_band()
        if self.selected_edit_item is self.band:
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(value)
            self.selected_size_spin.blockSignals(False)

    def _snap_band_to_default_position(self):
        rect = self.band.childrenBoundingRect()
        scale = self.band.scale()
        scaled_w = rect.width() * scale
        x = (CANVAS_W - scaled_w) / 2 - rect.left() * scale
        y = DEFAULTS["band_y"]
        self.band.setPos(x, y)
        self.sync_position_controls_from_band()

    def _center_band_horizontally(self):
        rect = self.band.childrenBoundingRect()
        scale = self.band.scale()
        scaled_w = rect.width() * scale
        x = (CANVAS_W - scaled_w) / 2 - rect.left() * scale
        self.band.setX(x)
        self.sync_position_controls_from_band()

    def sync_position_controls_from_band(self):
        if not hasattr(self, "band_x_spin"):
            return
        self._syncing_position = True
        self.band_x_spin.blockSignals(True)
        self.band_y_spin.blockSignals(True)
        self.band_x_spin.setValue(round(self.band.x()))
        self.band_y_spin.setValue(round(self.band.y()))
        self.band_x_spin.blockSignals(False)
        self.band_y_spin.blockSignals(False)
        self._syncing_position = False

    def _position_controls_changed(self):
        if self._syncing_position:
            return
        self._syncing_position = True
        self.band.setPos(self.band_x_spin.value(), self.band_y_spin.value())
        self._syncing_position = False

    def _wire_history_tracking(self):
        for edit in self.findChildren(QLineEdit):
            edit.textChanged.connect(self._schedule_history_commit)
        for spin in self.findChildren(QSpinBox):
            spin.valueChanged.connect(self._schedule_history_commit)
        for check in self.findChildren(QCheckBox):
            check.toggled.connect(self._schedule_history_commit)

    def _begin_history_action(self):
        if self._restoring_history or self._history_state is None:
            return
        if self._history_timer.isActive():
            self._commit_history_now()
        self._action_start_state = self._capture_state()

    def _schedule_history_commit(self, *_):
        if self._restoring_history or self._history_state is None:
            return
        self._history_timer.start()

    def _commit_history_now(self):
        if self._restoring_history or self._history_state is None:
            return
        self._history_timer.stop()
        current = self._capture_state()
        previous = self._action_start_state or self._history_state
        self._action_start_state = None
        if current == previous:
            self._history_state = current
            self._update_history_buttons()
            return
        self._undo_stack.append(previous)
        self._undo_stack = self._undo_stack[-UNDO_LIMIT:]
        self._redo_stack.clear()
        self._history_state = current
        self._update_history_buttons()

    def undo(self):
        if self._history_timer.isActive():
            self._commit_history_now()

        if not self._undo_stack:
            self.statusBar().showMessage("Nothing to undo", 1500)
            return

        current = self._capture_state()
        target = self._undo_stack.pop()

        self._redo_stack.append(current)
        self._restoring_history = True
        try:
            self._apply_state(target)
        finally:
            self._restoring_history = False

        self._history_state = self._capture_state()
        self._update_history_buttons()
        self.statusBar().showMessage("Undo", 1500)

    def redo(self):
        if self._history_timer.isActive():
            self._commit_history_now()

        if not self._redo_stack:
            self.statusBar().showMessage("Nothing to redo", 1500)
            return

        current = self._capture_state()
        target = self._redo_stack.pop()

        self._undo_stack.append(current)
        self._restoring_history = True
        try:
            self._apply_state(target)
        finally:
            self._restoring_history = False

        self._history_state = self._capture_state()
        self._update_history_buttons()
        self.statusBar().showMessage("Redo", 1500)

    def _restore_history_state(self, state):
        self._history_timer.stop()
        self._action_start_state = None
        self._restoring_history = True
        try:
            self._apply_state(state)
        finally:
            self._restoring_history = False
        self._history_state = self._capture_state()
        self._update_history_buttons()

    def _update_history_buttons(self):
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(bool(self._undo_stack))
            self.btn_redo.setEnabled(bool(self._redo_stack))
            self.btn_delete.setEnabled(self.selected_edit_item is not None and self.selected_edit_item is not self.band)

    def delete_selected(self):
        item = self.selected_edit_item
        if item is None:
            return
        if item is self.band:
            self.statusBar().showMessage("The whole band is protected.", 2000)
            return
        self._begin_history_action()
        item.setVisible(False)
        self.selected_edit_item = None
        self.selected_name_label.setText("NOTHING SELECTED")
        self.selected_kind_label.setText("Use Undo to restore a deleted element.")
        self.selected_content_edit.setEnabled(False)
        self.selected_color_btn.setEnabled(False)
        self._commit_history_now()

    def _delete_shortcut(self):
        if isinstance(QApplication.focusWidget(), (QLineEdit, QSpinBox)):
            return
        self.delete_selected()

    def _capture_state(self):
        shape_scales = {}
        shape_appearances = {}
        text_sizes = {}
        colors = {}
        visibility = {}
        for item, meta in self.editable.items():
            name = meta["name"]
            visibility[name] = item.isVisible()
            if meta["kind"] == "shape":
                shape_scales[name] = int(item.data(100) or 100)
                brush = item.brush()
                pen = item.pen()
                appearance = {
                    "brush_style": brush.style().value,
                    "brush_color": brush.color().name(QColor.NameFormat.HexArgb),
                    "pen_style": pen.style().value,
                    "pen_color": pen.color().name(QColor.NameFormat.HexArgb),
                    "pen_width": pen.widthF(),
                }
                gradient = brush.gradient()
                if isinstance(gradient, QLinearGradient):
                    appearance["linear_gradient"] = {
                        "start": [gradient.start().x(), gradient.start().y()],
                        "end": [gradient.finalStop().x(), gradient.finalStop().y()],
                        "stops": [
                            [position, color.name(QColor.NameFormat.HexArgb)]
                            for position, color in gradient.stops()
                        ],
                    }
                shape_appearances[name] = appearance
                # Retain the old field so presets remain readable by v1/v2.
                colors[name] = (
                    brush.color().name(QColor.NameFormat.HexArgb)
                    if brush.style() != Qt.BrushStyle.NoBrush
                    else pen.color().name(QColor.NameFormat.HexArgb)
                )
            else:
                text_sizes[name] = item.font().pointSize()
                colors[name] = item.defaultTextColor().name()
        return {
            "title": self.title_edit.text(),
            "vs_text": self.vs_edit.text(),
            "left_country": self.left_country_edit.text(),
            "right_country": self.right_country_edit.text(),
            "band_scale": self.band_scale_spin.value(),
            "band_position": [self.band.x(), self.band.y()],
            "background_color": self.background_color.name(),
            "background_image_path": self.background_image_path,
            "shape_scales": shape_scales,
            "shape_appearances": shape_appearances,
            "text_sizes": text_sizes,
            "colors": colors,
            "item_visibility": visibility,
            "grid": {"enabled": self._grid_enabled, "spacing": self._grid_spacing, "snap": self._snap_enabled},
        }

    def _apply_state(self, state):
        self.background_color = QColor(state.get("background_color", DEFAULTS["background_color"]))
        self._set_default_background()
        self._update_background_color_button()
        grid = state.get("grid", {})
        self._grid_enabled = bool(grid.get("enabled", False))
        self._grid_spacing = int(grid.get("spacing", DEFAULTS["grid_spacing"]))
        self._snap_enabled = bool(grid.get("snap", True))
        if hasattr(self, "grid_checkbox"):
            self.grid_checkbox.setChecked(self._grid_enabled)
            self.grid_spacing_spin.setValue(self._grid_spacing)
            self.snap_checkbox.setChecked(self._snap_enabled)
        self._rebuild_grid()
        self.title_edit.setText(str(state.get("title", DEFAULTS["title"])))
        self.vs_edit.setText(str(state.get("vs_text", DEFAULTS["vs_text"])))

        # Restore text fields silently. Do not rebuild flags during undo/redo.
        # Rebuilding flags here caused cached pixmaps to disappear when the
        # network/cache lookup failed during history restore.
        self.left_country_edit.blockSignals(True)
        self.right_country_edit.blockSignals(True)
        self.title_edit.blockSignals(True)
        self.vs_edit.blockSignals(True)

        self.left_country_edit.setText(str(state.get("left_country", DEFAULTS["left_country"])))
        self.right_country_edit.setText(str(state.get("right_country", DEFAULTS["right_country"])))

        self.left_country_edit.blockSignals(False)
        self.right_country_edit.blockSignals(False)
        self.title_edit.blockSignals(False)
        self.vs_edit.blockSignals(False)

        self.header_text.setPlainText(self.title_edit.text().upper())
        self.vs_text_item.setPlainText(self.vs_edit.text().upper())
        self._center_header_text(self.header_text.y())
        self._center_text_in_path(self.vs_text_item, self.vs_panel.path())

        self.band_scale_spin.setValue(int(state.get("band_scale", DEFAULTS["band_scale"])))
        shape_scales = state.get("shape_scales", {})
        shape_appearances = state.get("shape_appearances", {})
        text_sizes = state.get("text_sizes", {})
        colors = state.get("colors", {})
        visibility = state.get("item_visibility", {})
        for item, meta in self.editable.items():
            name = meta["name"]
            item.setVisible(bool(visibility.get(name, True)))
            if meta["kind"] == "shape":
                pct = int(shape_scales.get(name, 100))
                item.setData(100, pct)
                item.setScale(pct / 100.0)
                appearance = shape_appearances.get(name)
                if isinstance(appearance, dict):
                    gradient_data = appearance.get("linear_gradient")
                    if isinstance(gradient_data, dict):
                        start = gradient_data.get("start", [0, 0])
                        end = gradient_data.get("end", [0, 1])
                        gradient = QLinearGradient(
                            float(start[0]), float(start[1]),
                            float(end[0]), float(end[1]),
                        )
                        for position, color_value in gradient_data.get("stops", []):
                            gradient.setColorAt(float(position), QColor(color_value))
                        item.setBrush(QBrush(gradient))
                    else:
                        brush = QBrush(QColor(appearance.get("brush_color", "#00000000")))
                        try:
                            brush.setStyle(Qt.BrushStyle(int(appearance.get("brush_style", Qt.BrushStyle.SolidPattern.value))))
                        except (TypeError, ValueError):
                            pass
                        item.setBrush(brush)

                    pen = QPen(item.pen())
                    pen.setColor(QColor(appearance.get("pen_color", "#00000000")))
                    pen.setWidthF(float(appearance.get("pen_width", pen.widthF())))
                    try:
                        pen.setStyle(Qt.PenStyle(int(appearance.get("pen_style", pen.style().value))))
                    except (TypeError, ValueError):
                        pass
                    item.setPen(pen)
                else:
                    # Legacy states stored one RGB value for both brush and pen.
                    # Never apply that value to transparent/gradient decorations;
                    # doing so was the source of the opaque black blocks.
                    c = colors.get(name)
                    brush = item.brush()
                    if c and brush.style() == Qt.BrushStyle.SolidPattern and brush.color().alpha() > 0:
                        restored = QColor(c)
                        restored.setAlpha(brush.color().alpha())
                        item.setBrush(QBrush(restored))
            else:
                if name in text_sizes:
                    preserve_center_while_changing_text_size(item, int(text_sizes[name]))
                if name in colors:
                    item.setDefaultTextColor(QColor(colors[name]))
        pos = state.get("band_position")
        if isinstance(pos, list) and len(pos) == 2:
            self.band.setPos(float(pos[0]), float(pos[1]))
        else:
            self._snap_band_to_default_position()
        self.sync_position_controls_from_band()
        bg_path = state.get("background_image_path")
        if bg_path and os.path.exists(bg_path):
            pix = load_pixmap_original(bg_path)
            if not pix.isNull():
                self.background_image_path = bg_path
                self._set_background_source(pix)
                self.bg_image_item.setVisible(True)
        else:
            self.background_image_path = None
            self.background_source_pixmap = QPixmap()
            self.bg_image_item.setPixmap(QPixmap())
            self.bg_image_item.setVisible(False)

    def _save_preset(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Preset", os.path.join(PRESET_DIR, f"next_match_{STYLE['name'].lower()}.json"), "JSON Files (*.json)")
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self._capture_state(), f, indent=2)
        self.statusBar().showMessage(f"Preset saved: {path}", 3000)

    def _load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Preset", PRESET_DIR, "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            self._begin_history_action()
            self._apply_state(state)
            self._commit_history_now()
        except Exception as exc:
            QMessageBox.critical(self, "Preset Error", str(exc))

    def _prepare_export(self, include_background):
        selected = self.band.isSelected()
        grid_visible = self.grid_item.isVisible()
        bg_visible = self.bg_image_item.isVisible()
        canvas_visible = self.canvas_bg.isVisible()
        self.band.setSelected(False)
        self.grid_item.setVisible(False)
        if not include_background:
            self.canvas_bg.setVisible(False)
            self.bg_image_item.setVisible(False)
        return selected, grid_visible, bg_visible, canvas_visible

    def _restore_after_export(self, state):
        selected, grid_visible, bg_visible, canvas_visible = state
        self.band.setSelected(selected)
        self.grid_item.setVisible(grid_visible)
        self.bg_image_item.setVisible(bg_visible)
        self.canvas_bg.setVisible(canvas_visible)

    def _render_4k(self, include_background):
        image = QImage(EXPORT_W, EXPORT_H, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        state = self._prepare_export(include_background)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.scene.render(painter, QRectF(0,0,EXPORT_W,EXPORT_H), QRectF(0,0,CANVAS_W,CANVAS_H))
        painter.end()
        self._restore_after_export(state)
        return image

    def _export_with_bg(self):
        path, _ = QFileDialog.getSaveFileName(self, "Download WITH BG — 4K", f"next_match_{STYLE['name'].lower()}_with_bg.png", "PNG Image (*.png)")
        if not path:
            return
        if not path.lower().endswith('.png'):
            path += '.png'
        img = self._render_4k(True)
        if img.save(path):
            QMessageBox.information(self, 'Saved', f'4K PNG WITH background saved:\n{path}')

    def _export_without_bg(self):
        path, _ = QFileDialog.getSaveFileName(self, "Download WITHOUT BG — 4K", f"next_match_{STYLE['name'].lower()}_transparent.png", "PNG Image (*.png)")
        if not path:
            return
        if not path.lower().endswith('.png'):
            path += '.png'
        img = self._render_4k(False)
        if img.save(path):
            QMessageBox.information(self, 'Saved', f'4K transparent PNG saved:\n{path}')

    def _fit_view(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_view()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_view()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QMainWindow, QDockWidget > QWidget, QScrollArea, QTabWidget::pane { background:#17191d; }
        QDockWidget { color:#ffffff; font-weight:700; }
        QLabel, QCheckBox { color:#d9dde5; }
        QGroupBox { color:#f3f4f6; font-weight:700; border:1px solid #353b45; border-radius:8px; margin-top:10px; padding:12px 8px 8px 8px; }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }
        QLineEdit, QSpinBox { background:#101216; color:#ffffff; border:1px solid #404754; border-radius:6px; padding:6px 8px; min-height:29px; }
        QLineEdit:focus, QSpinBox:focus { border-color:#60a5fa; }
        QSpinBox::up-button, QSpinBox::down-button { width:0px; height:0px; border:none; }
        QPushButton { background:#303640; color:#ffffff; border:1px solid #464e5a; border-radius:7px; padding:7px 10px; min-height:30px; }
        QPushButton:hover { background:#3b424d; }
        QPushButton:disabled { color:#737b87; background:#22262c; border-color:#303640; }
        QPushButton#dangerButton { background:#5b2027; border-color:#8f303b; }
        QPushButton#dangerButton:hover { background:#762a34; }
        QPushButton#sizeButton { min-width:42px; max-width:42px; min-height:38px; font-size:22px; font-weight:900; background:#242a32; }
        QPushButton#exportWithBg { background:#157347; border-color:#25a66a; min-height:48px; font-weight:900; font-size:13px; }
        QPushButton#exportNoBg { background:#2563eb; border-color:#60a5fa; min-height:48px; font-weight:900; font-size:13px; }
        QTabBar::tab { background:#252a31; color:#b8bec8; padding:9px 11px; border:1px solid #343a44; }
        QTabBar::tab:selected { background:#3b82f6; color:white; }
        QStatusBar { color:#c9ced7; }
        """
    )
    win = NextMatchGenerator()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        input("Press Enter to close...")
