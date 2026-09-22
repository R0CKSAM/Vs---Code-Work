"""
Davis Cup Player Data Scraper (v2 - URL-based navigation)
------------------------------------------------------------
Automates the exact workflow you described:
  1. https://www.daviscup.com/en/teams           -> list of countries
                                                      (links to /en/teams/<uuid>)
  2. https://www.daviscup.com/en/teams/<uuid>     -> that country's roster page
                                                      (links to /en/players/<uuid>)
  3. https://www.daviscup.com/en/players/<uuid>   -> that player's profile page
                                                      (Nominations, Singles W/L, Total W/L, Ties Played, First Year Played, Favourite Hand, Last Nation Represented)

For each requested country, the script:
  1. Opens /en/teams and finds the link whose visible text matches the country name.
  2. Opens that team's roster page and collects every player profile link on it.
  3. Opens each player's profile page and extracts Name / Nominations / Singles W/L / Total W/L / Ties Played / First Year Played /
     Favourite Hand / Last Nation Represented using LABEL-BASED text matching -- it looks for the visible label
     text (e.g. "Nominations") and reads whatever value sits next to it, rather than relying on
     a guessed CSS class name. This makes it resilient to front-end styling changes.
  4. Writes everything to one CSV.

SETUP (run once):
    pip install selenium webdriver-manager pandas

USAGE:
    python daviscup_scraper.py --country India
    python daviscup_scraper.py --country India Spain Japan     (multiple countries at once)
    python daviscup_scraper.py --country India --debug         (visible browser + HTML dumps)

OUTPUT:
    daviscup_players.csv   (one row per player, all requested countries combined)

IF SOMETHING BREAKS:
Run with --debug. It saves debug_team_page.html (the roster page) and
debug_player_<id>.html (each player page) in this folder. Open the relevant one,
Ctrl+F for the missing value (e.g. "Right" for hand), and send me that snippet --
I can adjust FIELD_LABELS or extract_field() precisely instead of guessing again.
"""

import argparse
import re
import sys
import time

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

TEAMS_URL = "https://www.daviscup.com/en/teams"

# The 14 Round 2 Qualifier countries (Sep 2026) -- used as the default set
# when --country isn't given. Names must match how they appear as link text
# on daviscup.com/en/teams (substring matching is used as a fallback too).
DEFAULT_COUNTRIES = [
    "Chile",
    "Spain",
    "Germany",
    "Croatia",
    "Great Britain",
    "Ecuador",
    "Austria",
    "Belgium",
    "Korea, Rep.",
    "India",
    "Czechia",
    "USA",
    "Canada",
    "France",
]

# Label text as it's likely to appear on the player profile page, lowercased.
# If a field comes back empty, add more variants here based on what you see
# in a debug_player_*.html dump.
FIELD_LABELS = {
    "age": ["age"],
    "singles_ranking": ["singles ranking", "singles rank", "ranking"],
    "nominations": ["nominations", "nomination"],
    "singles_wl": ["singles w/l", "singles w-l", "singles"],
    "total_wl": ["total w/l", "total w-l", "w/l", "total"],
    "ties_played": ["ties played", "ties"],
    "first_year_played": ["first year played", "first year", "debut year", "debut"],
    "favourite_hand": ["favourite hand", "favorite hand", "hand"],
    "last_nation_represented": ["last nation represented", "last nation", "nation represented"],
}


def build_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def dismiss_cookie_banner(driver):
    """Accept/hide the Termly cookie-consent banner so it can't intercept clicks."""
    accept_xpaths = [
        "//button[contains(translate(., 'ACEPT', 'acept'), 'accept')]",
        "//*[contains(@class,'termly')]//button",
        "//button[contains(@id,'accept') or contains(@class,'accept')]",
    ]
    for xp in accept_xpaths:
        try:
            for b in driver.find_elements(By.XPATH, xp):
                if b.is_displayed():
                    driver.execute_script("arguments[0].click();", b)
                    time.sleep(1)
                    return
        except Exception:
            continue
    driver.execute_script(
        """
        document.querySelectorAll("[class*='termly'], [id*='termly']").forEach(el => {
            el.style.display = 'none';
            el.style.pointerEvents = 'none';
        });
        """
    )


