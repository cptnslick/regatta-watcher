# Regatta Results Watcher

Checks https://nextsailor.com/app/page/regatta/1364/results for changes and posts a message to your Discord channel when new race results go up. No AI/tokens involved — it's a plain script that runs on a timer on your Raspberry Pi.

Tuned for your schedule: races are Wednesday night, results usually post Thursday afternoon but sometimes early, often late. The script checks daily and just keeps going — if nothing's posted Thursday, it tries again Friday, Saturday, etc. — until it actually sees new results, then goes quiet until the next race.

The series' last race is 8/26. Once results for that race (or later) are posted, the watcher sends a wrap-up message and **stops itself** — no more checks, no more Discord noise — until you point it at the next series.

## How it works

`results_watcher.py` fetches the page, pulls out just the "Results" section (so unrelated page changes don't trigger false alarms), and hashes it. Each run compares against the hash from last time (`last_hash.txt`). If it changed, it posts to Discord via webhook.

It also reads the race date(s) out of the results text. If the newest race date is on or after `SERIES_END_DATE` (currently 8/26/2026), it treats that as the final results of the series: it sends a second Discord message asking for the next series' URL and end date, and writes `series_complete.flag`. Every run after that is an instant no-op until you update the script for the new series.

## 1. Create a Discord webhook

1. In Discord, go to your server → **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel you want results posted to, then click **Copy Webhook URL**.
3. Open `results_watcher.py` and paste it into `DISCORD_WEBHOOK_URL`.

No bot, no Discord app permissions, no ongoing account needed — the webhook URL is all it takes.

## 2. Put it on GitHub

1. Go to [github.com/new](https://github.com/new), name the repo (e.g. `regatta-watcher`), create it.
2. On the repo page, click **"uploading an existing file"** and drag in `results_watcher.py` and `README.md`, then commit. No git or terminal needed for this step.

## 3. Set up on the Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip git
pip3 install requests beautifulsoup4 --break-system-packages

git clone https://github.com/<your-username>/regatta-watcher.git ~/regatta-watcher
cd ~/regatta-watcher
```

**To pull down future updates** (e.g. when the script changes for a new series), just run:

```bash
cd ~/regatta-watcher && git pull
```

Test it manually:

```bash
python3 results_watcher.py
# "Baseline saved, no notification sent." on first run
python3 results_watcher.py
# "No change yet." on subsequent runs (until the page actually changes)
```

## 4. Run it automatically (cron)

```bash
crontab -e
```

Add this line — checks hourly, 8am–11pm, every day (so it keeps trying even if Thursday comes and goes with nothing posted):

```
0 8-23 * * * /usr/bin/python3 /home/pi/regatta-watcher/results_watcher.py >> /home/pi/regatta-watcher/watcher.log 2>&1
```

Adjust the path and username to match your Pi setup (run `pwd` and `whoami` in the watcher folder to confirm). Save and exit — cron picks it up automatically, no reboot needed.

That's it: the Pi checks hourly, every day, pings Discord the moment results appear (whatever day that ends up being), and automatically shuts itself off once the final race of the series (8/26+) is posted. Zero ongoing cost, no API keys, no tokens.

## Setting up the next series

When the wrap-up Discord message arrives, reply here (in this chat) with the new results-page URL and the new series' last race date — I'll update `SERIES_END_DATE` and `URL` in the script. Re-upload the updated file to the GitHub repo (same drag-and-drop as step 2), then on the Pi run `cd ~/regatta-watcher && git pull` to sync it. (The script itself can only *post* to Discord, not read replies from it — there's no bot listening on the other end — so the "ask" happens here rather than in Discord.)

## Notes

- You can leave cron running all the time — once `series_complete.flag` exists, checks are essentially free (one quick file read, no web request).
- If nextSailor changes their page layout, the script falls back to hashing the whole page, so it'll never silently break — worst case is an extra notification.
- To reset for testing, delete `last_hash.txt`, `series_complete.flag`.
