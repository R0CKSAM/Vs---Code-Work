#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chatgpt_batch.py
----------------
Drives ChatGPT's web UI through prompts.csv: type prompt -> Enter -> wait for
the image -> save it -> next prompt. Resumable, human-paced.

Put this file and prompts.csv in the SAME folder, then:  python chatgpt_batch.py

Creates: output/  .progress.txt  .chrome-profile/
Delete .progress.txt to restart from the top.
"""

import csv
import random
import socket
import subprocess
import sys
import time
from pathlib import Path

# ======================================================================
# CONFIG  -- everything you may want to change lives here
# ======================================================================
CSV_FILE   = "prompts.csv"
PROMPT_COL = "prompt"

BROWSER = "chrome"          # "chrome" | "msedge" | "chromium"

# False = script opens its own browser window (simplest, recommended)
# True  = attach to a Chrome YOU started with --remote-debugging-port=9222
ATTACH_MODE = False
CDP_URL     = "http://127.0.0.1:9222"     # NOTE: 127.0.0.1, not localhost

# WHICH TAB it works on: script finds a tab whose URL contains this text.
# Use a unique fragment to target one exact chat. Leave as "chatgpt.com" for any ChatGPT tab.
TAB_URL_CONTAINS   = "c/6ad07978-47fc-83ec-a024-f78d162e3829"
NEW_TAB_IF_MISSING = True

START_URL     = "https://chatgpt.com/c/6ad07978-47fc-83ec-a024-f78d162e3829"
NEW_CHAT_EACH = False
DELAY_RANGE   = (4, 9)
GEN_TIMEOUT   = 900
MAX_PROMPTS   = None        # set to 2 for a fast test
KEEP_OPEN     = True
# ======================================================================

HERE        = Path(__file__).resolve().parent
OUT_DIR     = HERE / "output"
STATE_FILE  = HERE / ".progress.txt"
PROFILE_DIR = HERE / ".chrome-profile"
MOD         = "Meta" if sys.platform == "darwin" else "Control"

DEMO_CSV = """id,prompt
1,a red fox sitting in a field of tall grass at golden hour, cinematic photo
2,the same fox asleep on a mossy rock, soft morning light
3,a tiny red fox wearing a knitted scarf, studio portrait, plain background
4,a red fox running through falling snow, motion blur, winter light
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]


# ------------------------------- bootstrap ---------------------------
def bootstrap():
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    print("playwright missing in THIS interpreter -> installing...")
    for extra in ([], ["--no-cache-dir"], ["--user", "--no-cache-dir"]):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *extra, "playwright"])
            break
        except subprocess.CalledProcessError:
            print(f"  retrying with {' '.join(extra) or 'default flags'}...")
    try:
        import playwright  # noqa: F401
    except ImportError:
        sys.exit("Still no playwright. Run:  python -m pip install playwright")


bootstrap()
from playwright.sync_api import sync_playwright  # noqa: E402


