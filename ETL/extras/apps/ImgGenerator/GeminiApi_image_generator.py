"""
Batch Image Generator - Excel Prompts -> Gemini Images
--------------------------------------------------------
What this does:
  1. Reads a list of prompts from an Excel file (one prompt per row)
  2. Sends each prompt to Google's Gemini image model
  3. Saves every generated image to an output folder, auto-numbered
  4. Logs any failures to a text file so nothing silently vanishes
  5. Squeezes the most images out of the free tier: it waits exactly as
     long as Google's API says to (not a guess), tells the difference
     between "wait a few seconds" and "you're out of free requests for
     today", skips images it already made, and can optionally sleep
     overnight and keep going the moment your daily quota resets.

ABOUT FREE-TIER LIMITS: Google no longer publishes a fixed RPM/RPD number
per model on its docs site - it now says limits vary by project, tier,
and time, and points developers to their own live dashboard instead:
https://aistudio.google.com/rate-limit
Check that page for your actual numbers. Because of that, this script
doesn't hardcode a "safe" delay and hope for the best - it reacts to the
real, current limit the API reports back on every call.

NOTE ON MULTI-IMAGE REQUESTS: it might look like you can get more than
one image per API call (Google's Vertex AI page lists "up to 10 images
per prompt", and there's a candidate_count option in the SDK). In
practice, multiple developers have reported this throwing
INVALID_ARGUMENT errors or behaving unpredictably on gemini-2.5-flash-
image, so this script sticks to the one-request-one-image path that's
known to work, rather than something you'd have to babysit.

CHANGES FROM THE PREVIOUS (batch_image_generator_improved.py) VERSION:
  - 429 errors are now parsed for Google's own retry-after time and quota
    type instead of guessing a backoff. A "per-minute" 429 waits exactly
    as long as told, then retries. A "per-day" 429 (you're out of free
    quota until it resets) stops the run cleanly instead of retrying
    pointlessly.
  - Optional WAIT_FOR_DAILY_RESET: if you'd rather the script sleep until
    midnight Pacific and keep going than stop and wait for you to re-run
    it tomorrow, flip this to True.
  - Slightly shorter fixed delay between requests, since the real ceiling
    is now enforced reactively instead of guessed conservatively.

SETUP (one-time):
  1. Get a free API key: https://aistudio.google.com  -> "Get API key"
  2. Set it as an environment variable (do NOT paste it into this file):

     Windows (Command Prompt):
         setx GEMINI_API_KEY "your-key-here"
         (then close and reopen the terminal)

     Windows (PowerShell):
         $env:GEMINI_API_KEY="your-key-here"

     Mac/Linux:
         export GEMINI_API_KEY="your-key-here"

  3. Install requirements:
         pip install google-genai openpyxl pandas

  4. Make an Excel file called Prompts.xlsx in the same folder as this
     script, with your prompts in column A, one per row, no header
     needed (or a header matching PROMPT_COLUMN below).

  5. Run it:
         python batch_image_generator_optimized.py

Your images will appear in the "generated_images" folder, and a
generation_log.txt file will record exactly what succeeded/failed.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from google import genai
from google.genai import types, errors

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads a ".env" file in the same folder, if present
except ImportError:
    pass  # dotenv is optional - falls back to system environment variables

# ---------------------- CONFIG - edit these if needed ----------------------

EXCEL_FILE = "Prompts.xlsx"          # your Excel file with prompts
PROMPT_COLUMN = "ChatGPT Image Prompt (Semi-Realistic + Negative Prompt)"  # column name
USE_COLUMN_INDEX = 0                 # fallback: 0 = column A, if no header match
FRAME_TITLE_COLUMN = None            # not used in this file version
FRAME_NO_COLUMN = "S.No."            # used in the saved filename
OUTPUT_FOLDER = "generated_images"
LOG_FILE = "generation_log.txt"

# Google has gemini-2.5-flash-image scheduled for shutdown Oct 2, 2026.
# Current recommended GA replacement: "gemini-3.1-flash-image".
# Check https://aistudio.google.com/rate-limit to compare free-tier
# limits across models for your account before switching - it varies.
MODEL_NAME = "gemini-2.5-flash-image"   # free-tier eligible image model
DELAY_BETWEEN_REQUESTS_SECONDS = 2      # floor only - real throttling is reactive, see below
IMAGE_SIZE = "1K"                       # ignored by gemini-2.5-flash-image; applies to 3.x models
MAX_RETRIES = 4                         # per-row retries for rate-limit / transient server errors
RETRY_BACKOFF_SECONDS = 8               # fallback wait if the API doesn't specify one, doubles each retry
SKIP_EXISTING = True                    # resume-safe: won't regenerate files already on disk
WAIT_FOR_DAILY_RESET = False             # True = sleep until midnight Pacific and keep going;
                                         # False = stop cleanly and let you re-run tomorrow
                                         # (SKIP_EXISTING means a re-run picks up exactly where
                                         # you left off, so False is the friendlier unattended default)

# -----------------------------------------------------------------------


class DailyQuotaExhausted(Exception):
    """Raised when the free tier's per-day quota is used up - retrying now won't help."""


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


def seconds_until_pacific_midnight() -> float:
    """Gemini API free-tier daily quotas reset at midnight Pacific time."""
    pacific_now = datetime.now(ZoneInfo("America/Los_Angeles"))
    next_midnight = (pacific_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_midnight - pacific_now).total_seconds()


def slugify(text: str) -> str:
    """Turn a frame title into a safe filename chunk."""
    keep = [c if c.isalnum() or c in (" ", "-", "_") else "" for c in str(text)]
    cleaned = "".join(keep).strip().replace(" ", "_")
    return cleaned[:40] if cleaned else "frame"


def load_prompts(excel_path: Path) -> list[dict]:
    """Returns a list of dicts: {'prompt': ..., 'label': ...}"""
    if not excel_path.exists():
        logging.error("Could not find '%s'.", excel_path)
        logging.error("Create an Excel file with your prompts (one per row) and try again.")
        sys.exit(1)

    df = pd.read_excel(excel_path)

    if PROMPT_COLUMN in df.columns:
        prompt_series = df[PROMPT_COLUMN]
    else:
        fallback_name = df.columns[USE_COLUMN_INDEX] if len(df.columns) > USE_COLUMN_INDEX else "?"
        logging.warning(
            "Prompt column '%s' not found - falling back to column index %d ('%s'). "
            "Double-check that's really where your prompts are before this burns API calls.",
            PROMPT_COLUMN, USE_COLUMN_INDEX, fallback_name,
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
            logging.warning(
                "Row %d has a missing/invalid '%s' value - using %d for the filename instead.",
                idx, FRAME_NO_COLUMN, frame_no,
            )

        title = slugify(df[FRAME_TITLE_COLUMN].iloc[idx]) if has_title else ""
        label = f"frame{frame_no:03d}_{title}" if title else f"frame{frame_no:03d}"

        rows.append({"prompt": prompt_str, "label": label})

    if not rows:
        logging.error("No prompts found in the Excel file. Check the file and column.")
        sys.exit(1)

    return rows


def generate_image(client: "genai.Client", prompt: str) -> bytes:
    """
    Calls Gemini and returns raw image bytes.
    Raises RuntimeError with a specific reason if no image comes back
    (safety block, recitation, max tokens, etc.) instead of a bare
    AttributeError on a None candidate/content.
    """
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size=IMAGE_SIZE),
        ),
    )

    # The whole prompt can be blocked before any candidates are generated.
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = getattr(feedback, "block_reason", None) if feedback else None
    if block_reason:
        raise RuntimeError(f"prompt blocked before generation (reason: {block_reason})")

    candidates = response.candidates or []
    for candidate in candidates:
        content = candidate.content
        if content is None:
            continue
        for part in (content.parts or []):
            if part.inline_data is not None and part.inline_data.data is not None:
                return part.inline_data.data  # already raw bytes in this SDK

    reasons = [str(getattr(c, "finish_reason", "UNKNOWN")) for c in candidates]
    raise RuntimeError(f"no image in response (finish_reason: {reasons or 'no candidates returned'})")


def _parse_retry_info(e: "errors.APIError"):
    """
    Best-effort parse of the structured retry/quota info Google's API attaches
    to 429 responses (google.rpc.RetryInfo / google.rpc.QuotaFailure). Returns
    (retry_seconds_or_None, is_daily_quota_bool). Falls back to (None, False)
    if the shape isn't what's expected rather than raising - a missed parse
    just means the caller falls back to its own backoff instead of the
    server's exact number.
    """
    try:
        details = e.details or {}
        if isinstance(details, dict) and "error" in details:
            details = details["error"]
        detail_list = details.get("details", []) if isinstance(details, dict) else []

        retry_seconds = None
        is_daily = False
        for item in detail_list:
            type_name = str(item.get("@type", ""))
            if type_name.endswith("RetryInfo"):
                delay = str(item.get("retryDelay", ""))
                if delay.endswith("s"):
                    retry_seconds = float(delay[:-1])
            elif type_name.endswith("QuotaFailure"):
                for violation in item.get("violations", []):
                    if "perday" in str(violation.get("quotaId", "")).lower():
                        is_daily = True
        return retry_seconds, is_daily
    except Exception:
        return None, False


def call_with_retry(client: "genai.Client", prompt: str) -> bytes:
    """
    Wraps generate_image with retries for rate limits / transient server
    errors. Auth errors stop the whole run immediately (retrying a bad key
    just repeats the same failure on every row). A per-day quota 429 raises
    DailyQuotaExhausted instead of retrying, since no amount of waiting a
    few seconds fixes that.
    """
    delay = RETRY_BACKOFF_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return generate_image(client, prompt)
        except errors.ClientError as e:
            if e.code in (401, 403):
                raise SystemExit(
                    f"Auth error ({e.code}) calling the Gemini API - check GEMINI_API_KEY. "
                    "Stopping now instead of repeating this for every remaining row."
                ) from e
            if e.code == 429:
                retry_seconds, is_daily = _parse_retry_info(e)
                if is_daily:
                    raise DailyQuotaExhausted(str(e)) from e
                if attempt < MAX_RETRIES:
                    wait = retry_seconds + 1 if retry_seconds is not None else delay
                    source = "server-specified" if retry_seconds is not None else "fallback"
                    logging.warning(
                        "Rate limited (429) - waiting %.0fs [%s] (attempt %d/%d)",
                        wait, source, attempt, MAX_RETRIES,
                    )
                    time.sleep(wait)
                    delay *= 2
                    continue
            raise
        except errors.ServerError:
            if attempt < MAX_RETRIES:
                logging.warning("Server error - retrying in %ds (attempt %d/%d)", delay, attempt, MAX_RETRIES)
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("retry loop exited unexpectedly")  # should never hit this


def process_row(client: "genai.Client", prompt: str, filepath: Path) -> None:
    """
    Generates one image and writes it to filepath. If the free daily quota
    is hit and WAIT_FOR_DAILY_RESET is on, sleeps until reset and tries once
    more; otherwise lets DailyQuotaExhausted propagate up to main().
    """
    try:
        image_bytes = call_with_retry(client, prompt)
    except DailyQuotaExhausted:
        if not WAIT_FOR_DAILY_RESET:
            raise
        wait_s = seconds_until_pacific_midnight() + 30  # small buffer past midnight
        logging.info(
            "Free daily quota reached - sleeping %.0f min until reset at midnight Pacific...",
            wait_s / 60,
        )
        time.sleep(wait_s)
        image_bytes = call_with_retry(client, prompt)  # one retry now that quota should be back

    filepath.write_bytes(image_bytes)


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.")
        print("See the setup instructions at the top of this script.")
        sys.exit(1)

    base_dir = Path(__file__).parent
    excel_path = base_dir / EXCEL_FILE
    output_dir = base_dir / OUTPUT_FOLDER
    log_path = base_dir / LOG_FILE
    output_dir.mkdir(exist_ok=True)

    setup_logging(log_path)

    client = genai.Client(api_key=api_key)

    rows = load_prompts(excel_path)
    logging.info("Loaded %d prompts from %s", len(rows), EXCEL_FILE)

    success_count = 0
    fail_count = 0
    skip_count = 0
    stopped_early = False

    for i, row in enumerate(rows, start=1):
        prompt = row["prompt"]
        label = row["label"]
        filepath = output_dir / f"{label}.png"

        if SKIP_EXISTING and filepath.exists():
            logging.info("[%d/%d] Skipping (%s): already generated", i, len(rows), label)
            skip_count += 1
            continue

        short_prompt = (prompt[:60] + "...") if len(prompt) > 60 else prompt
        logging.info("[%d/%d] Generating (%s): %s", i, len(rows), label, short_prompt)

        try:
            process_row(client, prompt, filepath)
            logging.info("  -> Saved %s", filepath.name)
            success_count += 1
        except SystemExit:
            raise
        except DailyQuotaExhausted as e:
            logging.error("Free daily quota reached: %s", e)
            logging.info(
                "Stopping for today. Re-run this script after midnight Pacific - "
                "already-generated images are skipped automatically, so it'll pick up "
                "exactly where it left off."
            )
            stopped_early = True
            break
        except Exception as e:
            logging.error("  -> FAILED for prompt #%d: %s", i, e)
            fail_count += 1

        if i < len(rows):
            time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    remaining = len(rows) - (success_count + fail_count + skip_count)
    logging.info(
        "DONE. Success: %d, Failed: %d, Skipped (already existed): %d, Remaining: %d%s",
        success_count, fail_count, skip_count, remaining,
        " (stopped early - daily quota reached)" if stopped_early else "",
    )
    print(f"\nAll images saved in: {output_dir}")
    print(f"Full log saved in: {log_path}")


if __name__ == "__main__":
    main()