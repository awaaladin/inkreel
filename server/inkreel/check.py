"""check_scene: lint a scene for problems a director (human or AI) should fix.

Every finding: {severity: error|warning|info, code, message, t?, hint}. Used by the AI tool, `/lint` and the studio.
"""
from __future__ import annotations

from . import timing
from . import vocab as V
from .store import Store, StoreError

OVERLAP_PX_FRACTION = 0.16      # bodies closer than this * height overlap
MIN_GAP = 0.12                  # two events on one actor closer than this are unreadable
SECS_PER_CHAR = 0.035           # fastest readable speech


def _find(tx, sid: str, scn: str):
    series = tx.read(f"series/{sid}/series.json")
    for eid in series["episodes"]:
        if scn in tx.read(f"series/{sid}/episodes/{eid}/episode.json")["scenes"]:
            return eid, tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json")
    raise StoreError(f"no scene '{scn}'", "list scenes with /scene")


def check_scene(store: Store, sid: str, scn: str) -> list[dict]:
    tx = store.reader()
    _, sc = _find(tx, sid, scn)
    chars = {f[:-5]: tx.read(f"series/{sid}/libraries/characters/{f}") for f in tx.list(f"series/{sid}/libraries/characters")}
    custom = {f[:-5]: tx.read(f"series/{sid}/libraries/actions/{f}") for f in tx.list(f"series/{sid}/libraries/actions")}
    local = sc.get("local_actions", {})
    lib = V.builtin_actions()

    def lookup(n):
        return local.get(n) or custom.get(n) or lib.get(n)

    F: list[dict] = []

    def add(sev, code, msg, t=None, hint=""):
        d = {"severity": sev, "code": code, "message": msg, "hint": hint}
        if t is not None:
            d["t"] = round(t, 2)
        F.append(d)

    dur = timing.scene_duration(sc)
    W = sc.get("width", 1280)

    if not sc["actors"]:
        add("info", "empty_cast", "No characters placed in this scene.", hint="use place to add cast")
    for cid in sc["actors"]:
        if cid not in chars:
            add("error", "missing_character", f"'{cid}' is placed but is not in the series library.", hint="create_character, or remove the actor")

    # ---- per-actor checks
    for cid, a in sc["actors"].items():
        ch = chars.get(cid, {})
        acts = sorted(a["actions"], key=lambda e: e["t"])
        for e in acts:
            df = lookup(e["action"])
            if df is None:
                add("error", "missing_action", f"{cid} uses unknown action '{e['action']}'.", e["t"], "use a library action or define_action it")
                continue
            if df.get("trail") == "weapon" and ch.get("weapon", "none") == "none":
                add("error", "needs_weapon", f"{cid} does '{e['action']}' with no weapon.", e["t"], "give them a weapon or use punch/kick")
        # overlapping actions on one actor (a later non-reaction action cuts the earlier one short)
        for prev, nxt in zip(acts, acts[1:]):
            pdf = lookup(prev["action"]) or {}
            pdur = prev.get("dur") or pdf.get("dur", 0.8)
            if nxt["t"] < prev["t"] + pdur - 0.05 and (pdf.get("mask", "full") == "full") and nxt["action"] != prev["action"]:
                add("warning", "actions_overlap", f"{cid}: '{nxt['action']}' starts at {nxt['t']:.2f}s while '{prev['action']}' runs until {prev['t'] + pdur:.2f}s.",
                    nxt["t"], f"start it at {prev['t'] + pdur:.2f}s or later")
        # unreadable timing: events packed together
        evs = sorted([(e["t"], f"move") for e in a["moves"]] + [(e["t"], e["action"]) for e in acts], key=lambda x: x[0])
        for (t0, n0), (t1, n1) in zip(evs, evs[1:]):
            if 0 < t1 - t0 < MIN_GAP:
                add("warning", "events_too_close", f"{cid}: '{n0}' and '{n1}' are {t1 - t0:.2f}s apart - the viewer will not read both.", t1, "separate them by at least 0.15s")
        # lying down: any action after knockdown/collapse without getup
        down_at = None
        for e in acts:
            df = lookup(e["action"]) or {}
            if down_at is not None and e["action"] not in ("getup",) and df.get("category") in ("attack", "defense", "movement") and e["t"] > down_at + 0.1:
                add("warning", "acts_while_down", f"{cid} does '{e['action']}' while still lying down from t={down_at:.2f}s.", e["t"], "add getup first")
            if df.get("endStance") == "down":
                down_at = e["t"] + (e.get("dur") or df.get("dur", 0.8))
            if e["action"] == "getup":
                down_at = None
        for m in a["moves"]:
            if down_at is not None and m["t"] > down_at + 0.1:
                add("warning", "moves_while_down", f"{cid} moves while lying down.", m["t"], "add getup first")
        # off-screen: stage position
        for m in a["moves"]:
            x = m.get("x")
            if x is not None and (x < -50 or x > W + 50):
                add("warning", "off_stage", f"{cid} moves to x={x:.0f}, outside the set (0..{W:.0f}).", m["t"], "keep inside the scene width or widen the scene")
        if a["x"] < -50 or a["x"] > W + 50:
            add("warning", "off_stage", f"{cid} starts at x={a['x']:.0f}, outside the set.", 0, "")
        # speech readability
        for s in a["says"]:
            need = len(s["text"]) * SECS_PER_CHAR
            if s["dur"] < need:
                add("warning", "speech_too_fast", f"{cid}'s line \"{s['text'][:30]}\" needs {need:.1f}s to read, has {s['dur']:.1f}s.", s["t"], f"dur >= {need:.1f}")
            if s["t"] + s["dur"] > dur + 0.05:
                add("warning", "speech_cut_off", f"{cid}'s line runs past the end of the scene ({dur:.1f}s).", s["t"], "set a longer scene duration")

    # ---- cross-actor checks
    lines = sorted(((s["t"], s["t"] + s["dur"], cid, s["text"]) for cid, a in sc["actors"].items() for s in a["says"]), key=lambda x: x[0])
    for (a0, a1, ca, _), (b0, b1, cb, tb) in zip(lines, lines[1:]):
        if b0 < a1 - 0.05 and ca != cb:
            add("warning", "dialogue_overlap", f"{cb} starts \"{tb[:24]}\" at {b0:.2f}s while {ca} is still speaking until {a1:.2f}s.", b0, f"start at {a1 + 0.2:.2f}s")
        elif b0 < a1 - 0.05:
            add("warning", "dialogue_overlap", f"{ca} has two overlapping lines at {b0:.2f}s.", b0, "")

    ids = list(sc["actors"])
    lk = lambda n: lookup(n)  # noqa: E731
    step = 0.25
    t = 0.0
    flagged: set[tuple[str, str]] = set()
    while t <= dur:
        for i, ca in enumerate(ids):
            for cb in ids[i + 1:]:
                if (ca, cb) in flagged:
                    continue
                try:
                    gap = abs(timing.x_at(sc, lk, ca, t) - timing.x_at(sc, lk, cb, t))
                except KeyError:
                    continue
                h = min(chars.get(ca, {}).get("height", 300), chars.get(cb, {}).get("height", 300))
                if gap < OVERLAP_PX_FRACTION * h:
                    add("warning", "characters_overlap", f"{ca} and {cb} overlap (only {gap:.0f}px apart) at {t:.1f}s.", t, "space them out with a move/backstep")
                    flagged.add((ca, cb))
        t += step

    # ---- attacks: reach at contact
    for cid, a in sc["actors"].items():
        for e in a["actions"]:
            df = lookup(e["action"]) or {}
            if not df.get("hit") or not e.get("target") or e["target"] not in sc["actors"]:
                continue
            d = e.get("dur") or df.get("dur", 0.8)
            tc = e["t"] + d * df["hit"]
            gap = abs(timing.x_at(sc, lk, cid, tc) - timing.x_at(sc, lk, e["target"], tc))
            reach = df.get("reach", 150)
            if gap > reach * 1.45:
                add("error", "out_of_reach", f"{cid}'s {e['action']} at {e['t']:.2f}s contacts at {tc:.2f}s but the target is {gap:.0f}px away (reach ~{reach}px).", tc, "move closer first or use dash_strike")
            elif gap < reach * 0.65:
                add("warning", "too_close", f"{cid}'s {e['action']} contacts at {tc:.2f}s with only {gap:.0f}px between bodies (reach ~{reach}px).", tc, "backstep before the strike")
            # a hit needs a reaction on the defender near the contact frame
            tg = sc["actors"][e["target"]]
            reacts = [r for r in tg["actions"] if abs(r["t"] - tc) < 0.35 and (lookup(r["action"]) or {}).get("category") in ("reaction", "defense")]
            if not reacts:
                add("warning", "no_reaction", f"{cid}'s {e['action']} at {tc:.2f}s has no reaction from {e['target']}.", tc, "use strike, which wires the reaction")

    # ---- camera
    cams = [c for c in sc["camera"] if c["kind"] != "shake"]
    if sc["actors"] and not cams:
        add("info", "no_camera", "No camera direction; it stays on the default wide shot.", hint="add camera set/frame/follow")
    for c in sc["camera"]:
        if c["kind"] == "follow" and c.get("char") not in sc["actors"]:
            add("error", "camera_missing_target", f"camera follows '{c.get('char')}' who is not in the scene.", c["t"])
    if W > 1280 and not any(c["kind"] in ("follow", "frame", "move", "set") and c["t"] > 0 for c in sc["camera"]) and not any(c["kind"] == "follow" for c in sc["camera"]):
        add("info", "wide_set_static_camera", f"Scene is {W:.0f}px wide but the camera never travels; action may leave the frame.", hint="follow or frame the characters")

    # ---- assets
    if sc["background"].get("preset") not in V.BACKGROUNDS and not sc["background"].get("image"):
        add("error", "missing_background", f"Unknown background '{sc['background'].get('preset')}'.", hint=f"one of {V.BACKGROUNDS}")
    for p in sc["props"]:
        if p.get("kind") not in V.PROPS:
            add("error", "missing_prop", f"Unknown prop kind '{p.get('kind')}'.", hint=f"one of {V.PROPS}")
    for cue in sc.get("audio", []):
        if cue.get("asset") and not (store.root / cue["asset"]).exists() and not cue["asset"].startswith("builtin:"):
            add("error", "missing_audio", f"Audio asset '{cue['asset']}' not found.", cue["t"], "import it or pick a built-in sfx")

    if dur > 90:
        add("info", "long_scene", f"Scene is {dur:.0f}s; consider splitting it into shots.", hint="")
    order = {"error": 0, "warning": 1, "info": 2}
    F.sort(key=lambda f: (order[f["severity"]], f.get("t", 0)))
    return F


def summarize(findings: list[dict]) -> str:
    if not findings:
        return "OK: no problems found."
    return "\n".join(f"{f['severity'].upper()} {f['code']}" + (f" @{f['t']}s" if "t" in f else "") + f": {f['message']}" + (f" Fix: {f['hint']}" if f.get("hint") else "") for f in findings)