# ------------------------------- helpers -----------------------------
def port_open(host="127.0.0.1", port=9222, timeout=1.0):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def load_prompts():
    if not (HERE / CSV_FILE).exists():
        (HERE / CSV_FILE).write_text(DEMO_CSV, encoding="utf-8")
        print(f"'{CSV_FILE}' was missing -> created a demo one for you.")
    with open(HERE / CSV_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        col = PROMPT_COL if PROMPT_COL in fields else (fields[-1] if fields else None)
        if not col:
            sys.exit("CSV has no usable column.")
        return [r[col].strip() for r in reader if r.get(col, "").strip()]


def composer(page):
    return page.locator('#prompt-textarea, div[contenteditable="true"]').last


def is_busy(page):
    return page.locator('button[data-testid="stop-button"]').count() > 0


def msg_count(page):
    return page.locator('div[data-message-author-role="assistant"]').count()


def last_reply_text(page):
    msgs = page.locator('div[data-message-author-role="assistant"]')
    if msgs.count() == 0:
        return ""
    try:
        return msgs.nth(msgs.count() - 1).inner_text().lower()
    except Exception:
        return ""


def assistant_images(page):
    msgs = page.locator('div[data-message-author-role="assistant"]')
    if msgs.count() == 0:
        return []
    imgs = msgs.nth(msgs.count() - 1).locator("img")
    good = []
    for i in range(imgs.count()):
        el = imgs.nth(i)
        try:
            b = el.bounding_box()
        except Exception:
            continue
        if b and b["width"] >= 120 and b["height"] >= 120:
            good.append(el)
    return good


def download(el, path):
    try:
        data = el.evaluate(
            """async el => {
                const r = await fetch(el.currentSrc || el.src);
                return Array.from(new Uint8Array(await r.arrayBuffer()));
            }"""
        )
        path.write_bytes(bytes(data))
        return True
    except Exception:
        try:
            el.screenshot(path=str(path))
            return True
        except Exception:
            return False


def wait_for_result(page, before, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if not is_busy(page) and msg_count(page) > before:
            time.sleep(2.5)
            return True
        time.sleep(1)
    return False


def wait_for_images(page, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if assistant_images(page):
            return True
        time.sleep(1)
    return False


def pick_tab(ctx):
    """Choose which tab to drive."""
    pages = [pg for pg in ctx.pages if pg.url and pg.url.startswith("http")]
    for pg in pages:
        if TAB_URL_CONTAINS.lower() in pg.url.lower():
            print(f"Using tab: {pg.url[:90]}")
            return pg
    print(f"! no tab matching '{TAB_URL_CONTAINS}'. Open tabs are:")
    for pg in pages:
        print(f"    - {pg.url[:90]}")
    if pages and not NEW_TAB_IF_MISSING:
        return pages[0]
    pg = ctx.new_page()
    pg.goto(START_URL)
    return pg


def ensure_ready(page):
    if "chatgpt.com" not in page.url:
        page.goto(START_URL)
    try:
        composer(page).wait_for(state="visible", timeout=15000)
    except Exception:
        input(">>> Log into ChatGPT in the open window, then press Enter here...")
        composer(page).wait_for(state="visible", timeout=60000)


def open_session(p):
    """Attach to an existing debug Chrome if possible, otherwise launch our own."""
    if ATTACH_MODE:
        if port_open():
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                print(f"Attached to your Chrome on {CDP_URL}.")
                return browser, ctx, pick_tab(ctx)
            except Exception as e:
                print(f"! attach failed ({e})")
        else:
            print(f"! nothing listening on {CDP_URL}")
            print("  Start Chrome with start_chrome_debug.bat first, or set ATTACH_MODE = False.")
        print("  -> launching my own browser instead.\n")

    common = dict(headless=False, viewport={"width": 1400, "height": 950}, args=LAUNCH_ARGS)
    if BROWSER != "chromium":
        try:
            ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), channel=BROWSER, **common)
        except Exception as e:
            print(f"! couldn't launch '{BROWSER}' ({e}) -> using bundled Chromium.")
            ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), **common)
    else:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), **common)
    return None, ctx, pick_tab(ctx)


# -------------------------------- main -------------------------------
def main():
    prompts = load_prompts()
    if MAX_PROMPTS:
        prompts = prompts[:MAX_PROMPTS]
    OUT_DIR.mkdir(exist_ok=True)

    start = 0
    if STATE_FILE.exists():
        try:
            start = int(STATE_FILE.read_text().strip())
        except ValueError:
            start = 0
    start = min(start, len(prompts))
    print(f"{len(prompts)} prompt(s) loaded. Starting at #{start + 1}.")

    with sync_playwright() as p:
        browser, ctx, page = open_session(p)
        page.bring_to_front()
        ensure_ready(page)
        print("Ready. Don't touch the mouse/keyboard in that window.")

        try:
            for i in range(start, len(prompts)):
                prompt = prompts[i]
                print(f"[{i + 1}/{len(prompts)}] {prompt[:70]}")

                if NEW_CHAT_EACH and i > 0:
                    page.goto(START_URL)
                    page.wait_for_timeout(1500)

                box = composer(page)
                box.wait_for(state="visible", timeout=60000)
                box.click()
                page.keyboard.press(f"{MOD}+A")
                page.keyboard.press("Backspace")

                before = msg_count(page)
                page.keyboard.type(prompt, delay=6)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")

                if wait_for_result(page, before, GEN_TIMEOUT) and wait_for_images(page):
                    imgs = assistant_images(page)
                    for n, el in enumerate(imgs, 1):
                        name = f"{i + 1:03d}.png" if len(imgs) == 1 else f"{i + 1:03d}_{n}.png"
                        download(el, OUT_DIR / name)
                    print(f"   saved {len(imgs)} image(s) -> output/")
                else:
                    reply = last_reply_text(page)
                    reason = "rate limit / needs attention" if "limit" in reply else "no image found"
                    print(f"   ! {reason} (logged to output/errors.log)")
                    with open(OUT_DIR / "errors.log", "a", encoding="utf-8") as f:
                        f.write(f"{i + 1}\t{prompt}\n")
                    if "limit" in reply:
                        print("   waiting 60s...")
                        time.sleep(60)

                STATE_FILE.write_text(str(i + 1))
                time.sleep(random.uniform(*DELAY_RANGE))

        except KeyboardInterrupt:
            print("\nInterrupted. Progress saved - re-run to continue where you left off.")

        print("Finished. Images are in:", OUT_DIR)
        if KEEP_OPEN:
            if ATTACH_MODE:
                input("Press Enter to detach...")
            else:
                input("Press Enter to close the browser...")
                ctx.close()


if __name__ == "__main__":
    main()