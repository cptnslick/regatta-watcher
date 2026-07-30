#!/usr/bin/env python3
"""
Regatta Standings Watcher
--------------------------
Watches the nextSailor "Overall Results" standings page (not just the plain
results landing page -- this one updates sooner and has real data). Each
time a new race gets scored, it posts a Discord message with Flyer's score
for that race, current series position, and points, plus a link straight to
that race's results.

Runs on a schedule (cron). Once the final race of the series (TOTAL_RACES)
is scored, it posts a wrap-up message and stops itself until pointed at the
next series.

No AI/LLM calls, no ongoing cost. The Discord webhook URL is read from
discord_webhook_url.txt (gitignored) rather than hardcoded here, since
this repo is public.
"""

import datetime
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

# ---- Config -------------------------------------------------------------
STANDINGS_URL = "https://nextsailor.com/app/scoring/view_regatta/1364"

# Used to find your boat's row on the standings table (case-insensitive
# substring match against the Boat / Skipper columns).
TARGET_BOAT_NAME = "Flyer"
TARGET_SKIPPER_NAME = "Rhodes"

# Total races in the series (7/15, 7/22, 7/29, 8/5, 8/12, 8/19, 8/26).
# Once this many race columns appear on the standings page, the watcher
# treats it as final and stops. Update this (and STANDINGS_URL) for the
# next series -- if this number's wrong, just edit it any time.
TOTAL_RACES = 7

# State files, kept next to the script.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RACE_COUNT_FILE = os.path.join(SCRIPT_DIR, "last_race_count.txt")
DONE_FILE = os.path.join(SCRIPT_DIR, "series_complete.flag")

# Discord webhook URL lives in its own file, NOT in this script. This repo
# is public -- a webhook URL baked into tracked code would let anyone who
# finds it spam your Discord channel. Create this file once on the Pi with
# just the URL as its contents (Server Settings -> Integrations -> Webhooks
# -> New Webhook -> Copy URL). It's listed in .gitignore, so it never gets
# committed or uploaded to GitHub.
WEBHOOK_FILE = os.path.join(SCRIPT_DIR, "discord_webhook_url.txt")

RACE_HEADER_RE = re.compile(r"Race\s+(\d+)", re.IGNORECASE)
FLEET_SUFFIX_RE = re.compile(r"\s*\(\d+\s*boats?\)", re.IGNORECASE)
# ---------------------------------------------------------------------------


def fetch_html(url: str) -> str:
    resp = requests.get(
        url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (regatta-watcher-bot)"}
    )
    resp.raise_for_status()
    return resp.text


def absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return "https://nextsailor.com" + href


def parse_standings(html: str):
    """Returns (max_race_num, latest_race_url, target_row_dict_or_None)."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    max_race_num = 0
    latest_race_url = None
    target_row = None

    for table in tables:
        header_row = table.find("tr")
        if header_row is None:
            continue
        header_cells = header_row.find_all(["th", "td"])

        race_col_idx = {}
        race_urls = {}
        boat_idx = skipper_idx = points_idx = pos_idx = None

        for idx, cell in enumerate(header_cells):
            text = cell.get_text(strip=True)
            m = RACE_HEADER_RE.match(text)
            if m:
                n = int(m.group(1))
                race_col_idx[n] = idx
                a = cell.find("a")
                if a and a.get("href"):
                    race_urls[n] = absolute_url(a["href"])
            elif text.lower() == "boat":
                boat_idx = idx
            elif text.lower() == "skipper":
                skipper_idx = idx
            elif text.lower() == "points":
                points_idx = idx
            elif text.lower() == "pos":
                pos_idx = idx

        if race_col_idx:
            table_max = max(race_col_idx)
            if table_max > max_race_num:
                max_race_num = table_max
                latest_race_url = race_urls.get(table_max)

        fleet_name = "Fleet"
        heading = table.find_previous(["h1", "h2", "h3", "h4", "h5"])
        if heading:
            fleet_name = FLEET_SUFFIX_RE.sub("", heading.get_text(strip=True))

        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            cell_texts = [c.get_text(strip=True) for c in cells]

            boat = cell_texts[boat_idx] if boat_idx is not None and boat_idx < len(cell_texts) else ""
            skipper = cell_texts[skipper_idx] if skipper_idx is not None and skipper_idx < len(cell_texts) else ""

            if TARGET_BOAT_NAME.lower() in boat.lower() or TARGET_SKIPPER_NAME.lower() in skipper.lower():
                latest_score = None
                if max_race_num in race_col_idx:
                    idx = race_col_idx[max_race_num]
                    if idx < len(cell_texts):
                        latest_score = cell_texts[idx]
                target_row = {
                    "fleet": fleet_name,
                    "boat": boat,
                    "points": cell_texts[points_idx] if points_idx is not None and points_idx < len(cell_texts) else "?",
                    "pos": cell_texts[pos_idx] if pos_idx is not None and pos_idx < len(cell_texts) else "?",
                    "latest_score": latest_score,
                }

    return max_race_num, latest_race_url, target_row


def parse_race_result(html: str):
    """Find the target boat's row on a single race's results page.

    Returns a dict with that race's finishing position, corrected time,
    and fleet size (total boats in the same fleet that race), or None if
    the boat isn't found.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    for table in tables:
        header_row = table.find("tr")
        if header_row is None:
            continue
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]

        def col(name):
            for i, h in enumerate(headers):
                if h.lower() == name.lower():
                    return i
            return None

        pos_idx = col("Pos")
        boat_idx = col("Boat")
        skipper_idx = col("Skipper")
        corrected_idx = col("Corrected")

        rows = table.find_all("tr")[1:]
        total_boats = len(rows)

        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue
            cell_texts = [c.get_text(strip=True) for c in cells]
            boat = cell_texts[boat_idx] if boat_idx is not None and boat_idx < len(cell_texts) else ""
            skipper = cell_texts[skipper_idx] if skipper_idx is not None and skipper_idx < len(cell_texts) else ""

            if TARGET_BOAT_NAME.lower() in boat.lower() or TARGET_SKIPPER_NAME.lower() in skipper.lower():
                return {
                    "pos": cell_texts[pos_idx] if pos_idx is not None and pos_idx < len(cell_texts) else "?",
                    "corrected": cell_texts[corrected_idx]
                    if corrected_idx is not None and corrected_idx < len(cell_texts)
                    else None,
                    "total_boats": total_boats,
                }

    return None


