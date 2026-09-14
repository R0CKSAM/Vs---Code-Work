# Davis Cup Match Graphic & Thumbnail Generator (Pro Studio v3.0)

A high-performance, Canva-style thumbnail and match poster generator software engineered specifically for tennis match day and tournament graphics (modeled directly on the Davis Cup design: Sumit Nagal vs Soonwoo Kwon, Day 1 / Match 1, IND vs KOR).

Delivered as **one complete, fully integrated Python script** (`davis_cup_generator.py`) based on **PyQt6**.

---

## Quick Start

Run the software directly using your terminal or PowerShell:

```bash
# Recommended: Launches app and auto-initializes assets
python run_app.py

# Or run the single standalone script directly:
python davis_cup_generator.py
```

### Running the Headless Self-Audit Test Suite:
```bash
python davis_cup_generator.py --audit
```

---

## All 12 Requested Features & Enhancements

### 1. Complete Working Software in One Python Script
- Entire application is self-contained in `davis_cup_generator.py` (4000+ lines of robust, production-grade PyQt6 code).
- Built-in automatic dependency installer for `PyQt6`, `pycountry`, and `Pillow`.

### 2. Full Logo Management System
- Located in the **`🏷️ Logo`** tab:
  - **Upload / Add Logo**: Load custom tournament/sponsor logos (`.png` with transparency, `.jpg`, `.webp`, `.svg`).
  - **Replace Logo**: Swap logos on the fly while preserving dimensions and positioning.
  - **Remove Logo**: Instantly clear logos without breaking the layout or canvas alignment.
  - **Reset to Davis Cup**: 1-click reset to the official vector Davis Cup emblem and title.
  - High-DPI scaling and true aspect ratio preservation.

### 3. Radiant Glowing Effect Behind Images
- Located in the **`👤 Left`** and **`👤 Right`** player tabs:
  - Multi-layer luminous radial backlight glow rendered **strictly behind** player cutouts.
  - Leaves the original foreground cutout pixels untouched, crisp, and vivid.
  - Custom aura color picker, intensity slider (0–100%), and spread/radius slider (50–500px).

### 4. Improved Flag & Image Quality (Zero Squishing)
- Located in the **`⚔️ Match`** tab:
  - Strict 3:2 flag aspect ratio preservation with letterboxing and centering.
  - High-resolution `w640` flag CDN auto-fetching with local persistent caching (`flag_cache/`).
  - Built-in vector flags for India (IND) and South Korea (KOR) with Ashoka Chakra and Taegeuk trigrams.

### 5. Comprehensive Text Styles & Typography
- Located in the **`🔤 Text`** tab:
  - Live searchable font picker (`QFontDialog`) + quick-access athletic font presets (*Arial, Montserrat, Trebuchet MS, Impact, Segoe UI, Georgia, Times New Roman, Tahoma, Verdana*).
  - Font size (10–300 pt), bold, italic, underline toggles, and letter spacing (-5 to 50 px).
  - Text alignment (Center, Left, Right) and quick casing transforms (**UPPER**, **Title Case**, **lower**).
  - Custom text color picker with live visual canvas updates.

### 6. Clean Underline Directly Below Pictures
- Located in the **`👤 Left`** and **`👤 Right`** player tabs:
  - Luminous neon accent baseline anchored directly underneath each player portrait cutout.
  - Multi-stop outer glow and inner highlight creating a professional sports broadcast finish.
  - Customizable color, thickness (1–30 px), width (50–900 px), and vertical offset.

### 7. Slant Angle for Naming & Match Banners
- Located in the **`👤 Left`**, **`👤 Right`**, and **`⚔️ Match`** tabs:
  - **Independent Badge Slant Angle** (-45° to +45°): Tilts the dark athletic parallelogram nameplate.
  - **Independent Text Slant/Rotation Angle** (-45° to +45°): Rotates the typography independently of the badge angle.
  - Center match banners ("DAY 1" & "MATCH 1") feature dedicated slant angle controls.

### 8. Modern Redesigned UI
- Canva / Adobe Express inspired dark studio theme (`#0d1217` / `#141b24`).
- Clean visual hierarchy with 7 organized tabs:
  1. `🏷️ Logo` - Tournament logo upload, replacement, removal, and title typography.
  2. `⚔️ Match` - Day & Match banners, country flags, and auto-flag fetcher.
  3. `👤 Left` - Left player photo, radiant glow, neon underline, and nameplate slant.
  4. `👤 Right` - Right player photo, radiant glow, neon underline, and nameplate slant.
  5. `🔤 Text` - Universal typography styling, font picker, case formatting, and custom text.
  6. `🌌 Court` - Tennis court atmosphere, floodlight effects, laser trails, grid & snapping.
  7. `💾 Save` - Presets, layout reset, element deletion, and 1920×1080 export.

### 9. Removed Up/Down Arrows on Inputs
- QSS stylesheet removes spinbox up/down arrow buttons across all numeric inputs.
- Supports smooth mouse-wheel scrolling, trackpad swipe, direct numeric entry, and paired sliders.

### 10. Removed Bring Forward / Send Backward Buttons from UI
- Toolbar clutter eliminated while retaining underlying layer z-ordering.
- Intuitive keyboard shortcuts: `Ctrl+]` (Bring Forward) and `Ctrl+[` (Send Backward).

### 11. Streamlined Core Workflow
- All redundant buttons and clutter eliminated to focus strictly on match day graphic creation.
- 8-point Canva-style drag handles (NW, N, NE, E, SE, S, SW, W) with directional cursors.
- Smart alignment snapping to canvas center, edges, and adjacent elements.
- Full undo/redo engine (`Ctrl+Z`, `Ctrl+Y`).

### 12. Programmatic Test & Self-Audit Suite
- Run `python davis_cup_generator.py --audit` to execute the headless test suite validating canvas bounds, items, logo management, glowing backlights, underlines, slant angles, JSON serialization, undo/redo round-tripping, and 1920×1080 off-screen rendering.

---

## Requirements
```bash
pip install PyQt6 pycountry Pillow
```
