"""
Batch Image Generator + Auto-Upscaler - Excel Prompts -> Final Images
------------------------------------------------------------------------
What this does, fully automatically, no manual steps between them:
  1. Reads a list of prompts from an Excel file (one prompt per row)
  2. Sends each prompt to Pollinations.ai's free image API (Flux model)
  3. Immediately upscales that image with Real-ESRGAN (same engine as
     your 8.py tool, just running headlessly - no window to click through)
  4. Saves the final upscaled image to its own output folder
  5. Logs any failures, skips work already done, so a re-run resumes

WHY POLLINATIONS: free, unlimited, no account/API key/billing needed.
WHY AUTO-UPSCALE: Flux output at free/fast settings can look a bit soft;
Real-ESRGAN sharpens and upscales it as a second automatic pass, so you
wake up to final-quality images, not raw ones you'd have to process
yourself.

SETUP (one-time):
  1. Install requirements:
         pip install requests openpyxl pandas
         pip install torch basicsr realesrgan opencv-python

     Note: torch/basicsr/realesrgan are the same packages your 8.py tool
     already needs - if that tool already works on your machine, you
     already have these installed and can skip this line.

  2. Make sure Prompts.xlsx is in the same folder as this script.

  3. Run it:
         python batch_image_generator_pollinations.py

  First run downloads a small (~65MB) upscaling model automatically -
  one time only, then it's cached in a "weights" folder and reused.

Your FINAL images land in "generated_images_upscaled". Raw pre-upscale
images are kept in "generated_images" too, in case you want to compare.
No API key, no .env file, no login needed anywhere in this script.
"""

import logging
import sys
import time
import urllib.parse
from pathlib import Path

import pandas as pd
import requests

# Import torch first, unconditionally, before anything else has a chance
# to import cv2/torchvision first. On Windows, if opencv-python's compiled
# DLLs load before torch finishes initializing, torch ends up "partially
# initialized" and later crashes with confusing errors like
# "module 'torch' has no attribute 'library'". Importing it here, once,
# up front, avoids that DLL race entirely - regardless of what order
# basicsr/realesrgan/cv2 get imported later inside the Upscaler class.
try:
    import torch  # noqa: F401
except ImportError:
    pass  # fine if AUTO_UPSCALE is off and torch was never installed

# ---------------------- CONFIG - edit these if needed ----------------------

EXCEL_FILE = "Prompts.xlsx"
PROMPT_COLUMN = "ChatGPT Image Prompt (Semi-Realistic + Negative Prompt)"
USE_COLUMN_INDEX = 0                 # fallback: column A, if header not found
FRAME_NO_COLUMN = "S.No."            # used in the saved filename
FRAME_TITLE_COLUMN = None            # not used in this file version

OUTPUT_FOLDER = "generated_images"
LOG_FILE = "generation_log.txt"

# Pollinations image settings
IMAGE_WIDTH = 1536
IMAGE_HEIGHT = 864                   # 16:9, bumped up for sharper native output
MODEL = "flux"                       # free, unlimited. Try "dirtberry" for higher realism (may use paid credits)
NO_LOGO = True                       # tries to skip Pollinations' watermark
ENHANCE = True                       # lets Pollinations' AI improve/expand your prompt before generating
SEED = None                          # set a number for reproducible results, or leave None

DELAY_BETWEEN_REQUESTS_SECONDS = 3   # be a good citizen on a shared free service
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 8            # doubles each retry
REQUEST_TIMEOUT_SECONDS = 180         # image generation can take a while under load
SKIP_EXISTING = True                 # resume-safe: won't regenerate files already on disk

