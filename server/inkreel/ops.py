"""Typed, validated operations: the vocabulary shared by the AI director, the CLI and the studio.

Each op is `fn(ctx, args) -> message`. Failures raise OpError(msg, hint); the text goes back to the model
verbatim so it can correct itself. Ops are atomic (Tx.attempt rolls back a failed op's partial edits).

Provenance/lock rules (enforced here, not in the prompt):
  * every event is created with a stable id, src = who made it, lock = False;
  * src="ai" may not modify or delete an event that is locked or has src="user";
  * src="user" may do anything (the studio unlocks before editing locked events).
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import model as M
from . import timing
from . import vocab as V
from .store import StoreError, Tx, slug as _slug


class OpError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

    def __str__(self):
        base = super().__str__()
        return f"{base} Hint: {self.hint}" if self.hint else base


def slug(s) -> str:
    try:
        return _slug(s)
    except StoreError as e:
        raise OpError(str(e))


# --------------------------------------------------------------------------- arg helpers
def color(v, field="color"):
    if not isinstance(v, str):
        raise OpError(f"{field} must be a hex colour string", "e.g. '#c8553d'")
    v = v.strip()
    if v.lower() in V.NAMED_COLORS:
        return V.NAMED_COLORS[v.lower()]
    if not v.startswith("#") and re.fullmatch(r"[0-9a-fA-F]{6}", v):
        v = "#" + v
    if not V.HEX.match(v):
        raise OpError(f"{field} must be a hex colour like '#c8553d' (got {v!r})", "or a name: " + ", ".join(sorted(V.NAMED_COLORS)))
    return v


def num(a, key, default=None, lo=None, hi=None, required=False):
    v = a.get(key, default)
    if v is None:
        if required:
            raise OpError(f"'{key}' is required")
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"'{key}' must be a number (got {v!r})")
    if v != v or v in (float("inf"), float("-inf")):
        raise OpError(f"'{key}' must be a finite number")
    if lo is not None and v < lo:
        raise OpError(f"'{key}' must be >= {lo} (got {v})")
    if hi is not None and v > hi:
        raise OpError(f"'{key}' must be <= {hi} (got {v})")
    return v


def choice(a, key, options, default=None, required=False):
    v = a.get(key, default)
    if v is None:
        if required:
            raise OpError(f"'{key}' is required", f"one of {list(options)}")
        return None
    if v not in options:
        raise OpError(f"'{key}' must be one of {list(options)} (got {v!r})")
    return v


def r2(x):
    return round(float(x), 3)


# --------------------------------------------------------------------------- context
class OpCtx:
    def __init__(self, tx: Tx, sid: str, eid: str | None = None, src: str = "ai"):
        self.tx, self.sid, self.eid, self.src = tx, sid, eid, src
        self.touched_scene_rels: set[str] = set()

    # ---- paths
    @property
    def series_rel(self):
        return f"series/{self.sid}/series.json"

    def episode_rel(self, eid):
        return f"series/{self.sid}/episodes/{eid}/episode.json"

    def char_rel(self, cid):
        return f"series/{self.sid}/libraries/characters/{cid}.json"

    def action_rel(self, name):
        return f"series/{self.sid}/libraries/actions/{name}.json"

    # ---- series level
    def series(self) -> dict:
        return self.tx.mut(self.series_rel)

    def style(self) -> dict:
        return self.tx.mut(f"series/{self.sid}/style.json", M.Style().model_dump())

    def characters(self) -> dict[str, dict]:
        out = {}
        for fn in self.tx.list(f"series/{self.sid}/libraries/characters"):
            out[fn[:-5]] = self.tx.read(self.char_rel(fn[:-5]))
        return out

    def get_char(self, cid) -> str:
        cid = slug(cid)
        if not self.tx.exists(self.char_rel(cid)):
            have = [f[:-5] for f in self.tx.list(f"series/{self.sid}/libraries/characters")]
            raise OpError(f"no character '{cid}'", f"existing: {have or 'none'}; call create_character first")
        return cid

    def custom_actions(self) -> dict[str, dict]:
        return {f[:-5]: self.tx.read(self.action_rel(f[:-5])) for f in self.tx.list(f"series/{self.sid}/libraries/actions")}

    def lookup(self, scene: dict | None = None) -> timing.ActionLookup:
        series_actions = self.custom_actions()
        local = (scene or {}).get("local_actions", {})
        lib = V.builtin_actions()
        return lambda name: local.get(name) or series_actions.get(name) or lib.get(name)

    def action_def(self, scene: dict, name: str) -> dict:
        df = self.lookup(scene)(name)
        if df is None:
            names = sorted(set(V.builtin_actions()) | set(self.custom_actions()))
            raise OpError(f"unknown action '{name}'", f"available: {names}")
        return df

    # ---- episodes / scenes
    def episodes(self) -> list[str]:
        return list(self.series().get("episodes", []))

    def find_scene(self, scn) -> tuple[str, dict, str]:
        """-> (rel path, scene dict (mutable), episode id)"""
        sid_ = slug(scn) if scn else None
        for eid in self.episodes():
            ep = self.tx.read(self.episode_rel(eid))
            if sid_ in ep.get("scenes", []):
                rel = f"series/{self.sid}/episodes/{eid}/scenes/{sid_}.json"
                self.touched_scene_rels.add(rel)
                self.tx.touch(rel)
                if rel not in self.tx.touched_scenes:
                    self.tx.touched_scenes.append(rel)
                return rel, self.tx.read(rel), eid
        have = [s for e in self.episodes() for s in self.tx.read(self.episode_rel(e)).get("scenes", [])]
        raise OpError(f"no scene '{sid_}'", f"existing scenes: {have or 'none'}; use create_scene first")

    def scene(self, scn) -> dict:
        return self.find_scene(scn)[1]

    # ---- events
    def new_event(self, scene: dict, prefix: str, **fields) -> dict:
        n = scene.get("next_event", 1)
        scene["next_event"] = n + 1
        e = {"id": f"{prefix}{n}", "src": self.src, "lock": False}
        e.update(fields)
        return e

    def guard(self, ev: dict, what: str = "event"):
        """AI must not touch locked or user-authored events."""
        if self.src == "ai" and (ev.get("lock") or ev.get("src") == "user"):
            why = "locked" if ev.get("lock") else "authored by the user"
            raise OpError(f"{what} {ev.get('id', '?')} is {why}", "leave it alone, add a new event instead, or ask the user to unlock it")


def get_actor(scene, cid):
    cid = slug(cid)
    if cid not in scene["actors"]:
        raise OpError(f"character '{cid}' is not placed in scene '{scene['id']}'",
                      f"call place first. Placed: {list(scene['actors'])}")
    return scene["actors"][cid]


# --------------------------------------------------------------------------- registry
OPS: dict[str, Callable] = {}
TOOLS: list[dict] = []
GROUPS: dict[str, str] = {}


def op(name, description, props, required=(), group="scene"):
    def deco(fn):
        OPS[name] = fn
        GROUPS[name] = group
        TOOLS.append({"name": name, "description": description,
                      "input_schema": {"type": "object", "properties": props, "required": list(required)}})
        return fn
    return deco


T_ = {"type": "number", "description": "start time in seconds from the start of the scene"}
SCENE_ = {"type": "string", "description": "scene id"}
CHAR_ = {"type": "string", "description": "character id"}
HEXC = {"type": "string", "description": "hex colour like #c8553d"}


def apply_op(ctx: OpCtx, name: str, args: dict) -> str:
    """Run one op. Raises OpError on failure; validates every touched scene against the model afterwards."""
    fn = OPS.get(name)
    if not fn:
        raise OpError(f"unknown tool '{name}'", f"available: {sorted(OPS)}")
    ctx.touched_scene_rels = set()
    msg = fn(ctx, dict(args or {}))
    for rel in ctx.touched_scene_rels:
        sc = ctx.tx.cache.get(rel)
        if sc is None:
            continue
        try:
            M.Scene.model_validate(sc)
        except Exception as e:  # pydantic.ValidationError
            raise OpError(f"scene '{sc.get('id')}' would be invalid after {name}: {str(e).splitlines()[0:3]}", "check field types and ranges")
    return msg


# --------------------------------------------------------------------------- management ops
@op("set_series", "Set the series title, logline, fps or frame size.",
    {"title": {"type": "string"}, "logline": {"type": "string"}, "fps": {"type": "number", "description": "12-60"}}, group="manage")
def set_series(ctx, a):
    s = ctx.series()
    if a.get("title"):
        s["title"] = str(a["title"])[:120]
    if a.get("logline") is not None:
        s["logline"] = str(a["logline"])[:600]
    if a.get("fps") is not None:
        ctx.style()["fps"] = int(num(a, "fps", lo=8, hi=60))
    return f"series: {s['title']} @ {ctx.style()['fps']}fps"


@op("set_style", "Tune the series' hand-drawn look (applies to every scene). Fields: line_weight, boil_fps, wobble, animate_on (ones|twos|auto), grain, vignette, shading (flat|hatch|crosshatch), handheld, overlap, hit_stop_frames.",
    {k: {"type": "number" if k not in ("animate_on", "shading") else "string"} for k in
     ("line_weight", "boil_fps", "wobble", "animate_on", "grain", "vignette", "shading", "handheld", "overlap", "hit_stop_frames")}, group="manage")
def set_style(ctx, a):
    st = ctx.style()
    changed = []
    for k, v in a.items():
        if k not in M.Style.model_fields:
            raise OpError(f"unknown style field '{k}'", f"fields: {list(M.Style.model_fields)}")
        st[k] = v
        changed.append(k)
    try:
        M.Style.model_validate(st)
    except Exception as e:
        raise OpError(f"invalid style: {str(e).splitlines()[:3]}")
    return f"style updated: {', '.join(changed) or 'nothing'}"


@op("set_bible", "Write to the series bible (markdown the director sees every turn: characters, world rules, art style, locations, story so far). "
    "mode 'append' adds a section; 'replace_section' replaces the section with the same heading; 'replace_all' rewrites everything.",
    {"heading": {"type": "string"}, "text": {"type": "string"}, "mode": {"type": "string", "enum": ["append", "replace_section", "replace_all"]}},
    ["text"], group="manage")
def set_bible(ctx, a):
    rel = f"series/{ctx.sid}/bible.md"
    cur = ctx.tx.read(rel, {"_text": ""})["_text"] if ctx.tx.exists(rel) else ""
    mode = choice(a, "mode", ["append", "replace_section", "replace_all"], "append")
    text, head = str(a["text"]).strip(), (a.get("heading") or "").strip()
    block = f"## {head}\n{text}\n" if head else text + "\n"
    if mode == "replace_all":
        new = block
    elif mode == "replace_section" and head:
        pat = re.compile(rf"(^## {re.escape(head)}\n.*?)(?=^## |\Z)", re.S | re.M)
        new = pat.sub(block + "\n", cur) if pat.search(cur) else cur.rstrip() + "\n\n" + block
    else:
        new = cur.rstrip() + ("\n\n" if cur.strip() else "") + block
    ctx.tx.write(rel, {"_text": new})
    return f"bible updated ({mode}{' ' + head if head else ''}, {len(new)} chars)"


@op("create_episode", "Create or update an episode of the series (ordered list of scenes). Focus moves to it.",
    {"id": {"type": "string"}, "title": {"type": "string"}, "synopsis": {"type": "string"}, "number": {"type": "number"}}, ["id"], group="manage")
def create_episode(ctx, a):
    eid = slug(a["id"])
    s = ctx.series()
    rel = ctx.episode_rel(eid)
    new = eid not in s["episodes"]
    ep = ctx.tx.mut(rel, None) if not new else None
    if ep is None:
        ep = M.Episode(id=eid, title=a.get("title") or eid.replace("_", " ").title(), number=len(s["episodes"]) + 1).model_dump()
        s["episodes"].append(eid)
    if a.get("title"):
        ep["title"] = str(a["title"])[:120]
    if a.get("synopsis") is not None:
        ep["synopsis"] = str(a["synopsis"])[:1500]
    if a.get("number") is not None:
        ep["number"] = int(num(a, "number", lo=0, hi=9999))
    ctx.tx.write(rel, ep)
    ctx.eid = eid
    return f"episode '{eid}' {'created' if new else 'updated'}"


@op("create_character",
    "Create or update a character in the SERIES library (call again with the same id to change it). It then looks identical in every scene of every episode. "
    "Characters are hand-drawn jointed cut-out puppets. Heights are px (300 = normal adult in a 1280x720 frame; 220 = child, 360 = giant).",
    {"id": {"type": "string", "description": "short id, e.g. 'kabi'"}, "name": {"type": "string"},
     "height": {"type": "number", "description": "120-560, default 300"},
     "skin": HEXC, "hair": HEXC, "hair_style": {"type": "string", "enum": V.HAIR},
     "top": HEXC, "bottom": HEXC, "accent": {**HEXC, "description": "boots/belt/headband/trim colour"},
     "outfit": {"type": "string", "enum": V.OUTFITS, "description": "tee=short sleeves, long=long sleeves, tank/bare=bare arms"},
     "legs": {"type": "string", "enum": V.LEGS}, "build": {"type": "string", "enum": V.BUILDS},
     "weapon": {"type": "string", "enum": V.WEAPONS, "description": "held in the front hand; needed for slash/thrust attacks"},
     "weapon_color": HEXC, "boots": HEXC, "barefoot": {"type": "boolean"},
     "headband": {"type": "boolean"}, "beard": {"type": "boolean"}, "glasses": {"type": "boolean"},
     "scarf": {"type": "boolean"}, "scar": {"type": "boolean"},
     "head_scale": {"type": "number", "description": "0.6-1.8; bigger = more cartoony"},
     "voice_id": {"type": "string"},
     "notes": {"type": "string", "description": "personality / backstory / design notes"}},
    ["id"], group="characters")
def create_character(ctx, a):
    cid = slug(a["id"])
    rel = ctx.char_rel(cid)
    new = not ctx.tx.exists(rel)
    ch = ctx.tx.mut(rel) if not new else {"id": cid}
    for k in ("skin", "hair", "top", "bottom", "accent", "weapon_color", "boots"):
        if a.get(k) is not None:
            ch[k] = color(a[k], k)
    for k, opts in (("hair_style", V.HAIR), ("outfit", V.OUTFITS), ("legs", V.LEGS), ("build", V.BUILDS), ("weapon", V.WEAPONS)):
        v = choice(a, k, opts)
        if v:
            ch[k] = v
    for k in ("headband", "beard", "glasses", "scarf", "scar", "barefoot"):
        if a.get(k) is not None:
            ch[k] = bool(a[k])
    if a.get("height") is not None:
        ch["height"] = num(a, "height", lo=120, hi=560)
    if a.get("head_scale") is not None:
        ch["head_scale"] = num(a, "head_scale", lo=0.6, hi=1.8)
    for k in ("name", "notes", "voice_id"):
        if a.get(k):
            ch[k] = str(a[k])[:400]
    ch.setdefault("name", cid.title())
    try:
        M.Character.model_validate(ch)
    except Exception as e:
        raise OpError(f"invalid character: {str(e).splitlines()[:3]}")
    ctx.tx.write(rel, ch)
    return f"character '{cid}' {'created' if new else 'updated'}"


@op("create_scene",
    "Create or update a scene (a shot / location) in an episode. Scenes play in episode order. The camera shows a 1280x720 view; "
    "world x runs 0..width, y is vertical with the ground line at ground_y (default 570). "
    "Use a wider `width` (up to 4000) for tracking shots across a long set.",
    {"id": {"type": "string"}, "name": {"type": "string"}, "episode": {"type": "string", "description": "episode id (default: current)"},
     "background": {"type": "string", "enum": V.BACKGROUNDS}, "time": {"type": "string", "enum": V.TIMES, "description": "time of day / mood palette"},
     "weather": {"type": "string", "enum": ["clear", "rain"]},
     "palette": {"type": "object", "description": "optional colour overrides: skyTop, skyBot, ground, ground2, far, mid, water, water2, stone, wall, tint (css rgba)"},
     "width": {"type": "number", "description": "world width, 1280-4000 (default 1280)"},
     "ground_y": {"type": "number", "description": "ground line y (default 570)"},
     "duration": {"type": "number", "description": "force scene length in seconds (default: auto, last event + 0.6s)"},
     "letterbox": {"type": "number", "description": "cinematic bar height in px (0-120)"},
     "transition_in": {"type": "string", "enum": ["cut", "fade"]}, "transition_out": {"type": "string", "enum": ["cut", "fade"]},
     "transition_color": {"type": "string", "enum": ["black", "white"]}, "transition_dur": {"type": "number"}},
    ["id"], group="scene")
def create_scene(ctx, a):
    scn = slug(a["id"])
    existing = None
    for eid in ctx.episodes():
        if scn in ctx.tx.read(ctx.episode_rel(eid)).get("scenes", []):
            existing = eid
    eid = existing or (slug(a["episode"]) if a.get("episode") else ctx.eid)
    if not eid:
        eps = ctx.episodes()
        if len(eps) == 1:
            eid = eps[0]
        else:
            raise OpError("no episode selected", f"pass episode=<id>; existing: {eps or 'none (call create_episode first)'}")
    if eid not in ctx.episodes():
        raise OpError(f"no episode '{eid}'", f"existing: {ctx.episodes() or 'none'}; call create_episode first")
    ep = ctx.tx.mut(ctx.episode_rel(eid))
    rel = f"series/{ctx.sid}/episodes/{eid}/scenes/{scn}.json"
    new = scn not in ep["scenes"]
    sc = ctx.tx.mut(rel) if not new else M.Scene(id=scn, name=scn.replace("_", " ").title()).model_dump(by_alias=True, exclude_none=True)
    if new:
        ep["scenes"].append(scn)
    ctx.eid = eid
    if a.get("name"):
        sc["name"] = str(a["name"])[:100]
    bg = sc["background"]
    if a.get("background"):
        bg["preset"] = choice(a, "background", V.BACKGROUNDS)
    if a.get("time"):
        bg["time"] = choice(a, "time", V.TIMES)
    if a.get("weather"):
        bg["weather"] = choice(a, "weather", ["clear", "rain"])
    if isinstance(a.get("palette"), dict):
        pal = bg.setdefault("palette", {})
        for k, v in a["palette"].items():
            pal[k] = v if k == "tint" else color(v, f"palette.{k}")
    if a.get("width") is not None:
        sc["width"] = num(a, "width", lo=1280, hi=4000)
    if a.get("ground_y") is not None:
        sc["groundY"] = num(a, "ground_y", lo=380, hi=700)
    if a.get("duration") is not None:
        sc["duration"] = num(a, "duration", lo=1, hi=300)
    if a.get("letterbox") is not None:
        sc["letterbox"] = num(a, "letterbox", lo=0, hi=140)
    tr = sc.setdefault("transition", {}) or {}
    sc["transition"] = tr
    if a.get("transition_in"):
        tr["in"] = a["transition_in"]
    if a.get("transition_out"):
        tr["out"] = a["transition_out"]
    if a.get("transition_color"):
        tr["color"] = a["transition_color"]
    if a.get("transition_dur") is not None:
        tr["dur"] = num(a, "transition_dur", lo=0.1, hi=3)
    ctx.tx.write(rel, sc)
    ctx.touched_scene_rels.add(rel)
    ctx.tx.touched_scenes.append(rel)
    return f"scene '{scn}' {'created' if new else 'updated'} in episode '{eid}' ({bg['preset']}/{bg.get('time', 'day')}, width {sc['width']}, ground y {sc['groundY']})"


@op("add_prop",
    "Add a set-dressing prop to a scene. x is world position; y is depth offset from the ground line (+ = nearer camera, drawn lower). "
    f"Kinds: {', '.join(V.PROPS)}.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": V.PROPS}, "x": {"type": "number"}, "y": {"type": "number"},
     "scale": {"type": "number"}, "flip": {"type": "boolean"}, "layer": {"type": "string", "enum": ["back", "front"], "description": "front = drawn over characters"},
     "color": HEXC}, ["scene", "kind", "x"])
def add_prop(ctx, a):
    sc = ctx.scene(a.get("scene"))
    p = ctx.new_event(sc, "p", kind=choice(a, "kind", V.PROPS, required=True), x=num(a, "x", required=True))
    if a.get("y") is not None:
        p["y"] = num(a, "y", lo=-400, hi=400)
    if a.get("scale") is not None:
        p["scale"] = num(a, "scale", lo=0.2, hi=4)
    if a.get("flip"):
        p["flip"] = True
    if a.get("layer") == "front":
        p["layer"] = "front"
    if a.get("color"):
        p["color"] = color(a["color"])
    sc["props"].append(p)
    return f"prop {p['kind']} ({p['id']}) at x={p['x']} ({len(sc['props'])} props in scene)"


@op("place",
    "Place a character in a scene at the scene start (or re-place it). x = world x of the feet, y = depth offset from the ground line. "
    "facing says which way they look at the start. A character must be placed before it can move, act or speak.",
    {"scene": SCENE_, "char": CHAR_, "x": {"type": "number"}, "y": {"type": "number"},
     "facing": {"type": "string", "enum": ["left", "right"]},
     "stance": {"type": "string", "description": "starting stance, default idle (" + ", ".join(V.stances()) + ")"}},
    ["scene", "char", "x"])
def place(ctx, a):
    sc = ctx.scene(a.get("scene"))
    cid = ctx.get_char(a.get("char"))
    st = choice(a, "stance", V.stances(), "idle")
    old = sc["actors"].get(cid)
    if old:
        for track in ("moves", "actions", "says", "emotes", "faces", "stances"):
            for e in old.get(track, []):
                ctx.guard(e, f"{track} event")
    act = {"x": num(a, "x", required=True), "y": num(a, "y", 0, lo=-400, hi=400),
           "facing": -1 if a.get("facing") == "left" else 1,
           "moves": [], "actions": [], "stances": [], "emotes": [], "says": [], "faces": []}
    if old:  # re-place keeps existing timeline
        for track in ("moves", "actions", "says", "emotes", "faces", "stances"):
            act[track] = old.get(track, [])
    if st != "idle":
        act["stances"] = [s for s in act["stances"] if s["t"] >= 0] + [ctx.new_event(sc, "s", t=-1, stance=st, blend=0.01)]
    sc["actors"][cid] = act
    return f"placed {cid} at x={act['x']} facing {'left' if act['facing'] < 0 else 'right'} in {st}"


@op("stance",
    "Change a character's base stance at time t (blends over `blend` seconds). Stances: " + ", ".join(V.stances()) + ". "
    "'fight' = guarded combat stance; 'down' = lying on back; 'kneel'; 'crouch'; 'tired'; 'arms_crossed'.",
    {"scene": SCENE_, "char": CHAR_, "stance": {"type": "string"}, "t": T_, "blend": {"type": "number"}},
    ["scene", "char", "stance", "t"])
def stance(ctx, a):
    sc = ctx.scene(a.get("scene"))
    ac = get_actor(sc, a.get("char"))
    t = num(a, "t", required=True, lo=0)
    ac["stances"].append(ctx.new_event(sc, "s", t=t, stance=choice(a, "stance", V.stances(), required=True), blend=num(a, "blend", 0.3, lo=0, hi=3)))
    return f"{a['char']} -> {a['stance']} at t={r2(t)}"


@op("move",
    "Move a character along the ground to world x (and optionally depth y offset). Legs animate automatically (walk/run/sneak), "
    "'slide' glides without stepping, 'backstep' retreats while still facing the opponent. If dur is omitted it is computed from the "
    "distance and style (walk 150px/s, run 380px/s). The character turns to face the direction of travel.",
    {"scene": SCENE_, "char": CHAR_, "to_x": {"type": "number"}, "to_y": {"type": "number"}, "t": T_,
     "dur": {"type": "number"}, "style": {"type": "string", "enum": V.MOVE_STYLES}, "ease": {"type": "string", "enum": V.EASES}},
    ["scene", "char", "to_x", "t"])
def move(ctx, a):
    sc = ctx.scene(a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    lk = ctx.lookup(sc)
    t = num(a, "t", required=True, lo=0)
    style = choice(a, "style", V.MOVE_STYLES, "walk")
    x0 = timing.x_at(sc, lk, cid, t)
    tx = num(a, "to_x", required=True)
    dist = abs(tx - x0)
    dur = num(a, "dur", lo=0.1, hi=60) or max(0.3, dist / V.MOVE_SPEED[style])
    offset = timing.x_at(sc, lk, cid, t + dur) - timing.base_x(ac, t + dur)
    m = ctx.new_event(sc, "m", t=t, x=tx - offset, dur=dur, style=style, ease=choice(a, "ease", V.EASES, "smooth"))
    if a.get("to_y") is not None:
        m["y"] = num(a, "to_y", lo=-400, hi=400)
    ac["moves"].append(m)
    msg = f"{cid} {style} x{r2(x0)} -> x{r2(tx)} over t={r2(t)}..{r2(t + dur)}"
    if dist > 1 and dur and dist / dur > V.MOVE_SPEED["run"] * 1.6 and style in ("walk", "run", "sneak"):
        msg += " (WARNING: very fast for this gait; use slide or a longer dur)"
    return msg


def _reach_warning(sc, lk, atk, dfn, act_def, t_contact):
    reach = act_def.get("reach")
    if not reach:
        return ""
    gap = abs(timing.x_at(sc, lk, dfn, t_contact) - timing.x_at(sc, lk, atk, t_contact))
    if gap > reach * 1.45:
        return (f" WARNING: at contact they are {int(gap)}px apart but this attack wants ~{reach}px - it will visibly miss. "
                f"Add a `move` so they close in first (or use dash_strike).")
    if gap < reach * 0.65:
        return (f" WARNING: at contact they are only {int(gap)}px apart (this attack wants ~{reach}px) - the bodies will overlap. "
                f"Space them out with a `move` (backstep) before this strike.")
    return ""


@op("act",
    "Perform a library action (a pre-animated move) at time t. Attacks: punch, hook, uppercut, kick, slash_down, slash_up, thrust, dash_strike. "
    "Defense: block, dodge, duck. Reactions: hit_light, hit_heavy, hit_knockdown (ends lying down - follow with getup), stagger, collapse, surprised. "
    "Movement: jump, backflip, getup. Acting: gesture, point, shrug, nod, wave, think, laugh, cheer, victory, taunt, power_up, bow. "
    "For a full attack-and-reaction exchange prefer the `strike` tool, which wires everything together. "
    "Pass `target` to make the character face another character as the action starts.",
    {"scene": SCENE_, "char": CHAR_, "action": {"type": "string"}, "t": T_,
     "dur": {"type": "number", "description": "override action length (seconds)"},
     "intensity": {"type": "number", "description": "0.3-1.6 scales how big the pose is (default 1)"},
     "dx": {"type": "number", "description": "override travel in px along facing direction (negative = backward)"},
     "target": {"type": "string", "description": "character id to face"}},
    ["scene", "char", "action", "t"])
def act(ctx, a):
    sc = ctx.scene(a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    name = a.get("action")
    df = ctx.action_def(sc, name)
    t = num(a, "t", required=True, lo=0)
    ch = ctx.tx.read(ctx.char_rel(cid))
    if df.get("trail") == "weapon" and ch.get("weapon", "none") == "none":
        raise OpError(f"'{name}' needs a weapon but {cid} has none",
                      "call create_character with weapon set (sword, katana, greatblade, spear, staff) or use punch/kick")
    ev = ctx.new_event(sc, "a", t=t, action=name)
    if a.get("dur") is not None:
        ev["dur"] = num(a, "dur", lo=0.1, hi=30)
    if a.get("intensity") is not None:
        ev["intensity"] = num(a, "intensity", lo=0.1, hi=2.5)
    if a.get("dx") is not None:
        ev["dx"] = num(a, "dx", lo=-800, hi=800)
    if a.get("target"):
        tg = slug(a["target"])
        get_actor(sc, tg)
        ev["target"] = tg
    ac["actions"].append(ev)
    dur = ev.get("dur") or df.get("dur", 0.8)
    msg = f"{cid} {name} t={r2(t)}..{r2(t + dur)}"
    if df.get("hit"):
        msg += f" (contact at t={r2(t + dur * df['hit'])})"
    if df.get("endStance"):
        msg += f"; ends in '{df['endStance']}' stance"
    return msg


@op("strike",
    "CHOREOGRAPHY MACRO for one attack exchange: schedules the attacker's attack, the defender's reaction at the exact contact frame, "
    "an impact burst, camera shake, comic sound-text and dust (scaled by power). result='hit' (defender reacts), 'block' (guard + sparks) or 'dodge' (attack whiffs). "
    "Returns timing (contact time and when both fighters are free again) so you can chain the next exchange. "
    "Heavy/knockdown hits leave the defender lying down; schedule `act getup` later. Place fighters about the attack's reach apart (punch ~130px, kick ~150, slash ~190, thrust ~230).",
    {"scene": SCENE_, "attacker": CHAR_, "defender": CHAR_,
     "attack": {"type": "string", "description": "punch, hook, uppercut, kick, slash_down, slash_up, thrust, dash_strike"},
     "t": {**T_, "description": "when the attacker starts the wind-up"},
     "result": {"type": "string", "enum": ["hit", "block", "dodge"]},
     "power": {"type": "string", "enum": list(V.POWER), "description": "how hard a hit lands (default medium)"},
     "dur": {"type": "number", "description": "override attack length"},
     "sfx": {"type": "string", "description": "custom sound text e.g. 'KRAK!' (or empty string for none)"},
     "effects": {"type": "boolean", "description": "set false to skip impact/shake/sfx (default true)"}},
    ["scene", "attacker", "defender", "attack", "t"], group="choreo")
def strike(ctx, a):
    sc = ctx.scene(a.get("scene"))
    lk = ctx.lookup(sc)
    atk, dfn = slug(a.get("attacker", "")), slug(a.get("defender", ""))
    if atk == dfn:
        raise OpError("attacker and defender must differ")
    get_actor(sc, atk)
    get_actor(sc, dfn)
    t = num(a, "t", required=True, lo=0)
    name = a.get("attack")
    adef = ctx.action_def(sc, name)
    if not adef.get("hit"):
        attacks = [k for k, v in {**V.builtin_actions(), **ctx.custom_actions()}.items() if v.get("hit")]
        raise OpError(f"'{name}' is not an attack with a contact frame", "use: " + ", ".join(attacks))
    ach = ctx.tx.read(ctx.char_rel(atk))
    if adef.get("trail") == "weapon" and ach.get("weapon", "none") == "none":
        raise OpError(f"'{name}' needs a weapon but {atk} has none", "give them a weapon with create_character or use punch/kick")
    result = choice(a, "result", ["hit", "block", "dodge"], "hit")
    power = choice(a, "power", list(V.POWER), "medium")
    P = V.POWER[power]
    dur = num(a, "dur", lo=0.2, hi=5) or adef["dur"]
    tc = t + dur * adef["hit"]
    fx_on = a.get("effects", True)
    atk_ev = ctx.new_event(sc, "a", t=t, action=name, target=dfn)
    if a.get("dur") is not None:
        atk_ev["dur"] = dur
    sc["actors"][atk]["actions"].append(atk_ev)
    warn = _reach_warning(sc, lk, atk, dfn, adef, tc)
    dsc = sc["actors"][dfn]
    n = len(sc["fx"])
    sfx = a.get("sfx")
    texts = P["sfx"]
    end_def = tc
    B = V.builtin_actions()
    ex = lambda **k: ctx.new_event(sc, "x", **k)  # noqa: E731

    if result == "hit":
        rdur = B[P["react"]]["dur"]
        ev = ctx.new_event(sc, "a", t=r2(tc), action=P["react"], target=atk)
        if power == "heavy":
            ev["intensity"], ev["dx"] = 1.2, -140
        dsc["actions"].append(ev)
        end_def = tc + rdur
        if fx_on:
            part = "head" if name == "uppercut" else "chest"
            sc["fx"].append(ex(kind="impact", t=r2(tc), dur=0.42, at_char=dfn, part=part, size=P["size"]))
            sc["camera"].append(ex(kind="shake", t=r2(tc), dur=0.2 + P["amp"] * 0.012, amp=P["amp"]))
            if sfx != "":
                away = 1 if timing.x_at(sc, lk, dfn, tc) >= timing.x_at(sc, lk, atk, tc) else -1
                sc["fx"].append(ex(kind="sfx_text", t=r2(tc + 0.02), dur=0.75, text=sfx or texts[n % len(texts)], at_char=dfn, part="chest",
                                   oy=-70 - (n % 2) * 30, ox=away * (80 + P["size"] * 0.7), size=0.7 + P["size"] / 220, angle=(-10 if n % 2 else 8) * away))
            if P["flash"]:
                sc["fx"].append(ex(kind="flash", t=r2(tc), dur=0.14, intensity=P["flash"]))
            if P["dust"]:
                sc["fx"].append(ex(kind="dust", t=r2(tc + 0.1), dur=0.7, at_char=dfn, part="feet", size=38, count=7))
            if power == "knockdown":
                sc["fx"].append(ex(kind="ring", t=r2(tc), dur=0.5, at_char=dfn, part="feet", size=200, ground=True))
    elif result == "block":
        bdef = B["block"]
        dsc["actions"].append(ctx.new_event(sc, "a", t=r2(max(0, tc - 0.25)), action="block", target=atk))
        end_def = tc - 0.25 + bdef["dur"]
        if fx_on:
            sc["fx"].append(ex(kind="sparks", t=r2(tc), dur=0.4, at_char=dfn, part="hand_front", size=110, count=16))
            sc["camera"].append(ex(kind="shake", t=r2(tc), dur=0.18, amp=6))
            if sfx != "":
                has_w = ach.get("weapon", "none") != "none"
                sc["fx"].append(ex(kind="sfx_text", t=r2(tc + 0.02), dur=0.6, text=sfx or ("CLANG!" if has_w else "THUD!"), at_char=dfn, part="chest", oy=-90,
                                   ox=110 * (1 if timing.x_at(sc, lk, dfn, tc) >= timing.x_at(sc, lk, atk, tc) else -1), size=0.9, angle=-6, color="#ffd23f"))
    else:
        ddef = B["dodge"]
        dsc["actions"].append(ctx.new_event(sc, "a", t=r2(max(0, tc - 0.3)), action="dodge", target=atk))
        end_def = tc - 0.3 + ddef["dur"]
        if fx_on and sfx != "":
            sc["fx"].append(ex(kind="sfx_text", t=r2(tc), dur=0.5, text=sfx or "WHOOSH!", at_char=atk, part="hand_front", oy=-90, size=0.7, angle=-4, color="#ffffff"))
    return (f"{atk} {name} -> {dfn} {result}{'/' + power if result == 'hit' else ''}: attack t={r2(t)}..{r2(t + dur)}, "
            f"contact t={r2(tc)}, defender free at t={r2(end_def)}" + (" (lying down; needs getup)" if result == 'hit' and power == 'knockdown' else "") + warn)


def _check_keys(keys):
    if not isinstance(keys, list) or len(keys) < 2:
        raise OpError("keys must be a list of at least 2 keyframes", "each {t: 0..1, pose: {joint: degrees}, ease?}")
    out = []
    for k in keys:
        if not isinstance(k, dict):
            raise OpError("each key must be an object")
        pose = k.get("pose", {})
        if isinstance(pose, str):
            if pose not in V.stances():
                raise OpError(f"pose '{pose}' is not a stance", f"use one of {V.stances()}")
        else:
            if not isinstance(pose, dict):
                raise OpError("key.pose must be an object of joint angles or a stance name")
            for j, v in pose.items():
                if j not in V.JOINTS:
                    raise OpError(f"unknown joint '{j}'", f"joints: {V.JOINTS}")
                if not isinstance(v, (int, float)) or v != v:
                    raise OpError(f"joint '{j}' must be a number")
        e = k.get("ease", "smooth")
        if e not in V.EASES:
            raise OpError(f"ease must be one of {V.EASES}")
        out.append({"t": num(k, "t", required=True, lo=0, hi=1), "pose": pose, "ease": e})
    return out


_ACTION_PROPS = {
    "keys": {"type": "array", "description": "keyframes. Each {t: 0..1 of the action, pose: {joint: degrees} or stance name, ease?: 'snap'|'out'|'inOut'|'back'|'linear'|'hold'}. "
             "Joints: torso, head (lean fwd +), aF/aB front/back upper arm, eF/eB elbow (+ bends forward), tF/tB front/back thigh, kF/kB knee (- bends back); angles measured from straight down, + = toward facing direction. "
             "rx/ry root offset in character-heights (ry negative = up), rot whole-body rotation (+ forward, -90 = lying on back), wpn weapon angle vs forearm. Unspecified joints stay at the current stance. "
             "Include an anticipation key before the main move and a follow-through key after it.",
             "items": {"type": "object"}},
    "mask": {"type": "string", "enum": ["full", "upper"], "description": "upper = only arms/torso/head (can play while walking)"},
    "trail": {"type": "string", "enum": ["weapon", "hand", "foot"], "description": "motion smear while moving fast"},
    "face": {"type": "string", "enum": V.emotions()},
    "end_stance": {"type": "string", "description": "stance the character stays in after the action"},
    "dx": {"type": "number", "description": "px to travel along the facing direction"},
}


def _build_def(a, dur):
    df = {"dur": dur, "mask": choice(a, "mask", ["full", "upper"], "full"), "keys": _check_keys(a.get("keys"))}
    if a.get("trail"):
        df["trail"] = choice(a, "trail", ["weapon", "hand", "foot"])
    if a.get("face"):
        df["face"] = choice(a, "face", V.emotions())
    if a.get("end_stance"):
        df["endStance"] = choice(a, "end_stance", V.stances())
    if a.get("dx") is not None:
        df["dx"] = num(a, "dx", lo=-800, hi=800)
    return df


@op("keyframes",
    "Animate a ONE-OFF custom action by writing joint-angle keyframes (use when no library action fits, e.g. a special move, a dance, a stumble). "
    "Applied to one character at time t. Stored with the scene.",
    {"scene": SCENE_, "char": CHAR_, "t": T_, "dur": {"type": "number", "description": "seconds, 0.2-20"}, **_ACTION_PROPS},
    ["scene", "char", "t", "dur", "keys"], group="choreo")
def keyframes(ctx, a):
    sc = ctx.scene(a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", required=True, lo=0.2, hi=20)
    df = _build_def(a, dur)
    local = sc.setdefault("local_actions", {})
    name = f"_{sc['id']}_{cid}_{len(local) + 1}"
    local[name] = df
    ac["actions"].append(ctx.new_event(sc, "a", t=t, action=name))
    return f"{cid} custom action t={r2(t)}..{r2(t + dur)} ({len(df['keys'])} keys)"


@op("define_action",
    "Define a NEW REUSABLE action in the SERIES library (e.g. a signature move) that `act` and `strike` can then use by name in any scene. "
    "Give `hit` (0..1 contact fraction) and `reach` (px) to make it usable as an attack in `strike`.",
    {"name": {"type": "string"}, "desc": {"type": "string"}, "dur": {"type": "number"},
     "hit": {"type": "number", "description": "fraction of dur when it connects (attacks only)"},
     "reach": {"type": "number"}, **_ACTION_PROPS},
    ["name", "dur", "keys"], group="choreo")
def define_action(ctx, a):
    name = slug(a.get("name", ""))
    if name in V.builtin_actions():
        raise OpError(f"'{name}' is a built-in action", "pick a different name")
    df = _build_def(a, num(a, "dur", required=True, lo=0.2, hi=20))
    df["category"] = "custom"
    if a.get("desc"):
        df["desc"] = str(a["desc"])[:300]
    if a.get("hit") is not None:
        df["hit"] = num(a, "hit", lo=0.1, hi=0.95)
        df["reach"] = num(a, "reach", 100, lo=20, hi=600)
    M.ActionDef.model_validate(df)
    ctx.tx.write(ctx.action_rel(name), df)
    return f"action '{name}' defined ({len(df['keys'])} keys, {df['dur']}s)"


@op("say",
    "Make a character speak: a hand-lettered speech bubble types out above their head while the mouth moves and they gesture. "
    "dur defaults from text length. Style: say, shout (spiky bubble, bold caps), whisper, think. Returns when the line ends so you can sequence dialogue.",
    {"scene": SCENE_, "char": CHAR_, "text": {"type": "string"}, "t": T_, "dur": {"type": "number"},
     "emotion": {"type": "string", "enum": V.emotions()}, "style": {"type": "string", "enum": V.BUBBLE_STYLES}},
    ["scene", "char", "text", "t"], group="dialogue")
def say(ctx, a):
    sc = ctx.scene(a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    text = str(a.get("text", "")).strip()
    if not text:
        raise OpError("text is empty")
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", lo=0.4, hi=30) or min(12, max(1.4, len(text) * 0.065 + 0.8))
    ev = ctx.new_event(sc, "d", t=t, dur=dur, text=text[:400])
    if a.get("emotion"):
        ev["emotion"] = choice(a, "emotion", V.emotions())
    if a.get("style"):
        ev["style"] = choice(a, "style", V.BUBBLE_STYLES)
    ac["says"].append(ev)
    return f"{cid} says \"{text[:40]}{'...' if len(text) > 40 else ''}\" t={r2(t)}..{r2(t + dur)}"


@op("emote", "Change a character's facial expression from time t (stays until changed). Emotions: " + ", ".join(V.emotions()),
    {"scene": SCENE_, "char": CHAR_, "t": T_, "emotion": {"type": "string", "enum": V.emotions()}}, ["scene", "char", "t", "emotion"], group="dialogue")
def emote(ctx, a):
    sc = ctx.scene(a.get("scene"))
    ac = get_actor(sc, a.get("char", ""))
    t = num(a, "t", required=True, lo=0)
    ac["emotes"].append(ctx.new_event(sc, "e", t=t, emotion=choice(a, "emotion", V.emotions(), required=True)))
    return f"{a['char']} looks {a['emotion']} from t={r2(t)}"


@op("face", "Turn a character to face 'left', 'right', or another character (keeps tracking them) from time t.",
    {"scene": SCENE_, "char": CHAR_, "t": T_, "toward": {"type": "string", "description": "'left', 'right' or a character id"}},
    ["scene", "char", "t", "toward"])
def face(ctx, a):
    sc = ctx.scene(a.get("scene"))
    ac = get_actor(sc, a.get("char", ""))
    t = num(a, "t", required=True, lo=0)
    tw = str(a.get("toward", ""))
    if tw in ("left", "right"):
        ac["faces"].append(ctx.new_event(sc, "f", t=t, dir=-1 if tw == "left" else 1))
    else:
        tg = slug(tw)
        get_actor(sc, tg)
        ac["faces"].append(ctx.new_event(sc, "f", t=t, target=tg))
    return f"{a['char']} faces {tw} at t={r2(t)}"


@op("camera",
    "Direct the camera. kinds: 'set' (cut to x,y,zoom at t), 'move' (ease to x,y,zoom over dur), 'follow' (track one character), "
    "'frame' (auto-zoom to keep several characters in shot), 'shake' (screen shake, amp px). x,y are the world point at screen centre "
    "(frame centre default x=640,y=360 at zoom 1; zoom>1 = closer). Good shots: wide establishing -> frame fighters -> push in (zoom 1.4-1.8) on a hit -> pull back.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": V.CAM_KINDS}, "t": T_, "dur": {"type": "number"},
     "x": {"type": "number"}, "y": {"type": "number"}, "zoom": {"type": "number", "description": "0.5-3"},
     "char": {"type": "string", "description": "for follow"}, "chars": {"type": "array", "items": {"type": "string"}, "description": "for frame (default: everyone)"},
     "pad": {"type": "number", "description": "frame padding px (default 220; smaller = tighter)"},
     "blend": {"type": "number", "description": "seconds to ease into follow/frame (default 0.6)"},
     "amp": {"type": "number", "description": "shake amplitude px"}, "ease": {"type": "string", "enum": V.EASES}},
    ["scene", "kind", "t"], group="camera")
def camera(ctx, a):
    sc = ctx.scene(a.get("scene"))
    kind = choice(a, "kind", V.CAM_KINDS, required=True)
    ev = ctx.new_event(sc, "c", kind=kind, t=num(a, "t", required=True, lo=0))
    if a.get("dur") is not None:
        ev["dur"] = num(a, "dur", lo=0, hi=60)
    for k, lo, hi in (("x", -2000, 6000), ("y", -2000, 2000), ("zoom", 0.4, 4), ("pad", 0, 800), ("blend", 0, 6), ("amp", 0, 80)):
        if a.get(k) is not None:
            ev[k] = num(a, k, lo=lo, hi=hi)
    if a.get("ease"):
        ev["ease"] = choice(a, "ease", V.EASES)
    if kind == "follow":
        ev["char"] = slug(a.get("char", ""))
        get_actor(sc, ev["char"])
    if kind == "frame" and a.get("chars"):
        ev["chars"] = [slug(c) for c in a["chars"]]
        for c in ev["chars"]:
            get_actor(sc, c)
    if kind == "move" and ev.get("dur") is None:
        ev["dur"] = 1.0
    sc["camera"].append(ev)
    return f"camera {kind} at t={r2(ev['t'])}" + (f" over {r2(ev['dur'])}s" if "dur" in ev else "")


@op("fx",
    "Add a visual effect. World effects (anchor to a character with at_char+part, or give x,y): impact (starburst), slash (curved sword swoosh), dust (puffs), "
    "ring (shockwave; ground:true for flat), sparks, sfx_text (comic lettering, needs text). Screen effects: flash, vignette, tint, speedlines (dir left/right or radial), rain. "
    "Parts: " + ", ".join(V.PARTS) + ". ox/oy nudge the position in px.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": V.FX_KINDS}, "t": T_, "dur": {"type": "number"},
     "x": {"type": "number"}, "y": {"type": "number"}, "at_char": {"type": "string"}, "part": {"type": "string", "enum": V.PARTS},
     "follow": {"type": "boolean", "description": "keep tracking the character while the effect plays"},
     "ox": {"type": "number"}, "oy": {"type": "number"}, "size": {"type": "number"}, "intensity": {"type": "number"},
     "color": HEXC, "text": {"type": "string"}, "angle": {"type": "number"}, "count": {"type": "number"},
     "dir": {"type": "string", "enum": ["left", "right", "radial"]}, "ground": {"type": "boolean"}, "flip": {"type": "boolean"},
     "angle0": {"type": "number"}, "angle1": {"type": "number"}},
    ["scene", "kind", "t"], group="fx")
def fx(ctx, a):
    sc = ctx.scene(a.get("scene"))
    kind = choice(a, "kind", V.FX_KINDS, required=True)
    ev = ctx.new_event(sc, "x", kind=kind, t=num(a, "t", required=True, lo=0),
                       dur=num(a, "dur", {"flash": 0.15, "impact": 0.42, "sfx_text": 0.8, "speedlines": 1.0, "dust": 0.7}.get(kind, 0.6), lo=0.05, hi=60))
    for k in ("x", "y", "ox", "oy", "size", "intensity", "angle", "count", "angle0", "angle1"):
        if a.get(k) is not None:
            ev[k] = num(a, k)
    if a.get("at_char"):
        ev["at_char"] = slug(a["at_char"])
        get_actor(sc, ev["at_char"])
        ev["part"] = choice(a, "part", V.PARTS, "chest")
    for k in ("follow", "ground", "flip"):
        if a.get(k):
            ev[k] = True
    if a.get("color"):
        ev["color"] = color(a["color"])
    if a.get("text"):
        ev["text"] = str(a["text"])[:30]
    if a.get("dir"):
        ev["dir"] = a["dir"]
    if kind == "sfx_text" and not ev.get("text"):
        raise OpError("sfx_text needs 'text'", "e.g. text='WHAM!'")
    sc["fx"].append(ev)
    return f"fx {kind} at t={r2(ev['t'])}..{r2(ev['t'] + ev['dur'])}"


@op("caption", "Add on-screen text: 'narration' (box at the bottom), 'title' (big centred title card), 'location' (corner label that types out).",
    {"scene": SCENE_, "text": {"type": "string"}, "t": T_, "dur": {"type": "number"}, "style": {"type": "string", "enum": V.CAPTION_STYLES},
     "color": HEXC}, ["scene", "text", "t"])
def caption(ctx, a):
    sc = ctx.scene(a.get("scene"))
    text = str(a.get("text", "")).strip()
    if not text:
        raise OpError("text is empty")
    style = choice(a, "style", V.CAPTION_STYLES, "narration")
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", lo=0.5, hi=60) or min(10, max(2.0, len(text) * 0.06 + 1.2))
    ev = ctx.new_event(sc, "k", t=t, dur=dur, text=text[:240], style=style)
    if a.get("color"):
        ev["color"] = color(a["color"])
    sc["captions"].append(ev)
    return f"caption ({style}) t={r2(t)}..{r2(t + dur)}"


# --------------------------------------------------------------------------- editing existing events (provenance + locks)
def _all_events(sc: dict):
    """yield (list, event) for every editable event in a scene."""
    for cid, a in sc["actors"].items():
        for track in ("moves", "actions", "stances", "emotes", "says", "faces"):
            for e in a[track]:
                yield a[track], e, cid
    for track in ("camera", "fx", "captions", "audio", "props"):
        for e in sc.get(track, []):
            yield sc[track], e, None


def _find_event(sc, eid):
    for lst, e, cid in _all_events(sc):
        if e.get("id") == eid:
            return lst, e, cid
    raise OpError(f"no event '{eid}' in scene '{sc['id']}'", "ids appear in the scene summary, e.g. a12, m3")


@op("update_event", "Edit fields of an existing event by id (retime, change text, etc). Marks the event as authored by the editor. "
    "AI cannot edit locked or user-authored events.",
    {"scene": SCENE_, "id": {"type": "string", "description": "event id"}, "fields": {"type": "object", "description": "fields to set, e.g. {t: 3.2, text: '...'}"}},
    ["scene", "id", "fields"], group="edit")
def update_event(ctx, a):
    sc = ctx.scene(a.get("scene"))
    _, e, _ = _find_event(sc, a.get("id"))
    ctx.guard(e)
    fields = a.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise OpError("fields must be a non-empty object")
    for k, v in fields.items():
        if k in ("id", "src"):
            raise OpError(f"field '{k}' cannot be edited")
        if k == "lock" and ctx.src != "user":
            raise OpError("only the user can change locks")
        e[k] = v
    if ctx.src == "user":
        e["src"] = "user"
    return f"updated {e['id']}: {', '.join(fields)}"


@op("delete_event", "Delete one event by id.", {"scene": SCENE_, "id": {"type": "string"}}, ["scene", "id"], group="edit")
def delete_event(ctx, a):
    sc = ctx.scene(a.get("scene"))
    lst, e, _ = _find_event(sc, a.get("id"))
    ctx.guard(e)
    lst.remove(e)
    return f"deleted {a['id']}"


@op("set_lock", "Lock or unlock events so the AI cannot change them (user action).",
    {"scene": SCENE_, "ids": {"type": "array", "items": {"type": "string"}}, "lock": {"type": "boolean"}}, ["scene", "ids", "lock"], group="edit")
def set_lock(ctx, a):
    if ctx.src != "user":
        raise OpError("only the user can lock or unlock events", "ask the user to lock it in the studio (L) or with /lock")
    sc = ctx.scene(a.get("scene"))
    for eid in a.get("ids", []):
        _, e, _ = _find_event(sc, eid)
        e["lock"] = bool(a.get("lock"))
    return f"{'locked' if a.get('lock') else 'unlocked'} {len(a.get('ids', []))} event(s)"


@op("remove_events",
    "Delete timeline events so a shot can be redone. `what`: all | moves | actions | says | emotes | faces | stances | fx | camera | captions | props. "
    "Optionally limit to one character (char) and/or a time window (t_from..t_to). Locked and user-authored events are always skipped for the AI.",
    {"scene": SCENE_, "what": {"type": "string", "enum": ["all", "moves", "actions", "says", "emotes", "faces", "stances", "fx", "camera", "captions", "props"]},
     "char": CHAR_, "t_from": {"type": "number"}, "t_to": {"type": "number"}}, ["scene", "what"])
def remove_events(ctx, a):
    sc = ctx.scene(a.get("scene"))
    what = a.get("what")
    lo, hi = num(a, "t_from", -1e9), num(a, "t_to", 1e9)
    cid = slug(a["char"]) if a.get("char") else None
    removed = skipped = 0

    def keep(e):
        nonlocal removed, skipped
        if e.get("t", 0) < -0.5 and what != "props":   # initial stance set by place
            return True
        inside = lo <= e.get("t", 0) <= hi if what != "props" else True
        if not inside:
            return True
        if ctx.src == "ai" and (e.get("lock") or e.get("src") == "user"):
            skipped += 1
            return True
        removed += 1
        return False

    kinds = ["moves", "actions", "says", "emotes", "faces", "stances"]
    for k in (kinds if what == "all" else [what] if what in kinds else []):
        for c, ac in sc["actors"].items():
            if cid and c != cid:
                continue
            ac[k] = [e for e in ac[k] if keep(e)]
    if what in ("all", "fx"):
        sc["fx"] = [e for e in sc["fx"] if (cid and e.get("at_char") != cid) or keep(e)]
    if what in ("all", "camera"):
        sc["camera"] = [e for e in sc["camera"] if keep(e)]
    if what in ("all", "captions"):
        sc["captions"] = [e for e in sc["captions"] if keep(e)]
    if what == "props":
        sc["props"] = [e for e in sc["props"] if keep(e)]
    msg = f"removed {removed} {what} events from '{sc['id']}'"
    if skipped:
        msg += f" (kept {skipped} locked/user-authored events)"
    return msg


@op("delete", "Delete a scene, an episode, a character (everywhere), an actor from one scene, or a prop by id.",
    {"kind": {"type": "string", "enum": ["scene", "episode", "character", "actor", "prop"]}, "id": {"type": "string"},
     "scene": SCENE_}, ["kind", "id"], group="manage")
def delete(ctx, a):
    kind = a.get("kind")
    if kind == "scene":
        rel, sc, eid = ctx.find_scene(a.get("id"))
        for lst, e, _ in _all_events(sc):
            ctx.guard(e, "scene content")
        ep = ctx.tx.mut(ctx.episode_rel(eid))
        ep["scenes"].remove(sc["id"])
        ctx.tx.delete(rel)
        ctx.touched_scene_rels.discard(rel)
        return f"deleted scene '{sc['id']}'"
    if kind == "episode":
        eid = slug(a.get("id", ""))
        if eid not in ctx.episodes():
            raise OpError(f"no episode '{eid}'", f"existing: {ctx.episodes()}")
        ep = ctx.tx.read(ctx.episode_rel(eid))
        if ctx.src == "ai" and ep["scenes"]:
            raise OpError(f"episode '{eid}' still has scenes {ep['scenes']}", "delete or move its scenes first; deleting a whole episode is a user action")
        ctx.series()["episodes"].remove(eid)
        ctx.tx.delete(ctx.episode_rel(eid))
        return f"deleted episode '{eid}'"
    if kind == "character":
        cid = ctx.get_char(a.get("id"))
        used = []
        for e in ctx.episodes():
            for s in ctx.tx.read(ctx.episode_rel(e))["scenes"]:
                if cid in ctx.tx.read(f"series/{ctx.sid}/episodes/{e}/scenes/{s}.json")["actors"]:
                    used.append(s)
        if used and ctx.src == "ai":
            raise OpError(f"character '{cid}' is used in scenes {used}", "remove them from those scenes first (delete kind=actor)")
        ctx.tx.delete(ctx.char_rel(cid))
        return f"deleted character '{cid}'"
    sc = ctx.scene(a.get("scene"))
    if kind == "actor":
        cid = slug(a.get("id", ""))
        ac = get_actor(sc, cid)
        for tr in ("moves", "actions", "stances", "emotes", "says", "faces"):
            for e in ac[tr]:
                ctx.guard(e, f"{tr} event")
        del sc["actors"][cid]
        return f"removed {cid} from '{sc['id']}'"
    lst, e, _ = _find_event(sc, a.get("id"))
    ctx.guard(e)
    sc["props"].remove(e)
    return f"removed prop {e['kind']} ({e['id']})"


@op("reorder_scenes", "Set the playback order of an episode's scenes.",
    {"order": {"type": "array", "items": {"type": "string"}}, "episode": {"type": "string"}}, ["order"], group="manage")
def reorder_scenes(ctx, a):
    eid = slug(a["episode"]) if a.get("episode") else ctx.eid
    if not eid or eid not in ctx.episodes():
        raise OpError("no such episode", f"pass episode=<id>; existing: {ctx.episodes()}")
    ep = ctx.tx.mut(ctx.episode_rel(eid))
    order = [slug(x) for x in a.get("order", [])]
    if sorted(order) != sorted(ep["scenes"]):
        raise OpError("order must list every scene of the episode exactly once", f"scenes: {ep['scenes']}")
    ep["scenes"] = order
    return "scene order: " + " > ".join(order)


@op("duplicate_scene", "Copy a scene (e.g. to try an alternative take). The copy gets new_id and is placed after the original.",
    {"scene": SCENE_, "new_id": {"type": "string"}}, ["scene", "new_id"], group="manage")
def duplicate_scene(ctx, a):
    import copy
    rel, sc, eid = ctx.find_scene(a.get("scene"))
    nid = slug(a["new_id"])
    ep = ctx.tx.mut(ctx.episode_rel(eid))
    if any(nid in ctx.tx.read(ctx.episode_rel(e))["scenes"] for e in ctx.episodes()):
        raise OpError(f"scene '{nid}' already exists", "pick another id")
    new = copy.deepcopy(sc)
    new["id"], new["name"] = nid, (sc.get("name") or sc["id"]) + " (copy)"
    ep["scenes"].insert(ep["scenes"].index(sc["id"]) + 1, nid)
    nrel = f"series/{ctx.sid}/episodes/{eid}/scenes/{nid}.json"
    ctx.tx.write(nrel, new)
    ctx.touched_scene_rels.add(nrel)
    return f"duplicated '{sc['id']}' -> '{nid}'"


@op("note_research",
    "Save a research finding or style decision to the series notes (shown to you in every later turn). Use after web research, e.g. on a "
    "location, culture, costume, fight style, animation technique, or a story/world rule you decided together with the user.",
    {"topic": {"type": "string"}, "summary": {"type": "string", "description": "the useful facts / decisions, 1-6 sentences"},
     "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs"}}, ["topic", "summary"], group="research")
def note_research(ctx, a):
    s = ctx.series()
    s.setdefault("notes", []).append({"topic": str(a["topic"])[:120], "summary": str(a["summary"])[:1500],
                                      "sources": [str(x)[:300] for x in a.get("sources", [])][:6]})
    s["notes"] = s["notes"][-80:]
    return f"saved note '{a['topic']}'"
