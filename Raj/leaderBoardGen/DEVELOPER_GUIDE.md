# Match Stats & Scoreboard Graphics Studio — Developer & Architecture Guide

Welcome to the **Match Stats & Scoreboard Graphics Studio** developer documentation. This guide is written specifically for software engineers, broadcast technicians, and technical staff who wish to understand, maintain, integrate, or extend the codebase.

---

## 1. High-Level Architecture Overview

The application is architected around a clean, unidirectional data-flow pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                      ScoreboardConfig                       │
│        (Type-Safe Dataclass / Serialized JSON Model)        │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│    ScoreboardStudioApp      │ │         CLI / API           │
│ (Clean Light Theme GUI:     │ │   (Headless Automation &    │
│  White Cards, Light Inputs, │ │    Python Module Import)    │
│  Sleek Blue Buttons)        │ │                             │
└──────────────┬──────────────┘ └──────────────┬──────────────┘
               │ (debounced render job)        │ (direct render)
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     ScoreboardRenderer                      │
│                  (Dispatcher & Multiplier)                  │
└──────────────┬───────────────────────────────┬──────────────┘
               │ (Renders Dark TV Broadcast Aesthetics on Canvas)
               ▼
     ┌─────────┴─────────┐           ┌─────────┴─────────┐
     ▼                   ▼           ▼                   ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Layout 1:   │ │  Layout 2:   │ │  Layout 3:   │ │  Layout 4:   │
│   ATP H2H    │ │ Service Grid │ │Shot Breakdown│ │Classic Card  │
│ (Image 1 Ref)│ │ (Image 2 Ref)│ │ (Image 3 Ref)│ │  (Sidebar)   │
└──────────────┴──────────────┴─┴──────────────┴─┴──────────────┘
               ▲                               ▲
               └───────────────┬───────────────┘
                               │
                ┌─────────────────────────────┐
                │         GraphicsKit         │
                │  - Procedural Arena Lights  │
                │  - Glassmorphic Cards       │
                │  - Comparison Bars & Glow   │
                │  - Mini Flag Vector Badges  │
                │  - Player Portrait Cutouts  │
                └─────────────────────────────┘
```

> [!NOTE]
> **Dual UI Styling Architecture**:
> - **Software GUI (Controls, Filters, Buttons, Tabs)**: Styled in an elegant **Light Theme** (pure white `#ffffff` cards, soft off-white `#f1f5f9` window backgrounds, dark slate `#0f172a` typography, crisp light buttons, and vibrant blue `#0284c7` primary actions) for maximum daytime legibility and clean controls.
> - **Canvas & Generated Graphic (Output)**: Retains the TV-broadcast **Dark Graphic Aesthetics** (procedural arena floodlights, glassmorphic dark navy cards, and electric neon lime `#dfff3c` leader highlights) as seen on professional ATP Tour and Grand Slam broadcasts.

---

## 2. Project Directory & Key Components

- **`scoreboard_generator.py`**: The complete, self-contained single-file engine containing all data models, renderers, CLI, and GUI.
- **`DEVELOPER_GUIDE.md`**: This technical guide.
- **Dependencies**: Only `Pillow` (PIL) is strictly required (`numpy` is optional for accelerated gradients). Standard Python library (`tkinter`, `json`, `dataclasses`, `argparse`, `threading`, `queue`).

---

## 3. Interactive PPT Drag-and-Drop Positioning System

The studio allows users to reposition graphic elements directly on the preview canvas using the mouse, exactly like PowerPoint, Google Slides, or Canva:

### How it Works:
1. **Coordinate Hit-Testing**: `ScoreboardRenderer.get_element_bounds(config)` calculates normalized bounding boxes `(x0, y0, x1, y1)` in 1920x1080 space for all visual elements (Header Banner, Player 1 Profile, Player 2 Profile, Center Stats / Service Cards / Breakdown Tables).
2. **Mouse Interaction**:
   - **Hover**: Subtle dashed cyan outline indicates the element under the cursor; cursor changes to `fleur` (✥).
   - **Click & Drag**: Real-time bounding box with 8 circular anchor handles and a position badge (`✥ Player 1: [X: +30px, Y: -10px]`) follows mouse movement at 60fps.
   - **Keyboard Nudge**: When an element is selected, arrow keys nudge it by 2px (or 10px with `Shift`).
   - **Drop / Commit**: Releasing the mouse updates `config.element_offsets` and triggers asynchronous high-fidelity redraw.
   - **Reset**: Clicking "↺ Reset Positions" instantly resets all element offsets back to `[0, 0]`.
3. **Multi-Resolution Scaling**: `(dx, dy)` offsets scale proportionally across all resolutions (1080p, 4K, 8K) so custom placements look crisp on TV broadcast outputs.
4. **JSON Serialization**: Custom positions are saved in JSON match configurations under `element_offsets`.

---

## 4. Python API Integration (Headless / Backend Usage)

Technical staff can use the studio as a headless Python rendering library without opening the desktop GUI:

### Basic Example: Generate an ATP Head-to-Head Graphic in 5 Lines

