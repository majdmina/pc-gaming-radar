# Local Weekly Radar Pipeline (n8n-free, GPU-powered, $0)

A self-hosted alternative to the Perplexity task. Pulls ~20 RSS feeds, taste-filters to your
profile, has a **local Ollama model curate** the result (no paid API), and posts a
Telegram-ready brief — **with a clickable link per headline**. Runs weekly via a systemd
timer that **catches up if your PC was off** at the scheduled time.

## Architecture (why it doesn't hallucinate)

```
RSS feeds ──► fetch + date filter ──► taste score + dedupe/cluster ──►  [rules layer: owns facts + links]
                                                                  │
                                                                  ▼
                                              Ollama model CURATES by id (keep/drop/section)
                                                                  │
                                                                  ▼
                                   render brief from REAL cluster data ──► Telegram + archive/
```

The LLM never rewrites headlines or invents text — it only **classifies/drops** by id. Links and
facts come from the feed data, so the output can't hallucinate and never loses a link.

## Files

- `weekly_radar.py` — the whole pipeline (fetch, filter, cluster, curate, send, save).
- `run_weekly.sh` — wrapper the timer calls (loads `.env`, ensures Ollama is up).
- `systemd/` — user-level `.service` + `.timer` (weekly, `Persistent=true`).
- `.env.example` — copy to `.env`, add Telegram token + model choice.

## Quick start

```bash
cd ~/LocalOps/projects/pc-gaming-radar/pipeline
python3 weekly_radar.py                       # rules-only, prints to terminal
python3 weekly_radar.py --model gemma3:12b-it-qat   # + local LLM curation
```

## Model picks (RTX 5070 Ti 16GB, measured)

| Model | Curate time | Verdict |
|---|---|---|
| `gemma3:12b-it-qat` | ~11s | **default** — fast, clean, fits easily |
| `gpt-oss:20b` | ~36s | already installed, a touch more thorough |
| `gemma3:4b-it-qat` | fastest | weak judgment, pinch only |
| `gemma3:27b-it-qat` | slow | max quality; spills to RAM at 16GB but fine for a weekly batch |

## Telegram setup

1. Message **@BotFather** → `/newbot` → copy the token.
2. Create a channel, add the bot as admin, get its chat id (e.g. via `@username_to_id_bot`
   or the `getUpdates` API). Channel ids are negative, like `-1001234567890`.
3. `cp .env.example .env` and fill `TG_BOT_TOKEN` / `TG_CHAT_ID`.
4. Test: `set -a; . ./.env; set +a; python3 weekly_radar.py --model gemma3:12b-it-qat --telegram`

## Install the weekly timer (catches up if PC was off)

```bash
mkdir -p ~/.config/systemd/user
cp ~/LocalOps/projects/pc-gaming-radar/pipeline/systemd/radar-weekly.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now radar-weekly.timer
systemctl --user list-timers radar-weekly.timer      # confirm next run
# optional: run even before you log in
loginctl enable-linger "$USER"
```

Fire a run by hand any time: `systemctl --user start radar-weekly.service`

## Tuning

- Add/remove sources: edit the `FEEDS` dict in `weekly_radar.py`.
- Change taste: edit `BATMAN` / `FRANCHISE` / `GENRE` / `TECH` / `NEGATIVE` lists.
- Window: `--days N` or `RADAR_DAYS` in `.env`.