def get_all_countries(driver):
    """Find every country name + /en/teams/<uuid> link on the main teams list page."""
    driver.get(TEAMS_URL)
    wait = WebDriverWait(driver, 25)
    wait.until(
        lambda d: len(d.find_elements(
            By.XPATH, "//a[contains(@href,'/en/teams/') and string-length(@href) > 20]"
        )) > 0
    )
    dismiss_cookie_banner(driver)
    time.sleep(1)

    # Only keep links that end in a UUID-like id (this is how real team pages are
    # linked, e.g. /en/teams/babe228c-fe49-424a-a7fc-03c6439b019e) -- filters out
    # nav links like the bare "/en/teams" link itself.
    uuid_re = re.compile(
        r"/en/teams/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    links = driver.find_elements(By.XPATH, "//a[contains(@href,'/en/teams/')]")
    countries = []
    seen = set()
    for link in links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if href and text and uuid_re.search(href) and href not in seen:
            seen.add(href)
            countries.append((text, href))
    return countries


def get_team_url(driver, country: str) -> str:
    """Find the /en/teams/<uuid> link for this country directly from the teams list page."""
    for name, href in get_all_countries(driver):
        if name.lower() == country.strip().lower():
            return href
    for name, href in get_all_countries(driver):
        if country.strip().lower() in name.lower():
            return href
    raise RuntimeError(
        f"Could not find a team link for '{country}' on {TEAMS_URL}. "
        f"Double check the country name spelling matches how it's shown on the site."
    )


def get_player_urls(driver, team_url: str, debug: bool = False):
    """Open the team roster page and collect every player profile link."""
    driver.get(team_url)
    wait = WebDriverWait(driver, 25)
    try:
        wait.until(
            lambda d: len(d.find_elements(By.XPATH, "//a[contains(@href,'/en/players/')]")) > 0
        )
    except TimeoutException:
        pass
    dismiss_cookie_banner(driver)
    time.sleep(1)

    if debug:
        with open("debug_team_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("     (saved debug_team_page.html)")

    links = driver.find_elements(By.XPATH, "//a[contains(@href,'/en/players/')]")
    urls, seen = [], set()
    for link in links:
        href = link.get_attribute("href")
        if href and href not in seen:
            seen.add(href)
            urls.append(href)

    if not urls:
        raise RuntimeError(
            f"No player links found on {team_url}. Run with --debug and check "
            f"debug_team_page.html for the roster's real markup."
        )
    return urls


def extract_field(driver, label_variants):
    """
    Class-name-independent extraction: find an element whose visible text exactly
    matches one of the label variants (e.g. 'Nominations'), then return the parent
    element's text with that label stripped out -- i.e. the value sitting next
    to the label on the page.
    """
    for label in label_variants:
        xp = (
            "//*[translate(normalize-space(text()), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
            f"='{label}']"
        )
        try:
            els = driver.find_elements(By.XPATH, xp)
        except Exception:
            continue
        for el in els:
            try:
                parent = el.find_element(By.XPATH, "./..")
                full_text = parent.text.strip()
                value = re.sub(
                    re.escape(el.text.strip()), "", full_text, flags=re.IGNORECASE
                ).strip(" :\n")
                if value:
                    return value
            except Exception:
                continue
    return ""


def wait_for_stats_block(driver, timeout=15):
    """Wait until at least the 'Nominations' stat label has rendered -- this app loads
    the stats section asynchronously after the h1/name appears, so reading
    too early gives blank fields intermittently."""
    xp = (
        "//*[translate(normalize-space(text()), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='nominations']"
    )
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xp)))
    except TimeoutException:
        pass


