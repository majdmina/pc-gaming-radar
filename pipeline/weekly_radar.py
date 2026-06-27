#!/usr/bin/env python3
"""
Weekly Deep PC Gaming Radar — local aggregation pipeline.

Stage 1 (no LLM, free, reliable): pull RSS from a curated source list, keep the
last N days, taste-filter + dedupe to the user's profile, group into sections.
Stage 2 (optional, local Ollama): hand the curated items to a local model to
write the final Telegram-ready brief. No paid API, no cloud.

Usage:
  python3 weekly_radar.py                       # rules-only digest, last 7 days
  python3 weekly_radar.py --model gpt-oss:20b   # + LLM synthesis (local Ollama)
  python3 weekly_radar.py --days 7 --model gemma3:12b-it-qat
"""
import argparse, re, sys, time, json, html, socket, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
import feedparser

socket.setdefaulttimeout(20)  # feedparser has no timeout; stop slow feeds from hanging the run

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 weekly-radar/1.0"

# name: (url, tier)  — tier 3 = corroboration only (down-weighted, never the headline source)
FEEDS = {
    "IGN":              ("https://feeds.feedburner.com/ign/games-all", 1),
    "PC Gamer":         ("https://www.pcgamer.com/rss/", 1),
    "GamesRadar+":      ("https://www.gamesradar.com/rss/", 1),
    "Eurogamer":        ("https://www.eurogamer.net/feed", 1),
    "Rock Paper Shotgun":("https://www.rockpapershotgun.com/feed", 1),
    "VGC":              ("https://www.videogameschronicle.com/feed/", 1),
    "Gematsu":          ("https://www.gematsu.com/feed", 1),
    "Push Square":      ("https://www.pushsquare.com/feeds/latest", 1),
    "Pure Xbox":        ("https://www.purexbox.com/feeds/latest", 1),
    "PCGamesN":         ("https://www.pcgamesn.com/mainrss.xml", 1),
    "DSOGaming":        ("https://www.dsogaming.com/feed/", 1),
    "GameSpot":         ("https://www.gamespot.com/feeds/mashup/", 2),
    "Shacknews":        ("https://www.shacknews.com/feed/rss", 2),
    "Siliconera":       ("https://www.siliconera.com/feed/", 2),   # JP games / Capcom / RE / SH
    "Automaton West":   ("https://automaton-media.com/en/feed/", 2),# JP games
    "TechRaptor":       ("https://techraptor.net/feed", 2),
    "GamingBolt":       ("https://gamingbolt.com/feed", 2),
    "TorrentFreak":     ("https://torrentfreak.com/feed/", 2),     # DRM / preservation news
    "r/Games":          ("https://www.reddit.com/r/Games/.rss", 2),
    "Wccftech":         ("https://wccftech.com/feed/", 3),         # leaks/speculation — corroboration only
}

# --- taste model (mirrors radar.md / profile.md) ---
BATMAN = ["batman", "arkham"]
FRANCHISE = [
    "resident evil", "capcom", "silent hill", "alan wake", "remedy", "control 2",
    "spider-man", "spiderman", "marvel", "hitman", "io interactive", "007", "james bond",
    "tomb raider", "ghost of tsushima", "ghost of yotei", "last of us", "horizon",
    "hogwarts", "pragmata", "doom: the dark ages", "doom the dark ages", "assassin's creed shadows",
    "star wars outlaws", "jedi survivor", "jedi: survivor", "red dead", "death stranding",
]
GENRE = [
    "single-player", "single player", "story-driven", "campaign", "survival horror",
    "psychological horror", "stealth", "action-adventure", "action adventure", "cinematic",
]
TECH = [
    "denuvo", "dlss", "fsr", "xess", "ray tracing", "ray-tracing", "stutter", "shader",
    "pc port", "port ", "benchmark", "rtx 50", "rtx 5070", "5070 ti", "frame generation",
    "vram", "ps plus", "playstation plus", "opencritic", "metacritic", "howlongtobeat",
    "review", "delayed", "release date", "deal", "discount", "steam sale", "preservation",
]
NEGATIVE = [
    "battle royale", "battle-royale", "esports", "e-sports", "hero shooter", "mmo ", "mmorpg",
    "gacha", "fortnite", "valorant", "counter-strike", "cs2", "overwatch", "apex legends",
    "league of legends", "dota", "rocket league", "fall guys", "warzone", "the finals",
    "marvel rivals", "deadlock", "tournament", "ranked season", "battle pass",
]

