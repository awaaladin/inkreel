"""Compact text views of a series for the AI director and the CLI. Bounded size: the focus scene is detailed, everything else is one line."""
from __future__ import annotations

import re

from . import timing
from . import vocab as V
from .store import Store, Tx


def _lookup_factory(tx: Tx, sid: str, scene: dict):
    custom = {f[:-5]: tx.read(f"series/{sid}/libraries/actions/{f}") for f in tx.list(f"series/{sid}/libraries/actions")}
    local = scene.get("local_actions", {})
    lib = V.builtin_actions()
    return lambda n: local.get(n) or custom.get(n) or lib.get(n)


def describe_scene(tx: Tx, sid: str, eid: str, scn: str, max_events: int = 90) -> str:
    sc = tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json")
    lk = _lookup_factory(tx, sid, sc)
    bg = sc["background"]
    lines = [f"SCENE {sc['id']} \"{sc.get('name', '')}\" {bg['preset']}/{bg.get('time', 'day')}{'/' + bg['weather'] if bg.get('weather') else ''} "
             f"dur={timing.scene_duration(sc):.1f}s width={sc.get('width', 1280):.0f} groundY={sc.get('groundY', 570):.0f}"
             + (f" letterbox={sc['letterbox']:.0f}" if sc.get("letterbox") else "")]
    if sc["props"]:
        lines.append("  props: " + ", ".join(f"{p['kind']}@{p['x']:.0f}[{p.get('id', '')}]" for p in sc["props"]))
    ev: list[tuple[float, str]] = []

    def tag(e):
        return f"[{e.get('id', '')}{'*' if e.get('src') == 'user' else ''}{'L' if e.get('lock') else ''}]"

    for cid, a in sc["actors"].items():
        st0 = next((s["stance"] for s in a["stances"] if s["t"] < 0), "idle")
        lines.append(f"  actor {cid}: x={a['x']:.0f} y={a['y']:.0f} facing {'L' if a['facing'] < 0 else 'R'} stance {st0}")
        for m in a["moves"]:
            ev.append((m["t"], f"{cid} {m.get('style', 'walk')} to x{timing.x_at(sc, lk, cid, m['t'] + m['dur']):.0f} ({m['dur']:.1f}s) {tag(m)}"))
        for e in a["actions"]:
            nm = e["action"]
            df = lk(nm) or {}
            extra = f" contact@{e['t'] + (e.get('dur') or df.get('dur', 0.8)) * df['hit']:.2f}" if df.get("hit") else ""
            ev.append((e["t"], f"{cid} ACT {'custom' if nm.startswith('_') else nm}{extra}" + (f" ->{e['target']}" if e.get("target") else "") + f" {tag(e)}"))
        for s in a["says"]:
            ev.append((s["t"], f"{cid} SAY \"{s['text'][:60]}\" ({s['dur']:.1f}s)" + (f" [{s['emotion']}]" if s.get("emotion") else "") + f" {tag(s)}"))
        for e in a["emotes"]:
            ev.append((e["t"], f"{cid} emote {e['emotion']} {tag(e)}"))
        for s in a["stances"]:
            if s["t"] >= 0:
                ev.append((s["t"], f"{cid} stance {s['stance']} {tag(s)}"))
    for f in sc["fx"]:
        ev.append((f["t"], f"fx {f['kind']}" + (f" '{f['text']}'" if f.get("text") else "") + (f" @{f['at_char']}" if f.get("at_char") else "") + f" {tag(f)}"))
    for c in sc["camera"]:
        ev.append((c["t"], f"camera {c['kind']}" + (f" zoom {c['zoom']}" if c.get("zoom") else "") + f" {tag(c)}"))
    for c in sc["captions"]:
        ev.append((c["t"], f"caption [{c['style']}] \"{c['text'][:40]}\" {tag(c)}"))
    ev.sort(key=lambda e: e[0])
    if len(ev) > max_events:
        lines.append(f"  ({len(ev) - max_events} earlier events omitted)")
        ev = ev[-max_events:]
    lines += [f"    {t:5.2f}  {x}" for t, x in ev]
    return "\n".join(lines)


def one_line_scene(sc: dict) -> str:
    bg = sc["background"]
    n = sum(len(a[k]) for a in sc["actors"].values() for k in ("moves", "actions", "says"))
    return f"{sc['id']} \"{sc.get('name', '')}\" {bg['preset']}/{bg.get('time', 'day')} {timing.scene_duration(sc):.1f}s cast={','.join(sc['actors']) or '-'} events={n}"