```python
from scoreboard_generator import ScoreboardConfig, ScoreboardRenderer

# 1. Initialize configuration with defaults
config = ScoreboardConfig()
config.layout_mode = "h2h_broadcast"
config.player1.name = "CARLOS ALCARAZ"
config.player1.country = "ESP"
config.player2.name = "JACK DRAPER"
config.player2.country = "GBR"

# 2. Render image (multiplier=1 is 1080p, multiplier=2 is 4K)
image = ScoreboardRenderer.render(config, multiplier=1)

# 3. Save to disk
image.save("match_preview.png", "PNG")
print("Saved 1920x1080 graphic!")
```

### Loading from a JSON Config File

```python
from scoreboard_generator import ScoreboardConfig, ScoreboardRenderer

# Load saved match JSON
config = ScoreboardConfig.load_from_file("match_data.json")

# Render at 4K resolution (3840x2160)
img_4k = ScoreboardRenderer.render(config, multiplier=2)
img_4k.save("broadcast_4k.jpg", "JPEG", quality=95)
```

---

## 5. Command-Line Interface (CLI)

The script features a built-in CLI for headless automation, batch processing, and CI/CD pipelines:

```bash
# Display CLI help
python scoreboard_generator.py --help

# Generate a graphic using a built-in preset
python scoreboard_generator.py --preset "ATP Brisbane Blue (Image 1)" --export match1.png

# Generate a 4K graphic (scale=2) from a JSON config
python scoreboard_generator.py --config my_match.json --export high_res.png --scale 2

# Export JPEG with custom quality
python scoreboard_generator.py --preset "Winston-Salem Dark (Image 2)" --export service.jpg --format JPEG --quality 95

# Launch the interactive GUI Studio (default)
python scoreboard_generator.py
```

---

## 6. How to Add a New Theme Preset (in 10 Lines)

To add a new theme (e.g. "Australian Open Cyan"), simply add an entry to `PRESET_THEMES` inside `scoreboard_generator.py`:

```python
PRESET_THEMES["Australian Open Cyan"] = {
    "layout_mode": "h2h_broadcast",
    "bg_color": [6, 20, 36],
    "panel_top_color": [10, 30, 56],
    "panel_bottom_color": [4, 14, 28],
    "accent_color": [0, 220, 255],        # Cyan Accent
    "secondary_accent": [0, 110, 240],    # Deep Ocean Blue
    "highlight_color": [0, 220, 255],
    "bar_track_color": [24, 48, 76],
    "title_color": [255, 255, 255],
    "label_color": [210, 230, 245],
}
```
The new preset will automatically appear in the GUI dropdown and CLI `--preset` argument!

---

## 7. How to Add a New Graphic Layout

All layouts are rendered by dedicated methods on `ScoreboardRenderer`. To create a new layout (e.g. `render_basketball_boxscore`):

1. **Add the method signature**:
   ```python
   @classmethod
   def render_basketball_boxscore(cls, config: ScoreboardConfig, W: int, H: int) -> Image.Image:
       img = GraphicsKit.create_procedural_arena_bg(W, H, tuple(config.bg_color))
       draw = ImageDraw.Draw(img)
       s = W / 1920.0
       # Draw your custom layout elements using GraphicsKit primitives
       return img.convert("RGB")
   ```

2. **Add to `render()` dispatcher**:
   ```python
   if config.layout_mode == "basketball_boxscore":
       return cls.render_basketball_boxscore(config, W, H)
   ```

3. **Add to `LAYOUT_MODES` dictionary**:
   ```python
   LAYOUT_MODES["basketball_boxscore"] = "🏀 Basketball Box Score"
   ```

---

## 8. GraphicsKit Primitives Reference

The `GraphicsKit` class encapsulates broadcast-grade visual primitives:
- **`create_procedural_arena_bg(W, H, base_color)`**: Generates an ambient arena spotlight and dark vignette backdrop with subtle stadium lighting.
- **`draw_glass_card(draw, xy, radius, fill, outline, border_width)`**: Draws a rounded card with a 1px specular top highlight and subtle depth.
- **`draw_flag_badge(draw, x, y, w, h, country_code, font)`**: Draws an authentic national flag pill for 20+ countries (AUS, USA, FRA, ESP, GBR, ITA, GER, etc.).
- **`draw_comparison_bar(draw, x0, y, w, h, pct, is_leader, accent_col, track_col)`**: Draws a comparative meter with rounded corners and glowing leader edge.
- **`draw_player_portrait(img, x, y, size, photo_path, player_name, border_col)`**: Formats a player portrait or generates a broadcast silhouette avatar with initials.

---

## 9. Threading & Performance Architecture

- **UI Thread Safety**: Rendering is performed on a background daemon worker thread.
- **Render Queue Debounce**: User keystrokes and switch toggles trigger a 100ms debounce timer before pushing a job to `render_queue`.
- **Backlog Dropping**: If multiple rapid redraw requests arrive while the worker is busy, the queue automatically discards intermediate requests and processes only the latest state, ensuring zero UI freezing or memory leaks.