# ---------------------- Auto-upscale settings (Real-ESRGAN) ----------------------
# OFF by default: this local pipeline (basicsr/realesrgan) has proven too
# fragile on this machine across many dependency-version conflicts. Since
# Pollinations now generates at higher native resolution directly (see
# IMAGE_WIDTH/HEIGHT above), that's a more reliable way to get sharper
# results without a local ML dependency chain that can break in new ways
# on any given Windows/Python setup. Flip back to True only if you want
# to experiment further with local upscaling.
AUTO_UPSCALE = False
UPSCALE_FOLDER = "generated_images_upscaled"
UPSCALE_MODEL_KEY = "fast"           # "fast" (2x, lightest on CPU) or "balanced" (4x, slower on CPU)
UPSCALE_TILE = 400                   # splits large images into tiles to limit RAM use on CPU; 0 = no tiling
MODEL_WEIGHTS_DIR = "weights"        # downloaded once, reused every run

UPSCALE_MODELS = {
    "fast": {
        "filename": "RealESRGAN_x2plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "scale": 2,
        "num_block": 23,
    },
    "balanced": {
        "filename": "RealESRGAN_x4plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "scale": 4,
        "num_block": 23,
    },
}

# -----------------------------------------------------------------------


def setup_logging(log_path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def slugify(text: str) -> str:
    keep = [c if c.isalnum() or c in (" ", "-", "_") else "" for c in str(text)]
    cleaned = "".join(keep).strip().replace(" ", "_")
    return cleaned[:40] if cleaned else "frame"


def load_prompts(excel_path: Path) -> list[dict]:
    if not excel_path.exists():
        logging.error("Could not find '%s'.", excel_path)
        sys.exit(1)

    df = pd.read_excel(excel_path)

    if PROMPT_COLUMN in df.columns:
        prompt_series = df[PROMPT_COLUMN]
    else:
        fallback_name = df.columns[USE_COLUMN_INDEX] if len(df.columns) > USE_COLUMN_INDEX else "?"
        logging.warning(
            "Prompt column '%s' not found - falling back to column '%s'. Double-check this is correct.",
            PROMPT_COLUMN, fallback_name,
        )
        prompt_series = df.iloc[:, USE_COLUMN_INDEX]

    has_frame_no = FRAME_NO_COLUMN in df.columns
    has_title = FRAME_TITLE_COLUMN in df.columns

    rows = []
    for idx, prompt in enumerate(prompt_series.tolist()):
        prompt_str = str(prompt).strip()
        if not prompt_str or prompt_str.lower() == "nan":
            continue

        raw_frame_no = df[FRAME_NO_COLUMN].iloc[idx] if has_frame_no else idx + 1
        try:
            frame_no = int(raw_frame_no)
        except (TypeError, ValueError):
            frame_no = idx + 1

        title = slugify(df[FRAME_TITLE_COLUMN].iloc[idx]) if has_title else ""
        label = f"frame{frame_no:03d}_{title}" if title else f"frame{frame_no:03d}"

        rows.append({"prompt": prompt_str, "label": label})

    if not rows:
        logging.error("No prompts found in the Excel file. Check the file and column.")
        sys.exit(1)

    return rows


class Upscaler:
    """
    Headless Real-ESRGAN upscaler - same engine as 8.py, with the tkinter
    GUI stripped out. Loads its model once (lazily, on first use) and
    reuses it for every image, so it doesn't reload per-frame.
    """

    def __init__(self, base_dir: Path):
        self._upsampler = None
        self._base_dir = base_dir

    def _load(self):
        if self._upsampler is not None:
            return self._upsampler

        # basicsr is a barely-maintained package whose __init__.py eagerly
        # imports ALL of its submodules (archs, data, losses, metrics,
        # models, ops, test, train, utils) - including training-pipeline
        # code that has drifted out of sync with itself across versions.
        # Simple image upscaling only ever needs basicsr.archs (RRDBNet)
        # and parts of basicsr.utils. Rather than patch each broken
        # training-only submodule one at a time as they surface, every
        # submodule we don't need is stubbed out in one place, up front.
        if "basicsr.data" not in sys.modules:
            import types as _types

            def _stub_fn(*_args, **_kwargs):
                raise NotImplementedError("stubbed basicsr internal - not used for simple image upscaling")

            for _name in ("data", "losses", "metrics", "models", "ops", "test", "train"):
                _mod = _types.ModuleType(f"basicsr.{_name}")
                _mod.__getattr__ = lambda _n, _f=_stub_fn: _f
                sys.modules[f"basicsr.{_name}"] = _mod

            # basicsr.utils itself IS needed (load_file_from_url etc.), but
            # one of its internal files (diffjpeg, a JPEG-degradation
            # simulator used only in training) can itself be broken/out of
            # sync - stub just that one file, letting the rest of
            # basicsr.utils import for real.
            _diffjpeg_stub = _types.ModuleType("basicsr.utils.diffjpeg")
            _diffjpeg_stub.__getattr__ = lambda _n: _stub_fn
            sys.modules["basicsr.utils.diffjpeg"] = _diffjpeg_stub

        # Compatibility patch for newer torchvision versions, which removed
        # torchvision.transforms.functional_tensor. Older basicsr code
        # still expects it to exist.
        try:
            import torchvision.transforms.functional as F
            import types as _types
            functional_tensor = _types.ModuleType("torchvision.transforms.functional_tensor")
            functional_tensor.rgb_to_grayscale = F.rgb_to_grayscale
            sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor
        except Exception:
            pass

        # Belt-and-suspenders: if load_file_from_url still ends up missing
        # for any other reason, define a working replacement rather than
        # depend on this specific basicsr version having it.
        try:
            import basicsr.utils.download_util as _dl_util
            if not hasattr(_dl_util, "load_file_from_url"):
                import os as _os
                from urllib.parse import urlparse as _urlparse
                from torch.hub import download_url_to_file as _download_url_to_file

                def _load_file_from_url(url, model_dir=None, progress=True, file_name=None):
                    _os.makedirs(model_dir, exist_ok=True)
                    if not file_name:
                        file_name = _os.path.basename(_urlparse(url).path)
                    cached_file = _os.path.abspath(_os.path.join(model_dir, file_name))
                    if not _os.path.exists(cached_file):
                        _download_url_to_file(url, cached_file, progress=progress)
                    return cached_file

                _dl_util.load_file_from_url = _load_file_from_url
        except Exception:
            pass

        # Imported lazily so the rest of the script still works even if
        # these heavier packages aren't installed and AUTO_UPSCALE is off.
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from basicsr.utils.download_util import load_file_from_url
        from realesrgan import RealESRGANer

        model_info = UPSCALE_MODELS[UPSCALE_MODEL_KEY]
        weights_dir = self._base_dir / MODEL_WEIGHTS_DIR
        weights_dir.mkdir(parents=True, exist_ok=True)
        model_path = weights_dir / model_info["filename"]

        if not model_path.exists():
            logging.info("Downloading upscale model %s (one-time, ~60-70MB)...", model_info["filename"])
            load_file_from_url(
                url=model_info["url"],
                model_dir=str(weights_dir),
                progress=True,
                file_name=model_info["filename"],
            )

        model = RRDBNet(
            num_in_ch=3, num_out_ch=3, num_feat=64,
            num_block=model_info["num_block"], num_grow_ch=32,
            scale=model_info["scale"],
        )

        self._upsampler = RealESRGANer(
            scale=model_info["scale"],
            model_path=str(model_path),
            model=model,
            tile=UPSCALE_TILE,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
            gpu_id=0 if torch.cuda.is_available() else None,
        )
        logging.info(
            "Upscale model ready (%s, %s)",
            model_info["filename"], "GPU" if torch.cuda.is_available() else "CPU - this is the slow part",
        )
        return self._upsampler

    def upscale_file(self, input_path: Path, output_path: Path) -> None:
        import cv2

        upsampler = self._load()
        img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise RuntimeError("could not read generated image for upscaling")

        model_info = UPSCALE_MODELS[UPSCALE_MODEL_KEY]
        output, _ = upsampler.enhance(img, outscale=model_info["scale"])

        success = cv2.imwrite(str(output_path), output)
        if not success:
            raise RuntimeError("could not save upscaled image")


def build_url(prompt: str) -> str:
    encoded_prompt = urllib.parse.quote(prompt)
    params = {
        "width": IMAGE_WIDTH,
        "height": IMAGE_HEIGHT,
        "model": MODEL,
    }
    if NO_LOGO:
        params["nologo"] = "true"
    if ENHANCE:
        params["enhance"] = "true"
    if SEED is not None:
        params["seed"] = SEED

    query = urllib.parse.urlencode(params)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query}"


