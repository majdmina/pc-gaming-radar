#!/usr/bin/env bash
# Weekly radar runner. Called by the systemd user timer (or by hand).
set -euo pipefail
cd "$(dirname "$0")"

# Load Telegram creds + model choice if present (see .env.example)
[ -f .env ] && set -a && . ./.env && set +a

MODEL="${RADAR_MODEL:-gemma3:12b-it-qat}"   # override in .env
DAYS="${RADAR_DAYS:-7}"

# Make sure ollama is reachable; start the server if it isn't.
if ! curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "ollama not responding; starting 'ollama serve'..." >&2
  ollama serve >/dev/null 2>&1 &
  for i in $(seq 1 30); do
    curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

exec python3 weekly_radar.py --days "$DAYS" --model "$MODEL" --telegram --save ../archive
