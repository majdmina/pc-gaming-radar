# PC Gaming Radar — Perplexity Pipeline

A weekly **PC-first, single-player, offline-AAA** gaming briefing run by a Perplexity scheduled task.

The problem this repo solves: Perplexity's task box caps at **~2,000 characters**, but the full spec is ~7,500.
So the spec lives here as a fetchable file, and the Perplexity task is just a tiny pointer that says
"go read this URL, then do the brief." Edit the spec here anytime — the Perplexity task never changes.

## Files

| File | What it is |
|------|------------|
| **`radar.md`** | The full, authoritative spec. This is what Perplexity fetches and obeys. |
| **`prompt.txt`** | The exact text to paste into the Perplexity task box (pointer + compressed fallback, **under 2,000 chars**). |
| **`last-week.md`** | Optional de-dup memory. Paste last week's brief here so the next run avoids repeating stories. |
| **`profile.md`** | Optional. Your owned/finished/backlog/wishlist lists — the spec reads it so it never recommends games you already have and prioritizes your wishlist. |
| **`archive/`** | Drop each week's output as `YYYY-MM-DD.md` to build a searchable personal history. |

## The fetch URLs (raw, stable, public)

- Spec: `https://raw.githubusercontent.com/majdmina/pc-gaming-radar/main/radar.md`
- De-dup memory: `https://raw.githubusercontent.com/majdmina/pc-gaming-radar/main/last-week.md`
- Profile: `https://raw.githubusercontent.com/majdmina/pc-gaming-radar/main/profile.md`

## Setup (one time)

1. Open Perplexity → create a **Scheduled Task**, weekly, Friday 08:00.
2. Paste the contents of **`prompt.txt`** into the task box.
3. Done. The task fetches `radar.md` each run.

> **Honest caveat:** Perplexity's scheduled tasks can't *guarantee* fetching an arbitrary URL every run —
> it's a search tool first. That's why `prompt.txt` carries a **compressed fallback spec** inline: if the fetch
> ever fails, the brief still runs from the essentials instead of erroring.

## Updating the brief (no Perplexity edits ever again)

- Change taste, sources, or structure → edit **`radar.md`**, commit, push. Next run picks it up.
- Stop repetition → after each brief, paste its output into **`last-week.md`** (and archive a dated copy).

## Smart uses of this repo

- **One spec, many tasks.** Point a second Perplexity task (e.g. a monthly PS Plus + deals deep-dive) at the same repo.
- **Versioned taste.** Git history shows how your priorities/wishlist changed over time.
- **Personal memory.** `archive/` + `last-week.md` give the brief a sense of "what I already told you."
- **Portable.** The same `radar.md` works pasted into ChatGPT / Gemini / Claude manually on weeks you want it on demand.