def generate_image(session: requests.Session, prompt: str) -> bytes:
    url = build_url(prompt)
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "image" not in content_type:
        raise RuntimeError(f"unexpected response (not an image): {content_type} - {response.text[:200]}")

    return response.content


def generate_with_retry(session: requests.Session, prompt: str) -> bytes:
    delay = RETRY_BACKOFF_SECONDS
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return generate_image(session, prompt)
        except (requests.RequestException, RuntimeError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logging.warning("  Attempt %d/%d failed (%s) - retrying in %ds", attempt, MAX_RETRIES, e, delay)
                time.sleep(delay)
                delay *= 2

    raise RuntimeError(f"failed after {MAX_RETRIES} attempts: {last_error}")


def make_session() -> requests.Session:
    """
    A plain requests.get() with default headers gets flagged/dropped by
    some servers as bot traffic. A browser-like User-Agent plus a reused
    session (instead of a fresh connection per request) fixes most
    'connection forcibly closed' errors against Pollinations.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    return session


def main():
    base_dir = Path(__file__).parent
    excel_path = base_dir / EXCEL_FILE
    output_dir = base_dir / OUTPUT_FOLDER
    upscale_dir = base_dir / UPSCALE_FOLDER
    log_path = base_dir / LOG_FILE
    output_dir.mkdir(exist_ok=True)
    if AUTO_UPSCALE:
        upscale_dir.mkdir(exist_ok=True)

    setup_logging(log_path)

    rows = load_prompts(excel_path)
    logging.info("Loaded %d prompts from %s", len(rows), EXCEL_FILE)
    logging.info("Using Pollinations.ai (free, no API key) - model: %s", MODEL)

    session = make_session()
    upscaler = Upscaler(base_dir) if AUTO_UPSCALE else None
    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, row in enumerate(rows, start=1):
        prompt = row["prompt"]
        label = row["label"]
        filepath = output_dir / f"{label}.png"
        upscaled_path = upscale_dir / f"{label}.png"
        final_path = upscaled_path if AUTO_UPSCALE else filepath

        if SKIP_EXISTING and final_path.exists():
            logging.info("[%d/%d] Skipping (%s): already generated", i, len(rows), label)
            skip_count += 1
            continue

        short_prompt = (prompt[:60] + "...") if len(prompt) > 60 else prompt
        logging.info("[%d/%d] Generating (%s): %s", i, len(rows), label, short_prompt)

        try:
            image_bytes = generate_with_retry(session, prompt)
            filepath.write_bytes(image_bytes)
            logging.info("  -> Saved %s (%d KB)", filepath.name, len(image_bytes) // 1024)

            if AUTO_UPSCALE:
                logging.info("  -> Upscaling (this is the slow step on CPU)...")
                upscaler.upscale_file(filepath, upscaled_path)
                logging.info("  -> Upscaled -> %s (%d KB)", upscaled_path.name, upscaled_path.stat().st_size // 1024)

            success_count += 1
        except Exception as e:
            logging.error("  -> FAILED for prompt #%d: %s", i, e)
            fail_count += 1

        if i < len(rows):
            time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    logging.info(
        "DONE. Success: %d, Failed: %d, Skipped (already existed): %d",
        success_count, fail_count, skip_count,
    )
    print(f"\nRaw generated images: {output_dir}")
    if AUTO_UPSCALE:
        print(f"Final upscaled images (use these): {upscale_dir}")
    print(f"Full log saved in: {log_path}")


if __name__ == "__main__":
    main()