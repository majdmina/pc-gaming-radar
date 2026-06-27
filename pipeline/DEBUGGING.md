# Debugging & State Handoff

Snapshot of the live local pipeline so a future session (or you) can debug fast.
Last verified: **2026-06-27**.

## What is running

- **Repo / code:** `~/pc-gaming-radar/` (GitHub: `majdmina/pc-gaming-radar`).
- **Scheduler:** `systemd --user` units `radar-weekly.{timer,service}` in `~/.config/systemd/user/`.
  - Fires **Fri 08:00** (`+RandomizedDelaySec=300`, so ~08:0X). `Persistent=true` → if the PC was
    off at 08:00 it runs at the next login/boot.
- **Runner:** `pipeline/run_weekly.sh` → `pipeline/weekly_radar.py`.
- **Model:** `gemma3:12b-it-qat` via local Ollama on the RTX 5070 Ti. (Alts: `gpt-oss:20b`,
  `gemma3:27b-it-qat`, `gemma3:4b-it-qat`.)
- **Output:** one Telegram message per story → bot **@MinacoGamingBot** → channel **"GamingRadar"**.
  Also archived to `~/pc-gaming-radar/archive/YYYY-MM-DD.md`.
- **Secrets:** `pipeline/.env` (gitignored) holds `TG_BOT_TOKEN`, `TG_CHAT_ID`, `RADAR_MODEL`,
  `RADAR_DAYS`. Never committed.

## Health checks

```bash
systemctl --user list-timers radar-weekly.timer     # is it scheduled? when next?
systemctl --user is-enabled radar-weekly.timer       # should say: enabled
journalctl --user -u radar-weekly.service -n 40       # last run's log
ollama ps ; ollama list                               # model server up / installed?
curl -s http://localhost:11434/api/tags >/dev/null && echo ollama-ok
```

## Run it by hand

```bash
# full production path (fetch -> curate -> Telegram -> archive), via systemd:
systemctl --user start radar-weekly.service

# or directly, to see output in the terminal:
cd ~/pc-gaming-radar/pipeline
python3 weekly_radar.py                               # rules-only, no LLM, no send
python3 weekly_radar.py --model gemma3:12b-it-qat     # with summaries, prints only
set -a; . ./.env; set +a
python3 weekly_radar.py --model "$RADAR_MODEL" --telegram --save ../archive   # full
```

## Common failures → fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `# telegram send failed: ... Network is unreachable` | transient IPv6/network blip | `_tg_post` already retries 4× w/ backoff; if persistent, check connectivity / `curl https://api.telegram.org`. |
| `TG_BOT_TOKEN / TG_CHAT_ID not set` | `.env` missing/not loaded | ensure `pipeline/.env` exists; runner auto-loads it. |
| Telegram 400 "chat not found" | bot removed from channel, or wrong id | re-add **@MinacoGamingBot** as channel admin; re-read id via `getUpdates`. |
| Telegram 429 | rate limit | handled (honors `retry_after`); lower per-section cap `items[:10]` if spammy. |
| `# feed errors: <name>: ...` | a source feed down/changed | non-fatal; one feed failing doesn't stop the run. Remove/replace in `FEEDS`. |
| Fetch very slow (minutes) | a hung feed | `socket.setdefaulttimeout(20)` caps it; raise/lower if needed. |
| Empty/garbled brief | Ollama down or model missing | `ollama serve`; `ollama pull <model>`; runner also auto-starts `ollama serve`. |
| Model OOM / very slow | 27B too big for 16GB w/ long ctx | use `gemma3:12b-it-qat` (default) or `gpt-oss:20b`. |
| Bad JSON from model | model ignored format | code falls back to regex-extract `{...}`; if still bad, lower `--days` or switch model. |

## Tuning knobs (all in `weekly_radar.py`)

- **Sources:** `FEEDS` dict (name → url, tier). Tier 3 = corroboration only.
- **Taste:** `BATMAN` / `FRANCHISE` / `GENRE` / `TECH` / `NEGATIVE` keyword lists + `WEIGHTS`.
- **Items per section:** `items[:10]` in `render_md` and `send_telegram_items`.
- **Clustering tightness:** `jaccard(...) >= 0.55` in `cluster()`.
- **Window:** `--days N` or `RADAR_DAYS` in `.env`.

## If the schedule should survive full logout (headless)

```bash
loginctl enable-linger "$USER"     # user services run even before you log in
```
Not needed if you log into the desktop regularly (Persistent=true catches up anyway).
