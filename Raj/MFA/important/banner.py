"""
Live Banner Generator
======================
Creates a mirrored stadium/court promo banner with a vertical text divider,
in the style of "LIVE FROM <CITY>" broadcast graphics.

Usage (CLI):
    python live_banner_generator.py --text "LIVE FROM SEOUL" --out banner.png
    python live_banner_generator.py --text "LIVE FROM PARIS" --half-width 700 --height 900
    python live_banner_generator.py --text "LIVE FROM TOKYO" --wall-color "#7A1F3D" --accent-color "#F2C14E"

Usage (as a module):
    from live_banner_generator import BannerConfig, build_banner
    cfg = BannerConfig(text="LIVE FROM SEOUL")
    img = build_banner(cfg)
    img.save("banner.png")

Requirements:
    pip install pillow
"""

import argparse
import random
from dataclasses import dataclass, field
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
@dataclass
class BannerConfig:
    text: str = "LIVE FROM SEOUL"          # word(s) shown stacked in the bar
    half_width: int = 683                  # width of ONE mirrored half
    height: int = 768                      # overall image height
    bar_width: int = 121                   # width of the white vertical divider
    font_path: str = DEFAULT_FONT_PATH
    font_size: int = 40
    text_color: str = "#111111"
    bar_color: str = "#FFFFFF"

    sky_top_color: Tuple[int, int, int] = (128, 195, 235)
    sky_bottom_color: Tuple[int, int, int] = (30, 110, 175)
    wall_color: str = "#0B6B46"
    accent_color: str = "#7ED957"
    court_color: str = "#1D6FB5"

    seed: int = 7                          # RNG seed -> reproducible crowd/cloud texture

    @property
    def width(self) -> int:
        return self.half_width * 2 + self.bar_width


