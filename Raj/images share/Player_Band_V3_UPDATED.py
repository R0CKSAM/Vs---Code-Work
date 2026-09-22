"""
Player Band Generator V3 — Updated Lower Third Editor
======================================================

Requested features implemented:
1. Increase/decrease the complete band size.
2. Click an element -> its editor opens automatically. Resize/recolor that element.
3. YEARS is placed at the bottom-right of the AGE cell.
4. Spin-box up/down arrows are removed.
5. Two high-quality download buttons:
      - WITH BG: 3840x2160 PNG
      - WITHOUT BG: 3840x2160 transparent PNG
6. Clicking an element automatically opens the Selected Element editing tab.
7. Moving the band anywhere is preserved in exports and presets.
8. Player uploads stay at ORIGINAL source resolution. Player resizing is
   non-destructive, so 4K exports do not use a previously downscaled copy.

Requirements:
    pip install PyQt6
"""

import json
import os
import sys

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QPixmap,
    QKeySequence,
    QShortcut,
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

# -----------------------------------------------------------------------------
# Canvas / export
# -----------------------------------------------------------------------------
CANVAS_W = 1920
CANVAS_H = 1080
EXPORT_W = 3840
EXPORT_H = 2160

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRESET_DIR = os.path.join(SCRIPT_DIR, "player_band_presets")

DEFAULTS = {
    "first_name": "SUMIT",
    "last_name": "NAGAL",
    "age": "29",
    "ranking": "XX",
    "plays": "XX",
    "band_scale": 100,
    "bottom_margin": 64,
    "player_height": 178,
    "player_offset_x": 0,
    "player_offset_y": 0,
    "band_green": "#086B3B",
    "accent_green": "#42C233",
    "accent_dark": "#159645",
    "panel_white": "#F3F3EE",
    "stats_green": "#00663A",
    "separator": "#7A9E8C",
    "name_text": "#F5F5F1",
    "background_color": "#FFFFFF",
    "grid_spacing": 80,
}

UNDO_LIMIT = 60

BASE_FONT = {
    "first_name": 18,
    "last_name": 34,
    "label": 15,
    "value": 34,
    "years": 13,
}

BASE_POS = {
    "player_anchor_x": 118,
    "player_feet_y": 121,
    "first_name": (190, 39),
    "last_name": (188, 59),
    "age_label": (612, 36),
    "rank_label": (756, 36),
    "plays_label": (913, 36),
    "age_value": (610, 56),
    "rank_value": (752, 56),
    "plays_value": (910, 56),
}

AGE_CELL_RIGHT = 738
AGE_CELL_BOTTOM = 110


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def make_text(text, size, weight=QFont.Weight.Bold, color="#FFFFFF", italic=False):
    item = QGraphicsTextItem(text)
    font = QFont("Arial", size)
    font.setWeight(weight)
    font.setItalic(italic)
    item.setFont(font)
    item.setDefaultTextColor(QColor(color))
    # Events pass through to the parent band so the complete band remains draggable.
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    return item


def fit_text(item, max_width, default_size, min_size=9):
    font = item.font()
    font.setPointSize(default_size)
    item.setFont(font)
    size = default_size
    while item.boundingRect().width() > max_width and size > min_size:
        size -= 1
        font.setPointSize(size)
        item.setFont(font)


def preserve_center_while_changing_text_size(item, new_size):
    """Change point size while keeping the item's center stable in parent coordinates."""
    old_center = item.mapToParent(item.boundingRect().center())
    font = item.font()
    font.setPointSize(max(4, int(new_size)))
    item.setFont(font)
    new_center = item.mapToParent(item.boundingRect().center())
    delta = old_center - new_center
    item.setPos(item.pos() + delta)


# -----------------------------------------------------------------------------
# Graphics view / group
# -----------------------------------------------------------------------------
class BandView(QGraphicsView):
    """Click detection for automatic element-editor routing."""

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
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(10)

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.owner is not None
            and not getattr(self.owner, "_restoring_history", False)
        ):
            value = self.owner._snap_band_position(value)
        result = super().itemChange(change, value)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and self.owner is not None
            and hasattr(self.owner, "band_x_spin")
            and not getattr(self.owner, "_syncing_position", False)
        ):
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


