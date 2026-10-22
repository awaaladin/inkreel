"""Timing model for scene dicts (mirrors the engine so the server can reason about positions and contact frames)."""
from __future__ import annotations

from typing import Callable

ActionLookup = Callable[[str], dict | None]


def ease(name: str, u: float) -> float:
    u = max(0.0, min(1.0, u))
    return {
        "linear": u, "in": u * u, "out": 1 - (1 - u) ** 2, "inOut": 2 * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 2 / 2,
        "smooth": u * u * (3 - 2 * u), "snap": 1 - (1 - u) ** 4,
    }.get(name, u * u * (3 - 2 * u))


def moves(actor: dict) -> list[dict]:
    out, cx, cy = [], actor.get("x", 0), actor.get("y", 0)
    for m in sorted(actor.get("moves", []), key=lambda m: m["t"]):
        tx = m["x"] if m.get("x") is not None else cx
        ty = m["y"] if m.get("y") is not None else cy
        out.append(dict(m, fx=cx, fy=cy, tx=tx, ty=ty))
        cx, cy = tx, ty
    return out


def base_x(actor: dict, t: float) -> float:
    x = actor.get("x", 0)
    for m in moves(actor):
        if t < m["t"]:
            break
        p = max(0.0, min(1.0, (t - m["t"]) / max(0.05, m.get("dur", 1))))
        x = m["fx"] + (m["tx"] - m["fx"]) * ease(m.get("ease", "smooth"), p)
    return x


def facing_at(scene: dict, cid: str, t: float) -> int:
    actor = scene["actors"][cid]
    ev = []
    for f in actor.get("faces", []):
        ev.append((f["t"], f.get("dir"), f.get("target")))
    for m in moves(actor):
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


def x_at(scene: dict, lookup: ActionLookup, cid: str, t: float) -> float:
    actor = scene["actors"][cid]
    x = base_x(actor, t)
    for a in actor.get("actions", []):
        if t < a["t"]:
            continue
        df = lookup(a["action"]) or {}
        dx = a.get("dx", df.get("dx", 0)) or 0
        if not dx:
            continue
        dur = a.get("dur") or df.get("dur", 0.8)
        u = max(0.0, min(1.0, (t - a["t"]) / (dur * df.get("dxSpan", 0.8))))
        x += facing_at(scene, cid, a["t"]) * dx * (1 - (1 - u) ** 2)
    return x


def scene_end(scene: dict) -> float:
    m = 0.0
    for a in scene.get("actors", {}).values():
        for mv in a.get("moves", []):
            m = max(m, mv["t"] + mv.get("dur", 1))
        for ac in a.get("actions", []):
            m = max(m, ac["t"] + (ac.get("dur") or 0.8))
        for s in a.get("says", []):
            m = max(m, s["t"] + s.get("dur", 2))
    for f in scene.get("fx", []):
        m = max(m, f["t"] + f.get("dur", 0.5))
    for c in scene.get("captions", []):
        m = max(m, c["t"] + c.get("dur", 2))
    for c in scene.get("camera", []):
        m = max(m, c["t"] + (c.get("dur") or 0))
    for c in scene.get("audio", []):
        m = max(m, c["t"] + (c.get("dur") or 0))
    return m


def scene_duration(scene: dict) -> float:
    return scene["duration"] if scene.get("duration") else max(2.0, scene_end(scene) + 0.6)