# ---------------------------------------------------------------- bible retrieval
_WORD = re.compile(r"[a-z0-9']+")


def _chunks(bible: str) -> list[tuple[str, str]]:
    out, head, buf = [], "intro", []
    for line in bible.splitlines():
        if line.startswith("#"):
            if buf:
                out.append((head, "\n".join(buf).strip()))
            head, buf = line.lstrip("# ").strip(), []
        else:
            buf.append(line)
    if buf:
        out.append((head, "\n".join(buf).strip()))
    return [(h, t) for h, t in out if t]


def retrieve(bible: str, notes: list[dict], query: str, budget_chars: int = 3500) -> str:
    """Bounded context: if the bible+notes fit, send everything; otherwise rank sections by keyword overlap (BM25-lite)."""
    docs = [(f"BIBLE / {h}", t) for h, t in _chunks(bible)] + [(f"NOTE / {n['topic']}", n["summary"]) for n in notes]
    total = sum(len(h) + len(t) for h, t in docs)
    if total <= budget_chars:
        return "\n\n".join(f"[{h}]\n{t}" for h, t in docs)
    q = set(_WORD.findall(query.lower()))
    import math
    df: dict[str, int] = {}
    toks = [set(_WORD.findall((h + " " + t).lower())) for h, t in docs]
    for s in toks:
        for w in s:
            df[w] = df.get(w, 0) + 1
    scored = []
    for i, ((h, t), s) in enumerate(zip(docs, toks)):
        score = sum(math.log(1 + len(docs) / df[w]) for w in q & s)
        if h.startswith("BIBLE / ") and h.split("/ ", 1)[1].lower() in ("premise", "cast", "world rules", "look", "intro"):
            score += 0.75  # core sections always rank decently
        scored.append((score, -i, h, t))
    out, used = [], 0
    for score, _, h, t in sorted(scored, reverse=True):
        chunk = f"[{h}]\n{t}"
        if used + len(chunk) > budget_chars:
            continue
        out.append(chunk)
        used += len(chunk)
    return "\n\n".join(out) + f"\n(bible/notes truncated to the most relevant {len(out)} of {len(docs)} sections; ask for more with search_bible)"


def series_context(store: Store, sid: str, focus_episode: str | None, focus_scene: str | None, query: str) -> str:
    tx = store.reader()
    s = tx.read(f"series/{sid}/series.json")
    style = tx.read(f"series/{sid}/style.json")
    bible = tx.read(f"series/{sid}/bible.md", {"_text": ""})["_text"]
    out = [f"SERIES {s['id']} \"{s['title']}\" - {s.get('logline', '')}",
           "STYLE: " + ", ".join(f"{k}={v}" for k, v in style.items() if k in ("line_weight", "boil_fps", "animate_on", "shading", "grain", "handheld", "fps"))]
    out.append("CAST:")
    for f in tx.list(f"series/{sid}/libraries/characters"):
        c = tx.read(f"series/{sid}/libraries/characters/{f}")
        bits = [f"{k}={v}" for k, v in c.items() if k not in ("id", "name", "notes", "views", "rig_type") and v not in (None, False, "")]
        out.append(f"  {c['id']} \"{c['name']}\": " + ", ".join(bits) + (f" | {c['notes']}" if c.get("notes") else ""))
    custom = [f[:-5] for f in tx.list(f"series/{sid}/libraries/actions")]
    if custom:
        out.append("SERIES ACTIONS: " + ", ".join(custom))
    out.append("EPISODES:")
    focus_ep_scene = None
    for eid in s["episodes"]:
        ep = tx.read(f"series/{sid}/episodes/{eid}/episode.json")
        mark = " <focus>" if eid == focus_episode else ""
        out.append(f"  {eid} \"{ep['title']}\" ({len(ep['scenes'])} scenes){mark}" + (f" - {ep['synopsis']}" if ep.get("synopsis") else ""))
        for scn in ep["scenes"]:
            sc = tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json")
            if scn == focus_scene:
                focus_ep_scene = (eid, scn)
            out.append("    " + one_line_scene(sc))
    ctx = "\n".join(out)
    if focus_ep_scene:
        ctx += "\n\nFOCUS " + describe_scene(tx, sid, *focus_ep_scene)
    elif focus_episode:
        ctx += f"\n\n(no scene focused; current episode is '{focus_episode}')"
    ctx += "\n\n" + retrieve(bible, s.get("notes", []), query)
    return ctx