WEIGHTS = {"batman": 100, "franchise": 40, "genre": 8, "tech": 6}
NEG_PENALTY = 50

STOP = set("a an the of to in on for and or with is are this that new your you it its as at "
           "get gets all how why what when game games update updates first into out now".split())

def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def score(title, summary):
    t = (title + " " + summary).lower()
    s, hits = 0, []
    for k in BATMAN:
        if k in t: s += WEIGHTS["batman"]; hits.append(k)
    for k in FRANCHISE:
        if k in t: s += WEIGHTS["franchise"]; hits.append(k)
    for k in GENRE:
        if k in t: s += WEIGHTS["genre"]
    for k in TECH:
        if k in t: s += WEIGHTS["tech"]
    neg = sum(1 for k in NEGATIVE if k in t)
    s -= neg * NEG_PENALTY
    return s, hits, neg

def tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if w not in STOP and len(w) > 2}

def jaccard(a, b):
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

def fetch(days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items, errors = [], []
    for name, (url, tier) in FEEDS.items():
        try:
            d = feedparser.parse(url, agent=UA)
            n = 0
            for e in d.entries:
                tp = e.get("published_parsed") or e.get("updated_parsed")
                when = datetime(*tp[:6], tzinfo=timezone.utc) if tp else None
                if when and when < cutoff:
                    continue
                title = clean(e.get("title", ""))
                if not title:
                    continue
                summary = clean(e.get("summary", ""))[:400]
                link = e.get("link", "")
                sc, hits, neg = score(title, summary)
                if sc <= 0:
                    continue
                items.append(dict(source=name, tier=tier, title=title, link=link,
                                  summary=summary, when=when, score=sc, hits=hits, neg=neg,
                                  tok=tokens(title)))
                n += 1
            time.sleep(0.4)  # be polite
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    return items, errors

def cluster(items):
    """Group near-duplicate stories; strongest (lowest tier, highest score) leads."""
    items.sort(key=lambda x: (x["tier"], -x["score"]))
    clusters = []
    for it in items:
        placed = False
        for c in clusters:
            if jaccard(it["tok"], c[0]["tok"]) >= 0.55:
                c.append(it); placed = True; break
        if not placed:
            clusters.append([it])
    # rank clusters by lead score, then size
    clusters.sort(key=lambda c: (-c[0]["score"], -len(c)))
    return clusters

def bucket(lead):
    t = (lead["title"] + " " + lead["summary"]).lower()
    if any(k in t for k in BATMAN): return "batman"
    if lead["source"] == "TorrentFreak" or "denuvo" in t or "preservation" in t or "crack" in t:
        return "drm"
    if any(k in t for k in ["dlss","fsr","xess","stutter","shader","pc port","benchmark","vram","ray tracing","frame gen"]):
        return "ports"
    if any(k in t for k in ["deal","discount","sale","ps plus","playstation plus","free"]):
        return "deals"
    if any(k in t for k in FRANCHISE): return "franchise"
    return "radar"

def render_rules(clusters, days):
    now = datetime.now(timezone.utc)
    out = [f"🎮 *Deep PC Gaming Radar* — last {days} days "
           f"({(now-timedelta(days=days)).strftime('%b %d')}–{now.strftime('%b %d, %Y')})",
           "_PC-first · single-player · offline-AAA · 1440p/RTX 5070 Ti_\n"]
    titles = {"batman":"🦇 Batman / Arkham Watch","franchise":"⭐ Priority Franchises",
              "radar":"🕹️ Offline AAA Radar","ports":"⚙️ PC Port & Performance",
              "deals":"💸 Deals & PS Plus","drm":"🔓 DRM / Preservation (news only)"}
    groups = {k: [] for k in titles}
    for c in clusters:
        groups[bucket(c[0])].append(c)
    for key in ["batman","franchise","radar","ports","deals","drm"]:
        cs = groups[key]
        if key == "batman" and not cs:
            out.append(f"\n*{titles[key]}*\n• No Batman/Arkham news in the window.")
            continue
        if not cs: continue
        out.append(f"\n*{titles[key]}*")
        for c in cs[:8 if key!="batman" else 12]:
            lead = c[0]
            also = ""
            extra = sorted({x["source"] for x in c[1:]})
            if extra:
                also = f"  _(also: {', '.join(extra[:4])})_"
            tag = "  ⚠️_corroboration_" if lead["tier"] == 3 else ""
            out.append(f"• [{lead['title']}]({lead['link']}) — {lead['source']}{also}{tag}")
    return "\n".join(out)

SECTIONS = ["batman", "franchise", "radar", "ports", "deals", "drm"]
SEC_TITLES = {"batman":"🦇 Batman / Arkham Watch","franchise":"⭐ Priority Franchises",
              "radar":"🕹️ Offline AAA Radar","ports":"⚙️ PC Port & Performance",
              "deals":"💸 Deals & PS Plus","drm":"🔓 DRM / Preservation (news only)"}
SEC_EMOJI = {"batman":"🦇","franchise":"⭐","radar":"🕹️","ports":"⚙️","deals":"💸","drm":"🔓"}

CURATE_SYSTEM = (
    "You are a PC-first, single-player-first gaming editor for a reader who plays OFFLINE AAA story "
    "games on an RTX 5070 Ti (16GB, 1440p). Priorities: Batman/Arkham #1, then Resident Evil/Capcom, "
    "Silent Hill, Remedy (Alan Wake/Control), Spider-Man/Marvel, Hitman/IO/007, Tomb Raider, Ghost of "
    "Tsushima/Yotei, Last of Us, Horizon, Hogwarts, Pragmata, Doom Dark Ages, AC Shadows, Star Wars "
    "Outlaws/Jedi Survivor. You are given a numbered list of story clusters. DO NOT rewrite or invent "
    "anything. Just CLASSIFY each id you consider worth keeping into one section, and write a SHORT "
    "(<=12 word) reason note. DROP off-taste noise: PvP/battle-royale/esports/MMO/live-service, generic "
    "merch/board-game/blu-ray deals, GPU giveaways, unrelated hardware. Sections: "
    "batman, franchise (priority series), radar (other offline single-player AAA), ports (PC "
    "port/perf/DLSS/FSR/stutter/VRAM), deals (game deals/PS Plus), drm (Denuvo/crack/preservation news). "
    'Return ONLY JSON: {"keep":[{"id":N,"section":"...","note":"..."}],"drop":[N,...]}.'
)

def llm_chat(model, system, user, fmt=None, timeout=600):
    payload = {"model": model,
               "messages": [{"role":"system","content":system},{"role":"user","content":user}],
               "stream": False, "options": {"temperature": 0.2, "num_ctx": 8192}}
    if fmt: payload["format"] = fmt
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]

