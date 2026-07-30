# Regatta Standings Watcher

Watches the nextSailor **Overall Results / standings page** (https://nextsailor.com/app/scoring/view_regatta/1364) — not the plain results page, this one updates sooner and has real data — and posts a Discord message the moment a new race is scored. No AI/tokens involved — it's a plain script that runs on a timer on your Raspberry Pi.

Tuned for your schedule: races are Wednesday night, results get scored whenever the club gets to it. The script checks daily and just keeps going until it sees a new race column appear, then goes quiet until the next one.

The series has 7 races total (7/15 through 8/26). Once the 7th is scored, the watcher sends a wrap-up message and **stops itself** — no more checks, no more Discord noise — until you point it at the next series.

## How it works

`regatta_watcher.py` fetches the standings page and counts how many "Race N" columns exist in the table. That count (`last_race_count.txt`) is the trigger — when it goes up, new results have been scored.

When it fires, it also finds your boat's row on the standings table (matches "Flyer" or skipper "Rhodes"), then fetches that specific race's results page and pulls your finish for that week too, so the Discord message includes both:

> 🏁 Race 3 results are up!
> This week: Flyer finished 4 of 10 in Spinnaker (corrected 00:56:10).
> Series: 6th overall in Spinnaker, 17 pts.
> https://nextsailor.com/app/scoring/view_results/1364/3213

The link goes straight to that specific race's results page, not just the regatta homepage.

Once the race count reaches `TOTAL_RACES` (7), it sends a second Discord message announcing the series is done, and writes `series_complete.flag`. Every run after that is an instant no-op until you update the script for the new series.

## 1. Create a Discord webhook

1. In Discord, go to your server → **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel you want results posted to, then click **Copy Webhook URL**.
3. Open `regatta_watcher.py` and paste it into `DISCORD_WEBHOOK_URL`.

No bot, no Discord app permissions, no ongoing account needed — the webhook URL is all it takes.

## 2. Put it on GitHub

1. Go to [github.com/new](https://github.com/new), name the repo `regatta_watcher`, create it.
2. On the repo page, click **"uploading an existing file"** and drag in `regatta_watcher.py` and `README.md`, then commit. No git or terminal needed for this step.

## 3. Set up on the Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip git
pip3 install requests beautifulsoup4 --break-system-packages

git clone https://github.com/cptnslick/regatta_watcher.git ~/regatta_watcher
cd ~/regatta_watcher
```

**To pull down future updates** (e.g. when the script changes for a new series), just run:

```bash
cd ~/regatta_watcher && git pull
```

Test it manually:

```bash
python3 regatta_watcher.py
# "Baseline saved at race 3, no notification sent." on first run
python3 regatta_watcher.py
# "No new race results yet." on subsequent runs (until a new race is scored)
```

## 4. Run it automatically (cron)

```bash
crontab -e
```

Add this line — checks hourly, 8am–11pm, every day (so it keeps trying no matter which day results actually land):

```
0 8-23 * * * /usr/bin/python3 /home/pi/regatta_watcher/regatta_watcher.py >> /home/pi/regatta_watcher/watcher.log 2>&1
```

Adjust the path and username to match your Pi setup (run `pwd` and `whoami` in the watcher folder to confirm). Save and exit — cron picks it up automatically, no reboot needed.

That's it: the Pi checks hourly, every day, pings Discord with your standing the moment a new race is scored, and automatically shuts itself off once the final race (race 7) posts. Zero ongoing cost, no API keys, no tokens.

## Setting up the next series

When the wrap-up Discord message arrives, reply here (in this chat) with the next series' standings-page URL, the total number of races, and your boat/skipper name if it's different — I'll update `STANDINGS_URL`, `TOTAL_RACES`, `TARGET_BOAT_NAME`, and `TARGET_SKIPPER_NAME` in the script. Re-upload the updated file to the GitHub repo (same drag-and-drop as step 2), then on the Pi run `cd ~/regatta_watcher && git pull` to sync it. (The script itself can only *post* to Discord, not read replies from it — there's no bot listening on the other end — so the "ask" happens here rather than in Discord.)

## Notes

- You can leave cron running all the time — once `series_complete.flag` exists, checks are essentially free (one quick file read, no web request).
- If your boat's name or skipper changes, or Flyer isn't found on the page for some reason, the Discord message just skips the personalized line and posts a generic "Race N results are up!" instead — it never breaks silently.
- To reset for testing, delete `last_race_count.txt` and `series_complete.flag`.
