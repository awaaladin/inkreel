"""Compile a series/episode/scene into the bundle the studio's engine draws.

Drawing happens in the browser (live preview, orbit view and recording all use the same engine). The server only
compiles the bundle and finds ffmpeg for turning recordings into MP4.
"""
from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path

from . import model as M
from . import timing
from .store import Store, StoreError


def _char_for_engine(ch: dict) -> dict:
    out = {k: v for k, v in ch.items() if v is not None}
    if "head_scale" in out:
        out["headScale"] = out.pop("head_scale")
    if "weapon_color" in out:
        out["weaponColor"] = out.pop("weapon_color")
    return out


def compile_bundle(store: Store, sid: str, eid: str | None = None, scene: str | None = None) -> dict:
    """Self-contained project for the engine.

    eid=None and scene=None -> every episode in order; eid only -> that episode; scene -> just that scene.
    """
    tx = store.reader()
    series = tx.read(f"series/{sid}/series.json")
    style = tx.read(f"series/{sid}/style.json", M.Style().model_dump())
    chars = {fn[:-5]: _char_for_engine(tx.read(f"series/{sid}/libraries/characters/{fn}")) for fn in tx.list(f"series/{sid}/libraries/characters")}
    actions = {fn[:-5]: tx.read(f"series/{sid}/libraries/actions/{fn}") for fn in tx.list(f"series/{sid}/libraries/actions")}
    scenes: list[dict] = []
    eps = [eid] if eid else series.get("episodes", [])
    for e in eps:
        if not tx.exists(f"series/{sid}/episodes/{e}/episode.json"):
            raise StoreError(f"no episode '{e}' in series '{sid}'", f"episodes: {series.get('episodes', [])}")
        ep = tx.read(f"series/{sid}/episodes/{e}/episode.json")
        for sc_id in ep.get("scenes", []):
            if scene and sc_id != scene:
                continue
            sc = copy.deepcopy(tx.read(f"series/{sid}/episodes/{e}/scenes/{sc_id}.json"))
            actions.update(sc.pop("local_actions", {}) or {})
            scenes.append(sc)
    if scene and not scenes:
        raise StoreError(f"no scene '{scene}'", f"look in episode(s) {eps}")
    return {"meta": {"title": series["title"], "fps": style.get("fps", 24), "width": style.get("width", 1280), "height": style.get("height", 720)},
            "style": style, "characters": chars, "scenes": scenes, "actions": actions}


def bundle_duration(bundle: dict) -> float:
    return sum(timing.scene_duration(s) for s in bundle["scenes"])


def find_ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if root.exists():
        for c in root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
            return str(c)
    return None