EXPLAIN_SYSTEM = (
    "For each gaming news item, write ONE plain-English sentence (max 22 words) explaining what it is, "
    "based ONLY on the given title and blurb. No hype, no marketing words, no invented facts. If the blurb "
    "is empty, summarize the title plainly. Return ONLY JSON mapping the number to the sentence, "
    'e.g. {"0":"...","1":"..."}.'
)

def explain(items, model):
    """One grounded sentence per kept item, from title+blurb (no hallucination)."""
    if not items:
        return {}
    blocks = []
    for i, it in enumerate(items):
        blurb = (it["lead"]["summary"] or "")[:240]
        blocks.append(f'{i}: TITLE: {it["lead"]["title"]}\nBLURB: {blurb}')
    raw = llm_chat(model, EXPLAIN_SYSTEM, "\n\n".join(blocks), fmt="json")
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {}

def curate(clusters, model, days):
    """Stage 1: LLM classifies ids into sections. Stage 2: LLM explains kept items.
    Links/facts stay deterministic from cluster data. Returns {section: [item,...]}."""
    pool = clusters[:80]
    lines = []
    for i, c in enumerate(pool):
        lead = c[0]
        also = ",".join(sorted({x["source"] for x in c[1:]})[:4])
        lines.append(f"{i}: {lead['title']} [{lead['source']}{(' +'+also) if also else ''}]")
    raw = llm_chat(model, CURATE_SYSTEM,
                   f"Window: last {days} days. Clusters:\n" + "\n".join(lines), fmt="json")
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {"keep": []}

    sections = {k: [] for k in SECTIONS}
    flat = []
    for k in data.get("keep", []):
        try:
            idx = int(k["id"]); sec = k.get("section", "radar")
        except Exception:
            continue
        if sec in sections and 0 <= idx < len(pool):
            c = pool[idx]; lead = c[0]
            item = {"lead": lead, "also": sorted({x["source"] for x in c[1:]}),
                    "note": (k.get("note") or "").strip(), "tier": lead["tier"], "explain": ""}
            sections[sec].append(item); flat.append(item)

    ex = explain(flat, model)
    for i, item in enumerate(flat):
        item["explain"] = (ex.get(str(i)) or item["note"] or "").strip()
    return sections