def scrape_player(driver, player_url: str, country: str, debug: bool = False, max_attempts: int = 3):
    """
    Load a player's profile page and extract all fields. Retries with a FULL
    page reload (not just re-reading the DOM) if fields are missing, since a
    partial/failed render needs a fresh load, not just a longer wait. Keeps
    the best (most-filled) attempt across retries.
    """
    best_row = None

    for attempt in range(1, max_attempts + 1):
        driver.get(player_url)
        wait = WebDriverWait(driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        except TimeoutException:
            pass
        dismiss_cookie_banner(driver)
        wait_for_stats_block(driver)
        time.sleep(1.5 + attempt * 0.5)  # back off a bit more on each retry

        if debug and attempt == 1:
            safe_id = re.sub(r"\W+", "_", player_url)[-40:]
            with open(f"debug_player_{safe_id}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)

        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            name = h1.text.replace("\n", " ").strip()
            name = re.sub(r"\s+", " ", name)
        except NoSuchElementException:
            name = ""

        row = {
            "COUNTRY": country,
            "NAME": name,
            "AGE": extract_field(driver, FIELD_LABELS["age"]),
            "SINGLES RANKING": extract_field(driver, FIELD_LABELS["singles_ranking"]),
            "NOMINATIONS": extract_field(driver, FIELD_LABELS["nominations"]),
            "SINGLES W/L": extract_field(driver, FIELD_LABELS["singles_wl"]),
            "TOTAL W/L": extract_field(driver, FIELD_LABELS["total_wl"]),
            "TIES PLAYED": extract_field(driver, FIELD_LABELS["ties_played"]),
            "FIRST YEAR PLAYED": extract_field(driver, FIELD_LABELS["first_year_played"]),
            "FAVOURITE HAND": extract_field(driver, FIELD_LABELS["favourite_hand"]),
            "LAST NATION REPRESENTED": extract_field(driver, FIELD_LABELS["last_nation_represented"]),
        }

        filled_count = sum(1 for v in row.values() if v)
        if best_row is None or filled_count > sum(1 for v in best_row.values() if v):
            best_row = row

        if all(row.values()):
            break  # everything filled -- no need to retry further
        if attempt < max_attempts:
            print(f"        (incomplete, reloading page -- attempt {attempt}/{max_attempts})")

    if not best_row["NAME"]:
        print(f"        WARNING: failed to load {player_url} after {max_attempts} attempts (blank row)")
    elif not all(best_row.values()):
        missing = [k for k, v in best_row.items() if not v]
        print(f"        NOTE: {best_row['NAME']} missing {missing} (may be genuinely blank on the site)")

    return best_row


def scrape_country(driver, country: str, debug: bool = False, team_url: str = None):
    print(f"  -> Team page for {country}...")
    if team_url is None:
        team_url = get_team_url(driver, country)
    print(f"  -> {team_url}")

    print("  -> Collecting player links...")
    player_urls = get_player_urls(driver, team_url, debug=debug)
    print(f"  -> Found {len(player_urls)} players.")

    rows = []
    for i, url in enumerate(player_urls, 1):
        print(f"     [{i}/{len(player_urls)}] Scraping {url}")
        try:
            rows.append(scrape_player(driver, url, country, debug=debug))
        except Exception as e:
            print(f"        WARNING: failed to scrape {url}: {e}")
        time.sleep(0.8)  # small pause between requests to avoid rate-limiting
    return rows


def main():
    parser = argparse.ArgumentParser(description="Scrape Davis Cup player data.")
    parser.add_argument(
        "--country", nargs="+", default=None,
        help="One or more country names, e.g. --country India Spain Japan. "
             "If omitted, scrapes the default 14 Round-2-qualifier countries "
             "(use --all to scrape EVERY country on the site instead)."
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Scrape every country listed on the site (overrides the default 14)."
    )
    parser.add_argument("--debug", action="store_true", help="Visible browser + save HTML dumps")
    parser.add_argument("--out", default="daviscup_all14_players.csv", help="Output CSV filename")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="When scraping all countries, stop after this many (useful for testing)."
    )
    args = parser.parse_args()

    driver = build_driver(headless=not args.debug)
    all_rows = []
    try:
        if args.country:
            targets = [(c, None) for c in args.country]
        elif args.all:
            print("No --country given, --all set: discovering every country on the site...")
            targets = get_all_countries(driver)
            print(f"Found {len(targets)} countries.")
            if args.limit:
                targets = targets[: args.limit]
        else:
            print(f"No --country given: using default list of {len(DEFAULT_COUNTRIES)} countries.")
            targets = [(c, None) for c in DEFAULT_COUNTRIES]

        for country, team_url in targets:
            print(f"\n=== {country} ===")
            try:
                all_rows.extend(scrape_country(driver, country, debug=args.debug, team_url=team_url))
            except Exception as e:
                print(f"  ERROR scraping {country}: {e}", file=sys.stderr)

        if not all_rows:
            print("\nNo data scraped -- see errors above.", file=sys.stderr)
            sys.exit(1)

        df = pd.DataFrame(all_rows)

        columns = [
            "COUNTRY",
            "NAME",
            "AGE",
            "SINGLES RANKING",
            "NOMINATIONS",
            "SINGLES W/L",
            "TOTAL W/L",
            "TIES PLAYED",
            "FIRST YEAR PLAYED",
            "FAVOURITE HAND",
            "LAST NATION REPRESENTED",
        ]
        df = df.reindex(columns=columns)

        # Excel auto-detects values like "4/0" as a date (e.g. "4-Jan") when a
        # CSV is opened directly. Prefixing with a leading apostrophe forces
        # Excel to treat the cell as TEXT (the apostrophe itself is hidden in
        # the display) -- this only affects how Excel *opens* the CSV, the
        # underlying value is unchanged.
        for col in ("TOTAL W/L", "SINGLES W/L", "FIRST YEAR PLAYED"):
            df[col] = df[col].apply(lambda v: f"'{v}" if v else v)

        df.to_csv(args.out, index=False)
        print(f"\nDone! Saved {len(df)} rows to {args.out}\n")
        print(df.to_string(index=False))

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