# -----------------------------------------------------------------------------
# Scene drawing (one half; mirrored to build the full banner)
# -----------------------------------------------------------------------------
def _draw_half(cfg: BannerConfig, rng: random.Random) -> Image.Image:
    w, h = cfg.half_width, cfg.height
    img = Image.new("RGB", (w, h), cfg.court_color)
    draw = ImageDraw.Draw(img)

    # ---- Sky gradient ----
    sky_bottom = int(h * 0.42)
    top_c, bot_c = cfg.sky_top_color, cfg.sky_bottom_color
    for y in range(sky_bottom):
        t = y / sky_bottom
        r = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
        g = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
        b = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # ---- Clouds ----
    cloud_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(cloud_layer)
    for _ in range(5):
        cx = rng.randint(int(w * 0.1), int(w * 0.9))
        cy = rng.randint(20, int(sky_bottom * 0.55))
        for _ in range(6):
            rx = rng.randint(30, 70)
            ry = rng.randint(10, 20)
            ox = cx + rng.randint(-60, 60)
            oy = cy + rng.randint(-10, 10)
            cdraw.ellipse([ox - rx, oy - ry, ox + rx, oy + ry], fill=(255, 255, 255, 60))
    cloud_layer = cloud_layer.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img.convert("RGBA"), cloud_layer).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ---- Floodlights ----
    def floodlight(cx, cy, scale=1.0):
        rows, cols = 4, 5
        spacing = 13 * scale
        for r in range(rows):
            for c in range(cols):
                lx = cx + (c - cols / 2) * spacing
                ly = cy + (r - rows / 2) * spacing
                rad = 5 * scale
                draw.ellipse([lx - rad, ly - rad, lx + rad, ly + rad], fill="#fff9e0")
                draw.ellipse([lx - rad, ly - rad, lx + rad, ly + rad], outline="#d8cf9a", width=1)
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        gr = 70 * scale
        gdraw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=(255, 250, 220, 70))
        return glow.filter(ImageFilter.GaussianBlur(25))

    positions = [(w * 0.06, h * 0.07, 1.15), (w * 0.86, h * 0.085, 0.7)]
    for cx, cy, scale in positions:
        glow = floodlight(cx, cy, scale)
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(img)
        floodlight(cx, cy, scale)  # redraw bulbs crisp on top of glow

    for cx, top in [(w * 0.06, h * 0.10), (w * 0.86, h * 0.115)]:
        draw.line([(cx - 18, top), (cx - 4, top + 55)], fill="#3a4a55", width=2)
        draw.line([(cx + 18, top), (cx + 4, top + 55)], fill="#3a4a55", width=2)
        for k in range(4):
            yk = top + 12 * (k + 1)
            xw = 18 - k * 3
            draw.line([(cx - xw, yk), (cx + xw, yk)], fill="#3a4a55", width=1)

    # ---- Stadium bowl ----
    bowl_top = int(h * 0.16)
    bowl_bottom = int(h * 0.44)
    tiers = 5
    for t in range(tiers):
        ty0 = bowl_top + (bowl_bottom - bowl_top) * t / tiers
        ty1 = bowl_top + (bowl_bottom - bowl_top) * (t + 1) / tiers
        shade = 235 - t * 14
        draw.rectangle([0, ty0, w, ty1], fill=(shade - 30, shade - 15, shade))
        for _ in range(int(w * 0.9)):
            px = rng.randint(0, w)
            py = rng.randint(int(ty0), int(ty1))
            if rng.random() < 0.35:
                c = rng.choice(["#8b98a8", "#c9d3de", "#5c6a7a", "#e8ecf1", "#2f3a45"])
                draw.point((px, py), fill=c)
        draw.line([(0, ty1), (w, ty1)], fill="#a9b6c2", width=1)

    for x in range(0, w, 26):
        draw.line([(x, bowl_top - 6), (x + 13, bowl_top + 4)], fill="#3a4a55", width=1)

    draw.rectangle([0, bowl_bottom, w, bowl_bottom + 6], fill="#f2e9c9")

    # ---- Wall with diagonal accent ----
    wall_top = bowl_bottom + 6
    wall_bottom = int(h * 0.62)
    draw.rectangle([0, wall_top, w, wall_bottom], fill=cfg.wall_color)
    stripe_w = 70
    x0, y0 = int(w * 0.10), wall_bottom
    x1, y1 = int(w * 0.32), wall_top
    for off in range(-stripe_w // 2, stripe_w // 2):
        draw.line([(x0 + off, y0), (x1 + off, y1)], fill=cfg.accent_color, width=1)

    # ---- Court ----
    draw.rectangle([0, wall_bottom, w, h], fill=cfg.court_color)
    draw.line([(0, h), (int(w * 0.30), wall_bottom)], fill="#e7f1fb", width=3)
    draw.line([(int(w * 0.55), h), (int(w * 0.42), wall_bottom)], fill="#e7f1fb", width=2)

    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(sheen)
    for _ in range(6):
        sx = rng.randint(0, w)
        sdraw.polygon(
            [(sx, h), (sx + 40, wall_bottom), (sx + 70, wall_bottom), (sx + 15, h)],
            fill=(255, 255, 255, 22),
        )
    sheen = sheen.filter(ImageFilter.GaussianBlur(4))
    img = Image.alpha_composite(img.convert("RGBA"), sheen).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ---- Net ----
    net_y = wall_bottom + int((h - wall_bottom) * 0.30)
    net_h = int((h - wall_bottom) * 0.26)
    net_x0 = int(w * 0.05)
    net_x1 = w
    draw.rectangle([net_x0 - 4, net_y - 14, net_x0, net_y + net_h], fill="#1a1a1a")
    draw.rectangle([net_x1 - 4, net_y - 14, net_x1, net_y + net_h], fill="#1a1a1a")
    draw.rectangle([net_x0, net_y - 6, net_x1, net_y], fill="#f4f4f4")

    mesh = Image.new("RGBA", (net_x1 - net_x0, net_h), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(mesh)
    step = 9
    for x in range(0, mesh.width, step):
        mdraw.line([(x, 0), (x, mesh.height)], fill=(15, 15, 15, 160), width=1)
    for y in range(0, mesh.height, step):
        mdraw.line([(0, y), (mesh.width, y)], fill=(15, 15, 15, 160), width=1)
    net_region = img.crop((net_x0, net_y, net_x1, net_y + net_h)).convert("RGBA")
    img.paste(Image.alpha_composite(net_region, mesh).convert("RGB"), (net_x0, net_y))
    draw = ImageDraw.Draw(img)

    draw.line([(0, net_y + net_h + 2), (w, net_y + net_h + 2)], fill="#eef6ff", width=3)

    return img


# -----------------------------------------------------------------------------
# Vertical divider text
# -----------------------------------------------------------------------------
def _draw_vertical_text(draw: ImageDraw.ImageDraw, cfg: BannerConfig, bar_x0: int) -> None:
    words = cfg.text.split(" ")
    font = ImageFont.truetype(cfg.font_path, cfg.font_size)
    bbox = font.getbbox("M")
    line_h = (bbox[3] - bbox[1]) + 14
    gap_h = line_h * 0.55

    n_letters = sum(len(w) for w in words)
    n_gaps = max(0, len(words) - 1)
    total_h = line_h * n_letters + gap_h * n_gaps
    y = (cfg.height - total_h) / 2

    for word in words:
        for ch in word:
            cb = font.getbbox(ch)
            cw = cb[2] - cb[0]
            cx = bar_x0 + cfg.bar_width / 2 - cw / 2 - cb[0]
            cy = y - cb[1]
            draw.text((cx, cy), ch, font=font, fill=cfg.text_color)
            y += line_h
        y += gap_h


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------
def build_banner(cfg: BannerConfig) -> Image.Image:
    """Build and return the finished mirrored banner as a PIL Image."""
    rng = random.Random(cfg.seed)
    half = _draw_half(cfg, rng)
    mirrored = half.transpose(Image.FLIP_LEFT_RIGHT)

    scene = Image.new("RGB", (cfg.width, cfg.height), cfg.bar_color)
    scene.paste(half, (0, 0))
    scene.paste(mirrored, (cfg.half_width + cfg.bar_width, 0))

    draw = ImageDraw.Draw(scene)
    bar_x0 = cfg.half_width
    draw.rectangle([bar_x0, 0, bar_x0 + cfg.bar_width, cfg.height], fill=cfg.bar_color)
    _draw_vertical_text(draw, cfg, bar_x0)

    return scene


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def _parse_args() -> BannerConfig:
    p = argparse.ArgumentParser(description="Generate a mirrored 'LIVE FROM ...' stadium banner.")
    p.add_argument("--text", default="LIVE FROM SEOUL", help='Words to stack vertically, e.g. "LIVE FROM TOKYO"')
    p.add_argument("--out", default="live_banner.png", help="Output PNG path")
    p.add_argument("--half-width", type=int, default=683, help="Width of one mirrored half, in px")
    p.add_argument("--height", type=int, default=768, help="Overall image height, in px")
    p.add_argument("--bar-width", type=int, default=121, help="Width of the white vertical divider, in px")
    p.add_argument("--font-size", type=int, default=40)
    p.add_argument("--font-path", default=DEFAULT_FONT_PATH)
    p.add_argument("--text-color", default="#111111")
    p.add_argument("--bar-color", default="#FFFFFF")
    p.add_argument("--wall-color", default="#0B6B46", help="Back-wall color behind the net")
    p.add_argument("--accent-color", default="#7ED957", help="Diagonal accent stripe color")
    p.add_argument("--court-color", default="#1D6FB5", help="Court surface / base color")
    p.add_argument("--seed", type=int, default=7, help="RNG seed for crowd/cloud texture (reproducible output)")
    args = p.parse_args()

    return BannerConfig(
        text=args.text,
        half_width=args.half_width,
        height=args.height,
        bar_width=args.bar_width,
        font_path=args.font_path,
        font_size=args.font_size,
        text_color=args.text_color,
        bar_color=args.bar_color,
        wall_color=args.wall_color,
        accent_color=args.accent_color,
        court_color=args.court_color,
        seed=args.seed,
    ), args.out


def main():
    cfg, out_path = _parse_args()
    img = build_banner(cfg)
    img.save(out_path)
    print(f"Saved {img.size[0]}x{img.size[1]} banner -> {out_path}")


if __name__ == "__main__":
    main()