def render_md(sections, days):
    """Single-document markdown — for the terminal and the archive copy."""
    now = datetime.now(timezone.utc)
    out = [f"🎮 *Deep PC Gaming Radar* — last {days} days "
           f"({(now-timedelta(days=days)).strftime('%b %d')}–{now.strftime('%b %d, %Y')})",
           "_PC-first · single-player · offline-AAA · 1440p/RTX 5070 Ti_"]
    for key in SECTIONS:
        items = sections[key]
        if key == "batman" and not items:
            out.append(f"\n*{SEC_TITLES[key]}*\n• No Batman/Arkham news in the window.")
            continue
        if not items: continue
        out.append(f"\n*{SEC_TITLES[key]}*")
        for it in items[:10]:
            lead = it["lead"]
            also = f"  _(also: {', '.join(it['also'][:4])})_" if it["also"] else ""
            tag = "  ⚠️_corroboration_" if it["tier"] == 3 else ""
            exp = f"\n  {it['explain']}" if it["explain"] else ""
            out.append(f"• [{lead['title']}]({lead['link']}) — {lead['source']}{also}{tag}{exp}")
    return "\n".join(out)

def to_tg_html(md):
    """Convert our simple Markdown (*bold*, _italic_, [t](u)) to Telegram HTML."""
    links = []
    def stash(m):
        links.append((m.group(1), m.group(2))); return f"\x00{len(links)-1}\x00"
    md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", stash, md)
    md = md.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    md = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", md)
    md = re.sub(r"_([^_\n]+)_", r"<i>\1</i>", md)
    def restore(m):
        t, u = links[int(m.group(1))]
        t = t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f'<a href="{u}">{t}</a>'
    return re.sub(r"\x00(\d+)\x00", restore, md)

def split_msgs(text, limit=3800):
    blocks, cur = text.split("\n\n"), ""
    for b in blocks:
        if len(cur) + len(b) + 2 > limit:
            if cur: yield cur
            cur = b
        else:
            cur = (cur + "\n\n" + b) if cur else b
    if cur: yield cur

