"""Scene operations: the vocabulary the AI director (or you, from Python) uses to build animation.

Every op is a function (project_dict, args) -> message string. Raise OpError for problems; the message is
sent back to the model so it can correct itself. Warnings are appended to the result text.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
LIB = json.loads((WEB / "library.json").read_text())


class OpError(Exception):
    pass


# --------------------------------------------------------------------------- vocab
BACKGROUNDS = ["beach", "forest", "plains", "fortress", "street", "interior", "void"]
TIMES = ["day", "dawn", "golden", "dusk", "night", "storm"]
PROPS = ["palm", "tree", "bush", "rock", "crate", "barrel", "torch", "campfire", "hut", "boat", "lamp", "pillar",
         "banner", "fence", "sign", "grass", "monster_silhouette"]
FX_KINDS = ["impact", "slash", "dust", "ring", "sparks", "sfx_text", "flash", "vignette", "tint", "speedlines", "rain"]
PARTS = ["head", "chest", "hip", "hand_front", "hand_back", "foot_front", "foot_back", "weapon_tip", "feet", "center"]
WEAPONS = ["none", "sword", "katana", "dagger", "staff", "spear", "club", "greatblade"]
HAIR = ["short", "afro", "locs", "braids", "bun", "mohawk", "bald"]
OUTFITS = ["tee", "tank", "long", "bare"]
LEGS = ["pants", "shorts"]
BUILDS = ["slim", "average", "strong", "heavy", "child"]
STANCES = list(LIB["stances"].keys())
EMOTIONS = list(LIB["emotions"].keys())
EASES = ["linear", "in", "out", "inOut", "smooth", "snap", "back", "hold", "elastic"]
JOINTS = ["torso", "head", "aF", "eF", "aB", "eB", "tF", "kF", "tB", "kB", "wpn", "rx", "ry", "rot"]
MOVE_STYLES = ["walk", "run", "sneak", "slide", "backstep"]
MOVE_SPEED = {"walk": 150, "run": 380, "sneak": 80, "slide": 300, "backstep": 110}
CAM_KINDS = ["set", "move", "follow", "frame", "shake"]
BUBBLE_STYLES = ["say", "shout", "whisper", "think"]
CAPTION_STYLES = ["narration", "title", "location"]

POWER = {
    "light": dict(react="hit_light", amp=5, size=70, sfx=["POW!", "TAP!", "THWIP!"], flash=0.0, dust=False),
    "medium": dict(react="hit_heavy", amp=11, size=105, sfx=["WHAM!", "BAM!", "SMACK!"], flash=0.0, dust=False),
    "heavy": dict(react="hit_heavy", amp=18, size=140, sfx=["KRAKK!", "WHAMM!", "CRUNCH!"], flash=0.45, dust=True),
    "knockdown": dict(react="hit_knockdown", amp=26, size=170, sfx=["BOOOM!", "KA-BOOM!", "SLAMM!"], flash=0.6, dust=True),
}

NAMED = {
    "black": "#111111", "white": "#f5f5f0", "red": "#c83a2e", "blue": "#2f5fb5", "green": "#3a8a4a", "yellow": "#e8c13a",
    "orange": "#e07a2a", "purple": "#6a3f8f", "pink": "#e58aa8", "brown": "#7a5030", "grey": "#808080", "gray": "#808080",
    "gold": "#d6a93a", "teal": "#2d8f85", "navy": "#1f2f5a", "cream": "#f2e8cf", "silver": "#c7ced4", "crimson": "#a3202e",
}
_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def color(v, field="color"):
    if not isinstance(v, str):
        raise OpError(f"{field} must be a hex colour string like '#c8553d'")
    v = v.strip()
    if v.lower() in NAMED:
        return NAMED[v.lower()]
    if not v.startswith("#") and re.fullmatch(r"[0-9a-fA-F]{6}", v):
        v = "#" + v
    if not _HEX.match(v):
        raise OpError(f"{field} must be a hex colour like '#c8553d' (got {v!r})")
    return v


def slug(s) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    if not s:
        raise OpError("id must contain letters or digits")
    return s


def num(a, key, default=None, lo=None, hi=None, required=False):
    v = a.get(key, default)
    if v is None:
        if required:
            raise OpError(f"'{key}' is required")
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"'{key}' must be a number")
    if lo is not None and v < lo:
        raise OpError(f"'{key}' must be >= {lo}")
    if hi is not None and v > hi:
        raise OpError(f"'{key}' must be <= {hi}")
    return v


def choice(a, key, options, default=None, required=False):
    v = a.get(key, default)
    if v is None:
        if required:
            raise OpError(f"'{key}' is required; one of {options}")
        return None
    if v not in options:
        raise OpError(f"'{key}' must be one of {options} (got {v!r})")
    return v


def r2(x):
    return round(float(x), 3)


# --------------------------------------------------------------------------- project access
def new_project(title="Untitled"):
    return {"meta": {"title": title, "fps": 24, "width": 1280, "height": 720},
            "characters": {}, "scenes": [], "actions": {}, "research": []}


def get_scene(d, sid):
    sid = slug(sid) if sid else None
    for s in d["scenes"]:
        if s["id"] == sid:
            return s
    have = [s["id"] for s in d["scenes"]]
    raise OpError(f"no scene '{sid}'. Existing scenes: {have or 'none (use create_scene first)'}")


def get_char(d, cid):
    cid = slug(cid)
    if cid not in d["characters"]:
        raise OpError(f"no character '{cid}'. Existing: {list(d['characters']) or 'none (use create_character first)'}")
    return cid


def get_actor(scene, cid):
    cid = slug(cid)
    if cid not in scene["actors"]:
        raise OpError(f"character '{cid}' is not placed in scene '{scene['id']}'. Call place first. Placed: {list(scene['actors'])}")
    return scene["actors"][cid]


def action_def(d, name):
    if name in d.get("actions", {}):
        return d["actions"][name]
    if name in LIB["actions"]:
        return LIB["actions"][name]
    names = sorted(set(LIB["actions"]) | set(d.get("actions", {})))
    raise OpError(f"unknown action '{name}'. Available: {names}")


# --------------------------------------------------------------------------- timing model (mirrors engine)
def _ease(name, u):
    u = max(0.0, min(1.0, u))
    return {
        "linear": u, "in": u * u, "out": 1 - (1 - u) ** 2, "inOut": 2 * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 2 / 2,
        "smooth": u * u * (3 - 2 * u), "snap": 1 - (1 - u) ** 4,
    }.get(name, u * u * (3 - 2 * u))


def _moves(actor):
    out, cx, cy = [], actor.get("x", 0), actor.get("y", 0)
    for m in sorted(actor.get("moves", []), key=lambda m: m["t"]):
        tx = m["x"] if m.get("x") is not None else cx
        ty = m["y"] if m.get("y") is not None else cy
        out.append(dict(m, fx=cx, fy=cy, tx=tx, ty=ty))
        cx, cy = tx, ty
    return out


def base_x(actor, t):
    x = actor.get("x", 0)
    for m in _moves(actor):
        if t < m["t"]:
            break
        p = max(0.0, min(1.0, (t - m["t"]) / max(0.05, m.get("dur", 1))))
        x = m["fx"] + (m["tx"] - m["fx"]) * _ease(m.get("ease", "smooth"), p)
    return x


def facing_at(scene, cid, t):
    actor = scene["actors"][cid]
    ev = []
    for f in actor.get("faces", []):
        ev.append((f["t"], f.get("dir"), f.get("target")))
    for m in _moves(actor):
        if m.get("style") != "backstep" and m.get("autoFace", True) and abs(m["tx"] - m["fx"]) > 1:
            ev.append((m["t"], 1 if m["tx"] > m["fx"] else -1, None))
    for a in actor.get("actions", []):
        if a.get("target"):
            ev.append((a["t"], None, a["target"]))
    d = actor.get("facing", 1)
    for et, dr, tg in sorted(ev, key=lambda e: e[0]):
        if et > t:
            break
        if tg:
            if tg in scene["actors"]:
                dx = base_x(scene["actors"][tg], t) - base_x(actor, t)
                if abs(dx) > 2:
                    d = 1 if dx > 0 else -1
        elif dr:
            d = dr
    return d


def x_at(d, scene, cid, t):
    actor = scene["actors"][cid]
    x = base_x(actor, t)
    for a in actor.get("actions", []):
        if t < a["t"]:
            continue
        df = d.get("actions", {}).get(a["action"]) or LIB["actions"].get(a["action"]) or {}
        dx = a.get("dx", df.get("dx", 0)) or 0
        if not dx:
            continue
        dur = a.get("dur") or df.get("dur", 0.8)
        u = max(0.0, min(1.0, (t - a["t"]) / (dur * df.get("dxSpan", 0.8))))
        x += facing_at(scene, cid, a["t"]) * dx * (1 - (1 - u) ** 2)
    return x


def scene_end(scene):
    m = 0.0
    for a in scene["actors"].values():
        for mv in a.get("moves", []):
            m = max(m, mv["t"] + mv.get("dur", 1))
        for ac in a.get("actions", []):
            m = max(m, ac["t"] + ac.get("dur", 0.8))
        for s in a.get("says", []):
            m = max(m, s["t"] + s.get("dur", 2))
    for f in scene.get("fx", []):
        m = max(m, f["t"] + f.get("dur", 0.5))
    for c in scene.get("captions", []):
        m = max(m, c["t"] + c.get("dur", 2))
    for c in scene.get("camera", []):
        m = max(m, c["t"] + c.get("dur", 0))
    return m


def scene_duration(scene):
    return scene["duration"] if scene.get("duration") else max(2.0, scene_end(scene) + 0.6)


def total_duration(d):
    return sum(scene_duration(s) for s in d["scenes"])


# --------------------------------------------------------------------------- ops
OPS = {}
TOOLS = []


def op(name, description, props, required=()):
    def deco(fn):
        OPS[name] = fn
        TOOLS.append({"name": name, "description": description,
                      "input_schema": {"type": "object", "properties": props, "required": list(required)}})
        return fn
    return deco


T_ = {"type": "number", "description": "start time in seconds from the start of the scene"}
SCENE_ = {"type": "string", "description": "scene id"}
CHAR_ = {"type": "string", "description": "character id"}
HEXC = {"type": "string", "description": "hex colour like #c8553d"}


@op("set_project", "Set the project title and/or frames per second (default 24).",
    {"title": {"type": "string"}, "fps": {"type": "number", "description": "12-60"}})
def set_project(d, a):
    if a.get("title"):
        d["meta"]["title"] = str(a["title"])[:120]
    if a.get("fps") is not None:
        d["meta"]["fps"] = int(num(a, "fps", lo=8, hi=60))
    return f"project: {d['meta']['title']} @ {d['meta']['fps']}fps"


@op("create_character",
    "Create or update a character design (call again with the same id to change it). Characters are hand-drawn "
    "jointed cut-out puppets. Heights are px (300 = normal adult in a 1280x720 frame; 220 = child, 360 = giant).",
    {"id": {"type": "string", "description": "short id, e.g. 'kabi'"}, "name": {"type": "string"},
     "height": {"type": "number", "description": "150-520, default 300"},
     "skin": HEXC, "hair": HEXC, "hair_style": {"type": "string", "enum": HAIR},
     "top": HEXC, "bottom": HEXC, "accent": {**HEXC, "description": "boots/belt/headband/trim colour"},
     "outfit": {"type": "string", "enum": OUTFITS, "description": "tee=short sleeves, long=long sleeves, tank/bare=bare arms"},
     "legs": {"type": "string", "enum": LEGS}, "build": {"type": "string", "enum": BUILDS},
     "weapon": {"type": "string", "enum": WEAPONS, "description": "held in the front hand; needed for slash/thrust attacks"},
     "weapon_color": HEXC, "boots": HEXC, "barefoot": {"type": "boolean"},
     "headband": {"type": "boolean"}, "beard": {"type": "boolean"}, "glasses": {"type": "boolean"},
     "scarf": {"type": "boolean"}, "scar": {"type": "boolean"},
     "head_scale": {"type": "number", "description": "0.7-1.5; bigger = more cartoony"},
     "notes": {"type": "string", "description": "personality / backstory / design notes for later reference"}},
    ["id"])
def create_character(d, a):
    cid = slug(a["id"])
    ch = d["characters"].get(cid, {})
    new = cid not in d["characters"]
    for k in ("skin", "hair", "top", "bottom", "accent", "weapon_color", "boots"):
        if a.get(k) is not None:
            ch["weaponColor" if k == "weapon_color" else k] = color(a[k], k)
    for k, opts in (("hair_style", HAIR), ("outfit", OUTFITS), ("legs", LEGS), ("build", BUILDS), ("weapon", WEAPONS)):
        v = choice(a, k, opts)
        if v:
            ch[k] = v
    for k in ("headband", "beard", "glasses", "scarf", "scar", "barefoot"):
        if a.get(k) is not None:
            ch[k] = bool(a[k])
    if a.get("height") is not None:
        ch["height"] = num(a, "height", lo=120, hi=560)
    if a.get("head_scale") is not None:
        ch["headScale"] = num(a, "head_scale", lo=0.6, hi=1.8)
    for k in ("name", "notes"):
        if a.get(k):
            ch[k] = str(a[k])[:400]
    ch.setdefault("name", a.get("name") or cid.title())
    d["characters"][cid] = ch
    return f"character '{cid}' {'created' if new else 'updated'}"


@op("create_scene",
    "Create or update a scene (a shot / location). Scenes play in order. The camera shows a 1280x720 view; "
    "world x runs 0..width, y is vertical with the ground line at ground_y (default 570). "
    "Use a wider `width` (up to 4000) for tracking shots across a long set.",
    {"id": {"type": "string"}, "name": {"type": "string"},
     "background": {"type": "string", "enum": BACKGROUNDS},
     "time": {"type": "string", "enum": TIMES, "description": "time of day / mood palette"},
     "weather": {"type": "string", "enum": ["clear", "rain"]},
     "palette": {"type": "object", "description": "optional colour overrides: skyTop, skyBot, ground, ground2, far, mid, water, water2, stone, wall, tint (css rgba)"},
     "width": {"type": "number", "description": "world width, 1280-4000 (default 1280)"},
     "ground_y": {"type": "number", "description": "ground line y (default 570)"},
     "duration": {"type": "number", "description": "force scene length in seconds (default: auto, last event + 0.6s)"},
     "letterbox": {"type": "number", "description": "cinematic bar height in px (0-120)"},
     "transition_in": {"type": "string", "enum": ["cut", "fade"]}, "transition_out": {"type": "string", "enum": ["cut", "fade"]},
     "transition_color": {"type": "string", "enum": ["black", "white"]},
     "transition_dur": {"type": "number"}},
    ["id"])
def create_scene(d, a):
    sid = slug(a["id"])
    sc = next((s for s in d["scenes"] if s["id"] == sid), None)
    new = sc is None
    if new:
        sc = {"id": sid, "name": sid.replace("_", " ").title(), "background": {"preset": "beach", "time": "day"},
              "groundY": 570, "width": 1280, "props": [], "actors": {}, "camera": [], "fx": [], "captions": []}
        d["scenes"].append(sc)
    if a.get("name"):
        sc["name"] = str(a["name"])[:100]
    bg = sc["background"]
    if a.get("background"):
        bg["preset"] = choice(a, "background", BACKGROUNDS)
    if a.get("time"):
        bg["time"] = choice(a, "time", TIMES)
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
    tr = sc.setdefault("transition", {})
    if a.get("transition_in"):
        tr["in"] = a["transition_in"]
    if a.get("transition_out"):
        tr["out"] = a["transition_out"]
    if a.get("transition_color"):
        tr["color"] = a["transition_color"]
    if a.get("transition_dur") is not None:
        tr["dur"] = num(a, "transition_dur", lo=0.1, hi=3)
    return f"scene '{sid}' {'created' if new else 'updated'} ({bg['preset']}/{bg.get('time', 'day')}, width {sc['width']}, ground y {sc['groundY']})"


@op("add_prop",
    "Add a set-dressing prop to a scene. x is world position; y is depth offset from the ground line (+ = nearer camera, drawn lower). "
    f"Kinds: {', '.join(PROPS)}.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": PROPS}, "x": {"type": "number"}, "y": {"type": "number"},
     "scale": {"type": "number"}, "flip": {"type": "boolean"}, "layer": {"type": "string", "enum": ["back", "front"], "description": "front = drawn over characters"},
     "color": HEXC}, ["scene", "kind", "x"])
def add_prop(d, a):
    sc = get_scene(d, a.get("scene"))
    p = {"kind": choice(a, "kind", PROPS, required=True), "x": num(a, "x", required=True)}
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
    return f"prop {p['kind']} at x={p['x']} ({len(sc['props'])} props in scene)"


@op("place",
    "Place a character in a scene at the scene start (or re-place it). x = world x of the feet, y = depth offset from the ground line. "
    "facing says which way they look at the start. A character must be placed before it can move, act or speak.",
    {"scene": SCENE_, "char": CHAR_, "x": {"type": "number"}, "y": {"type": "number"},
     "facing": {"type": "string", "enum": ["left", "right"]},
     "stance": {"type": "string", "enum": STANCES, "description": "starting stance, default idle"}},
    ["scene", "char", "x"])
def place(d, a):
    sc = get_scene(d, a.get("scene"))
    cid = get_char(d, a.get("char"))
    st = choice(a, "stance", STANCES, "idle")
    act = {"x": num(a, "x", required=True), "y": num(a, "y", 0, lo=-400, hi=400),
           "facing": -1 if a.get("facing") == "left" else 1,
           "moves": [], "actions": [], "stances": [], "emotes": [], "says": [], "faces": []}
    if st != "idle":
        act["stances"].append({"t": -1, "stance": st, "blend": 0.01})
    sc["actors"][cid] = act
    return f"placed {cid} at x={act['x']} facing {'left' if act['facing'] < 0 else 'right'} in {st}"


@op("stance",
    "Change a character's base stance at time t (blends over `blend` seconds). Stances: " + ", ".join(STANCES) + ". "
    "'fight' = guarded combat stance; 'down' = lying on back; 'kneel'; 'crouch'; 'tired'; 'arms_crossed'.",
    {"scene": SCENE_, "char": CHAR_, "stance": {"type": "string", "enum": STANCES}, "t": T_, "blend": {"type": "number"}},
    ["scene", "char", "stance", "t"])
def stance(d, a):
    sc = get_scene(d, a.get("scene"))
    ac = get_actor(sc, a.get("char"))
    t = num(a, "t", required=True, lo=0)
    ac["stances"].append({"t": t, "stance": choice(a, "stance", STANCES, required=True), "blend": num(a, "blend", 0.3, lo=0, hi=3)})
    return f"{a['char']} -> {a['stance']} at t={r2(t)}"


@op("move",
    "Move a character along the ground to world x (and optionally depth y offset). Legs animate automatically (walk/run/sneak), "
    "'slide' glides without stepping, 'backstep' retreats while still facing the opponent. If dur is omitted it is computed from the "
    "distance and style (walk 150px/s, run 380px/s). The character turns to face the direction of travel.",
    {"scene": SCENE_, "char": CHAR_, "to_x": {"type": "number"}, "to_y": {"type": "number"}, "t": T_,
     "dur": {"type": "number"}, "style": {"type": "string", "enum": MOVE_STYLES}, "ease": {"type": "string", "enum": EASES}},
    ["scene", "char", "to_x", "t"])
def move(d, a):
    sc = get_scene(d, a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    t = num(a, "t", required=True, lo=0)
    style = choice(a, "style", MOVE_STYLES, "walk")
    x0 = x_at(d, sc, cid, t)
    tx = num(a, "to_x", required=True)
    dist = abs(tx - x0)
    dur = num(a, "dur", lo=0.1, hi=60) or max(0.3, dist / MOVE_SPEED[style])
    # moves are stored relative to the base track; knockback/dash offsets from actions are added on top.
    # Compensate so that to_x is always the real on-screen position at the end of the move.
    offset = x_at(d, sc, cid, t + dur) - base_x(ac, t + dur)
    m = {"t": t, "x": tx - offset, "dur": dur, "style": style, "ease": choice(a, "ease", EASES, "smooth")}
    if a.get("to_y") is not None:
        m["y"] = num(a, "to_y", lo=-400, hi=400)
    ac["moves"].append(m)
    msg = f"{cid} {style} x{r2(x0)} -> x{r2(tx)} over t={r2(t)}..{r2(t + dur)}"
    if dist > 1 and dur and dist / dur > MOVE_SPEED["run"] * 1.6 and style in ("walk", "run", "sneak"):
        msg += " (WARNING: very fast for this gait; use slide or a longer dur)"
    return msg


def _reach_warning(d, sc, atk, dfn, act_def, t_contact):
    reach = act_def.get("reach")
    if not reach:
        return ""
    gap = abs(x_at(d, sc, dfn, t_contact) - x_at(d, sc, atk, t_contact))
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
def act(d, a):
    sc = get_scene(d, a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    name = a.get("action")
    df = action_def(d, name)
    t = num(a, "t", required=True, lo=0)
    ch = d["characters"][cid]
    if df.get("trail") == "weapon" and ch.get("weapon", "none") == "none":
        raise OpError(f"'{name}' needs a weapon but {cid} has none. Call create_character with weapon set (e.g. sword, katana, greatblade, spear, staff) or use punch/kick.")
    ev = {"t": t, "action": name}
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
     "power": {"type": "string", "enum": list(POWER), "description": "how hard a hit lands (default medium)"},
     "dur": {"type": "number", "description": "override attack length"},
     "sfx": {"type": "string", "description": "custom sound text e.g. 'KRAK!' (or empty string for none)"},
     "effects": {"type": "boolean", "description": "set false to skip impact/shake/sfx (default true)"}},
    ["scene", "attacker", "defender", "attack", "t"])
def strike(d, a):
    sc = get_scene(d, a.get("scene"))
    atk, dfn = slug(a.get("attacker", "")), slug(a.get("defender", ""))
    if atk == dfn:
        raise OpError("attacker and defender must differ")
    get_actor(sc, atk)
    get_actor(sc, dfn)
    t = num(a, "t", required=True, lo=0)
    name = a.get("attack")
    adef = action_def(d, name)
    if not adef.get("hit"):
        raise OpError(f"'{name}' is not an attack with a contact frame. Use: " + ", ".join(k for k, v in LIB['actions'].items() if v.get("hit")))
    result = choice(a, "result", ["hit", "block", "dodge"], "hit")
    power = choice(a, "power", list(POWER), "medium")
    P = POWER[power]
    dur = num(a, "dur", lo=0.2, hi=5) or adef["dur"]
    tc = t + dur * adef["hit"]
    fx_on = a.get("effects", True)
    atk_ev = {"t": t, "action": name, "target": dfn}
    if a.get("dur") is not None:
        atk_ev["dur"] = dur
    sc["actors"][atk]["actions"].append(atk_ev)
    warn = _reach_warning(d, sc, atk, dfn, adef, tc)
    dsc = sc["actors"][dfn]
    n = len(sc["fx"])
    sfx = a.get("sfx")
    texts = P["sfx"]
    end_def = tc

    if result == "hit":
        rdur = LIB["actions"][P["react"]]["dur"]
        ev = {"t": tc, "action": P["react"], "target": atk}
        if power == "heavy":
            ev["intensity"], ev["dx"] = 1.2, -140
        dsc["actions"].append(ev)
        end_def = tc + rdur
        if fx_on:
            part = "head" if name == "uppercut" else "chest"
            sc["fx"].append({"kind": "impact", "t": r2(tc), "dur": 0.42, "at_char": dfn, "part": part, "size": P["size"]})
            sc["camera"].append({"kind": "shake", "t": r2(tc), "dur": 0.2 + P["amp"] * 0.012, "amp": P["amp"]})
            if sfx != "":
                away = 1 if x_at(d, sc, dfn, tc) >= x_at(d, sc, atk, tc) else -1
                sc["fx"].append({"kind": "sfx_text", "t": r2(tc + 0.02), "dur": 0.75, "text": sfx or texts[n % len(texts)],
                                 "at_char": dfn, "part": "chest", "oy": -70 - (n % 2) * 30, "ox": away * (80 + P["size"] * 0.7),
                                 "size": 0.7 + P["size"] / 220, "angle": (-10 if n % 2 else 8) * away})
            if P["flash"]:
                sc["fx"].append({"kind": "flash", "t": r2(tc), "dur": 0.14, "intensity": P["flash"]})
            if P["dust"]:
                sc["fx"].append({"kind": "dust", "t": r2(tc + 0.1), "dur": 0.7, "at_char": dfn, "part": "feet", "size": 38, "count": 7})
            if power == "knockdown":
                sc["fx"].append({"kind": "ring", "t": r2(tc), "dur": 0.5, "at_char": dfn, "part": "feet", "size": 200, "ground": True})
    elif result == "block":
        bdef = LIB["actions"]["block"]
        sc["actors"][dfn]["actions"].append({"t": r2(max(0, tc - 0.25)), "action": "block", "target": atk})
        end_def = tc - 0.25 + bdef["dur"]
        if fx_on:
            sc["fx"].append({"kind": "sparks", "t": r2(tc), "dur": 0.4, "at_char": dfn, "part": "hand_front", "size": 110, "count": 16})
            sc["camera"].append({"kind": "shake", "t": r2(tc), "dur": 0.18, "amp": 6})
            if sfx != "":
                has_w = d["characters"][atk].get("weapon", "none") != "none"
                sc["fx"].append({"kind": "sfx_text", "t": r2(tc + 0.02), "dur": 0.6, "text": sfx or ("CLANG!" if has_w else "THUD!"),
                                 "at_char": dfn, "part": "chest", "oy": -90, "ox": 110 * (1 if x_at(d, sc, dfn, tc) >= x_at(d, sc, atk, tc) else -1), "size": 0.9, "angle": -6, "color": "#ffd23f"})
    else:
        ddef = LIB["actions"]["dodge"]
        sc["actors"][dfn]["actions"].append({"t": r2(max(0, tc - 0.3)), "action": "dodge", "target": atk})
        end_def = tc - 0.3 + ddef["dur"]
        if fx_on and sfx != "":
            sc["fx"].append({"kind": "sfx_text", "t": r2(tc), "dur": 0.5, "text": sfx or "WHOOSH!", "at_char": atk, "part": "hand_front",
                             "oy": -90, "size": 0.7, "angle": -4, "color": "#ffffff"})
    atk_free = t + dur
    # reach check uses where the defender will be
    return (f"{atk} {name} -> {dfn} {result}{'/' + power if result == 'hit' else ''}: attack t={r2(t)}..{r2(atk_free)}, "
            f"contact t={r2(tc)}, defender free at t={r2(end_def)}" + (" (lying down; needs getup)" if result == 'hit' and power == 'knockdown' else "") + warn)


def _check_keys(keys):
    if not isinstance(keys, list) or len(keys) < 2:
        raise OpError("keys must be a list of at least 2 keyframes: {t: 0..1, pose: {joint: degrees}, ease?}")
    out = []
    for k in keys:
        if not isinstance(k, dict):
            raise OpError("each key must be an object")
        pose = k.get("pose", {})
        if isinstance(pose, str):
            if pose not in STANCES:
                raise OpError(f"pose '{pose}' is not a stance; use one of {STANCES}")
        else:
            if not isinstance(pose, dict):
                raise OpError("key.pose must be an object of joint angles or a stance name")
            for j, v in pose.items():
                if j not in JOINTS:
                    raise OpError(f"unknown joint '{j}'. Joints: {JOINTS}")
                if not isinstance(v, (int, float)):
                    raise OpError(f"joint '{j}' must be a number")
        e = k.get("ease", "smooth")
        if e not in EASES:
            raise OpError(f"ease must be one of {EASES}")
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
    "face": {"type": "string", "enum": EMOTIONS},
    "end_stance": {"type": "string", "enum": STANCES, "description": "stance the character stays in after the action"},
    "dx": {"type": "number", "description": "px to travel along the facing direction"},
}


def _build_def(a, dur):
    df = {"dur": dur, "mask": choice(a, "mask", ["full", "upper"], "full"), "keys": _check_keys(a.get("keys"))}
    if a.get("trail"):
        df["trail"] = choice(a, "trail", ["weapon", "hand", "foot"])
    if a.get("face"):
        df["face"] = choice(a, "face", EMOTIONS)
    if a.get("end_stance"):
        df["endStance"] = choice(a, "end_stance", STANCES)
    if a.get("dx") is not None:
        df["dx"] = num(a, "dx", lo=-800, hi=800)
    return df


@op("keyframes",
    "Animate a ONE-OFF custom action by writing joint-angle keyframes (use when no library action fits, e.g. a special move, a dance, a stumble). "
    "Applied to one character at time t.",
    {"scene": SCENE_, "char": CHAR_, "t": T_, "dur": {"type": "number", "description": "seconds, 0.2-20"}, **_ACTION_PROPS},
    ["scene", "char", "t", "dur", "keys"])
def keyframes(d, a):
    sc = get_scene(d, a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", required=True, lo=0.2, hi=20)
    df = _build_def(a, dur)
    name = f"_{sc['id']}_{cid}_{len(d['actions']) + 1}"
    d["actions"][name] = df
    ac["actions"].append({"t": t, "action": name})
    return f"{cid} custom action t={r2(t)}..{r2(t + dur)} ({len(df['keys'])} keys)"


@op("define_action",
    "Define a NEW REUSABLE action in the project library (e.g. a signature move) that `act` and `strike` can then use by name. "
    "Give `hit` (0..1 contact fraction) and `reach` (px) to make it usable as an attack in `strike`.",
    {"name": {"type": "string"}, "desc": {"type": "string"}, "dur": {"type": "number"},
     "hit": {"type": "number", "description": "fraction of dur when it connects (attacks only)"},
     "reach": {"type": "number"}, **_ACTION_PROPS},
    ["name", "dur", "keys"])
def define_action(d, a):
    name = slug(a.get("name", ""))
    if name in LIB["actions"]:
        raise OpError(f"'{name}' is a built-in action; pick a different name")
    df = _build_def(a, num(a, "dur", required=True, lo=0.2, hi=20))
    if a.get("desc"):
        df["desc"] = str(a["desc"])[:300]
    if a.get("hit") is not None:
        df["hit"] = num(a, "hit", lo=0.1, hi=0.95)
        df["reach"] = num(a, "reach", 100, lo=20, hi=600)
    d["actions"][name] = df
    return f"action '{name}' defined ({len(df['keys'])} keys, {df['dur']}s)"


@op("say",
    "Make a character speak: a hand-lettered speech bubble types out above their head while the mouth moves and they gesture. "
    "dur defaults from text length. Style: say, shout (spiky bubble, bold caps), whisper, think. Returns when the line ends so you can sequence dialogue.",
    {"scene": SCENE_, "char": CHAR_, "text": {"type": "string"}, "t": T_, "dur": {"type": "number"},
     "emotion": {"type": "string", "enum": EMOTIONS}, "style": {"type": "string", "enum": BUBBLE_STYLES}},
    ["scene", "char", "text", "t"])
def say(d, a):
    sc = get_scene(d, a.get("scene"))
    cid = slug(a.get("char", ""))
    ac = get_actor(sc, cid)
    text = str(a.get("text", "")).strip()
    if not text:
        raise OpError("text is empty")
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", lo=0.4, hi=30) or min(12, max(1.4, len(text) * 0.065 + 0.8))
    ev = {"t": t, "dur": dur, "text": text[:400]}
    if a.get("emotion"):
        ev["emotion"] = choice(a, "emotion", EMOTIONS)
    if a.get("style"):
        ev["style"] = choice(a, "style", BUBBLE_STYLES)
    ac["says"].append(ev)
    return f"{cid} says \"{text[:40]}{'...' if len(text) > 40 else ''}\" t={r2(t)}..{r2(t + dur)}"


@op("emote", "Change a character's facial expression from time t (stays until changed). Emotions: " + ", ".join(EMOTIONS),
    {"scene": SCENE_, "char": CHAR_, "t": T_, "emotion": {"type": "string", "enum": EMOTIONS}}, ["scene", "char", "t", "emotion"])
def emote(d, a):
    sc = get_scene(d, a.get("scene"))
    ac = get_actor(sc, a.get("char", ""))
    ac["emotes"].append({"t": num(a, "t", required=True, lo=0), "emotion": choice(a, "emotion", EMOTIONS, required=True)})
    return f"{a['char']} looks {a['emotion']} from t={r2(a['t'])}"


@op("face", "Turn a character to face 'left', 'right', or another character (keeps tracking them) from time t.",
    {"scene": SCENE_, "char": CHAR_, "t": T_, "toward": {"type": "string", "description": "'left', 'right' or a character id"}},
    ["scene", "char", "t", "toward"])
def face(d, a):
    sc = get_scene(d, a.get("scene"))
    ac = get_actor(sc, a.get("char", ""))
    t = num(a, "t", required=True, lo=0)
    tw = str(a.get("toward", ""))
    if tw in ("left", "right"):
        ac["faces"].append({"t": t, "dir": -1 if tw == "left" else 1})
    else:
        tg = slug(tw)
        get_actor(sc, tg)
        ac["faces"].append({"t": t, "target": tg})
    return f"{a['char']} faces {tw} at t={r2(t)}"


@op("camera",
    "Direct the camera. kinds: 'set' (cut to x,y,zoom at t), 'move' (ease to x,y,zoom over dur), 'follow' (track one character), "
    "'frame' (auto-zoom to keep several characters in shot), 'shake' (screen shake, amp px). x,y are the world point at screen centre "
    "(frame centre default x=640,y=360 at zoom 1; zoom>1 = closer). Good shots: wide establishing -> frame fighters -> push in (zoom 1.4-1.8) on a hit -> pull back.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": CAM_KINDS}, "t": T_, "dur": {"type": "number"},
     "x": {"type": "number"}, "y": {"type": "number"}, "zoom": {"type": "number", "description": "0.5-3"},
     "char": {"type": "string", "description": "for follow"}, "chars": {"type": "array", "items": {"type": "string"}, "description": "for frame (default: everyone)"},
     "pad": {"type": "number", "description": "frame padding px (default 220; smaller = tighter)"},
     "blend": {"type": "number", "description": "seconds to ease into follow/frame (default 0.6)"},
     "amp": {"type": "number", "description": "shake amplitude px"}, "ease": {"type": "string", "enum": EASES}},
    ["scene", "kind", "t"])
def camera(d, a):
    sc = get_scene(d, a.get("scene"))
    kind = choice(a, "kind", CAM_KINDS, required=True)
    ev = {"kind": kind, "t": num(a, "t", required=True, lo=0)}
    if a.get("dur") is not None:
        ev["dur"] = num(a, "dur", lo=0, hi=60)
    for k, lo, hi in (("x", -2000, 6000), ("y", -2000, 2000), ("zoom", 0.4, 4), ("pad", 0, 800), ("blend", 0, 6), ("amp", 0, 80)):
        if a.get(k) is not None:
            ev[k] = num(a, k, lo=lo, hi=hi)
    if a.get("ease"):
        ev["ease"] = choice(a, "ease", EASES)
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
    "Parts: " + ", ".join(PARTS) + ". ox/oy nudge the position in px.",
    {"scene": SCENE_, "kind": {"type": "string", "enum": FX_KINDS}, "t": T_, "dur": {"type": "number"},
     "x": {"type": "number"}, "y": {"type": "number"}, "at_char": {"type": "string"}, "part": {"type": "string", "enum": PARTS},
     "follow": {"type": "boolean", "description": "keep tracking the character while the effect plays"},
     "ox": {"type": "number"}, "oy": {"type": "number"}, "size": {"type": "number"}, "intensity": {"type": "number"},
     "color": HEXC, "text": {"type": "string"}, "angle": {"type": "number"}, "count": {"type": "number"},
     "dir": {"type": "string", "enum": ["left", "right", "radial"]}, "ground": {"type": "boolean"}, "flip": {"type": "boolean"},
     "angle0": {"type": "number"}, "angle1": {"type": "number"}},
    ["scene", "kind", "t"])
def fx(d, a):
    sc = get_scene(d, a.get("scene"))
    kind = choice(a, "kind", FX_KINDS, required=True)
    ev = {"kind": kind, "t": num(a, "t", required=True, lo=0), "dur": num(a, "dur", {"flash": 0.15, "impact": 0.42, "sfx_text": 0.8, "speedlines": 1.0, "dust": 0.7}.get(kind, 0.6), lo=0.05, hi=60)}
    for k in ("x", "y", "ox", "oy", "size", "intensity", "angle", "count", "angle0", "angle1"):
        if a.get(k) is not None:
            ev[k] = num(a, k)
    if a.get("at_char"):
        ev["at_char"] = slug(a["at_char"])
        get_actor(sc, ev["at_char"])
        ev["part"] = choice(a, "part", PARTS, "chest")
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
        raise OpError("sfx_text needs 'text', e.g. 'WHAM!'")
    sc["fx"].append(ev)
    return f"fx {kind} at t={r2(ev['t'])}..{r2(ev['t'] + ev['dur'])}"


@op("caption", "Add on-screen text: 'narration' (box at the bottom), 'title' (big centred title card), 'location' (corner label that types out).",
    {"scene": SCENE_, "text": {"type": "string"}, "t": T_, "dur": {"type": "number"}, "style": {"type": "string", "enum": CAPTION_STYLES},
     "color": HEXC}, ["scene", "text", "t"])
def caption(d, a):
    sc = get_scene(d, a.get("scene"))
    text = str(a.get("text", "")).strip()
    if not text:
        raise OpError("text is empty")
    style = choice(a, "style", CAPTION_STYLES, "narration")
    t = num(a, "t", required=True, lo=0)
    dur = num(a, "dur", lo=0.5, hi=60) or min(10, max(2.0, len(text) * 0.06 + 1.2))
    ev = {"t": t, "dur": dur, "text": text[:240], "style": style}
    if a.get("color"):
        ev["color"] = color(a["color"])
    sc["captions"].append(ev)
    return f"caption ({style}) t={r2(t)}..{r2(t + dur)}"


@op("remove_events",
    "Delete timeline events so a shot can be redone. `what`: all | moves | actions | says | emotes | faces | stances | fx | camera | captions | props. "
    "Optionally limit to one character (char) and/or a time window (t_from..t_to). 'actors'-scoped kinds need `char` or apply to all characters.",
    {"scene": SCENE_, "what": {"type": "string", "enum": ["all", "moves", "actions", "says", "emotes", "faces", "stances", "fx", "camera", "captions", "props"]},
     "char": CHAR_, "t_from": {"type": "number"}, "t_to": {"type": "number"}}, ["scene", "what"])
def remove_events(d, a):
    sc = get_scene(d, a.get("scene"))
    what = a.get("what")
    lo, hi = num(a, "t_from", -1e9), num(a, "t_to", 1e9)
    cid = slug(a["char"]) if a.get("char") else None
    removed = 0

    def keep(e):
        nonlocal removed
        inside = lo <= e.get("t", 0) <= hi
        if inside:
            removed += 1
        return not inside

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
        removed += len(sc["props"])
        sc["props"] = []
    return f"removed {removed} {what} events from '{sc['id']}'"


@op("delete", "Delete a scene, a character (everywhere), an actor from one scene, or a prop by index.",
    {"kind": {"type": "string", "enum": ["scene", "character", "actor", "prop"]}, "id": {"type": "string"},
     "scene": SCENE_, "index": {"type": "number", "description": "prop index (0-based) for kind=prop"}}, ["kind"])
def delete(d, a):
    kind = a.get("kind")
    if kind == "scene":
        sc = get_scene(d, a.get("id"))
        d["scenes"].remove(sc)
        return f"deleted scene '{sc['id']}'"
    if kind == "character":
        cid = get_char(d, a.get("id"))
        del d["characters"][cid]
        for s in d["scenes"]:
            s["actors"].pop(cid, None)
        return f"deleted character '{cid}'"
    sc = get_scene(d, a.get("scene"))
    if kind == "actor":
        cid = slug(a.get("id", ""))
        get_actor(sc, cid)
        del sc["actors"][cid]
        return f"removed {cid} from '{sc['id']}'"
    i = int(num(a, "index", required=True, lo=0))
    if i >= len(sc["props"]):
        raise OpError(f"prop index {i} out of range ({len(sc['props'])} props)")
    p = sc["props"].pop(i)
    return f"removed prop {p['kind']}"


@op("reorder_scenes", "Set the playback order of scenes.", {"order": {"type": "array", "items": {"type": "string"}}}, ["order"])
def reorder_scenes(d, a):
    order = [slug(x) for x in a.get("order", [])]
    ids = [s["id"] for s in d["scenes"]]
    if sorted(order) != sorted(ids):
        raise OpError(f"order must list every scene exactly once: {ids}")
    d["scenes"].sort(key=lambda s: order.index(s["id"]))
    return "scene order: " + " > ".join(order)


@op("note_research",
    "Save a research finding or style decision to the project's notes (shown to you in every later turn). Use after web research, e.g. on a "
    "location, culture, costume, fight style, animation technique, or a story/world rule you decided together with the user.",
    {"topic": {"type": "string"}, "summary": {"type": "string", "description": "the useful facts / decisions, 1-6 sentences"},
     "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs"}}, ["topic", "summary"])
def note_research(d, a):
    d.setdefault("research", []).append({"topic": str(a["topic"])[:120], "summary": str(a["summary"])[:1500],
                                         "sources": [str(s)[:300] for s in a.get("sources", [])][:6]})
    d["research"] = d["research"][-40:]
    return f"saved note '{a['topic']}'"


def apply(d, name, args):
    fn = OPS.get(name)
    if not fn:
        raise OpError(f"unknown tool '{name}'")
    return fn(d, args or {})


# --------------------------------------------------------------------------- summary for the model
def describe(d, max_events=70):
    m = d["meta"]
    lines = [f"PROJECT \"{m['title']}\"  {m['fps']}fps  total {total_duration(d):.1f}s  scenes {len(d['scenes'])}"]
    if d["characters"]:
        lines.append("CHARACTERS:")
        for cid, c in d["characters"].items():
            bits = [f"{k}={v}" for k, v in c.items() if k not in ("name", "notes")]
            lines.append(f"  {cid} \"{c.get('name', cid)}\": " + ", ".join(bits) + (f" | notes: {c['notes']}" if c.get("notes") else ""))
    else:
        lines.append("CHARACTERS: none yet")
    if d.get("actions"):
        lines.append("CUSTOM ACTIONS: " + ", ".join(f"{k}({v['dur']}s{', attack hit@%.2f' % v['hit'] if v.get('hit') else ''})" for k, v in d["actions"].items() if not k.startswith("_")))
    for i, s in enumerate(d["scenes"], 1):
        bg = s["background"]
        lines.append(f"SCENE {i} id={s['id']} \"{s['name']}\" {bg['preset']}/{bg.get('time', 'day')}{'/rain' if bg.get('weather') == 'rain' else ''} "
                     f"dur={scene_duration(s):.1f}s width={s['width']} groundY={s['groundY']}"
                     + (f" letterbox={s['letterbox']}" if s.get("letterbox") else "") + (f" transition={s['transition']}" if s.get("transition") else ""))
        if s["props"]:
            lines.append("  props: " + ", ".join(f"{p['kind']}@{int(p['x'])}" for p in s["props"]))
        ev = []
        for cid, ac in s["actors"].items():
            lines.append(f"  actor {cid}: start x={ac['x']:.0f} y={ac['y']:.0f} facing {'L' if ac['facing'] < 0 else 'R'}"
                         + (f" stance {ac['stances'][0]['stance']}" if ac["stances"] and ac["stances"][0]["t"] < 0 else ""))
            for m_ in ac["moves"]:
                ev.append((m_["t"], f"{cid} {m_.get('style', 'walk')} to x{x_at(d, s, cid, m_['t'] + m_['dur']):.0f} ({m_['dur']:.1f}s)"))
            for a_ in ac["actions"]:
                nm = a_["action"]
                ev.append((a_["t"], f"{cid} ACT {'custom' if nm.startswith('_') else nm}" + (f" ->{a_['target']}" if a_.get("target") else "")))
            for s_ in ac["says"]:
                ev.append((s_["t"], f"{cid} SAY \"{s_['text'][:50]}\"" + (f" [{s_['emotion']}]" if s_.get("emotion") else "")))
            for e_ in ac["emotes"]:
                ev.append((e_["t"], f"{cid} emote {e_['emotion']}"))
            for s_ in ac["stances"]:
                if s_["t"] >= 0:
                    ev.append((s_["t"], f"{cid} stance {s_['stance']}"))
        for f in s["fx"]:
            ev.append((f["t"], f"fx {f['kind']}" + (f" '{f['text']}'" if f.get("text") else "") + (f" @{f['at_char']}" if f.get("at_char") else "")))
        for c in s["camera"]:
            ev.append((c["t"], f"camera {c['kind']}" + (f" zoom {c['zoom']}" if c.get("zoom") else "")))
        for c in s["captions"]:
            ev.append((c["t"], f"caption [{c['style']}] \"{c['text'][:40]}\""))
        ev.sort(key=lambda e: e[0])
        if len(ev) > max_events:
            lines.append(f"  ({len(ev) - max_events} earlier events omitted)")
            ev = ev[-max_events:]
        for t, text in ev:
            lines.append(f"    {t:5.2f}  {text}")
    if d.get("research"):
        lines.append("NOTES:")
        for n in d["research"][-12:]:
            lines.append(f"  - {n['topic']}: {n['summary'][:260]}")
    return "\n".join(lines)


def library_text(d=None):
    out = []
    for k, v in LIB["actions"].items():
        out.append(f"  {k} ({v['dur']}s{', contact@%.2f reach %s' % (v['hit'], v.get('reach')) if v.get('hit') else ''}{', ends ' + v['endStance'] if v.get('endStance') else ''}): {v['desc']}")
    return "\n".join(out)