# -----------------------------------------------------------------------------
# Main window
# -----------------------------------------------------------------------------
class PlayerBandGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Player Band Generator V3 — Lower Third")
        self.resize(1580, 930)

        self.player_image_path = None
        self.player_source_pixmap = QPixmap()   # ORIGINAL upload, never destructively resized
        self.player_display_height = DEFAULTS["player_height"]
        self.background_image_path = None
        self.background_source_pixmap = QPixmap()
        self.background_color = QColor(DEFAULTS["background_color"])
        self._syncing_position = False
        self._restoring_history = False
        self.selected_edit_item = None

        self._undo_stack = []
        self._redo_stack = []
        self._history_state = None
        self._action_start_state = None
        self._history_timer = QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(300)
        self._history_timer.timeout.connect(self._commit_history_now)

        self._grid_enabled = False
        self._snap_enabled = True
        self._grid_spacing = DEFAULTS["grid_spacing"]

        # Logical colors
        self.band_color = QColor(DEFAULTS["band_green"])
        self.accent_color = QColor(DEFAULTS["accent_green"])
        self.accent_dark = QColor(DEFAULTS["accent_dark"])
        self.panel_color = QColor(DEFAULTS["panel_white"])
        self.stats_color = QColor(DEFAULTS["stats_green"])
        self.separator_color = QColor(DEFAULTS["separator"])
        self.name_text_color = QColor(DEFAULTS["name_text"])

        self.band_scale_pct = DEFAULTS["band_scale"]
        self.bottom_margin = DEFAULTS["bottom_margin"]

        # Maps for editor routing
        self.editable = {}           # graphics item -> metadata dict
        self.items_by_name = {}

        # Scene
        self.scene = QGraphicsScene(0, 0, CANVAS_W, CANVAS_H)
        self.view = BandView(self, self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QBrush(QColor("#202226")))
        self.setCentralWidget(self.view)

        # Exportable background: white by default (matching the supplied reference style).
        self.canvas_bg = QGraphicsPixmapItem()
        self.canvas_bg.setZValue(-300)
        self.canvas_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.canvas_bg)
        self._set_default_white_background()

        # Optional user background image overlays the white export background.
        self.bg_image_item = QGraphicsPixmapItem()
        self.bg_image_item.setZValue(-290)
        self.bg_image_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.bg_image_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.bg_image_item)

        # Preview-only guides. These NEVER export.
        self.guide_item = QGraphicsPixmapItem()
        self.guide_item.setZValue(-280)
        self.guide_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.guide_item)
        self._draw_preview_guides()

        self.grid_item = QGraphicsPathItem()
        self.grid_item.setZValue(-275)
        self.grid_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(self.grid_item)
        self._rebuild_grid()

        # Build complete band BEFORE sidebar controls.
        self.band = BandGroup(self)
        self.scene.addItem(self.band)
        self._build_band()
        self._apply_band_scale()
        self._snap_band_to_default_position()

        self._build_sidebar()
        self.sync_position_controls_from_band()
        self._wire_history_tracking()
        self._history_state = self._capture_state()
        self._update_history_buttons()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            "Click any band element to open its editor. Drag anywhere on the band to reposition the whole band."
        )
        self._fit_view()

    # ------------------------------------------------------------------ backgrounds
    def _set_default_white_background(self):
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        img.fill(self.background_color)
        self.canvas_bg.setPixmap(QPixmap.fromImage(img))

    def _draw_preview_guides(self):
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Lower-third guide zone only; transparent everywhere else.
        guide_top = CANVAS_H - 320
        p.fillRect(0, guide_top, CANVAS_W, 320, QColor(30, 30, 30, 12))
        pen = QPen(QColor(70, 70, 70, 70), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(0, guide_top, CANVAS_W, guide_top)
        p.setPen(QPen(QColor(110, 110, 110, 55), 2))
        p.drawRect(70, 70, CANVAS_W - 140, CANVAS_H - 140)
        p.end()
        self.guide_item.setPixmap(QPixmap.fromImage(img))

    def _choose_background_color(self):
        color = QColorDialog.getColor(self.background_color, self, "Choose Background Color")
        if not color.isValid():
            return
        self._begin_history_action()
        self.background_color = color
        self._set_default_white_background()
        self._update_background_color_button()
        self._commit_history_now()
        self.statusBar().showMessage(f"Background color set to {color.name().upper()}.", 3000)

    def _update_background_color_button(self):
        if not hasattr(self, "background_color_btn"):
            return
        color = self.background_color.name().upper()
        text_color = "#111111" if self.background_color.lightness() > 150 else "#FFFFFF"
        self.background_color_btn.setText(f"Background Color  {color}")
        self.background_color_btn.setStyleSheet(
            f"background:{color};color:{text_color};font-weight:800;"
        )

    def _rebuild_grid(self):
        path = QPainterPath()
        spacing = max(10, int(self._grid_spacing))
        for x in range(0, CANVAS_W + 1, spacing):
            path.moveTo(x, 0)
            path.lineTo(x, CANVAS_H)
        for y in range(0, CANVAS_H + 1, spacing):
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
        if (
            not self._grid_enabled
            or not self._snap_enabled
            or QApplication.mouseButtons() == Qt.MouseButton.NoButton
            or QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier
        ):
            return value
        spacing = max(10, int(self._grid_spacing))
        return QPointF(
            round(value.x() / spacing) * spacing,
            round(value.y() / spacing) * spacing,
        )

    def _load_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select 16:9 Background",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        src = self._load_original_pixmap(path)
        if src.isNull():
            QMessageBox.warning(self, "Image Error", "Could not load that background image.")
            return
        self._begin_history_action()
        self._set_background_source(src)
        self.bg_image_item.setVisible(True)
        self.background_image_path = path
        self._commit_history_now()
        self.statusBar().showMessage("Background loaded. WITH BG export will use it.", 3500)

    def _clear_background(self):
        self._begin_history_action()
        self.background_image_path = None
        self.background_source_pixmap = QPixmap()
        self.bg_image_item.setPixmap(QPixmap())
        self.bg_image_item.setVisible(False)
        self._commit_history_now()
        self.statusBar().showMessage("Background image cleared. The selected color remains active.", 3000)

    def _set_background_source(self, pixmap):
        """Keep the full source image and transform it non-destructively to cover 16:9."""
        self.background_source_pixmap = pixmap
        self.bg_image_item.setPixmap(pixmap)
        if pixmap.isNull():
            return
        scale = max(CANVAS_W / pixmap.width(), CANVAS_H / pixmap.height())
        self.bg_image_item.setScale(scale)
        self.bg_image_item.setPos(
            (CANVAS_W - pixmap.width() * scale) / 2,
            (CANVAS_H - pixmap.height() * scale) / 2,
        )

    # ------------------------------------------------------------------ graphics registration
    def _register_editable(self, item, name, kind, logical_group=None):
        self.editable[item] = {
            "name": name,
            "kind": kind,
            "logical_group": logical_group,
        }
        self.items_by_name[name] = item
        item.setData(100, 100)  # element size percent, where applicable

    def _path_item(self, points, color, z, name, logical_group=None):
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        path.closeSubpath()
        item = QGraphicsPathItem(path)
        item.setBrush(QBrush(color))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(z)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setTransformOriginPoint(item.boundingRect().center())
        self.band.addToGroup(item)
        self._register_editable(item, name, "shape", logical_group)
        return item

    # ------------------------------------------------------------------ band build
    def _build_band(self):
        # Left name area / slashes
        self.left_body = self._path_item(
            [(35, 30), (610, 30), (575, 120), (0, 120)],
            self.band_color, 1, "Main Green Panel", "band_green"
        )
        self.left_accent_1 = self._path_item(
            [(18, 30), (48, 30), (15, 120), (-15, 120)],
            self.accent_color, 2, "Left Accent Bright", "accent_green"
        )
        self.left_accent_2 = self._path_item(
            [(50, 30), (64, 30), (32, 120), (18, 120)],
            self.accent_dark, 2, "Left Accent Dark", "accent_dark"
        )

        # Stats area. Slightly tighter/right-slash treatment to match reference.
        self.stats_body = self._path_item(
            [(575, 30), (1112, 30), (1081, 120), (540, 120)],
            self.panel_color, 1, "Stats Panel", "panel_white"
        )
        self.right_slash_1 = self._path_item(
            [(1120, 30), (1131, 30), (1099, 120), (1088, 120)],
            self.accent_dark, 2, "Right Slash 1", "accent_dark"
        )
        self.right_slash_2 = self._path_item(
            [(1143, 30), (1154, 30), (1122, 120), (1111, 120)],
            self.accent_color, 2, "Right Slash 2", "accent_green"
        )

        self.sep1 = self._path_item(
            [(738, 47), (740, 47), (740, 104), (738, 104)],
            self.separator_color, 4, "Separator 1", "separator"
        )
        self.sep2 = self._path_item(
            [(883, 47), (885, 47), (885, 104), (883, 104)],
            self.separator_color, 4, "Separator 2", "separator"
        )

        # Player cutout
        self.player_pix = QGraphicsPixmapItem()
        self.player_pix.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        # QGraphicsPixmapItem otherwise defaults to fast/nearest-looking scaling.
        # SmoothTransformation keeps small uploads clean at every display size.
        self.player_pix.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.player_pix.setZValue(6)
        self.player_pix.setTransformOriginPoint(self.player_pix.boundingRect().center())
        self.band.addToGroup(self.player_pix)
        self._register_editable(self.player_pix, "Player Image", "image")
        self._set_player_placeholder()

        # Text
        self.first_name_item = make_text(
            DEFAULTS["first_name"], BASE_FONT["first_name"], QFont.Weight.Medium,
            self.name_text_color.name(), True
        )
        self.last_name_item = make_text(
            DEFAULTS["last_name"], BASE_FONT["last_name"], QFont.Weight.Black,
            self.name_text_color.name(), True
        )
        self.age_label = make_text("AGE", BASE_FONT["label"], QFont.Weight.Black, self.stats_color.name(), True)
        self.rank_label = make_text("RANKING", BASE_FONT["label"], QFont.Weight.Black, self.stats_color.name(), True)
        self.plays_label = make_text("PLAYS", BASE_FONT["label"], QFont.Weight.Black, self.stats_color.name(), True)
        self.age_item = make_text(DEFAULTS["age"], BASE_FONT["value"], QFont.Weight.Black, self.stats_color.name(), True)
        self.rank_item = make_text(DEFAULTS["ranking"], BASE_FONT["value"], QFont.Weight.Black, self.stats_color.name(), True)
        self.plays_item = make_text(DEFAULTS["plays"], BASE_FONT["value"], QFont.Weight.Black, self.stats_color.name(), True)
        self.years_item = make_text("YEARS", BASE_FONT["years"], QFont.Weight.Black, self.stats_color.name(), True)

        text_specs = [
            (self.first_name_item, "First Name", "first_name", "name_text"),
            (self.last_name_item, "Last Name", "last_name", "name_text"),
            (self.age_label, "Age Label", None, "stats_green"),
            (self.rank_label, "Ranking Label", None, "stats_green"),
            (self.plays_label, "Plays Label", None, "stats_green"),
            (self.age_item, "Age Value", "age", "stats_green"),
            (self.rank_item, "Ranking Value", "ranking", "stats_green"),
            (self.plays_item, "Plays Value", "plays", "stats_green"),
            (self.years_item, "Years Label", None, "stats_green"),
        ]
        for item, name, content_key, logical_group in text_specs:
            item.setZValue(7)
            item.setTransformOriginPoint(item.boundingRect().center())
            self.band.addToGroup(item)
            self._register_editable(item, name, "text", logical_group)
            self.editable[item]["content_key"] = content_key

        self._layout_band_elements()

    def _set_player_placeholder(self):
        w, h = 142, 152
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor("#EFEFEA")))
        p.setPen(QPen(QColor("#C1C4BF"), 2))
        p.drawEllipse(47, 8, 48, 48)
        p.drawRoundedRect(30, 54, 82, 92, 18, 18)
        p.end()

        # Placeholder is small by design. Real uploaded player images are kept
        # at their full/original pixel resolution (see _upload_player).
        placeholder = QPixmap.fromImage(img)
        self.player_source_pixmap = placeholder
        self.player_display_height = DEFAULTS["player_height"]
        self.player_pix.setPixmap(placeholder)
        self.player_pix.setTransformOriginPoint(QPointF(0, 0))
        self._apply_player_display_scale()
        self._layout_player_image()

    def _apply_player_display_scale(self):
        """Non-destructive player sizing.

        The QGraphicsPixmapItem always stores the ORIGINAL uploaded pixmap.
        We only change the graphics-item scale for preview/layout. This avoids
        throwing away pixels when the user makes the player smaller and later
        exports a 4K PNG.
        """
        pix = self.player_pix.pixmap()
        if pix.isNull() or pix.height() <= 0:
            return
        target_h = max(1, int(self.player_display_height))
        self.player_pix.setScale(target_h / float(pix.height()))

    def _layout_player_image(self):
        pix = self.player_pix.pixmap()
        if pix.isNull():
            return
        x_offset = self.player_x_spin.value() if hasattr(self, "player_x_spin") else DEFAULTS["player_offset_x"]
        y_offset = self.player_y_spin.value() if hasattr(self, "player_y_spin") else DEFAULTS["player_offset_y"]

        # Position using DISPLAYED dimensions, not source-pixel dimensions.
        scale = self.player_pix.scale()
        display_w = pix.width() * scale
        display_h = pix.height() * scale
        x = BASE_POS["player_anchor_x"] + x_offset - display_w / 2
        y = BASE_POS["player_feet_y"] + y_offset - display_h
        self.player_pix.setPos(x, y)

    def _layout_years_bottom_right(self):
        # Explicitly position YEARS at the bottom-right of the AGE cell.
        width = self.years_item.boundingRect().width()
        height = self.years_item.boundingRect().height()
        self.years_item.setPos(
            AGE_CELL_RIGHT - 8 - width,
            AGE_CELL_BOTTOM - height,
        )

    def _layout_band_elements(self):
        self.first_name_item.setPos(*BASE_POS["first_name"])
        self.last_name_item.setPos(*BASE_POS["last_name"])
        self.age_label.setPos(*BASE_POS["age_label"])
        self.rank_label.setPos(*BASE_POS["rank_label"])
        self.plays_label.setPos(*BASE_POS["plays_label"])
        self.age_item.setPos(*BASE_POS["age_value"])
        self.rank_item.setPos(*BASE_POS["rank_value"])
        self.plays_item.setPos(*BASE_POS["plays_value"])

        fit_text(self.first_name_item, 230, BASE_FONT["first_name"], 11)
        fit_text(self.last_name_item, 330, BASE_FONT["last_name"], 18)
        fit_text(self.age_item, 90, BASE_FONT["value"], 17)
        fit_text(self.rank_item, 100, BASE_FONT["value"], 17)
        fit_text(self.plays_item, 100, BASE_FONT["value"], 17)
        self._layout_years_bottom_right()
        self._layout_player_image()

    # ------------------------------------------------------------------ click -> selected element editor
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
        if target is None:
            return
        self.select_element_for_editing(target)

    def select_element_for_editing(self, item):
        self.selected_edit_item = item
        self._update_history_buttons()
        if not hasattr(self, "editor_tabs"):
            return

        # Clicking a design element automatically opens its editor.
        self.editor_tabs.setCurrentIndex(0)

        if item is self.band:
            self.selected_name_label.setText("WHOLE BAND")
            self.selected_kind_label.setText("Band / lower-third")
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

        kind = meta["kind"]
        if kind == "text":
            self.selected_content_edit.setEnabled(True)
            self.selected_content_edit.setText(item.toPlainText())
            self.selected_size_spin.setRange(4, 300)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(max(6, item.font().pointSize()))
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(True)
        elif kind == "image":
            self.selected_content_edit.setEnabled(False)
            self.selected_content_edit.setText("")
            self.selected_size_spin.setRange(20, 1000)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(max(60, int(self.player_display_height)))
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(False)
        else:  # shape
            self.selected_content_edit.setEnabled(False)
            self.selected_content_edit.setText("")
            self.selected_size_spin.setRange(10, 400)
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(int(item.data(100) or 100))
            self.selected_size_spin.blockSignals(False)
            self.selected_color_btn.setEnabled(True)

        self.statusBar().showMessage(f"Editing: {meta['name']}", 2500)

    # ------------------------------------------------------------------ selected element editor actions
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
        kind = meta["kind"]

        if kind == "text":
            preserve_center_while_changing_text_size(item, value)
            if item is self.years_item:
                self._layout_years_bottom_right()
        elif kind == "image":
            self.player_height_spin.setValue(value)
        elif kind == "shape":
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
        if item is self.years_item:
            self._layout_years_bottom_right()

        # Keep main player-data fields in sync when editing those elements directly.
        key = meta.get("content_key")
        field_map = {
            "first_name": self.first_name_edit,
            "last_name": self.last_name_edit,
            "age": self.age_edit,
            "ranking": self.rank_edit,
            "plays": self.plays_edit,
        }
        if key in field_map and field_map[key].text().upper() != text:
            field_map[key].blockSignals(True)
            field_map[key].setText(text)
            field_map[key].blockSignals(False)

    def _selected_change_color(self):
        item = self.selected_edit_item
        if item is None or item is self.band:
            return
        meta = self.editable.get(item)
        if not meta or meta["kind"] == "image":
            return

        if meta["kind"] == "text":
            current = item.defaultTextColor()
        else:
            current = item.brush().color()

        color = QColorDialog.getColor(current, self, f"Color — {meta['name']}")
        if not color.isValid():
            return
        self._begin_history_action()

        group = meta.get("logical_group")
        if group == "band_green":
            self.band_color = color
            self.left_body.setBrush(QBrush(color))
        elif group == "accent_green":
            self.accent_color = color
            # Same family, but clicked element still drives the visual family.
            self.left_accent_1.setBrush(QBrush(color))
            self.right_slash_2.setBrush(QBrush(color))
        elif group == "accent_dark":
            self.accent_dark = color
            self.left_accent_2.setBrush(QBrush(color))
            self.right_slash_1.setBrush(QBrush(color))
        elif group == "panel_white":
            self.panel_color = color
            self.stats_body.setBrush(QBrush(color))
        elif group == "separator":
            self.separator_color = color
            self.sep1.setBrush(QBrush(color))
            self.sep2.setBrush(QBrush(color))
        elif group == "name_text":
            self.name_text_color = color
            self.first_name_item.setDefaultTextColor(color)
            self.last_name_item.setDefaultTextColor(color)
        elif group == "stats_green":
            self.stats_color = color
            for text_item in (
                self.age_label, self.rank_label, self.plays_label,
                self.age_item, self.rank_item, self.plays_item, self.years_item,
            ):
                text_item.setDefaultTextColor(color)
        else:
            if meta["kind"] == "text":
                item.setDefaultTextColor(color)
            else:
                item.setBrush(QBrush(color))
        self._commit_history_now()

    # ------------------------------------------------------------------ sidebar
    def _make_spin(self, minimum, maximum, value, suffix="", prefix=""):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setPrefix(prefix)
        # Requirement: remove up/down arrows.
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
        dock.setMinimumWidth(390)

        dock_body = QWidget()
        dock_layout = QVBoxLayout(dock_body)
        dock_layout.setContentsMargins(8, 8, 8, 8)
        dock_layout.setSpacing(8)

        action_row = QHBoxLayout()
        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setToolTip("Undo last change (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.setToolTip("Redo last undone change (Ctrl+Y or Ctrl+Shift+Z)")
        self.btn_redo.clicked.connect(self.redo)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_delete.setToolTip("Hide the selected element (Delete)")
        self.btn_delete.clicked.connect(self.delete_selected)
        action_row.addWidget(self.btn_undo)
        action_row.addWidget(self.btn_redo)
        action_row.addWidget(self.btn_delete)
        dock_layout.addLayout(action_row)

        self.editor_tabs = QTabWidget()
        dock_layout.addWidget(self.editor_tabs, 1)

        # ---------------- Selected Element tab ----------------
        selected_page = QWidget()
        selected_root = QVBoxLayout(selected_page)
        selected_root.setContentsMargins(12, 12, 12, 12)
        selected_root.setSpacing(10)

        self.selected_name_label = QLabel("CLICK AN ELEMENT")
        self.selected_name_label.setStyleSheet("font-size:18px;font-weight:900;color:white;")
        selected_root.addWidget(self.selected_name_label)

        self.selected_kind_label = QLabel("The correct editing controls will open here automatically.")
        self.selected_kind_label.setWordWrap(True)
        self.selected_kind_label.setStyleSheet("color:#9fa7b3;font-size:11px;")
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
        self.selected_color_btn.clicked.connect(self._selected_change_color)
        self.selected_color_btn.setEnabled(False)
        selected_root.addWidget(self.selected_color_btn)

        select_band_btn = QPushButton("Edit Whole Band Size")
        select_band_btn.clicked.connect(lambda: self.select_element_for_editing(self.band))
        selected_root.addWidget(select_band_btn)

        selected_root.addStretch()
        self.editor_tabs.addTab(self._scroll_tab(selected_page), "Element")

        # ---------------- Player Data tab ----------------
        data_page = QWidget()
        data_root = QVBoxLayout(data_page)
        data_root.setContentsMargins(12, 12, 12, 12)
        data_root.setSpacing(10)

        data_title = QLabel("PLAYER DATA")
        data_title.setStyleSheet("font-size:16px;font-weight:800;color:white;")
        data_root.addWidget(data_title)

        form = QFormLayout()
        self.first_name_edit = QLineEdit(DEFAULTS["first_name"])
        self.last_name_edit = QLineEdit(DEFAULTS["last_name"])
        self.age_edit = QLineEdit(DEFAULTS["age"])
        self.rank_edit = QLineEdit(DEFAULTS["ranking"])
        self.plays_edit = QLineEdit(DEFAULTS["plays"])
        form.addRow("First name", self.first_name_edit)
        form.addRow("Last name", self.last_name_edit)
        form.addRow("Age", self.age_edit)
        form.addRow("Ranking", self.rank_edit)
        form.addRow("Plays", self.plays_edit)
        data_root.addLayout(form)
        for edit in (self.first_name_edit, self.last_name_edit, self.age_edit, self.rank_edit, self.plays_edit):
            edit.textChanged.connect(self._sync_text_from_data)

        image_group = QGroupBox("Player Image")
        image_layout = QVBoxLayout(image_group)
        image_buttons = QHBoxLayout()
        upload_btn = QPushButton("Upload Player")
        upload_btn.clicked.connect(self._upload_player)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_player)
        image_buttons.addWidget(upload_btn)
        image_buttons.addWidget(clear_btn)
        image_layout.addLayout(image_buttons)

        self.player_height_spin = self._make_spin(20, 1000, DEFAULTS["player_height"], " px")
        self.player_height_spin.valueChanged.connect(self._resize_player)
        image_layout.addWidget(QLabel("Height"))
        image_layout.addWidget(self.player_height_spin)

        offsets = QHBoxLayout()
        self.player_x_spin = self._make_spin(-250, 250, DEFAULTS["player_offset_x"], prefix="X ")
        self.player_y_spin = self._make_spin(-250, 250, DEFAULTS["player_offset_y"], prefix="Y ")
        self.player_x_spin.valueChanged.connect(lambda _: self._layout_player_image())
        self.player_y_spin.valueChanged.connect(lambda _: self._layout_player_image())
        offsets.addWidget(self.player_x_spin)
        offsets.addWidget(self.player_y_spin)
        image_layout.addLayout(offsets)
        data_root.addWidget(image_group)

        data_root.addStretch()
        self.editor_tabs.addTab(self._scroll_tab(data_page), "Player")

        # ---------------- Band / Position tab ----------------
        band_page = QWidget()
        band_root = QVBoxLayout(band_page)
        band_root.setContentsMargins(12, 12, 12, 12)
        band_root.setSpacing(10)

        band_title = QLabel("BAND / POSITION")
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
        self.bottom_margin_spin = self._make_spin(0, 400, DEFAULTS["bottom_margin"], " px")
        self.bottom_margin_spin.valueChanged.connect(self._bottom_margin_changed)
        pos_form.addRow("X", self.band_x_spin)
        pos_form.addRow("Y", self.band_y_spin)
        pos_form.addRow("Bottom margin", self.bottom_margin_spin)
        band_root.addWidget(position_group)

        pos_buttons = QHBoxLayout()
        snap_btn = QPushButton("Default Bottom Position")
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
        self.guides_check = QCheckBox("Show safe-area guides (preview only)")
        self.guides_check.setChecked(True)
        self.guides_check.toggled.connect(self.guide_item.setVisible)
        bg_layout.addWidget(self.guides_check)
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

        reset_btn = QPushButton("Reset Everything")
        reset_btn.clicked.connect(self._reset_defaults)
        band_root.addWidget(reset_btn)

        band_root.addStretch()

        # Exactly two prominent download buttons requested.
        export_with_bg = QPushButton("DOWNLOAD WITH BG — 4K PNG")
        export_with_bg.setObjectName("exportWithBg")
        export_with_bg.clicked.connect(self._export_with_bg)
        band_root.addWidget(export_with_bg)

        export_no_bg = QPushButton("DOWNLOAD WITHOUT BG — 4K PNG")
        export_no_bg.setObjectName("exportNoBg")
        export_no_bg.clicked.connect(self._export_without_bg)
        band_root.addWidget(export_no_bg)

        export_note = QLabel(
            "WITHOUT BG keeps the band at its exact current 16:9 position and exports transparency."
        )
        export_note.setWordWrap(True)
        export_note.setStyleSheet("color:#9fa7b3;font-size:11px;")
        band_root.addWidget(export_note)

        self.editor_tabs.addTab(self._scroll_tab(band_page), "Canvas")

        dock.setWidget(dock_body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # Apply no-button-symbol behavior to every spin box, including future child finds.
        for spin in dock.findChildren(QSpinBox):
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setKeyboardTracking(False)

        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_shortcut)

    # ------------------------------------------------------------------ data controls
    def _sync_text_from_data(self):
        self.first_name_item.setPlainText(self.first_name_edit.text().upper())
        self.last_name_item.setPlainText(self.last_name_edit.text().upper())
        self.age_item.setPlainText(self.age_edit.text().upper())
        self.rank_item.setPlainText(self.rank_edit.text().upper())
        self.plays_item.setPlainText(self.plays_edit.text().upper())
        self._layout_band_elements()

    def _load_original_pixmap(self, path):
        """Decode the upload once at ORIGINAL resolution with EXIF orientation."""
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image)

    def _upload_player(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Player Image — Original Quality",
            "",
            "Images (*.png *.webp *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return

        original = self._load_original_pixmap(path)
        if original.isNull():
            QMessageBox.warning(self, "Image Error", "Could not load the selected player image.")
            return

        self._begin_history_action()
        # IMPORTANT: Never replace this pixmap with a resized copy.
        # The complete source resolution stays inside the graphics item.
        self.player_image_path = path
        self.player_source_pixmap = original
        self.player_pix.setPixmap(original)
        self.player_pix.setTransformOriginPoint(QPointF(0, 0))
        self.player_display_height = self.player_height_spin.value()
        self._apply_player_display_scale()
        self._layout_player_image()
        self.player_pix.setVisible(True)
        self._commit_history_now()

        mp = (original.width() * original.height()) / 1_000_000.0
        self.statusBar().showMessage(
            f"Original-quality image loaded: {original.width()}×{original.height()} ({mp:.1f} MP). "
            "No destructive resizing is applied.",
            6000,
        )

    def _clear_player(self):
        self._begin_history_action()
        self.player_image_path = None
        self.player_source_pixmap = QPixmap()
        self._set_player_placeholder()
        if self.selected_edit_item is self.player_pix:
            self.select_element_for_editing(self.player_pix)
        self._commit_history_now()

    def _resize_player(self, height):
        # NON-DESTRUCTIVE resize: keep full source pixels and only change the
        # QGraphicsItem display scale. This preserves maximum quality for 4K.
        self.player_display_height = int(height)
        if self.player_image_path and not self.player_source_pixmap.isNull():
            if self.player_pix.pixmap().cacheKey() != self.player_source_pixmap.cacheKey():
                self.player_pix.setPixmap(self.player_source_pixmap)
            self._apply_player_display_scale()
        else:
            self._apply_player_display_scale()
        self._layout_player_image()
        if self.selected_edit_item is self.player_pix:
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(height)
            self.selected_size_spin.blockSignals(False)

    # ------------------------------------------------------------------ band position / size
    def _apply_band_scale(self):
        self.band.setScale(self.band_scale_pct / 100.0)

    def _change_band_scale(self, value):
        # Preserve the current visual center when resizing the entire band.
        old_center = self.band.sceneBoundingRect().center()
        self.band_scale_pct = value
        self._apply_band_scale()
        new_center = self.band.sceneBoundingRect().center()
        self.band.setPos(self.band.pos() + (old_center - new_center))
        self.sync_position_controls_from_band()
        if self.selected_edit_item is self.band:
            self.selected_size_spin.blockSignals(True)
            self.selected_size_spin.setValue(value)
            self.selected_size_spin.blockSignals(False)

    def _bottom_margin_changed(self, value):
        self.bottom_margin = value
        self._snap_band_to_default_position()

    def _snap_band_to_default_position(self):
        rect = self.band.childrenBoundingRect()
        scale = self.band.scale()
        scaled_w = rect.width() * scale
        scaled_h = rect.height() * scale
        x = (CANVAS_W - scaled_w) / 2 - rect.left() * scale
        y = CANVAS_H - self.bottom_margin - scaled_h - rect.top() * scale
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

    # ------------------------------------------------------------------ undo / redo / delete
    def _wire_history_tracking(self):
        """Debounce ordinary editor controls into useful, user-sized undo steps."""
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
            return
        current = self._capture_state()
        target = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_history_state(target)
        self.statusBar().showMessage("Undo", 1500)

    def redo(self):
        if self._history_timer.isActive():
            self._commit_history_now()
        if not self._redo_stack:
            return
        current = self._capture_state()
        target = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_history_state(target)
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
            self.btn_delete.setEnabled(
                self.selected_edit_item is not None and self.selected_edit_item is not self.band
            )

    def delete_selected(self):
        item = self.selected_edit_item
        if item is None:
            self.statusBar().showMessage("Select an element first, then press Delete.", 2500)
            return
        if item is self.band:
            self.statusBar().showMessage("The whole band is protected. Delete individual elements instead.", 3000)
            return
        self._begin_history_action()
        item.setVisible(False)
        name = self.editable.get(item, {}).get("name", "Element")
        self.selected_edit_item = None
        self.selected_name_label.setText("NOTHING SELECTED")
        self.selected_kind_label.setText("Use Undo to restore a deleted element.")
        self.selected_content_edit.setEnabled(False)
        self.selected_color_btn.setEnabled(False)
        self._commit_history_now()
        self._update_history_buttons()
        self.statusBar().showMessage(f"{name} deleted. Ctrl+Z restores it.", 3000)

    def _delete_shortcut(self):
        # Delete remains a normal editing key while the cursor is inside a field.
        if isinstance(QApplication.focusWidget(), (QLineEdit, QSpinBox)):
            return
        self.delete_selected()

    # ------------------------------------------------------------------ reset / state / presets
    def _reset_item_scales(self):
        for item, meta in self.editable.items():
            if meta["kind"] == "shape":
                item.setScale(1.0)
                item.setData(100, 100)

    def _reset_text_font_sizes(self):
        sizes = {
            self.first_name_item: BASE_FONT["first_name"],
            self.last_name_item: BASE_FONT["last_name"],
            self.age_label: BASE_FONT["label"],
            self.rank_label: BASE_FONT["label"],
            self.plays_label: BASE_FONT["label"],
            self.age_item: BASE_FONT["value"],
            self.rank_item: BASE_FONT["value"],
            self.plays_item: BASE_FONT["value"],
            self.years_item: BASE_FONT["years"],
        }
        for item, size in sizes.items():
            font = item.font()
            font.setPointSize(size)
            item.setFont(font)

    def _apply_default_colors(self):
        self.band_color = QColor(DEFAULTS["band_green"])
        self.accent_color = QColor(DEFAULTS["accent_green"])
        self.accent_dark = QColor(DEFAULTS["accent_dark"])
        self.panel_color = QColor(DEFAULTS["panel_white"])
        self.stats_color = QColor(DEFAULTS["stats_green"])
        self.separator_color = QColor(DEFAULTS["separator"])
        self.name_text_color = QColor(DEFAULTS["name_text"])

        self.left_body.setBrush(QBrush(self.band_color))
        self.left_accent_1.setBrush(QBrush(self.accent_color))
        self.right_slash_2.setBrush(QBrush(self.accent_color))
        self.left_accent_2.setBrush(QBrush(self.accent_dark))
        self.right_slash_1.setBrush(QBrush(self.accent_dark))
        self.stats_body.setBrush(QBrush(self.panel_color))
        self.sep1.setBrush(QBrush(self.separator_color))
        self.sep2.setBrush(QBrush(self.separator_color))
        self.first_name_item.setDefaultTextColor(self.name_text_color)
        self.last_name_item.setDefaultTextColor(self.name_text_color)
        for item in (
            self.age_label, self.rank_label, self.plays_label,
            self.age_item, self.rank_item, self.plays_item, self.years_item,
        ):
            item.setDefaultTextColor(self.stats_color)

    def _reset_defaults(self):
        self._begin_history_action()
        self.first_name_edit.setText(DEFAULTS["first_name"])
        self.last_name_edit.setText(DEFAULTS["last_name"])
        self.age_edit.setText(DEFAULTS["age"])
        self.rank_edit.setText(DEFAULTS["ranking"])
        self.plays_edit.setText(DEFAULTS["plays"])

        self.player_height_spin.setValue(DEFAULTS["player_height"])
        self.player_x_spin.setValue(DEFAULTS["player_offset_x"])
        self.player_y_spin.setValue(DEFAULTS["player_offset_y"])
        self.band_scale_spin.setValue(DEFAULTS["band_scale"])
        self.bottom_margin_spin.setValue(DEFAULTS["bottom_margin"])

        self._reset_item_scales()
        self._reset_text_font_sizes()
        self._apply_default_colors()
        for item in self.editable:
            item.setVisible(True)
        self.background_color = QColor(DEFAULTS["background_color"])
        self._set_default_white_background()
        self._update_background_color_button()
        self.background_image_path = None
        self.background_source_pixmap = QPixmap()
        self.bg_image_item.setPixmap(QPixmap())
        self.bg_image_item.setVisible(False)
        self.grid_checkbox.setChecked(False)
        self.grid_spacing_spin.setValue(DEFAULTS["grid_spacing"])
        self.snap_checkbox.setChecked(True)
        self._sync_text_from_data()
        if self.player_image_path:
            self._resize_player(self.player_height_spin.value())
        else:
            self._set_player_placeholder()
        self._snap_band_to_default_position()
        self._commit_history_now()
        self.statusBar().showMessage("Reset complete.", 2500)

    def _capture_state(self):
        shape_scales = {}
        text_sizes = {}
        colors = {}
        for item, meta in self.editable.items():
            name = meta["name"]
            if meta["kind"] == "shape":
                shape_scales[name] = int(item.data(100) or 100)
                colors[name] = item.brush().color().name()
            elif meta["kind"] == "text":
                text_sizes[name] = item.font().pointSize()
                colors[name] = item.defaultTextColor().name()

        return {
            "first_name": self.first_name_edit.text(),
            "last_name": self.last_name_edit.text(),
            "age": self.age_edit.text(),
            "ranking": self.rank_edit.text(),
            "plays": self.plays_edit.text(),
            "years_text": self.years_item.toPlainText(),
            "player_image_path": self.player_image_path,
            "player_height": self.player_height_spin.value(),
            "player_x": self.player_x_spin.value(),
            "player_y": self.player_y_spin.value(),
            "band_scale": self.band_scale_spin.value(),
            "bottom_margin": self.bottom_margin_spin.value(),
            "band_position": [self.band.x(), self.band.y()],
            "shape_scales": shape_scales,
            "text_sizes": text_sizes,
            "colors": colors,
            "item_visibility": {
                meta["name"]: item.isVisible() for item, meta in self.editable.items()
            },
            "background_image_path": self.background_image_path,
            "background_color": self.background_color.name(),
            "grid": {
                "enabled": self._grid_enabled,
                "spacing": self._grid_spacing,
                "snap": self._snap_enabled,
            },
        }

    def _apply_state(self, state):
        self.background_color = QColor(state.get("background_color", DEFAULTS["background_color"]))
        if not self.background_color.isValid():
            self.background_color = QColor(DEFAULTS["background_color"])
        self._set_default_white_background()
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

        self.first_name_edit.setText(str(state.get("first_name", DEFAULTS["first_name"])))
        self.last_name_edit.setText(str(state.get("last_name", DEFAULTS["last_name"])))
        self.age_edit.setText(str(state.get("age", DEFAULTS["age"])))
        self.rank_edit.setText(str(state.get("ranking", DEFAULTS["ranking"])))
        self.plays_edit.setText(str(state.get("plays", DEFAULTS["plays"])))
        self.years_item.setPlainText(str(state.get("years_text", "YEARS")))

        self.player_image_path = state.get("player_image_path")
        self.player_height_spin.setValue(int(state.get("player_height", DEFAULTS["player_height"])))
        self.player_x_spin.setValue(int(state.get("player_x", DEFAULTS["player_offset_x"])))
        self.player_y_spin.setValue(int(state.get("player_y", DEFAULTS["player_offset_y"])))
        self.band_scale_spin.setValue(int(state.get("band_scale", DEFAULTS["band_scale"])))
        self.bottom_margin_spin.setValue(int(state.get("bottom_margin", DEFAULTS["bottom_margin"])))

        if self.player_image_path and os.path.exists(self.player_image_path):
            original = self._load_original_pixmap(self.player_image_path)
            if not original.isNull():
                self.player_source_pixmap = original
                self.player_pix.setPixmap(original)
                self.player_pix.setTransformOriginPoint(QPointF(0, 0))
                self._resize_player(self.player_height_spin.value())
            else:
                self.player_image_path = None
                self.player_source_pixmap = QPixmap()
                self._set_player_placeholder()
        else:
            self.player_image_path = None
            self.player_source_pixmap = QPixmap()
            self._set_player_placeholder()
        # Placeholder creation resets its own default, so always re-apply the
        # size stored in the state after the source/placeholder is installed.
        self.player_display_height = self.player_height_spin.value()
        self._apply_player_display_scale()
        self._layout_player_image()

        shape_scales = state.get("shape_scales", {})
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
                if name in colors:
                    item.setBrush(QBrush(QColor(colors[name])))
            elif meta["kind"] == "text":
                if name in text_sizes:
                    font = item.font()
                    font.setPointSize(max(4, int(text_sizes[name])))
                    item.setFont(font)
                if name in colors:
                    item.setDefaultTextColor(QColor(colors[name]))

        self._sync_text_from_data()
        self._layout_years_bottom_right()

        pos = state.get("band_position")
        if isinstance(pos, list) and len(pos) == 2:
            self.band.setPos(float(pos[0]), float(pos[1]))
        else:
            self._snap_band_to_default_position()
        self.sync_position_controls_from_band()

        bg_path = state.get("background_image_path")
        if bg_path and os.path.exists(bg_path):
            src = self._load_original_pixmap(bg_path)
            if not src.isNull():
                self._set_background_source(src)
                self.bg_image_item.setVisible(True)
                self.background_image_path = bg_path
        else:
            self.background_image_path = None
            self.background_source_pixmap = QPixmap()
            self.bg_image_item.setPixmap(QPixmap())
            self.bg_image_item.setVisible(False)

    def _save_preset(self):
        os.makedirs(PRESET_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Band Preset",
            os.path.join(PRESET_DIR, "player_band_preset.json"),
            "JSON Files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._capture_state(), f, indent=2)
            self.statusBar().showMessage(f"Preset saved: {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Preset Error", f"Could not save preset.\n\n{exc}")

    def _load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Band Preset", PRESET_DIR, "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._begin_history_action()
            self._apply_state(state)
            self._commit_history_now()
            self.statusBar().showMessage(f"Preset loaded: {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Preset Error", f"Could not load preset.\n\n{exc}")

    # ------------------------------------------------------------------ 4K export
    def _prepare_export(self, include_background):
        selected = self.band.isSelected()
        guides_visible = self.guide_item.isVisible()
        grid_visible = self.grid_item.isVisible()
        bg_visible = self.bg_image_item.isVisible()
        canvas_visible = self.canvas_bg.isVisible()

        self.band.setSelected(False)
        self.guide_item.setVisible(False)  # guides are NEVER exported
        self.grid_item.setVisible(False)  # placement grid is NEVER exported
        if not include_background:
            self.canvas_bg.setVisible(False)
            self.bg_image_item.setVisible(False)
        return selected, guides_visible, grid_visible, bg_visible, canvas_visible

    def _restore_after_export(self, state):
        selected, guides_visible, grid_visible, bg_visible, canvas_visible = state
        self.band.setSelected(selected)
        self.guide_item.setVisible(guides_visible)
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
        self.scene.render(
            painter,
            QRectF(0, 0, EXPORT_W, EXPORT_H),
            QRectF(0, 0, CANVAS_W, CANVAS_H),
        )
        painter.end()
        self._restore_after_export(state)
        return image

    def _export_with_bg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Download WITH BG — 4K", "player_band_WITH_BG_4K.png", "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        image = self._render_4k(include_background=True)
        if image.save(path):
            QMessageBox.information(self, "Saved", f"4K PNG WITH background saved:\n{path}")
        else:
            QMessageBox.critical(self, "Export Error", "Could not save the image.")

    def _export_without_bg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Download WITHOUT BG — 4K", "player_band_TRANSPARENT_4K.png", "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        image = self._render_4k(include_background=False)
        if image.save(path):
            QMessageBox.information(
                self, "Saved",
                "4K transparent PNG saved.\n\nThe band keeps its exact current position on the 16:9 canvas.\n" + path
            )
        else:
            QMessageBox.critical(self, "Export Error", "Could not save the transparent image.")

    # ------------------------------------------------------------------ view
    def _fit_view(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_view()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_view()


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QMainWindow, QDockWidget > QWidget, QScrollArea, QTabWidget::pane {
            background:#17191d;
        }
        QDockWidget { color:#ffffff; font-weight:700; }
        QLabel, QCheckBox { color:#d9dde5; }
        QGroupBox {
            color:#f3f4f6;
            font-weight:700;
            border:1px solid #353b45;
            border-radius:8px;
            margin-top:10px;
            padding:12px 8px 8px 8px;
        }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }
        QLineEdit, QSpinBox {
            background:#101216;
            color:#ffffff;
            border:1px solid #404754;
            border-radius:6px;
            padding:6px 8px;
            min-height:29px;
        }
        QLineEdit:focus, QSpinBox:focus { border-color:#60a5fa; }
        /* Extra safety: visually remove spinbox arrows on all platforms. */
        QSpinBox::up-button, QSpinBox::down-button { width:0px; height:0px; border:none; }
        QPushButton {
            background:#303640;
            color:#ffffff;
            border:1px solid #464e5a;
            border-radius:7px;
            padding:7px 10px;
            min-height:30px;
        }
        QPushButton:hover { background:#3b424d; }
        QPushButton:disabled { color:#737b87; background:#22262c; border-color:#303640; }
        QPushButton#dangerButton {
            background:#5b2027;
            border-color:#8f303b;
        }
        QPushButton#dangerButton:hover { background:#762a34; }
        QPushButton#sizeButton {
            min-width:42px;
            max-width:42px;
            min-height:38px;
            font-size:22px;
            font-weight:900;
            background:#242a32;
        }
        QPushButton#exportWithBg {
            background:#157347;
            border-color:#25a66a;
            min-height:48px;
            font-weight:900;
            font-size:13px;
        }
        QPushButton#exportNoBg {
            background:#2563eb;
            border-color:#60a5fa;
            min-height:48px;
            font-weight:900;
            font-size:13px;
        }
        QTabBar::tab {
            background:#252a31;
            color:#b8bec8;
            padding:9px 11px;
            border:1px solid #343a44;
        }
        QTabBar::tab:selected { background:#3b82f6; color:white; }
        QStatusBar { color:#c9ced7; }
        """
    )

    win = PlayerBandGenerator()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
