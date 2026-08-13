import json
import logging
import os
import time
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
ACCOUNTS_TO_TRACK = ["BBCBreaking", "reuters"]  # X handles without '@'
CHECK_INTERVAL_SECONDS = 300  # 5 minutes (avoid checking too fast to prevent IP flags)
STATE_FILE = "seen_posts.json"

# Optional: Set a Webhook URL (Discord / Slack / Telegram) to receive alerts
WEBHOOK_URL = ""  # e.g., "https://discord.com/api/webhooks/..."


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def load_seen_posts() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Could not load state file: {e}")
    return {}


def save_seen_posts(seen_data: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_data, f, indent=2)


def send_alert(username: str, post_url: str, text: str, timestamp: str) -> None:
    message = (
        f"🚨 **NEW POST FROM @{username}**\n"
        f"**Time:** {timestamp}\n"
        f"**URL:** {post_url}\n"
        f"**Content:**\n{text}\n"
    )
    logging.info(f"NEW POST DETECTED: {post_url}")
    print("\n" + "=" * 50 + f"\n{message}" + "=" * 50 + "\n")

    if WEBHOOK_URL:
        try:
            requests.post(WEBHOOK_URL, json={"content": message}, timeout=10)
        except Exception as e:
            logging.error(f"Failed to send webhook notification: {e}")


def check_account(page, username: str, seen_posts: dict) -> None:
    url = f"https://x.com/{username}"
    logging.info(f"Checking @{username}...")

    try:
        # Navigate to the profile
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        
        # Wait for tweet elements to render in DOM
        page.wait_for_selector('article[data-testid="tweet"]', timeout=12000)
        
        # Select all visible tweets on profile top
        tweets = page.query_selector_all('article[data-testid="tweet"]')
        
        if username not in seen_posts:
            seen_posts[username] = []

        for tweet in tweets:
            # Locate post URL and ID
            link_elem = tweet.query_selector('a[href*="/status/"]')
            if not link_elem:
                continue

            href = link_elem.get_attribute("href")
            if not href or "/status/" not in href:
                continue

            # Extract clean Tweet ID and full URL
            post_id = href.split("/status/")[1].split("?")[0]
            post_url = f"https://x.com/{username}/status/{post_id}"

            if post_id in seen_posts[username]:
                continue  # Post already processed

            # Extract tweet text content
            text_elem = tweet.query_selector('div[data-testid="tweetText"]')
            post_text = text_elem.inner_text().strip() if text_elem else "[Media/No text]"

            # Extract timestamp
            time_elem = tweet.query_selector("time")
            timestamp = time_elem.get_attribute("datetime") if time_elem else "Unknown"

            # Alert and log state
            send_alert(username, post_url, post_text, timestamp)
            seen_posts[username].append(post_id)

    except Exception as e:
        logging.warning(f"Could not load posts for @{username} (Profile locked or rate limited): {e}")


def run_tracker():
    seen_posts = load_seen_posts()

    with sync_playwright() as p:
        # Launch Chromium with anti-detection configurations
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        for username in ACCOUNTS_TO_TRACK:
            check_account(page, username, seen_posts)
            save_seen_posts(seen_posts)
            time.sleep(4)  # Small pause between profiles to avoid sudden traffic spikes

        browser.close()


if __name__ == "__main__":
    logging.info("Starting X Post Monitor...")
    while True:
        run_tracker()
        logging.info(f"Cycle complete. Waiting {CHECK_INTERVAL_SECONDS} seconds...")
        time.sleep(CHECK_INTERVAL_SECONDS)