def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _tg_post(token, chat, text, preview=False):
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": not preview}
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(4):
        try:
            urllib.request.urlopen(req, timeout=30); return True
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited — honor retry_after
                try: wait = json.loads(e.read())["parameters"]["retry_after"]
                except Exception: wait = 3
                time.sleep(wait + 1); continue
            last = e; break  # non-retryable HTTP error (bad request, etc.)
        except Exception as ex:  # transient network (DNS/IPv6/unreachable) — back off and retry
            last = ex; time.sleep(2 * (attempt + 1))
    print(f"# telegram send failed: {last}", file=sys.stderr); return False

def _creds():
    import os
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        print("# TG_BOT_TOKEN / TG_CHAT_ID not set — skipping send", file=sys.stderr)
    return token, chat

def send_telegram(md):
    """Fallback: chunked single document (used by the rules-only path)."""
    token, chat = _creds()
    if not token or not chat: return
    for chunk in split_msgs(to_tg_html(md)):
        _tg_post(token, chat, chunk, preview=False)
        time.sleep(0.5)

def send_telegram_items(sections, days):
    """One message per story — reads like a news feed."""
    token, chat = _creds()
    if not token or not chat: return
    now = datetime.now(timezone.utc)
    rng = f"{(now-timedelta(days=days)).strftime('%b %d')}–{now.strftime('%b %d, %Y')}"
    _tg_post(token, chat,
             f"🎮 <b>Deep PC Gaming Radar</b> — last {days} days ({rng})\n"
             f"<i>PC-first · single-player · offline-AAA · 1440p/RTX 5070 Ti</i>")
    time.sleep(0.6)
    for key in SECTIONS:
        items = sections[key]
        if key == "batman" and not items:
            _tg_post(token, chat, "🦇 <b>Batman / Arkham:</b> no news this week.")
            time.sleep(0.6); continue
        for it in items[:10]:
            lead = it["lead"]
            also = f"  ·  also: {_esc(', '.join(it['also'][:4]))}" if it["also"] else ""
            tag = "  ⚠️ corroboration" if it["tier"] == 3 else ""
            exp = f"\n{_esc(it['explain'])}" if it["explain"] else ""
            url = (lead["link"] or "").replace("&", "&amp;")
            msg = (f'{SEC_EMOJI[key]} <b><a href="{url}">{_esc(lead["title"])}</a></b>'
                   f'{exp}\n<i>{_esc(lead["source"])}</i>{also}{tag}')
            _tg_post(token, chat, msg, preview=True)
            time.sleep(1.0)  # stay under Telegram per-channel rate limits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--model", default=None, help="Ollama model for synthesis; omit for rules-only")
    ap.add_argument("--telegram", action="store_true", help="send to Telegram (env TG_BOT_TOKEN/TG_CHAT_ID)")
    ap.add_argument("--save", metavar="DIR", default=None, help="also write dated copy to DIR/")
    args = ap.parse_args()

    t0 = time.time()
    items, errors = fetch(args.days)
    clusters = cluster(items)
    print(f"# fetched {len(items)} relevant items from {len(FEEDS)} feeds "
          f"-> {len(clusters)} clusters in {time.time()-t0:.1f}s", file=sys.stderr)
    if errors:
        print("# feed errors: " + "; ".join(errors), file=sys.stderr)

    sections = None
    if args.model:
        t1 = time.time()
        sections = curate(clusters, args.model, args.days)
        brief = render_md(sections, args.days)
        print(f"# LLM curate+explain ({args.model}) in {time.time()-t1:.1f}s", file=sys.stderr)
    else:
        brief = render_rules(clusters, args.days)

    print(brief)
    if args.save:
        import os
        os.makedirs(args.save, exist_ok=True)
        fn = os.path.join(args.save, datetime.now().strftime("%Y-%m-%d") + ".md")
        with open(fn, "w") as f:
            f.write(brief + "\n")
        print(f"# saved {fn}", file=sys.stderr)
    if args.telegram:
        if sections is not None:
            send_telegram_items(sections, args.days)
        else:
            send_telegram(brief)

if __name__ == "__main__":
    main()
