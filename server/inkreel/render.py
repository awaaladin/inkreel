"""Compile a series/episode/scene into an engine bundle and render it through a RenderBackend.

`RenderBackend` is the seam between the data model and the pixels: Phase 1 implements it with the prototype JS engine
(Node + @napi-rs/canvas); Phase 3 adds a Rust backend and golden tests compare the two.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Protocol

from . import model as M
from . import timing
from . import vocab as V
from .store import Store, StoreError, Tx

REPO = Path(__file__).resolve().parents[2]
ENGINE_JS = REPO / "engine_js"


# --------------------------------------------------------------------------- bundle
def _char_for_engine(ch: dict) -> dict:
    out = {k: v for k, v in ch.items() if v is not None}
    if "head_scale" in out:
        out["headScale"] = out.pop("head_scale")
    if "weapon_color" in out:
        out["weaponColor"] = out.pop("weapon_color")
    return out


def compile_bundle(store: Store, sid: str, eid: str | None = None, scene: str | None = None) -> dict:
    """Self-contained legacy-format project for the engine.

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


# --------------------------------------------------------------------------- tools
def find_ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if root.exists():
        for c in root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
            return str(c)
    return None


def find_node() -> str | None:
    return shutil.which("node")


class RenderError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

    def __str__(self):
        return f"{super().__str__()} Hint: {self.hint}" if self.hint else super().__str__()


class RenderBackend(Protocol):
    name: str

    def still(self, bundle: dict, t: float, out: Path, scale: float = 1.0) -> Path: ...

    def video(self, bundle: dict, out: Path, fps: float | None = None, scale: float = 1.0, t0: float = 0.0, t1: float | None = None,
              progress: Callable[[int, int], None] | None = None) -> Path: ...


class NodeBackend:
    """Prototype JS engine driven by engine_js/run.js."""
    name = "js"

    def _ensure(self):
        node = find_node()
        if not node:
            raise RenderError("Node.js not found", "install Node 18+ from https://nodejs.org (winget install OpenJS.NodeJS.LTS)")
        if not (ENGINE_JS / "node_modules" / "@napi-rs").exists():
            npm = shutil.which("npm") or "npm"
            r = subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund"], cwd=ENGINE_JS, capture_output=True, text=True, shell=os.name == "nt")
            if r.returncode != 0:
                raise RenderError("could not install the renderer's npm dependencies", (r.stderr or r.stdout)[-300:])
        return node

    def _write_bundle(self, bundle: dict) -> str:
        fd, path = tempfile.mkstemp(suffix=".json", prefix="inkreel-bundle-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(bundle, f)
        return path

    def still(self, bundle: dict, t: float, out: Path, scale: float = 1.0) -> Path:
        node = self._ensure()
        out = Path(out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        bpath = self._write_bundle(bundle)
        try:
            r = subprocess.run([node, str(ENGINE_JS / "run.js"), "still", bpath, str(out), "--t", str(t), "--scale", str(scale)],
                               capture_output=True, text=True, cwd=ENGINE_JS)
        finally:
            os.unlink(bpath)
        if r.returncode != 0:
            raise RenderError("still render failed", (r.stderr or r.stdout).strip()[-400:])
        return out

    def video(self, bundle: dict, out: Path, fps: float | None = None, scale: float = 1.0, t0: float = 0.0, t1: float | None = None,
              progress: Callable[[int, int], None] | None = None) -> Path:
        node = self._ensure()
        ff = find_ffmpeg()
        if not ff:
            raise RenderError("ffmpeg not found", "install it: winget install Gyan.FFmpeg (Windows), brew install ffmpeg (macOS), apt install ffmpeg (Linux)")
        out = Path(out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        bpath = self._write_bundle(bundle)
        cmd = [node, str(ENGINE_JS / "run.js"), "video", bpath, str(out), "--scale", str(scale), "--ffmpeg", ff, "--t0", str(t0)]
        if fps:
            cmd += ["--fps", str(fps)]
        if t1 is not None:
            cmd += ["--t1", str(t1)]
        import re
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ENGINE_JS)
            tail = []
            for line in p.stdout:
                m = re.match(r"frame (\d+)/(\d+)", line)
                if m and progress:
                    progress(int(m.group(1)), int(m.group(2)))
                elif not m:
                    tail.append(line.strip())
            p.wait()
        finally:
            os.unlink(bpath)
        if p.returncode != 0:
            raise RenderError("video render failed", " ".join(tail[-3:]))
        return out


def default_backend() -> RenderBackend:
    return NodeBackend()


def locate(bundle: dict, scene: str, local_t: float) -> float:
    """scene-local time -> bundle-global time"""
    t = 0.0
    for s in bundle["scenes"]:
        if s["id"] == scene:
            return t + local_t
        t += timing.scene_duration(s)
    raise StoreError(f"scene '{scene}' not in bundle")
