#!/usr/bin/env python3
"""
Match Stats Card Generator — 4-Template Production Build
=========================================================
All layouts pixel-matched to reference images:

  T1  Single Player Stats      — photo + solid dark panel, title + stacked stat rows
  T2  Head-to-Head Insights    — split cards, pill stat rows, playing-style tags, center-V
  T3  VS Tug-of-War            — split photos top, full-width mirrored bars, score line
  T4  Performance Spotlight    — 3-column player card leaderboard, banner, sponsor footer

Run:
    python scoreboard_app.py

Verify every template without opening the GUI:
    python scoreboard_app.py --render-all ./template_previews

Requires:
    pip install pillow
"""

from __future__ import annotations
import argparse, copy, csv, json, os, re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter, ImageEnhance
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

IMAGE_FILETYPES = [
    ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.avif"),
    ("All files", "*.*"),
]

PROJECT_FILETYPES = [
    ("Scoreboard project", "*.scoreboard.json"),
    ("JSON", "*.json"),
]


# ═══════════════════════════════════════════════════════════════════════════
# FONTS
# ═══════════════════════════════════════════════════════════════════════════

_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf",
]
_BOLD_ITALIC = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
]
_ITALIC = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "C:/Windows/Fonts/ariali.ttf",
]
_fc: Dict[Tuple, Any] = {}

def _lf(paths, size):
    k = (paths[0], size)
    if k in _fc: return _fc[k]
    f = None
    for p in paths:
        if os.path.exists(p):
            try: f = ImageFont.truetype(p, size); break
            except: pass
    if f is None: f = ImageFont.load_default()
    _fc[k] = f; return f

def fb(s):  return _lf(_BOLD, max(1, s))
def fr(s):  return _lf(_REG,  max(1, s))
def fbi(s): return _lf(_BOLD_ITALIC, max(1, s))
def fi(s):  return _lf(_ITALIC, max(1, s))


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def exnum(text: str) -> Optional[float]:
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(text))
    return float(m.group(0).replace(",", ".")) if m else None

def pct(val, maxv) -> float:
    n = exnum(val)
    if n is None: return 0.0
    try: mv = float(maxv)
    except: mv = 100.0
    if mv <= 0: mv = 100.0
    return max(0.0, min(100.0, n / mv * 100))

def load_photo(path: str) -> Optional[Image.Image]:
    if not path or not os.path.exists(path): return None
    try: return Image.open(path).convert("RGBA")
    except: return None