def read_int(path):
    if os.path.exists(path):
        try:
            return int(open(path).read().strip())
        except ValueError:
            return None
    return None


def read_text(path):
    if os.path.exists(path):
        return open(path).read().strip()
    return None


def write_text(path, content):
    with open(path, "w") as f:
        f.write(str(content))


def notify_discord(message: str):
    webhook_url = read_text(WEBHOOK_FILE)
    if not webhook_url:
        print(
            f"No webhook URL found at {WEBHOOK_FILE} -- create that file with your "
            "Discord webhook URL as its only contents. Skipping notification.",
            file=sys.stderr,
        )
        return
    try:
        requests.post(webhook_url, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)


def main():
    if os.path.exists(DONE_FILE):
        print("Series already complete, watcher is idle. Update config to reuse for a new series.")
        return

    try:
        html = fetch_html(STANDINGS_URL)
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        return

    race_num, race_url, target = parse_standings(html)

    if race_num == 0:
        print("Could not find any race columns on the page -- site layout may have changed.")
        return

    last_race_num = read_int(RACE_COUNT_FILE)

    if last_race_num is None:
        # First run ever: just record the baseline, don't notify.
        write_text(RACE_COUNT_FILE, race_num)
        print(f"Baseline saved at race {race_num}, no notification sent.")
        return

    if race_num <= last_race_num:
        print("No new race results yet.")
        return

    write_text(RACE_COUNT_FILE, race_num)

    race_detail = None
    if race_url:
        try:
            race_html = fetch_html(race_url)
            race_detail = parse_race_result(race_html)
        except Exception as e:
            print(f"Could not fetch race detail page: {e}", file=sys.stderr)

    lines = [f"\U0001F3C1 Race {race_num} results are up!"]

    if race_detail:
        corrected = f" (corrected {race_detail['corrected']})" if race_detail.get("corrected") else ""
        fleet = target["fleet"] if target else "fleet"
        lines.append(
            f"This week: Flyer finished {race_detail['pos']} of "
            f"{race_detail['total_boats']} in {fleet}{corrected}."
        )
    elif target:
        score = target["latest_score"] or "?"
        lines.append(f"This week: Flyer scored {score}.")

    if target:
        lines.append(f"Series: {target['pos']} overall in {target['fleet']}, {target['points']} pts.")

    if race_url:
        lines.append(race_url)

    message = "\n".join(lines)

    notify_discord(message)
    print(f"Race {race_num} -> Discord notification sent.")

    if race_num >= TOTAL_RACES:
        notify_discord(
            "\U0001F3C6 That was the final race of this series! The watcher is "
            "stopping now. Send Will the next series' standings-page URL, total "
            "race count, and boat info to set up a new watcher."
        )
        write_text(DONE_FILE, f"completed {datetime.date.today().isoformat()}")
        print("Series complete -> watcher stopped, wrap-up message sent.")


if __name__ == "__main__":
    main()
