#!/usr/bin/env python3
"""
nextSailor Regatta Results Watcher
-----------------------------------
Checks the regatta results page for changes and posts a message to a
Discord channel (via webhook) when new race results go up.

Designed to run daily (cron) starting the morning after race night.
It just keeps checking, day after day, until results actually appear --
no matter if they're posted early, late, or slip past Thursday.

Once results for the LAST race of the series (SERIES_END_DATE) are
detected, it posts a wrap-up message asking for the next series' URL
and end date, then stops checking entirely (safe no-op on every run
after that) until you point it at a new series.

No AI/LLM calls, no API keys required. Pure HTTP fetch + diff.
"""

import datetime
import hashlib
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

# ---- Config -----------------------------------------------------------
URL = "https://nextsailor.com/app/page/regatta/1364/results"

# Date of the LAST race in this series. Once results dated on/after this
# are posted, the watcher wraps up and stops. Update this (and URL above)
# when a new series starts.
SERIES_END_DATE = datetime.date(2026, 8, 26)

# Discord: Server Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/CHANGE-ME/CHANGE-ME"

# State files, kept next to the script.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HASH_FILE = os.path.join(SCRIPT_DIR, "last_hash.txt")
DONE_FILE = os.path.join(SCRIPT_DIR, "series_complete.flag")

DATE_RE = re.compile(r"Date:\s*(\d{2}/\d{2}/\d{4})")
# -------------------------------------------------------------------------


def fetch_results_text() -> str:
    """Fetch the page and return just the text of the Results section."""
    resp = requests.get(
        URL, timeout=20, headers={"User-Agent": "Mozilla/5.0 (results-watcher-bot)"}
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3")
        and tag.get_text(strip=True) == "Results"
    )

    if heading is None:
        # Fallback: hash the whole page body if the layout ever changes.
        return soup.get_text(separator="\n", strip=True)

    parts = []
    for sib in heading.find_all_next():
        if sib.name in ("h1", "h2"):
            break
        parts.append(sib.get_text(" ", strip=True))
    return "\n".join(p for p in parts if p)


def latest_race_date(text: str):
    """Return the most recent 'Date: MM/DD/YYYY' found in the results text, or None."""
    dates = []
    for m in DATE_RE.finditer(text):
        try:
            dates.append(datetime.datetime.strptime(m.group(1), "%m/%d/%Y").date())
        except ValueError:
            pass
    return max(dates) if dates else None


def read_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return None


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)


def notify_discord(message: str):
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)


def main():
    if read_file(DONE_FILE):
        print("Series already complete, watcher is idle. Update URL/SERIES_END_DATE to reuse.")
        return

    try:
        text = fetch_results_text()
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        return

    current_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    last_hash = read_file(HASH_FILE)

    if last_hash is None:
        # First run ever: just record the baseline, don't notify.
        write_file(HASH_FILE, current_hash)
        print("Baseline saved, no notification sent.")
        return

    if current_hash == last_hash:
        print("No change yet.")
        return

    # Content changed -> new results are up.
    write_file(HASH_FILE, current_hash)
    race_date = latest_race_date(text)
    date_str = race_date.strftime("%m/%d/%Y") if race_date else "unknown date"
    notify_discord(f"\U0001F3C1 New regatta results are up ({date_str}): {URL}")
    print(f"Change detected (race {date_str}) -> Discord notification sent.")

    if race_date and race_date >= SERIES_END_DATE:
        notify_discord(
            "\U0001F3C6 That was the final race of this series! The watcher is "
            "stopping now. Send Will the next series' results-page URL and its "
            "final race date to set up a new watcher."
        )
        write_file(DONE_FILE, f"completed {datetime.date.today().isoformat()}")
        print("Series complete -> watcher stopped, wrap-up message sent.")


if __name__ == "__main__":
    main()