def cover_crop(img: Image.Image, w: int, h: int, zoom: float = 100.0,
               focus_x: float = 50.0, focus_y: float = 50.0) -> Image.Image:
    img = img.convert("RGB")
    pw, ph = img.size
    scale = max(w / pw, h / ph) * max(1.0, float(zoom) / 100.0)
    nw, nh = max(1, int(pw*scale)), max(1, int(ph*scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = int(max(0, nw-w) * max(0.0, min(100.0, float(focus_x))) / 100.0)
    top = int(max(0, nh-h) * max(0.0, min(100.0, float(focus_y))) / 100.0)
    return img.crop((left, top, left+w, top+h))

def text_bbox(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def draw_text_centered(draw, text, font, cx, cy, fill):
    w, h = text_bbox(draw, text, font)
    bb = draw.textbbox((0,0), text, font=font)
    draw.text((cx - w//2, cy - h//2 - bb[1]), text, font=font, fill=fill)

def draw_text_right(draw, text, font, rx, y, fill):
    w, _ = text_bbox(draw, text, font)
    draw.text((rx - w, y), text, font=font, fill=fill)

def fit_font(draw, text: str, max_width: int, start_size: int,
             minimum: int = 8, factory=fb):
    """Return the largest requested font that fits the available width."""
    size = max(minimum, int(start_size))
    font = factory(size)
    while size > minimum and text_bbox(draw, text, font)[0] > max_width:
        size -= 1
        font = factory(size)
    return font

def ellipsize(draw, text: str, font, max_width: int) -> str:
    if text_bbox(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    value = text
    while value and text_bbox(draw, value + suffix, font)[0] > max_width:
        value = value[:-1]
    return value.rstrip() + suffix if value else suffix


# ═══════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════

THEME = {
    "bg":       (10, 30, 48),
    "panel":    (18, 32, 54),
    "row_bg":   (38, 54, 82),
    "bar_track":(28, 40, 58),
    "bar_lose": (80, 95, 115),
    "accent":   (210, 235, 60),
    "white":    (255, 255, 255),
    "label":    (220, 228, 235),
    "muted":    (145, 160, 180),
    "dark":     (12, 20, 34),
}


# ═══════════════════════════════════════════════════════════════════════════
# CANVAS SIZES
# ═══════════════════════════════════════════════════════════════════════════

T1_SIZES = {
    "16:9  (1920x1080)": (1920, 1080),
    "16:9  (1024x576)":  (1024, 576),
    "1:1   (1024x1024)": (1024, 1024),
    "9:16  (576x1024)":  (576, 1024),
}
T2_SIZES = {
    "Wide  (1152x640)":  (1152, 640),
    "Square(1080x1080)": (1080, 1080),
    "Story (1080x1920)": (1080, 1920),
}
T3_SIZES = {
    "Square(1080x1080)": (1080, 1080),
    "Wide  (1280x720)":  (1280, 720),
    "4:5   (1080x1350)": (1080, 1350),
}
T4_SIZES = {
    "Square(1080x1080)": (1080, 1080),
    "Wide  (1620x1080)": (1620, 1080),
    "4:5   (1080x1350)": (1080, 1350),
}


# ═══════════════════════════════════════════════════════════════════════════
# T1 — SINGLE PLAYER STATS
# Ref: LsozI9nozgQzay40lO0h2wBvlM.avif
# Full-bleed photo, solid black panel right, title, stacked rows
# ═══════════════════════════════════════════════════════════════════════════

def render_t1(cfg: Dict) -> Image.Image:
    W, H = T1_SIZES.get(cfg.get("canvas_size","16:9  (1920x1080)"), (1920,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc   = tuple(cfg.get("accent_color", THEME["accent"]))
    side  = cfg.get("panel_side","right")

    img = Image.new("RGB", (W,H), THEME["bg"])
    photo = load_photo(cfg.get("photo_path",""))
    if photo:
        img.paste(cover_crop(
            photo, W, H, cfg.get("photo_zoom", 100),
            cfg.get("photo_focus_x", 50), cfg.get("photo_focus_y", 50)
        ), (0,0))

    # Solid dark panel (ref shows near-black rectangle, not a fade)
    panel_ratio = 0.40
    panel_w = int(W * panel_ratio)
    x0 = W - panel_w if side == "right" else 0

    # Fade leading edge, solid rest
    fade_w = max(1, int(panel_w * 0.22))
    layer  = Image.new("RGBA", (W,H), (0,0,0,0))
    pd     = ImageDraw.Draw(layer)
    for x in range(panel_w):
        cx = x0 + x
        if side == "right":
            a = int(245 * min(1.0, x / fade_w)) if x < fade_w else 245
        else:
            rx = panel_w - 1 - x
            a  = int(245 * min(1.0, rx / fade_w)) if rx < fade_w else 245
        pd.line([(cx,0),(cx,H)], fill=(8,10,14,a))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

    draw   = ImageDraw.Draw(img)
    tx0    = x0 + int(panel_w * 0.09)
    tw     = panel_w - int(panel_w * 0.18)

    # Title
    title_sz = max(32, int(H * 0.082))
    tf  = fb(title_sz)
    cy  = int(H * 0.082)
    for line in cfg.get("title","Match\nStatistics").replace("\\n","\n").split("\n"):
        draw.text((tx0, cy), line, font=tf, fill=THEME["white"])
        bb = draw.textbbox((0,0), line, font=tf)
        cy += (bb[3]-bb[1]) + int(title_sz * 0.22)
    cy += int(H * 0.038)

    # Stat rows
    rows = cfg.get("rows",[])
    n    = max(1, len(rows))
    avail= H - cy - int(H * 0.05)
    slot = avail / n
    lsz  = max(14, int(H * 0.034))
    vsz  = max(26, int(H * 0.072))
    lf_  = fr(lsz)
    vf_  = fb(vsz)
    bar_h= max(4, int(H * 0.013))
    igap = int(H * 0.012)
    bgap = int(H * 0.016)

    for row in rows:
        label = row.get("label","")
        value = row.get("value","")
        maxv  = row.get("max","100")

        draw.text((tx0, cy), label, font=lf_, fill=THEME["label"])
        cy += lsz + igap

        draw.text((tx0, cy), value, font=vf_, fill=acc)
        vbb = draw.textbbox((0,0), value, font=vf_)
        cy += (vbb[3]-vbb[1]) + bgap

        b0, b1 = cy, cy + bar_h
        draw.rounded_rectangle([tx0,b0,tx0+tw,b1], radius=bar_h//2, fill=THEME["bar_track"])
        fw = int(tw * pct(value,maxv) / 100)
        if fw > 0:
            draw.rounded_rectangle([tx0,b0,tx0+max(fw,bar_h),b1], radius=bar_h//2, fill=acc)

        used = lsz + igap + (vbb[3]-vbb[1]) + bgap + bar_h
        cy   = b1 + slot - used

    return img


# ═══════════════════════════════════════════════════════════════════════════
# T2 — HEAD-TO-HEAD INSIGHTS
# Ref: PRESS_RELEASE.webp (Tsitsipas vs Schwartzman)
# Split panel, player photos flanking, pill stat rows, playing-style tags
# ═══════════════════════════════════════════════════════════════════════════

def _pill_row(draw, x0, w, cy, rh, bh, label, value, other_value,
              max_value, mirrored, acc, theme):
    """One side of a comparison row: rounded-rect pill + bar below."""
    n_v = exnum(value) or 0.0
    n_o = exnum(other_value) or 0.0
    winner = n_v >= n_o

    pad     = int(w * 0.06)
    lsz     = max(12, int(rh * 0.36))
    vsz     = max(16, int(rh * 0.46))
    lf_     = fit_font(draw, str(label), int(w*.62), lsz, minimum=8, factory=fb)
    vf_     = fit_font(draw, str(value), int(w*.30), vsz, minimum=9, factory=fb)
    val_col = acc if winner else theme["white"]

    # Pill background
    draw.rounded_rectangle([x0, cy, x0+w, cy+rh], radius=8, fill=(*theme["row_bg"],230))

    if not mirrored:
        draw.text((x0+pad, cy+rh//2), label, font=lf_, fill=theme["white"], anchor="lm")
        draw_text_right(draw, str(value), vf_, x0+w-pad, cy+(rh-vsz)//2, val_col)
    else:
        draw.text((x0+pad, cy+rh//2), str(value), font=vf_, fill=val_col, anchor="lm")
        draw_text_right(draw, label, lf_, x0+w-pad, cy+(rh-lsz)//2, theme["white"])

    # Bar
    by0, by1 = cy+rh+5, cy+rh+5+bh
    draw.rounded_rectangle([x0,by0,x0+w,by1], radius=bh//2, fill=theme["bar_track"])
    fw = int(w * pct(value, max_value) / 100)
    bc = acc if winner else theme["bar_lose"]
    if fw > 0:
        draw.rounded_rectangle([x0,by0,x0+max(fw,bh),by1], radius=bh//2, fill=bc)
    return by1

def render_t2(cfg: Dict) -> Image.Image:
    W, H = T2_SIZES.get(cfg.get("canvas_size","Wide  (1152x640)"), (1152,640))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = tuple(cfg.get("accent_color", THEME["accent"]))
    half = W // 2
    photo_w = int(half * 0.40)

    img = Image.new("RGB", (W,H), THEME["panel"])

    def paste_photo(path, x, prefix, flip=False):
        p = load_photo(path)
        if p is None: return
        p = p.convert("RGB")
        ph = cover_crop(
            p, photo_w, H, cfg.get(f"{prefix}_zoom", 100),
            cfg.get(f"{prefix}_focus_x", 50), cfg.get(f"{prefix}_focus_y", 50)
        )
        # bottom-fade into panel
        mask = Image.new("L",(photo_w,H),255)
        md   = ImageDraw.Draw(mask)
        fade = int(H*0.28)
        for y in range(fade):
            md.line([(0,y),(photo_w,y)], fill=int(255*y/fade))
        inner_fade = int(photo_w*0.28)
        px = mask.load()
        for x_ in range(inner_fade):
            a = int(255 * x_ / inner_fade)
            col = (photo_w-1-x_) if not flip else x_
            for y in range(fade, H):
                if a < px[col,y]: px[col,y]=a
        mask = mask.filter(ImageFilter.GaussianBlur(4))
        base = Image.new("RGBA",(photo_w,H),(*THEME["panel"],255))
        top_ = Image.new("RGBA",(photo_w,H),(*THEME["panel"],255))
        top_.paste(ph,(0,0)); top_.putalpha(mask)
        out  = Image.alpha_composite(base,top_).convert("RGB")
        img.paste(out, (x,0))

    paste_photo(cfg.get("photo_a",""), 0, "photo_a", flip=False)
    paste_photo(cfg.get("photo_b",""), W-photo_w, "photo_b", flip=True)

    draw = ImageDraw.Draw(img, "RGBA")
    margin = int(W*0.018)
    tz_w   = half - photo_w - margin*2
    ltz_x  = photo_w + margin
    rtz_x  = half + margin

    # Header bars (white pill)
    hdr_h = int(H * 0.055)
    hdr_w = tz_w + int(tz_w*0.05)
    hdr_y = int(H*0.04)
    hdr_text = cfg.get("header_text","INSIGHTS | SHOT QUALITY")
    hdr_f = fit_font(draw, hdr_text, hdr_w-int(hdr_w*.08),
                     max(10, int(hdr_h*0.38)), minimum=8, factory=fb)
    for hx in (ltz_x, rtz_x):
        draw.rectangle([hx, hdr_y, hx+hdr_w, hdr_y+hdr_h], fill=(255,255,255))
        tw_, th_ = text_bbox(draw, hdr_text, hdr_f)
        bb = draw.textbbox((0,0), hdr_text, hdr_f)
        draw.text((hx+(hdr_w-tw_)//2, hdr_y+(hdr_h-th_)//2-bb[1]),
                  hdr_text, font=hdr_f, fill=(18,28,44))

    # Player names
    name_y = hdr_y + hdr_h + int(H*0.028)
    ff_sz  = max(10, int(H*0.030))
    fl_sz  = max(14, int(H*0.048))
    ff_    = fr(ff_sz)
    fl_    = fb(fl_sz)

    def draw_name(x, fn, ln, abbr=""):
        # Draw italic first name muted, bold last name
        first = fn.upper()
        last = ln.upper()
        first_font = fit_font(draw, first, int(tz_w*.38), ff_sz, minimum=8, factory=fi)
        fw_ = text_bbox(draw, first+" ", first_font)[0]
        reserve = text_bbox(draw, abbr, fr(max(8,int(H*0.020))))[0] + 12 if abbr else 0
        last_font = fit_font(draw, last, max(20, tz_w-fw_-reserve), fl_sz,
                             minimum=10, factory=fb)
        draw.text((x, name_y), first, font=first_font, fill=THEME["muted"])
        draw.text((x+fw_, name_y+(ff_sz-fl_sz)//2), last, font=last_font, fill=THEME["white"])
        if abbr:
            abf = fr(max(8,int(H*0.020)))
            draw.text((x+fw_+text_bbox(draw,last,last_font)[0]+8, name_y+2),
                      abbr, font=abf, fill=THEME["muted"])

    draw_name(ltz_x, cfg.get("name_a_first","Player"), cfg.get("name_a_last","One"), cfg.get("abbr_a",""))
    draw_name(rtz_x, cfg.get("name_b_first","Player"), cfg.get("name_b_last","Two"), cfg.get("abbr_b",""))

    # Stat rows
    rows_y = name_y + fl_sz + int(H*0.065)
    rh     = int(H * 0.098)
    rgap   = int(H * 0.022)
    bar_h  = int(H * 0.011)
    rows   = cfg.get("rows",[])

    cy = rows_y
    for row in rows:
        label = row.get("label","")
        va    = str(row.get("value_a","0"))
        vb    = str(row.get("value_b","0"))
        maxv  = str(row.get("max","10"))
        bottom_a = _pill_row(
            draw, ltz_x, tz_w, cy, rh, bar_h, label, va, vb, maxv, False, acc, THEME
        )
        bottom_b = _pill_row(
            draw, rtz_x, tz_w, cy, rh, bar_h, label, vb, va, maxv, True, acc, THEME
        )
        cy = max(bottom_a,bottom_b) + rgap

    # Playing style
    if cfg.get("show_playing_style",True):
        style_h = int(H*0.078)
        sf_     = fb(max(10,int(H*0.028)))
        sl_lbl  = cfg.get("style_label","PLAYING STYLE")
        for sx in (ltz_x, rtz_x):
            draw.rounded_rectangle([sx,cy,sx+tz_w,cy+style_h], radius=8, fill=(*THEME["row_bg"],230))
            tw_,th_ = text_bbox(draw,sl_lbl,sf_)
            bb = draw.textbbox((0,0),sl_lbl,sf_)
            draw.text((sx+(tz_w-tw_)//2, cy+(style_h-th_)//2-bb[1]), sl_lbl, font=sf_, fill=THEME["white"])
        cy2 = cy + style_h + int(H*0.014)
        tag_h  = int(H*0.072)
        tag_f  = fb(max(9,int(H*0.022)))
        tags_a = cfg.get("tags_a",["",""])
        tags_b = cfg.get("tags_b",["",""])
        for sx, tags in ((ltz_x,tags_a),(rtz_x,tags_b)):
            tw_2 = (tz_w - 6) // 2
            for i, tag in enumerate(tags[:2]):
                tx0 = sx + i*(tw_2+6)
                draw.rounded_rectangle([tx0,cy2,tx0+tw_2,cy2+tag_h], radius=6, fill=(*THEME["panel"],255))
                draw.rectangle([tx0,cy2,tx0+tw_2,cy2+tag_h], outline=(75,92,118), width=1)
                words = tag.upper().split()
                ly = cy2 + (tag_h - len(words)*int(H*0.026))//2
                for wd in words:
                    ww,_ = text_bbox(draw,wd,tag_f)
                    draw.text((tx0+(tw_2-ww)//2, ly), wd, font=tag_f, fill=acc)
                    ly += int(H*0.028)

    # Center V divider
    vbox_w = int(W*0.042)
    vbox_h = int(rh*1.4)
    vbox_x = W//2 - vbox_w//2
    vbox_y = rows_y + int(H*0.06)
    draw.rectangle([vbox_x,vbox_y,vbox_x+vbox_w,vbox_y+vbox_h], fill=THEME["dark"])
    vf2    = fbi(int(vbox_h*0.52))
    vt     = cfg.get("divider_text","V")
    tw_,th_= text_bbox(draw,vt,vf2)
    bb     = draw.textbbox((0,0),vt,vf2)
    draw.text((vbox_x+(vbox_w-tw_)//2, vbox_y+(vbox_h-th_)//2-bb[1]), vt, font=vf2, fill=THEME["white"])

    return img.convert("RGB")


# ═══════════════════════════════════════════════════════════════════════════
# T3 — VS TUG-OF-WAR
# Ref: DEhdrT7QjZPSm8ZAYVdi3lKc20.avif (Blomqvist vs Gabran)
# Split photos top half, names flanking center VS, full-width symmetric bars
# ═══════════════════════════════════════════════════════════════════════════

def render_t3(cfg: Dict) -> Image.Image:
    W, H = T3_SIZES.get(cfg.get("canvas_size","Square(1080x1080)"), (1080,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = tuple(cfg.get("accent_color", THEME["accent"]))

    img  = Image.new("RGB",(W,H),THEME["bg"])
    draw_bg = ImageDraw.Draw(img)

    # Photo zone top ~52% of canvas
    photo_h = int(H * 0.52)
    half    = W // 2

    def paste_half_photo(path, x, w, prefix, flip_inner=False):
        p = load_photo(path)
        if p is None:
            Image.new("RGB",(w,photo_h),THEME["panel"]).convert("RGB")
            img.paste(Image.new("RGB",(w,photo_h),(28,40,58)), (x,0))
            return
        p = cover_crop(
            p, w, photo_h, cfg.get(f"{prefix}_zoom", 100),
            cfg.get(f"{prefix}_focus_x", 50), cfg.get(f"{prefix}_focus_y", 50)
        )
        # bottom fade
        mask = Image.new("L",(w,photo_h),255)
        md   = ImageDraw.Draw(mask)
        fade = int(photo_h*0.30)
        for y in range(photo_h-fade, photo_h):
            a = int(255*(1-(y-(photo_h-fade))/fade))
            md.line([(0,y),(w,y)], fill=a)
        mask = mask.filter(ImageFilter.GaussianBlur(6))
        base = Image.new("RGBA",(w,photo_h),(*THEME["bg"],255))
        top_ = p.convert("RGBA"); top_.putalpha(mask)
        out  = Image.alpha_composite(base,top_).convert("RGB")
        img.paste(out,(x,0))

    paste_half_photo(cfg.get("photo_a",""), 0,    half, "photo_a")
    paste_half_photo(cfg.get("photo_b",""), half, W-half, "photo_b")

    # Thin vertical seam line at center
    draw_bg.line([(half,0),(half,photo_h)], fill=(40,55,75), width=3)

    # Sponsor logo zone (top center)
    logo_path = cfg.get("logo_path","")
    logo_h    = int(H*0.08)
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            lw   = int(logo.width * logo_h / logo.height)
            logo = logo.resize((lw,logo_h), Image.LANCZOS)
            img.paste(logo, (half-lw//2, int(H*0.02)), logo)
        except: pass

    draw = ImageDraw.Draw(img)

    # Names sit in the photo fade, matching the reference composition.
    name_y  = photo_h - int(H*0.105)
    fn_sz   = max(14, int(H*0.036))
    ln_sz   = max(20, int(H*0.054))
    team_sz = max(10, int(H*0.022))
    team_f  = fr(team_sz)

    margin = int(W*0.028)

    # Left player
    fn_a  = cfg.get("name_a_first","CLARISSA")
    ln_a  = cfg.get("name_a_last","BLOMQVIST")
    team_a= cfg.get("team_a","HLK")
    fn_a_f = fit_font(draw, fn_a.upper(), half-2*margin, fn_sz, minimum=9, factory=fi)
    ln_a_f = fit_font(draw, ln_a.upper(), half-2*margin, ln_sz, minimum=12, factory=fbi)
    draw.text((margin, name_y), fn_a.upper(), font=fn_a_f, fill=THEME["muted"])
    draw.text((margin, name_y+fn_sz+4), ln_a.upper(), font=ln_a_f, fill=THEME["white"])
    draw.text((margin, name_y+fn_sz+ln_sz+8), team_a.upper(), font=team_f, fill=THEME["muted"])

    # Right player
    rx    = W - margin
    fn_b  = cfg.get("name_b_first","EMELIE")
    ln_b  = cfg.get("name_b_last","GABRÁN")
    team_b= cfg.get("team_b","ÅLK")
    fn_b_f = fit_font(draw, fn_b.upper(), half-2*margin, fn_sz, minimum=9, factory=fi)
    ln_b_f = fit_font(draw, ln_b.upper(), half-2*margin, ln_sz, minimum=12, factory=fbi)
    draw_text_right(draw, fn_b.upper(), fn_b_f, rx, name_y, THEME["muted"])
    draw_text_right(draw, ln_b.upper(), ln_b_f, rx, name_y+fn_sz+4, THEME["white"])
    draw_text_right(draw, team_b.upper(), team_f, rx, name_y+fn_sz+ln_sz+8, THEME["muted"])

    # VS + score in center
    vs_sz   = max(22, int(H*0.058))
    score_sz= max(12, int(H*0.026))
    vs_f    = fbi(vs_sz)
    sc_f    = fb(score_sz)
    vs_text = cfg.get("vs_text","VS")
    score   = cfg.get("score","6-4  3-6  10-4")
    draw_text_centered(draw, vs_text, vs_f, half, name_y+fn_sz+ln_sz//2, THEME["white"])
    draw_text_centered(draw, score, sc_f, half, name_y+fn_sz+ln_sz+score_sz, THEME["muted"])

    # Stat rows — full width, center-symmetric
    rows_y  = photo_h + int(H*0.055)
    lbl_sz  = max(11, int(H*0.026))
    val_sz  = max(18, int(H*0.046))
    bar_h   = max(4,  int(H*0.011))
    lbl_f   = fb(lbl_sz)
    val_f   = fb(val_sz)
    unit_f  = fr(max(9, int(val_sz*0.50)))

    rows    = cfg.get("rows",[])
    n_rows  = max(1,len(rows))
    avail   = H - rows_y - int(H*0.08)
    rslot   = avail / n_rows
    side_pad= int(W * 0.04)

    cy = rows_y
    for row in rows:
        label   = row.get("label","")
        va      = str(row.get("value_a","0"))
        vb      = str(row.get("value_b","0"))
        maxv    = str(row.get("max","200"))
        unit    = str(row.get("unit",""))

        na = exnum(va) or 0.0
        nb = exnum(vb) or 0.0
        a_wins = na >= nb

        row_top = cy
        label_y = row_top + int(val_sz * 0.42)
        row_label_font = fit_font(draw, label.upper(), int(W*.54), lbl_sz,
                                  minimum=8, factory=fb)
        draw_text_centered(draw, label.upper(), row_label_font, half, label_y, THEME["label"])

        # Values are anchored at the outside edges, leaving the center clear.
        a_col      = acc if a_wins else THEME["white"]
        b_col = acc if not a_wins else THEME["white"]
        val_a_w, _ = text_bbox(draw, va, val_f)
        val_b_w, _ = text_bbox(draw, vb, val_f)
        unit_w, _ = text_bbox(draw, unit.upper(), unit_f) if unit else (0, 0)
        unit_gap = 5 if unit else 0
        draw.text((side_pad, row_top), va, font=val_f, fill=a_col)
        right_group_x = W - side_pad - val_b_w - unit_gap - unit_w
        draw.text((right_group_x, row_top), vb, font=val_f, fill=b_col)

        # Optional units (KMH etc)
        if unit:
            unit_y = row_top + int(val_sz*0.23)
            draw.text((side_pad+val_a_w+unit_gap, unit_y), unit.upper(), font=unit_f, fill=THEME["muted"])
            draw.text((right_group_x+val_b_w+unit_gap, unit_y), unit.upper(), font=unit_f, fill=THEME["muted"])

        # Bars — grow from center outward
        bar_cy = row_top + val_sz + int(H*0.008)
        draw.rounded_rectangle([side_pad, bar_cy, half-4, bar_cy+bar_h],
                                radius=bar_h//2, fill=THEME["bar_track"])
        draw.rounded_rectangle([half+4, bar_cy, W-side_pad, bar_cy+bar_h],
                                radius=bar_h//2, fill=THEME["bar_track"])

        pct_a = pct(va, maxv) / 100
        pct_b = pct(vb, maxv) / 100
        bar_total = half - 4 - side_pad

        # Left bar: grows rightward from left edge to center-4
        fw_a = int(bar_total * pct_a)
        if fw_a > 0:
            draw.rounded_rectangle([half-4-fw_a, bar_cy, half-4, bar_cy+bar_h],
                                    radius=bar_h//2, fill=acc if a_wins else THEME["white"])
        # Right bar: grows leftward from right edge to center+4
        fw_b = int(bar_total * pct_b)
        if fw_b > 0:
            draw.rounded_rectangle([half+4, bar_cy, half+4+fw_b, bar_cy+bar_h],
                                    radius=bar_h//2, fill=acc if not a_wins else THEME["white"])

        cy += rslot

    # Footer sponsor logo text
    footer_text = cfg.get("sponsor_text","")
    if footer_text:
        ftf = fr(max(10,int(H*0.022)))
        tw_,_ = text_bbox(draw, footer_text, ftf)
        draw.text((half-tw_//2, H-int(H*0.05)), footer_text, font=ftf, fill=THEME["muted"])

    return img


# ═══════════════════════════════════════════════════════════════════════════
# T4 — PERFORMANCE SPOTLIGHT (3-column leaderboard)
# Ref: rnYnYY86X0jLaYZ6lR7P7g1New.avif
# Title banner, 3 equal player card columns, photo, stacked stats, result line
# ═══════════════════════════════════════════════════════════════════════════

def render_t4(cfg: Dict) -> Image.Image:
    W, H = T4_SIZES.get(cfg.get("canvas_size","Square(1080x1080)"), (1080,1080))
    render_scale = max(1, int(cfg.get("_render_scale", 1)))
    W, H = W * render_scale, H * render_scale
    acc  = tuple(cfg.get("accent_color", THEME["accent"]))

    img  = Image.new("RGB",(W,H),THEME["bg"])
    draw = ImageDraw.Draw(img)

    # Banner
    banner_h = int(H * 0.088)
    banner_text = cfg.get("banner_text","PERFORMANCE SPOTLIGHT")
    bf   = fit_font(draw, banner_text, int(W*.92), max(16, int(banner_h*0.48)),
                    minimum=12, factory=fb)
    tw_,th_ = text_bbox(draw, banner_text, bf)
    bb   = draw.textbbox((0,0),banner_text,bf)
    draw.text((W//2-tw_//2, (banner_h-th_)//2-bb[1]+int(H*0.012)), banner_text, font=bf, fill=THEME["white"])

    # Column layout
    n_players = 3
    col_gap   = int(W * 0.012)
    col_w     = (W - col_gap*(n_players+1)) // n_players
    col_y0    = banner_h + int(H*0.01)
    col_h     = H - col_y0 - int(H*0.09)  # leave footer
    players   = copy.deepcopy(cfg.get("players", []))

    # Pad to 3 players
    while len(players) < 3:
        players.append({"team":"","first":"Player","last":"","photo":"","stats":[],"result":""})

    for i, player in enumerate(players[:3]):
        cx0 = col_gap + i*(col_w + col_gap)
        cx1 = cx0 + col_w

        # Team label
        team_sz = max(9, int(H*0.020))
        name_sz_s = max(10, int(H*0.026))
        name_sz_l = max(14, int(H*0.038))
        team_f_  = fr(team_sz)

        name_y = col_y0 + int(H*0.005)
        team   = player.get("team","")
        fn_    = player.get("first","Player")
        ln_    = player.get("last","")
        if team:
            draw.text((cx0, name_y), team.upper(), font=team_f_, fill=THEME["muted"])
            name_y += team_sz + 3
        fn_f_ = fit_font(draw, fn_.upper(), col_w, name_sz_s, minimum=8, factory=fi)
        ln_f_ = fit_font(draw, ln_.upper(), col_w, name_sz_l, minimum=10, factory=fbi)
        draw.text((cx0, name_y), fn_.upper(), font=fn_f_, fill=THEME["muted"])
        draw.text((cx0, name_y+name_sz_s+2), ln_.upper(), font=ln_f_, fill=THEME["white"])
        name_block_h = (team_sz+3 if team else 0) + name_sz_s + 2 + name_sz_l

        # Photo
        photo_y0 = col_y0 + name_block_h + int(H*0.012)
        photo_h  = int(col_h * 0.46)
        p = load_photo(player.get("photo",""))
        if p:
            ph = cover_crop(
                p, col_w, photo_h, player.get("photo_zoom", 100),
                player.get("photo_focus_x", 50), player.get("photo_focus_y", 50)
            )
            # bottom fade into background
            mask = Image.new("L",(col_w,photo_h),255)
            md   = ImageDraw.Draw(mask)
            fade = int(photo_h*0.28)
            for y in range(photo_h-fade, photo_h):
                a = int(255*(1-(y-(photo_h-fade))/fade))
                md.line([(0,y),(col_w,y)],fill=a)
            mask = mask.filter(ImageFilter.GaussianBlur(5))
            base = Image.new("RGBA",(col_w,photo_h),(*THEME["bg"],255))
            ov   = ph.convert("RGBA"); ov.putalpha(mask)
            out  = Image.alpha_composite(base,ov).convert("RGB")
            img.paste(out,(cx0,photo_y0))
        else:
            draw.rectangle([cx0,photo_y0,cx1,photo_y0+photo_h], fill=(28,40,56))

        draw = ImageDraw.Draw(img)

        # Stats below photo
        stat_y = photo_y0 + photo_h + int(H*0.008)
        stats  = player.get("stats",[])
        lbl_sz = max(9,  int(H*0.020))
        val_sz = max(18, int(H*0.048))
        bar_h_ = max(3,  int(H*0.008))
        lf__   = fr(lbl_sz)
        vf__   = fb(val_sz)
        unit_  = fr(max(8,int(val_sz*0.45)))

        # First stat gets large treatment (Fastest Serve)
        first_stat = stats[0] if stats else None
        if first_stat:
            first_label = first_stat.get("label","").upper()
            first_label_font = fit_font(draw, first_label, col_w, lbl_sz,
                                        minimum=7, factory=fr)
            draw.text((cx0, stat_y), first_label, font=first_label_font, fill=THEME["label"])
            stat_y += lbl_sz + 3
            val_str = str(first_stat.get("value","0"))
            unit_str= first_stat.get("unit","")
            draw.text((cx0, stat_y), val_str, font=vf__, fill=THEME["white"])
            vw,_ = text_bbox(draw, val_str, vf__)
            if unit_str:
                draw.text((cx0+vw+4, stat_y+int(val_sz*0.2)), unit_str, font=unit_, fill=THEME["muted"])
            stat_y += val_sz + 3
            # bar
            draw.rounded_rectangle([cx0,stat_y,cx1,stat_y+bar_h_], radius=bar_h_//2, fill=THEME["bar_track"])
            fw_=int(col_w*pct(val_str,first_stat.get("max","250"))/100)
            if fw_>0: draw.rounded_rectangle([cx0,stat_y,cx0+fw_,stat_y+bar_h_],radius=bar_h_//2,fill=acc)
            stat_y += bar_h_ + int(H*0.012)

        # Remaining stats (smaller)
        sm_val_sz = max(12, int(H*0.032))
        sm_vf     = fb(sm_val_sz)
        for st in (stats[1:] if stats else []):
            lbl_str = st.get("label","").upper()
            val_str = str(st.get("value","0"))
            unit_str= st.get("unit","")
            stat_label_font = fit_font(draw, lbl_str, col_w, lbl_sz,
                                       minimum=7, factory=fr)
            draw.text((cx0, stat_y), lbl_str, font=stat_label_font, fill=THEME["label"])
            stat_y += lbl_sz + 2
            draw.text((cx0, stat_y), val_str, font=sm_vf, fill=THEME["white"])
            svw,_ = text_bbox(draw, val_str, sm_vf)
            if unit_str:
                draw.text((cx0+svw+3, stat_y+int(sm_val_sz*0.22)), unit_str, font=unit_, fill=THEME["muted"])
            stat_y += sm_val_sz + 2
            draw.rounded_rectangle([cx0,stat_y,cx1,stat_y+bar_h_],radius=bar_h_//2,fill=THEME["bar_track"])
            fw_=int(col_w*pct(val_str,st.get("max","100"))/100)
            if fw_>0: draw.rounded_rectangle([cx0,stat_y,cx0+fw_,stat_y+bar_h_],radius=bar_h_//2,fill=acc)
            stat_y += bar_h_ + int(H*0.011)

        # Result line
        result = player.get("result","")
        if result:
            rf  = fr(max(9,int(H*0.019)))
            ry  = H - int(H*0.075)
            result = ellipsize(draw, result.upper(), rf, col_w)
            tw__,_ = text_bbox(draw, result.upper(), rf)
            draw.text((cx0+(col_w-tw__)//2, ry), result.upper(), font=rf, fill=THEME["muted"])

    # Footer sponsors / logos
    footer_text = cfg.get("sponsor_text","")
    if footer_text:
        ftf = fr(max(11,int(H*0.024)))
        tw_,_ = text_bbox(draw, footer_text, ftf)
        draw.text((W//2-tw_//2, H-int(H*0.042)), footer_text, font=ftf, fill=THEME["muted"])

    # Vertical column dividers
    for i in range(1, n_players):
        dx = col_gap + i*(col_w+col_gap) - col_gap//2
        draw.line([(dx,col_y0+int(H*0.04)),(dx,H-int(H*0.1))], fill=(38,52,70), width=1)

    return img


# ═══════════════════════════════════════════════════════════════════════════
# DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════

DEF_T1 = {
    "template":"t1", "canvas_size":"16:9  (1920x1080)", "panel_side":"right",
    "photo_path":"", "photo_zoom":100, "photo_focus_x":50, "photo_focus_y":50,
    "title":"Match\nStatistics", "accent_color":list(THEME["accent"]),
    "rows":[
        {"label":"1st Serve %",              "value":"72 %","max":"100"},
        {"label":"2nd Serve win %",          "value":"71 %","max":"100"},
        {"label":"1st Serve Return win %",   "value":"54 %","max":"100"},
        {"label":"Short Rallies Won (1-4 shots)", "value":"66 %","max":"100"},
    ],
}

DEF_T2 = {
    "template":"t2", "canvas_size":"Wide  (1152x640)",
    "header_text":"INSIGHTS | SHOT QUALITY", "divider_text":"V",
    "photo_a":"","photo_b":"",
    "photo_a_zoom":100,"photo_a_focus_x":50,"photo_a_focus_y":50,
    "photo_b_zoom":100,"photo_b_focus_x":50,"photo_b_focus_y":50,
    "name_a_first":"Stefanos","name_a_last":"Tsitsipas","abbr_a":"GRE",
    "name_b_first":"Diego",   "name_b_last":"Schwartzman","abbr_b":"ARG",
    "accent_color":list(THEME["accent"]),
    "rows":[
        {"label":"SERVE",    "value_a":"8.2","value_b":"6.6","max":"10"},
        {"label":"RETURN",   "value_a":"7.0","value_b":"7.5","max":"10"},
        {"label":"FOREHAND", "value_a":"8.0","value_b":"7.9","max":"10"},
        {"label":"BACKHAND", "value_a":"7.5","value_b":"8.1","max":"10"},
    ],
    "show_playing_style":True, "style_label":"PLAYING STYLE",
    "tags_a":["Big Server","All Courter"],
    "tags_b":["Counter Puncher","Solid Baseliner"],
}

DEF_T3 = {
    "template":"t3", "canvas_size":"Square(1080x1080)",
    "photo_a":"","photo_b":"","logo_path":"",
    "photo_a_zoom":100,"photo_a_focus_x":50,"photo_a_focus_y":50,
    "photo_b_zoom":100,"photo_b_focus_x":50,"photo_b_focus_y":50,
    "name_a_first":"Clarissa","name_a_last":"Blomqvist","team_a":"HLK",
    "name_b_first":"Emelie",  "name_b_last":"Gabrán",  "team_b":"ÅLK",
    "vs_text":"VS","score":"6-4  3-6  10-4",
    "accent_color":list(THEME["accent"]),
    "sponsor_text":"zenniz",
    "rows":[
        {"label":"Groundstroke Speed","value_a":"107","value_b":"111","max":"200","unit":"KMH"},
        {"label":"1st Serve Speed",   "value_a":"154","value_b":"155","max":"250","unit":"KMH"},
        {"label":"Short Rallies Won", "value_a":"54", "value_b":"45", "max":"100","unit":""},
        {"label":"Long Rallies Won %","value_a":"4",  "value_b":"15", "max":"100","unit":""},
    ],
}

DEF_T4 = {
    "template":"t4", "canvas_size":"Square(1080x1080)",
    "banner_text":"PERFORMANCE SPOTLIGHT",
    "accent_color":list(THEME["accent"]),
    "sponsor_text":"TEHO TENNIS LIIGA   ·   zenniz",
    "players":[
        {"team":"HVS","first":"Otto","last":"Virtanen","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. J. Karlsson Wistrand 6-1, 6-2",
         "stats":[
             {"label":"Fastest Serve","value":"218","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"89","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"82","unit":"%","max":"100"},
             {"label":"Short Points Won %","value":"72","unit":"%","max":"100"},
         ]},
        {"team":"HVS","first":"Viktor","last":"Durasovic","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. V. Ahti 6-3, 6-1",
         "stats":[
             {"label":"Fastest Serve","value":"200","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"68","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"75","unit":"%","max":"100"},
             {"label":"Medium Points Won %","value":"71","unit":"%","max":"100"},
         ]},
        {"team":"HVS","first":"Leevi","last":"Säätelä","photo":"",
         "photo_zoom":100,"photo_focus_x":50,"photo_focus_y":50,
         "result":"Def. V. Ahti 6-4, 6-3",
         "stats":[
             {"label":"Fastest Serve","value":"197","unit":"KMH","max":"300"},
             {"label":"1st Serve Won %","value":"74","unit":"%","max":"100"},
             {"label":"1st Serve Return %","value":"71","unit":"%","max":"100"},
             {"label":"Long Points Won %","value":"74","unit":"%","max":"100"},
         ]},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# UNDO STACK
# ═══════════════════════════════════════════════════════════════════════════

class UndoStack:
    MAX=60
    def __init__(self): self._s=[]; self._p=-1
    def push(self,s):
        self._s=self._s[:self._p+1]; self._s.append(copy.deepcopy(s))
        if len(self._s)>self.MAX: self._s.pop(0)
        self._p=len(self._s)-1
    def undo(self):
        if self._p>0: self._p-=1; return copy.deepcopy(self._s[self._p])
        return None
    def redo(self):
        if self._p<len(self._s)-1: self._p+=1; return copy.deepcopy(self._s[self._p])
        return None


class PhotoFramingDialog(tk.Toplevel):
    """Small, visual crop editor shared by every photo slot."""

    def __init__(self, parent, path, target_size, zoom, focus_x, focus_y, on_apply):
        super().__init__(parent)
        self.title("Adjust photo")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._source = load_photo(path)
        self._on_apply = on_apply
        self._tk_preview = None

        target_w, target_h = target_size
        ratio = target_w / max(1, target_h)
        preview_w = 520
        preview_h = max(180, min(360, int(preview_w / ratio)))
        if preview_h == 360:
            preview_w = max(240, int(preview_h * ratio))
        self._preview_size = (preview_w, preview_h)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body, width=preview_w, height=preview_h, bg="#1d2630",
            highlightthickness=1, highlightbackground="#aeb8c2",
        )
        self.canvas.pack()

        self.zoom_var = tk.DoubleVar(value=float(zoom))
        self.focus_x_var = tk.DoubleVar(value=float(focus_x))
        self.focus_y_var = tk.DoubleVar(value=float(focus_y))
        for label, variable, low, high in (
            ("Zoom", self.zoom_var, 100, 300),
            ("Move left / right", self.focus_x_var, 0, 100),
            ("Move up / down", self.focus_y_var, 0, 100),
        ):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(10, 0))
            ttk.Label(row, text=label, width=18, anchor="w").pack(side="left")
            ttk.Scale(
                row, from_=low, to=high, variable=variable,
                command=lambda _=None: self._redraw(),
            ).pack(side="left", fill="x", expand=True)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Center photo", command=self._center).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(
            buttons, text="Apply framing", style="Primary.TButton", command=self._apply,
        ).pack(side="right", padx=(0, 8))
        self._redraw()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _center(self):
        self.zoom_var.set(100)
        self.focus_x_var.set(50)
        self.focus_y_var.set(50)
        self._redraw()

    def _redraw(self):
        if self._source is None:
            return
        width, height = self._preview_size
        preview = cover_crop(
            self._source, width, height, self.zoom_var.get(),
            self.focus_x_var.get(), self.focus_y_var.get(),
        )
        self._tk_preview = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(width // 2, height // 2, image=self._tk_preview)

    def _apply(self):
        self._on_apply(
            round(self.zoom_var.get(), 1),
            round(self.focus_x_var.get(), 1),
            round(self.focus_y_var.get(), 1),
        )
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# ROW WIDGETS
# ═══════════════════════════════════════════════════════════════════════════

class T1Row:
    def __init__(self, parent, on_change, data=None):
        data = data or {"label":"New Stat","value":"0 %","max":"100"}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data["label"])
        self.vv=tk.StringVar(value=data["value"])
        self.mv=tk.StringVar(value=str(data["max"]))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=30).grid(row=0,column=1,padx=3)
        ttk.Label(self.frame,text="Value:").grid(row=0,column=2,sticky="w")
        ttk.Entry(self.frame,textvariable=self.vv,width=10).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=4,sticky="w")
        ttk.Entry(self.frame,textvariable=self.mv,width=6).grid(row=0,column=5,padx=3)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=6,padx=(4,0))
        for v in (self.lv,self.vv,self.mv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self): return {"label":self.lv.get(),"value":self.vv.get(),"max":self.mv.get()}

class T2Row:
    def __init__(self, parent, on_change, data=None):
        data = data or {"label":"Stat","value_a":"0","value_b":"0","max":"10"}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data["label"])
        self.av=tk.StringVar(value=str(data["value_a"]))
        self.bv=tk.StringVar(value=str(data["value_b"]))
        self.mv=tk.StringVar(value=str(data["max"]))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=14).grid(row=0,column=1,padx=3)
        ttk.Label(self.frame,text="P1:").grid(row=0,column=2)
        ttk.Entry(self.frame,textvariable=self.av,width=7).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="P2:").grid(row=0,column=4)
        ttk.Entry(self.frame,textvariable=self.bv,width=7).grid(row=0,column=5,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=6)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=7,padx=3)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=8,padx=(4,0))
        for v in (self.lv,self.av,self.bv,self.mv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self): return {"label":self.lv.get(),"value_a":self.av.get(),"value_b":self.bv.get(),"max":self.mv.get()}

class T3Row:
    def __init__(self, parent, on_change, data=None):
        data = data or {"label":"Stat","value_a":"0","value_b":"0","max":"200","unit":""}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=2)
        self.lv=tk.StringVar(value=data["label"])
        self.av=tk.StringVar(value=str(data["value_a"]))
        self.bv=tk.StringVar(value=str(data["value_b"]))
        self.mv=tk.StringVar(value=str(data["max"]))
        self.uv=tk.StringVar(value=data.get("unit",""))
        ttk.Label(self.frame,text="Stat:").grid(row=0,column=0,sticky="w")
        ttk.Entry(self.frame,textvariable=self.lv,width=16).grid(row=0,column=1,padx=3)
        ttk.Label(self.frame,text="Left:").grid(row=0,column=2)
        ttk.Entry(self.frame,textvariable=self.av,width=7).grid(row=0,column=3,padx=3)
        ttk.Label(self.frame,text="Right:").grid(row=0,column=4)
        ttk.Entry(self.frame,textvariable=self.bv,width=7).grid(row=0,column=5,padx=3)
        ttk.Label(self.frame,text="Scale:").grid(row=0,column=6)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=7,padx=3)
        ttk.Label(self.frame,text="Unit:").grid(row=0,column=8)
        ttk.Entry(self.frame,textvariable=self.uv,width=5).grid(row=0,column=9,padx=3)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=10,padx=(4,0))
        for v in (self.lv,self.av,self.bv,self.mv,self.uv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self): return {"label":self.lv.get(),"value_a":self.av.get(),"value_b":self.bv.get(),"max":self.mv.get(),"unit":self.uv.get()}

class T4StatWidget:
    """Single stat row for one player in T4."""
    def __init__(self, parent, on_change, data=None):
        data = data or {"label":"Stat","value":"0","unit":"","max":"100"}
        self.on_change=on_change
        self.frame=ttk.Frame(parent); self.frame.pack(fill="x",pady=1)
        self.lv=tk.StringVar(value=data.get("label",""))
        self.vv=tk.StringVar(value=str(data.get("value","0")))
        self.uv=tk.StringVar(value=data.get("unit",""))
        self.mv=tk.StringVar(value=str(data.get("max","100")))
        ttk.Entry(self.frame,textvariable=self.lv,width=18).grid(row=0,column=0,padx=2)
        ttk.Entry(self.frame,textvariable=self.vv,width=6).grid(row=0,column=1,padx=2)
        ttk.Entry(self.frame,textvariable=self.uv,width=5).grid(row=0,column=2,padx=2)
        ttk.Entry(self.frame,textvariable=self.mv,width=5).grid(row=0,column=3,padx=2)
        ttk.Button(self.frame,text="Remove",width=7,command=self.delete).grid(row=0,column=4,padx=2)
        for v in (self.lv,self.vv,self.uv,self.mv): v.trace_add("write",lambda *a:self.on_change())
    def delete(self): self.frame.destroy(); self.on_change(remove=self)
    def get_data(self): return {"label":self.lv.get(),"value":self.vv.get(),"unit":self.uv.get(),"max":self.mv.get()}

class T4PlayerWidget:
    """Controls for one player column in T4."""
    def __init__(self, parent, on_change, data=None, idx=0):
        data = data or DEF_T4["players"][0]
        self.on_change=on_change; self.stat_widgets=[]
        self.frame=ttk.LabelFrame(parent, text=f"Player {idx+1}")
        self.frame.pack(fill="x",padx=4,pady=4)

        r=ttk.Frame(self.frame); r.pack(fill="x",pady=2)
        self.team_v=tk.StringVar(value=data.get("team",""))
        self.fn_v  =tk.StringVar(value=data.get("first",""))
        self.ln_v  =tk.StringVar(value=data.get("last",""))
        self.res_v =tk.StringVar(value=data.get("result",""))
        self.photo_path=data.get("photo","")
        self.photo_zoom=float(data.get("photo_zoom",100))
        self.photo_focus_x=float(data.get("photo_focus_x",50))
        self.photo_focus_y=float(data.get("photo_focus_y",50))

        ttk.Label(r,text="Team:").pack(side="left")
        ttk.Entry(r,textvariable=self.team_v,width=6).pack(side="left",padx=2)
        ttk.Label(r,text="First:").pack(side="left",padx=(8,2))
        ttk.Entry(r,textvariable=self.fn_v,width=10).pack(side="left",padx=2)
        ttk.Label(r,text="Last:").pack(side="left",padx=(8,2))
        ttk.Entry(r,textvariable=self.ln_v,width=12).pack(side="left",padx=2)

        r2=ttk.Frame(self.frame); r2.pack(fill="x",pady=2)
        ttk.Button(r2,text="Choose photo",command=self._photo).pack(side="left")
        ttk.Button(r2,text="Adjust",command=self._adjust_photo).pack(side="left",padx=(4,0))
        ttk.Button(r2,text="Remove",command=self._remove_photo).pack(side="left",padx=(4,0))
        self.photo_lbl=ttk.Label(
            r2,text=os.path.basename(self.photo_path) if self.photo_path else "No photo selected",
            foreground="#555",width=26,
        )
        self.photo_lbl.pack(side="left",padx=6)

        r3=ttk.Frame(self.frame); r3.pack(fill="x",pady=2)
        ttk.Label(r3,text="Result:").pack(side="left")
        ttk.Entry(r3,textvariable=self.res_v).pack(side="left",fill="x",expand=True,padx=4)

        # Stats sub-area
        sh=ttk.LabelFrame(self.frame,text="Stats  (stat | value | unit | bar scale)")
        sh.pack(fill="x",pady=4)
        self.stat_frame=ttk.Frame(sh); self.stat_frame.pack(fill="x")
        actions=ttk.Frame(sh); actions.pack(fill="x",padx=4,pady=3)
        ttk.Button(actions,text="Add stat",command=self._add_stat).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=self._paste_stats).pack(side="left",padx=4)
        for st in data.get("stats",[]): self._add_stat(st,commit=False)

        for v in (self.team_v,self.fn_v,self.ln_v,self.res_v):
            v.trace_add("write",lambda *a:self.on_change())

    def _photo(self):
        p=filedialog.askopenfilename(filetypes=IMAGE_FILETYPES)
        if p:
            self.photo_path=p
            self.photo_zoom=100; self.photo_focus_x=50; self.photo_focus_y=50
            self.photo_lbl.config(text=os.path.basename(p),foreground="#000")
            self.on_change()

    def _adjust_photo(self):
        if not self.photo_path or load_photo(self.photo_path) is None:
            messagebox.showinfo("Choose photo", "Choose a player photo first.", parent=self.frame)
            return
        PhotoFramingDialog(
            self.frame.winfo_toplevel(), self.photo_path, (3,4), self.photo_zoom,
            self.photo_focus_x, self.photo_focus_y, self._apply_photo_frame,
        )

    def _apply_photo_frame(self, zoom, focus_x, focus_y):
        self.photo_zoom=zoom; self.photo_focus_x=focus_x; self.photo_focus_y=focus_y
        self.on_change()

    def _remove_photo(self):
        self.photo_path=""
        self.photo_zoom=100; self.photo_focus_x=50; self.photo_focus_y=50
        self.photo_lbl.config(text="No photo selected",foreground="#555")
        self.on_change()

    def _paste_stats(self):
        try:
            text=self.frame.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Clipboard is empty", "Copy rows from Excel or Sheets first.", parent=self.frame)
            return
        rows=parse_pasted_rows(text,"t4")
        if not rows:
            messagebox.showwarning("No stats found", "The copied table did not contain usable rows.", parent=self.frame)
            return
        replace=messagebox.askyesnocancel(
            "Paste stats", "Replace existing stats?\n\nYes = replace   No = add below",
            parent=self.frame,
        )
        if replace is None:
            return
        if replace:
            for widget in self.stat_widgets:
                widget.frame.destroy()
            self.stat_widgets.clear()
        for row in rows:
            self._add_stat(row,commit=False)
        self.on_change()

    def _add_stat(self, data=None, commit=True):
        w=T4StatWidget(self.stat_frame,self._on_stat_change,data)
        self.stat_widgets.append(w)
        if commit: self.on_change()

    def _on_stat_change(self, remove=None):
        if remove and remove in self.stat_widgets: self.stat_widgets.remove(remove)
        self.on_change()

    def get_data(self):
        return {"team":self.team_v.get(),"first":self.fn_v.get(),"last":self.ln_v.get(),
                "photo":self.photo_path,"photo_zoom":self.photo_zoom,
                "photo_focus_x":self.photo_focus_x,"photo_focus_y":self.photo_focus_y,
                "result":self.res_v.get(),
                "stats":[w.get_data() for w in self.stat_widgets]}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE_NAMES = [
    "Single Player",
    "Head to Head",
    "Match Comparison",
    "3 Player Spotlight",
]
TEMPLATE_KEYS = ("t1", "t2", "t3", "t4")
RENDERERS = {
    "t1": render_t1,
    "t2": render_t2,
    "t3": render_t3,
    "t4": render_t4,
}
DEFAULT_CONFIGS = {
    "t1": DEF_T1,
    "t2": DEF_T2,
    "t3": DEF_T3,
    "t4": DEF_T4,
}


def normalise_project_configs(saved: Any) -> Dict[str, Dict]:
    """Merge a saved project with current defaults without trusting its shape."""
    source = saved if isinstance(saved, dict) else {}
    size_options = {"t1":T1_SIZES,"t2":T2_SIZES,"t3":T3_SIZES,"t4":T4_SIZES}
    result: Dict[str, Dict] = {}
    for key, default in DEFAULT_CONFIGS.items():
        config = copy.deepcopy(default)
        candidate = source.get(key)
        if isinstance(candidate, dict):
            config.update(copy.deepcopy(candidate))
        config["template"] = key
        if config.get("canvas_size") not in size_options[key]:
            config["canvas_size"] = default["canvas_size"]
        accent = config.get("accent_color")
        if not isinstance(accent,list) or len(accent) != 3:
            config["accent_color"] = copy.deepcopy(default["accent_color"])
        else:
            try:
                config["accent_color"] = [max(0,min(255,int(value))) for value in accent]
            except (TypeError,ValueError):
                config["accent_color"] = copy.deepcopy(default["accent_color"])
        if key == "t4":
            incoming=config.get("players") if isinstance(config.get("players"),list) else []
            players=[]
            for index in range(3):
                player=copy.deepcopy(default["players"][index])
                if index < len(incoming) and isinstance(incoming[index],dict):
                    player.update(copy.deepcopy(incoming[index]))
                stats=player.get("stats")
                player["stats"]=[row for row in stats if isinstance(row,dict)] if isinstance(stats,list) else []
                players.append(player)
            config["players"]=players
        else:
            rows=config.get("rows")
            config["rows"]=[row for row in rows if isinstance(row,dict)] if isinstance(rows,list) else copy.deepcopy(default["rows"])
        result[key] = config
    return result


def parse_pasted_rows(text: str, template: str) -> List[Dict[str, str]]:
    """Parse rows copied from Excel, Google Sheets, CSV, or pipe-delimited text."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return []
    if any("\t" in line for line in lines):
        values = [[cell.strip() for cell in line.split("\t")] for line in lines]
    elif any("|" in line for line in lines):
        values = [[cell.strip() for cell in line.split("|")] for line in lines]
    else:
        values = [[cell.strip() for cell in row] for row in csv.reader(lines)]

    if values and values[0]:
        first = values[0][0].strip().casefold()
        if first in {"label", "stat", "statistic", "metric"}:
            values = values[1:]

    rows: List[Dict[str, str]] = []
    for cells in values:
        if not cells or not cells[0]:
            continue
        cells += [""] * 5
        if template == "t1":
            rows.append({"label": cells[0], "value": cells[1], "max": cells[2] or "100"})
        elif template == "t2":
            rows.append({
                "label": cells[0], "value_a": cells[1], "value_b": cells[2],
                "max": cells[3] or "100",
            })
        elif template == "t3":
            rows.append({
                "label": cells[0], "value_a": cells[1], "value_b": cells[2],
                "max": cells[3] or "100", "unit": cells[4],
            })
        elif template == "t4":
            rows.append({
                "label": cells[0], "value": cells[1], "unit": cells[2],
                "max": cells[3] or "100",
            })
    return rows

class App:
    def __init__(self, root):
        self.root=root
        self._setup_style()
        root.geometry("1500x900")
        root.minsize(1200,700)

        self.cfgs = {
            key: copy.deepcopy(config)
            for key, config in DEFAULT_CONFIGS.items()
        }
        self.tpl     = "t1"
        self.t1_rows: List[T1Row] = []
        self.t2_rows: List[T2Row] = []
        self.t3_rows: List[T3Row] = []
        self.t4_players: List[T4PlayerWidget] = []
        self._undo   = UndoStack()
        self._suspend= False
        self._redraw_id = None
        self._undo_id   = None
        self._tk_img    = None
        self._last_render = None
        self._preview_resize_id = None
        self.current_project_path: Optional[Path] = None
        self._dirty = False

        self._build_ui()
        self._suspend = True
        try:
            self._rebuild_t1_rows()
            self._rebuild_t2_rows()
            self._rebuild_t3_rows()
            self._rebuild_t4_players()
        finally:
            self._suspend = False
        self._switch("t1", init=True)
        self._commit_undo()
        self._set_dirty(False)
        root.update_idletasks()
        self.redraw()
        root.bind("<Control-z>",lambda e:self.undo())
        root.bind("<Control-y>",lambda e:self.redo())
        root.bind("<Control-o>",lambda e:self.open_project())
        root.bind("<Control-s>",lambda e:self.save_project())
        root.bind("<Control-Shift-S>",lambda e:self.save_project(save_as=True))
        root.bind("<Control-e>",lambda e:self.export_png())
        root.protocol("WM_DELETE_WINDOW",self._on_close)

    def _setup_style(self):
        self.root.title("Scoreboard Maker")
        self.root.configure(bg="#eef2f5")
        style=ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame",background="#eef2f5")
        style.configure("TLabelframe",background="#f8fafb",bordercolor="#cbd4dc")
        style.configure("TLabelframe.Label",background="#f8fafb",foreground="#24313d",font=("Segoe UI",10,"bold"))
        style.configure("TLabel",background="#eef2f5",foreground="#24313d",font=("Segoe UI",9))
        style.configure("TButton",font=("Segoe UI",9),padding=(9,6))
        style.configure("Primary.TButton",background="#18794e",foreground="white",font=("Segoe UI",9,"bold"),padding=(12,7))
        style.map("Primary.TButton",background=[("active","#12613e"), ("pressed","#0e4f33")])
        style.configure("Toolbar.TFrame",background="#ffffff")
        style.configure("Title.TLabel",background="#ffffff",foreground="#15202b",font=("Segoe UI",15,"bold"))
        style.configure("Preview.TLabel",background="#eef2f5",foreground="#53616e",font=("Segoe UI",9))
        style.configure("Status.TLabel",background="#ffffff",foreground="#53616e",padding=(10,5))

    # ── UI scaffold ──────────────────────────────────────────────────────

    def _build_ui(self):
        top=ttk.Frame(self.root,style="Toolbar.TFrame",padding=(12,8)); top.pack(fill="x")
        ttk.Label(top,text="Scoreboard Maker",style="Title.TLabel").pack(side="left",padx=(0,16))
        ttk.Label(top,text="Layout",background="#ffffff").pack(side="left")
        self.tpl_var=tk.StringVar(value=TEMPLATE_NAMES[0])
        cb=ttk.Combobox(top,textvariable=self.tpl_var,values=TEMPLATE_NAMES,state="readonly",width=22)
        cb.pack(side="left",padx=(6,12))
        cb.bind("<<ComboboxSelected>>",self._on_tpl_switch)
        ttk.Button(top,text="Undo",command=self.undo).pack(side="left",padx=2)
        ttk.Button(top,text="Redo",command=self.redo).pack(side="left",padx=2)
        ttk.Separator(top,orient="vertical").pack(side="left",fill="y",padx=8)
        ttk.Button(top,text="Open project",command=self.open_project).pack(side="left",padx=2)
        ttk.Button(top,text="Save project",command=self.save_project).pack(side="left",padx=2)
        ttk.Button(top,text="Reset",command=self.reset_current_template).pack(side="left",padx=2)

        ttk.Button(top,text="Export PNG",style="Primary.TButton",command=self.export_png).pack(side="right",padx=(8,0))
        self.export_scale_var=tk.StringVar(value="Standard")
        ttk.Combobox(
            top,textvariable=self.export_scale_var,
            values=["Standard","High resolution (2x)"],state="readonly",width=20,
        ).pack(side="right")

        self.status_var=tk.StringVar(value="Ready")
        ttk.Label(self.root,textvariable=self.status_var,style="Status.TLabel",anchor="w").pack(side="bottom",fill="x")

        main=ttk.Panedwindow(self.root,orient="horizontal"); main.pack(fill="both",expand=True,padx=8,pady=8)
        lc=ttk.Frame(main,width=620); lc.pack_propagate(False)
        right=ttk.Frame(main)
        main.add(lc,weight=0); main.add(right,weight=1)

        edit_header=ttk.Frame(lc); edit_header.pack(fill="x",padx=(4,8),pady=(2,6))
        ttk.Label(edit_header,text="Edit content",font=("Segoe UI",12,"bold")).pack(side="left")
        sc=tk.Canvas(lc,borderwidth=0,highlightthickness=0,bg="#eef2f5")
        sb=ttk.Scrollbar(lc,orient="vertical",command=sc.yview)
        self.ctrl=ttk.Frame(sc)
        self.ctrl.bind("<Configure>",lambda e:sc.configure(scrollregion=sc.bbox("all")))
        self._ctrl_window=sc.create_window((0,0),window=self.ctrl,anchor="nw")
        sc.bind("<Configure>",lambda e:sc.itemconfigure(self._ctrl_window,width=e.width))
        sc.configure(yscrollcommand=sb.set)
        sc.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self._control_canvas=sc
        self.root.bind_all("<MouseWheel>",self._on_mousewheel,add="+")

        preview_header=ttk.Frame(right); preview_header.pack(fill="x",padx=8,pady=(2,6))
        ttk.Label(preview_header,text="Preview",font=("Segoe UI",12,"bold")).pack(side="left")
        self.preview_info_var=tk.StringVar(value="")
        ttk.Label(preview_header,textvariable=self.preview_info_var,style="Preview.TLabel").pack(side="right")
        self.preview_canvas=tk.Canvas(right,bg="#1c252d",highlightthickness=0)
        self.preview_canvas.pack(fill="both",expand=True,padx=8,pady=(0,8))
        self.preview_canvas.bind("<Configure>",self._on_preview_resize)

        # Build all 4 panels (hidden until switched)
        self.panels={}
        for key, builder in [("t1",self._build_t1),("t2",self._build_t2),
                               ("t3",self._build_t3),("t4",self._build_t4)]:
            p=ttk.Frame(self.ctrl); builder(p); self.panels[key]=p

    def _on_mousewheel(self,event):
        left=self._control_canvas.winfo_rootx()
        right=left+self._control_canvas.winfo_width()
        if left <= self.root.winfo_pointerx() <= right:
            self._control_canvas.yview_scroll(int(-event.delta/120),"units")

    def _on_preview_resize(self,_=None):
        if self._preview_resize_id:
            self.root.after_cancel(self._preview_resize_id)
        self._preview_resize_id=self.root.after(60,self._paint_preview)

    def _switch(self, key, init=False):
        for p in self.panels.values(): p.pack_forget()
        self.panels[key].pack(fill="both",expand=True)
        self.tpl=key
        if not init:
            self._commit_undo()
            self.redraw()

    def _on_tpl_switch(self, _=None):
        idx=TEMPLATE_NAMES.index(self.tpl_var.get())
        self._switch(TEMPLATE_KEYS[idx])

    # ── T1 controls ──────────────────────────────────────────────────────

    def _build_t1(self, p):
        pad={"padx":10,"pady":5}
        ib=ttk.LabelFrame(p,text="Photo"); ib.pack(fill="x",**pad)
        self._make_photo_row(ib,"t1","photo_path","_t1_img_lbl","Player photo")

        tb=ttk.LabelFrame(p,text="Title"); tb.pack(fill="x",**pad)
        self._t1_title=tk.Text(tb,height=2,width=30)
        self._t1_title.insert("1.0",self.cfgs["t1"]["title"])
        self._t1_title.pack(padx=6,pady=4,fill="x")
        self._t1_title.bind("<KeyRelease>",lambda e:self._txt_change("t1"))

        lb=ttk.LabelFrame(p,text="Appearance and size"); lb.pack(fill="x",**pad)
        ttk.Label(lb,text="Panel side:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        self._t1_side=tk.StringVar(value=self.cfgs["t1"]["panel_side"])
        ttk.Combobox(lb,textvariable=self._t1_side,values=["right","left"],state="readonly",width=8).grid(row=0,column=1,sticky="w",padx=6)
        self._t1_side.trace_add("write",lambda *a:self._disc_change("t1"))
        ttk.Label(lb,text="Canvas:").grid(row=1,column=0,sticky="w",padx=6)
        self._t1_size=tk.StringVar(value=self.cfgs["t1"]["canvas_size"])
        ttk.Combobox(lb,textvariable=self._t1_size,values=list(T1_SIZES.keys()),state="readonly",width=22).grid(row=1,column=1,sticky="w",padx=6)
        self._t1_size.trace_add("write",lambda *a:self._disc_change("t1"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t1")).grid(row=2,column=0,columnspan=2,sticky="w",padx=6,pady=5)

        sb=ttk.LabelFrame(p,text="Stat Rows"); sb.pack(fill="x",**pad)
        self._t1_rf=ttk.Frame(sb); self._t1_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t1_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t1")).pack(side="left",padx=4)

    def _rebuild_t1_rows(self):
        for r in self.t1_rows: r.frame.destroy()
        self.t1_rows.clear()
        for d in self.cfgs["t1"].get("rows",[]): self._add_t1_row(d,commit=False)

    def _add_t1_row(self,data=None,commit=True):
        r=T1Row(self._t1_rf,self._t1_row_change,data); self.t1_rows.append(r)
        if commit: self._disc_change("t1")

    def _t1_row_change(self,remove=None):
        if remove and remove in self.t1_rows: self.t1_rows.remove(remove); self._disc_change("t1"); return
        self._txt_change("t1")

    def _collect_t1(self):
        return {**self.cfgs["t1"],"panel_side":self._t1_side.get(),
                "canvas_size":self._t1_size.get(),"title":self._t1_title.get("1.0","end-1c"),
                "rows":[r.get_data() for r in self.t1_rows]}

    # ── T2 controls ──────────────────────────────────────────────────────

    def _build_t2(self, p):
        pad={"padx":10,"pady":5}
        pb=ttk.LabelFrame(p,text="Photos"); pb.pack(fill="x",**pad)
        self._make_photo_row(pb,"t2","photo_a","_t2_img_a","Player 1")
        self._make_photo_row(pb,"t2","photo_b","_t2_img_b","Player 2")

        nb=ttk.LabelFrame(p,text="Player Names"); nb.pack(fill="x",**pad)
        self._t2_nvars={}
        for key,lbl in [("name_a_first","P1 First"),("name_a_last","P1 Last"),("abbr_a","P1 Abbr"),
                         ("name_b_first","P2 First"),("name_b_last","P2 Last"),("abbr_b","P2 Abbr")]:
            r=ttk.Frame(nb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl+":",width=10,anchor="w").pack(side="left")
            v=tk.StringVar(value=self.cfgs["t2"].get(key,""))
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t2")); self._t2_nvars[key]=v

        hb=ttk.LabelFrame(p,text="Header & Divider"); hb.pack(fill="x",**pad)
        self._t2_header=tk.StringVar(value=self.cfgs["t2"]["header_text"])
        self._t2_divider=tk.StringVar(value=self.cfgs["t2"]["divider_text"])
        for lbl,var in [("Header:",self._t2_header),("Divider:",self._t2_divider)]:
            r=ttk.Frame(hb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl,width=8,anchor="w").pack(side="left")
            ttk.Entry(r,textvariable=var).pack(side="left",fill="x",expand=True,padx=4)
            var.trace_add("write",lambda *a:self._txt_change("t2"))

        lb=ttk.LabelFrame(p,text="Appearance and size"); lb.pack(fill="x",**pad)
        self._t2_size=tk.StringVar(value=self.cfgs["t2"]["canvas_size"])
        ttk.Label(lb,text="Canvas:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        ttk.Combobox(lb,textvariable=self._t2_size,values=list(T2_SIZES.keys()),state="readonly",width=18).grid(row=0,column=1,sticky="w",padx=6)
        self._t2_size.trace_add("write",lambda *a:self._disc_change("t2"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t2")).grid(row=1,column=0,columnspan=2,sticky="w",padx=6,pady=5)

        sb=ttk.LabelFrame(p,text="Comparison Rows  (winner auto-highlighted)"); sb.pack(fill="x",**pad)
        self._t2_rf=ttk.Frame(sb); self._t2_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t2_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t2")).pack(side="left",padx=4)

        sty=ttk.LabelFrame(p,text="Playing Style"); sty.pack(fill="x",**pad)
        self._t2_show_style=tk.BooleanVar(value=self.cfgs["t2"]["show_playing_style"])
        ttk.Checkbutton(sty,text="Show playing style",variable=self._t2_show_style,command=lambda:self._disc_change("t2")).pack(anchor="w",padx=6)
        self._t2_tag_vars={}
        for key,lbl in [("tags_a0","P1 tag 1"),("tags_a1","P1 tag 2"),("tags_b0","P2 tag 1"),("tags_b1","P2 tag 2")]:
            r=ttk.Frame(sty); r.pack(fill="x",pady=2,padx=6)
            ttk.Label(r,text=lbl+":",width=9,anchor="w").pack(side="left")
            side="a" if "a" in key else "b"; idx=int(key[-1])
            v=tk.StringVar(value=self.cfgs["t2"][f"tags_{side}"][idx])
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t2")); self._t2_tag_vars[key]=v

    def _rebuild_t2_rows(self):
        for r in self.t2_rows: r.frame.destroy()
        self.t2_rows.clear()
        for d in self.cfgs["t2"].get("rows",[]): self._add_t2_row(d,commit=False)

    def _add_t2_row(self,data=None,commit=True):
        r=T2Row(self._t2_rf,self._t2_row_change,data); self.t2_rows.append(r)
        if commit: self._disc_change("t2")

    def _t2_row_change(self,remove=None):
        if remove and remove in self.t2_rows: self.t2_rows.remove(remove); self._disc_change("t2"); return
        self._txt_change("t2")

    def _collect_t2(self):
        return {**self.cfgs["t2"],
                "canvas_size":self._t2_size.get(),
                "header_text":self._t2_header.get(),"divider_text":self._t2_divider.get(),
                **{k:v.get() for k,v in self._t2_nvars.items()},
                "rows":[r.get_data() for r in self.t2_rows],
                "show_playing_style":self._t2_show_style.get(),
                "tags_a":[self._t2_tag_vars["tags_a0"].get(),self._t2_tag_vars["tags_a1"].get()],
                "tags_b":[self._t2_tag_vars["tags_b0"].get(),self._t2_tag_vars["tags_b1"].get()]}

    # ── T3 controls ──────────────────────────────────────────────────────

    def _build_t3(self, p):
        pad={"padx":10,"pady":5}
        pb=ttk.LabelFrame(p,text="Photos"); pb.pack(fill="x",**pad)
        self._make_photo_row(pb,"t3","photo_a","_t3_img_a","Left player")
        self._make_photo_row(pb,"t3","photo_b","_t3_img_b","Right player")
        self._make_photo_row(pb,"t3","logo_path","_t3_logo","Center logo",framing=False)

        nb=ttk.LabelFrame(p,text="Players & Match Info"); nb.pack(fill="x",**pad)
        self._t3_vars={}
        fields=[("name_a_first","L First"),("name_a_last","L Last"),("team_a","L Team"),
                ("name_b_first","R First"),("name_b_last","R Last"),("team_b","R Team"),
                ("vs_text","VS text"),("score","Score line"),("sponsor_text","Sponsor text")]
        for key,lbl in fields:
            r=ttk.Frame(nb); r.pack(fill="x",pady=2)
            ttk.Label(r,text=lbl+":",width=12,anchor="w").pack(side="left")
            v=tk.StringVar(value=self.cfgs["t3"].get(key,""))
            ttk.Entry(r,textvariable=v).pack(side="left",fill="x",expand=True,padx=4)
            v.trace_add("write",lambda *a:self._txt_change("t3")); self._t3_vars[key]=v

        lb=ttk.LabelFrame(p,text="Appearance and size"); lb.pack(fill="x",**pad)
        self._t3_size=tk.StringVar(value=self.cfgs["t3"]["canvas_size"])
        ttk.Label(lb,text="Canvas:").grid(row=0,column=0,sticky="w",padx=6,pady=3)
        ttk.Combobox(lb,textvariable=self._t3_size,values=list(T3_SIZES.keys()),state="readonly",width=18).grid(row=0,column=1,padx=6)
        self._t3_size.trace_add("write",lambda *a:self._disc_change("t3"))
        ttk.Button(lb,text="Accent color…",command=lambda:self._pick_accent("t3")).grid(row=1,column=0,columnspan=2,sticky="w",padx=6,pady=5)

        sb=ttk.LabelFrame(p,text="Stat Rows  (left | stat | right | scale | unit)"); sb.pack(fill="x",**pad)
        self._t3_rf=ttk.Frame(sb); self._t3_rf.pack(fill="x",padx=4,pady=4)
        actions=ttk.Frame(sb); actions.pack(fill="x",padx=4,pady=4)
        ttk.Button(actions,text="Add stat",command=self._add_t3_row).pack(side="left")
        ttk.Button(actions,text="Paste from Excel",command=lambda:self._paste_rows("t3")).pack(side="left",padx=4)

    def _rebuild_t3_rows(self):
        for r in self.t3_rows: r.frame.destroy()
        self.t3_rows.clear()
        for d in self.cfgs["t3"].get("rows",[]): self._add_t3_row(d,commit=False)

    def _add_t3_row(self,data=None,commit=True):
        r=T3Row(self._t3_rf,self._t3_row_change,data); self.t3_rows.append(r)
        if commit: self._disc_change("t3")

    def _t3_row_change(self,remove=None):
        if remove and remove in self.t3_rows: self.t3_rows.remove(remove); self._disc_change("t3"); return
        self._txt_change("t3")

    def _collect_t3(self):
        return {**self.cfgs["t3"],"canvas_size":self._t3_size.get(),
                **{k:v.get() for k,v in self._t3_vars.items()},
                "rows":[r.get_data() for r in self.t3_rows]}

    # ── T4 controls ──────────────────────────────────────────────────────

    def _build_t4(self, p):
        pad={"padx":10,"pady":5}
        gb=ttk.LabelFrame(p,text="Global Settings"); gb.pack(fill="x",**pad)
        r0=ttk.Frame(gb); r0.pack(fill="x",pady=3)
        self._t4_banner=tk.StringVar(value=self.cfgs["t4"]["banner_text"])
        self._t4_sponsor=tk.StringVar(value=self.cfgs["t4"]["sponsor_text"])
        ttk.Label(r0,text="Banner:").pack(side="left")
        ttk.Entry(r0,textvariable=self._t4_banner).pack(side="left",fill="x",expand=True,padx=4)
        self._t4_banner.trace_add("write",lambda *a:self._txt_change("t4"))
        r1=ttk.Frame(gb); r1.pack(fill="x",pady=3)
        ttk.Label(r1,text="Sponsor:").pack(side="left")
        ttk.Entry(r1,textvariable=self._t4_sponsor).pack(side="left",fill="x",expand=True,padx=4)
        self._t4_sponsor.trace_add("write",lambda *a:self._txt_change("t4"))
        r2=ttk.Frame(gb); r2.pack(fill="x",pady=3)
        self._t4_size=tk.StringVar(value=self.cfgs["t4"]["canvas_size"])
        ttk.Label(r2,text="Canvas:").pack(side="left")
        ttk.Combobox(r2,textvariable=self._t4_size,values=list(T4_SIZES.keys()),state="readonly",width=18).pack(side="left",padx=6)
        self._t4_size.trace_add("write",lambda *a:self._disc_change("t4"))
        ttk.Button(r2,text="Accent…",command=lambda:self._pick_accent("t4")).pack(side="left",padx=6)

        # 3 player widgets
        self._t4_player_frame=ttk.Frame(p); self._t4_player_frame.pack(fill="x",**pad)

    def _rebuild_t4_players(self):
        for w in self.t4_players: w.frame.destroy()
        self.t4_players.clear()
        for i,d in enumerate(self.cfgs["t4"].get("players",DEF_T4["players"])[:3]):
            w=T4PlayerWidget(self._t4_player_frame,lambda:self._txt_change("t4"),d,i)
            self.t4_players.append(w)

    def _collect_t4(self):
        return {**self.cfgs["t4"],"canvas_size":self._t4_size.get(),
                "banner_text":self._t4_banner.get(),"sponsor_text":self._t4_sponsor.get(),
                "players":[w.get_data() for w in self.t4_players]}

    # ── Shared pickers ───────────────────────────────────────────────────

    def _make_photo_row(self,parent,tpl,key,label_attr,title,framing=True):
        row=ttk.Frame(parent); row.pack(fill="x",padx=6,pady=4)
        ttk.Label(row,text=title,width=14,anchor="w").pack(side="left")
        label=ttk.Label(row,width=26,foreground="#555",anchor="w")
        setattr(self,label_attr,label)
        ttk.Button(
            row,text="Choose",command=lambda:self._pick_photo(tpl,key,label),
        ).pack(side="left")
        if framing:
            ttk.Button(
                row,text="Adjust",command=lambda:self._adjust_photo(tpl,key),
            ).pack(side="left",padx=(4,0))
        ttk.Button(
            row,text="Remove",command=lambda:self._remove_photo(tpl,key,label),
        ).pack(side="left",padx=(4,0))
        label.pack(side="left",padx=8,fill="x",expand=True)
        self._set_photo_label(label,self.cfgs[tpl].get(key,""))

    @staticmethod
    def _set_photo_label(label,path):
        label.config(
            text=os.path.basename(path) if path else "No photo selected",
            foreground="#202830" if path else "#687681",
        )

    @staticmethod
    def _frame_keys(key):
        if key == "photo_path":
            return "photo_zoom","photo_focus_x","photo_focus_y"
        return f"{key}_zoom",f"{key}_focus_x",f"{key}_focus_y"

    def _photo_target_size(self,tpl):
        config=self.cfgs[tpl]
        if tpl == "t1":
            return T1_SIZES.get(config.get("canvas_size"),(16,9))
        if tpl == "t2":
            width,height=T2_SIZES.get(config.get("canvas_size"),(1152,640))
            return max(1,int(width*.20)),height
        width,height=T3_SIZES.get(config.get("canvas_size"),(1080,1080))
        return max(1,width//2),max(1,int(height*.52))

    def _pick_photo(self, tpl, key, lbl):
        p=filedialog.askopenfilename(filetypes=IMAGE_FILETYPES)
        if p:
            self.cfgs[tpl][key]=p
            if key != "logo_path":
                zoom_key,x_key,y_key=self._frame_keys(key)
                self.cfgs[tpl].update({zoom_key:100,x_key:50,y_key:50})
            self._set_photo_label(lbl,p)
            self._disc_change(tpl)

    def _adjust_photo(self,tpl,key):
        path=self.cfgs[tpl].get(key,"")
        if not path or load_photo(path) is None:
            messagebox.showinfo("Choose photo", "Choose a photo first.", parent=self.root)
            return
        zoom_key,x_key,y_key=self._frame_keys(key)
        def apply_frame(zoom,focus_x,focus_y):
            self.cfgs[tpl].update({zoom_key:zoom,x_key:focus_x,y_key:focus_y})
            self._disc_change(tpl)
        PhotoFramingDialog(
            self.root,path,self._photo_target_size(tpl),
            self.cfgs[tpl].get(zoom_key,100),self.cfgs[tpl].get(x_key,50),
            self.cfgs[tpl].get(y_key,50),apply_frame,
        )

    def _remove_photo(self,tpl,key,label):
        self.cfgs[tpl][key]=""
        if key != "logo_path":
            zoom_key,x_key,y_key=self._frame_keys(key)
            self.cfgs[tpl].update({zoom_key:100,x_key:50,y_key:50})
        self._set_photo_label(label,"")
        self._disc_change(tpl)

    def _paste_rows(self,tpl):
        try:
            text=self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo("Clipboard is empty", "Copy rows from Excel or Sheets first.", parent=self.root)
            return
        rows=parse_pasted_rows(text,tpl)
        if not rows:
            messagebox.showwarning("No stats found", "The copied table did not contain usable rows.", parent=self.root)
            return
        replace=messagebox.askyesnocancel(
            "Paste stats", "Replace existing stats?\n\nYes = replace   No = add below",
            parent=self.root,
        )
        if replace is None:
            return
        self.cfgs[tpl]["rows"]=rows if replace else self.cfgs[tpl].get("rows",[])+rows
        {"t1":self._rebuild_t1_rows,"t2":self._rebuild_t2_rows,"t3":self._rebuild_t3_rows}[tpl]()
        self._disc_change(tpl)

    def _pick_accent(self, tpl):
        cur=tuple(self.cfgs[tpl].get("accent_color",list(THEME["accent"])))
        c=colorchooser.askcolor(title="Accent color",initialcolor=cur)
        if c[0]:
            self.cfgs[tpl]["accent_color"]=list(int(x) for x in c[0])
            self._disc_change(tpl)

    # ── Change / undo flow ───────────────────────────────────────────────

    def _collect(self):
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        if not self._suspend:
            self.cfgs[self.tpl]=collectors[self.tpl]()
        return {k: copy.deepcopy(v) for k,v in self.cfgs.items()}

    def _disc_change(self, tpl):
        if self._suspend: return
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        self.cfgs[tpl]=collectors[tpl]()
        self._set_dirty(True)
        self._status("Updated")
        self._schedule_redraw()
        self._commit_undo()

    def _txt_change(self, tpl):
        if self._suspend: return
        collectors={"t1":self._collect_t1,"t2":self._collect_t2,
                    "t3":self._collect_t3,"t4":self._collect_t4}
        self.cfgs[tpl]=collectors[tpl]()
        self._set_dirty(True)
        self._status("Editing")
        self._schedule_redraw()
        if self._undo_id: self.root.after_cancel(self._undo_id)
        self._undo_id=self.root.after(600,self._commit_undo)

    def _commit_undo(self):
        self._undo_id=None
        self._undo.push({"tpl":self.tpl,"cfgs":self._collect()})

    def _apply_state(self, state):
        self._suspend=True
        try:
            self.cfgs=copy.deepcopy(state["cfgs"])
            # restore UI for each template
            t1=self.cfgs["t1"]
            self._t1_side.set(t1["panel_side"]); self._t1_size.set(t1["canvas_size"])
            self._t1_title.delete("1.0","end"); self._t1_title.insert("1.0",t1["title"])
            self._set_photo_label(self._t1_img_lbl,t1.get("photo_path",""))
            self._rebuild_t1_rows()

            t2=self.cfgs["t2"]
            self._t2_size.set(t2["canvas_size"]); self._t2_header.set(t2["header_text"])
            self._t2_divider.set(t2["divider_text"])
            for k,v in self._t2_nvars.items(): v.set(t2.get(k,""))
            self._t2_show_style.set(t2["show_playing_style"])
            for key in ["tags_a0","tags_a1","tags_b0","tags_b1"]:
                side="a" if "a" in key else "b"; idx=int(key[-1])
                self._t2_tag_vars[key].set(t2[f"tags_{side}"][idx])
            self._set_photo_label(self._t2_img_a,t2.get("photo_a",""))
            self._set_photo_label(self._t2_img_b,t2.get("photo_b",""))
            self._rebuild_t2_rows()

            t3=self.cfgs["t3"]
            self._t3_size.set(t3["canvas_size"])
            for k,v in self._t3_vars.items(): v.set(t3.get(k,""))
            self._set_photo_label(self._t3_img_a,t3.get("photo_a",""))
            self._set_photo_label(self._t3_img_b,t3.get("photo_b",""))
            self._set_photo_label(self._t3_logo,t3.get("logo_path",""))
            self._rebuild_t3_rows()

            t4=self.cfgs["t4"]
            self._t4_size.set(t4["canvas_size"])
            self._t4_banner.set(t4["banner_text"]); self._t4_sponsor.set(t4["sponsor_text"])
            self._rebuild_t4_players()

            # switch to correct template
            key=state["tpl"]; idx=TEMPLATE_KEYS.index(key)
            self.tpl_var.set(TEMPLATE_NAMES[idx])
            for p in self.panels.values(): p.pack_forget()
            self.panels[key].pack(fill="both",expand=True)
            self.tpl=key
        finally:
            self._suspend=False
        self.redraw()

    def undo(self):
        s=self._undo.undo()
        if s:
            self._apply_state(s)
            self._set_dirty(True)
            self._status("Undid last change")

    def redo(self):
        s=self._undo.redo()
        if s:
            self._apply_state(s)
            self._set_dirty(True)
            self._status("Redid change")

    # ── Projects and data safety ─────────────────────────────────────────

    def _status(self,text):
        if hasattr(self,"status_var"):
            self.status_var.set(text)

    def _set_dirty(self,value):
        self._dirty=bool(value)
        name=self.current_project_path.stem if self.current_project_path else "Untitled"
        marker=" *" if self._dirty else ""
        self.root.title(f"{name}{marker} - Scoreboard Maker")

    def _confirm_discard(self):
        if not self._dirty:
            return True
        answer=messagebox.askyesnocancel(
            "Unsaved changes", "Save your scoreboard project before continuing?",
            parent=self.root,
        )
        if answer is None:
            return False
        if answer:
            return self.save_project()
        return True

    def open_project(self):
        if not self._confirm_discard():
            return False
        path=filedialog.askopenfilename(filetypes=PROJECT_FILETYPES,parent=self.root)
        if not path:
            return False
        try:
            payload=json.loads(Path(path).read_text(encoding="utf-8"))
            raw_configs=payload.get("templates",payload) if isinstance(payload,dict) else {}
            configs=normalise_project_configs(raw_configs)
            active=payload.get("active_template","t1") if isinstance(payload,dict) else "t1"
            if active not in TEMPLATE_KEYS:
                active="t1"
            self._apply_state({"tpl":active,"cfgs":configs})
            self._undo=UndoStack(); self._commit_undo()
            self.current_project_path=Path(path)
            self._set_dirty(False)
            self._status(f"Opened {Path(path).name}")
            return True
        except (OSError,ValueError,TypeError,KeyError) as exc:
            messagebox.showerror("Open failed",str(exc),parent=self.root)
            self._status("Could not open project")
            return False

    def save_project(self,save_as=False):
        self._collect()
        path=self.current_project_path
        if save_as or path is None:
            selected=filedialog.asksaveasfilename(
                defaultextension=".scoreboard.json",filetypes=PROJECT_FILETYPES,
                initialfile="scoreboard_project.scoreboard.json",parent=self.root,
            )
            if not selected:
                return False
            path=Path(selected)
        payload={
            "version":1,
            "active_template":self.tpl,
            "templates":self.cfgs,
        }
        temporary=path.with_name(path.name+".tmp")
        try:
            temporary.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
            os.replace(temporary,path)
            self.current_project_path=path
            self._set_dirty(False)
            self._status(f"Saved {path.name}")
            return True
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Save failed",str(exc),parent=self.root)
            self._status("Could not save project")
            return False

    def reset_current_template(self):
        name=TEMPLATE_NAMES[TEMPLATE_KEYS.index(self.tpl)]
        if not messagebox.askyesno(
            "Reset layout",f"Reset {name} to its original content?",parent=self.root,
        ):
            return
        configs=self._collect()
        configs[self.tpl]=copy.deepcopy(DEFAULT_CONFIGS[self.tpl])
        self._apply_state({"tpl":self.tpl,"cfgs":configs})
        self._commit_undo()
        self._set_dirty(True)
        self._status(f"Reset {name}")

    def _on_close(self):
        if self._confirm_discard():
            self.root.destroy()

    # ── Render ───────────────────────────────────────────────────────────

    def _schedule_redraw(self):
        if self._redraw_id: self.root.after_cancel(self._redraw_id)
        self._redraw_id=self.root.after(130, self.redraw)

    def redraw(self):
        self._redraw_id=None
        try:
            img=RENDERERS[self.tpl](self.cfgs[self.tpl])
        except Exception as e:
            print(f"Render error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self._status(f"Preview error: {e}")
            return
        self._last_render=img
        self.preview_info_var.set(f"{img.width:,} x {img.height:,} px")
        self._paint_preview()

    def _paint_preview(self):
        self._preview_resize_id=None
        if self._last_render is None or not self.preview_canvas.winfo_exists():
            return
        canvas_w=max(320,self.preview_canvas.winfo_width())
        canvas_h=max(240,self.preview_canvas.winfo_height())
        image_w,image_h=self._last_render.size
        scale=min((canvas_w-48)/image_w,(canvas_h-48)/image_h,1.0)
        width=max(1,int(image_w*scale)); height=max(1,int(image_h*scale))
        preview=self._last_render.resize((width,height),Image.LANCZOS)
        self._tk_img=ImageTk.PhotoImage(preview)
        x=canvas_w//2; y=canvas_h//2
        self.preview_canvas.delete("all")
        self.preview_canvas.create_rectangle(
            x-width//2+7,y-height//2+8,x+width//2+7,y+height//2+8,
            fill="#10161b",outline="",
        )
        self.preview_canvas.create_image(x,y,image=self._tk_img)

    def export_png(self):
        config=copy.deepcopy(self.cfgs[self.tpl])
        scale=2 if self.export_scale_var.get().startswith("High") else 1
        config["_render_scale"]=scale
        base=self.current_project_path.stem.replace(".scoreboard","") if self.current_project_path else "scoreboard"
        p=filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG image","*.png")],initialfile=f"{base}_{self.tpl}.png",parent=self.root)
        if not p:
            return
        try:
            self._status("Exporting PNG")
            self.root.update_idletasks()
            img=RENDERERS[self.tpl](config)
            img.save(p,format="PNG")
            self._status(f"Exported {Path(p).name} ({img.width:,} x {img.height:,})")
            messagebox.showinfo("Export complete",f"Saved {Path(p).name}",parent=self.root)
        except (OSError,ValueError) as exc:
            self._status("Export failed")
            messagebox.showerror("Export failed",str(exc),parent=self.root)


def render_default(template: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = RENDERERS[template](copy.deepcopy(DEFAULT_CONFIGS[template]))
    image.save(output, format="PNG")
    print(f"Rendered {template}: {output} ({image.width}x{image.height})")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Four-template match stats card generator.")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--headless", type=Path, help="Render one default template to PNG.")
    output_group.add_argument("--render-all", type=Path, help="Render all default templates into a directory.")
    parser.add_argument("--template", choices=TEMPLATE_KEYS, default="t1")
    args = parser.parse_args(argv)

    if args.headless:
        render_default(args.template, args.headless)
        return
    if args.render_all:
        for key in TEMPLATE_KEYS:
            render_default(key, args.render_all / f"scoreboard_{key}.png")
        return

    root=tk.Tk(); App(root); root.mainloop()

if __name__=="__main__":
    main()
