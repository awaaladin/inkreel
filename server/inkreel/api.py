"""FastAPI app: REST + SSE for the studio. Serves the studio build and the engine files.

Rendering happens in the browser (one engine for preview and recording); the server stores the project, applies ops,
keeps history, and turns recordings into MP4 with ffmpeg.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import render, timing
from .session import Session
from .store import Store, StoreError

REPO = Path(__file__).resolve().parents[2]
STUDIO_DIST = REPO / "studio" / "dist"


class Hub:
    """Thread-safe fan-out of store events to SSE clients."""

    def __init__(self):
        self.clients: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self.lock = threading.Lock()

    def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        with self.lock:
            self.clients.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients = [(l, x) for l, x in self.clients if x is not q]

    def broadcast(self, ev: dict):
        with self.lock:
            cl = list(self.clients)
        for loop, q in cl:
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except RuntimeError:
                pass


class OpItem(BaseModel):
    name: str
    args: dict = {}


class OpsRequest(BaseModel):
    ops: list[OpItem]
    src: str = "user"
    label: str = "studio edit"
    episode: str | None = None


def _err(e: Exception) -> HTTPException:
    code = 404 if any(k in str(e) for k in ("no series", "no scene", "no episode")) else 400
    return HTTPException(code, {"error": str(e), "hint": getattr(e, "hint", "")})


def _safe(name: str, default: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return s or default


def create_app(store: Store, hub: Hub | None = None) -> FastAPI:
    hub = hub or Hub()
    store.listeners.append(hub.broadcast)
    app = FastAPI(title="Inkreel")
    app.state.store, app.state.hub = store, hub
    exports = store.root / "exports"
    exports.mkdir(exist_ok=True)
    audio_dir = store.root / "audio"
    audio_dir.mkdir(exist_ok=True)

    @app.middleware("http")
    async def nocache(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith(("/api", "/engine", "/exports", "/audio")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def sess(sid: str, eid: str | None = None) -> Session:
        try:
            return Session(store, sid, eid)
        except StoreError as e:
            raise _err(e)

    # ------------------------------------------------------------------ read
    @app.get("/api/workspace")
    def workspace():
        ws = json.loads((store.root / "workspace.json").read_text(encoding="utf-8"))
        return {**ws, "root": str(store.root)}

    @app.get("/api/series/{sid}")
    def series(sid: str):
        sess(sid)
        tx = store.reader()
        s = tx.read(f"series/{sid}/series.json")
        chars = {f[:-5]: tx.read(f"series/{sid}/libraries/characters/{f}") for f in tx.list(f"series/{sid}/libraries/characters")}
        eps = []
        for eid in s["episodes"]:
            ep = tx.read(f"series/{sid}/episodes/{eid}/episode.json")
            scenes = []
            for scn in ep["scenes"]:
                sc = tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json")
                scenes.append({"id": scn, "name": sc.get("name", scn), "duration": timing.scene_duration(sc),
                               "background": sc["background"], "cast": list(sc["actors"])})
            eps.append({**ep, "scene_info": scenes, "duration": sum(x["duration"] for x in scenes)})
        return {"series": s, "style": tx.read(f"series/{sid}/style.json"), "characters": chars,
                "bible": tx.read(f"series/{sid}/bible.md", {"_text": ""})["_text"], "episodes": eps, "rev": store.rev(sid)}

    @app.get("/api/series/{sid}/scene/{scn}")
    def scene(sid: str, scn: str):
        sess(sid)
        tx = store.reader()
        for eid in tx.read(f"series/{sid}/series.json")["episodes"]:
            if scn in tx.read(f"series/{sid}/episodes/{eid}/episode.json")["scenes"]:
                return {"episode": eid, "scene": tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json"), "rev": store.rev(sid)}
        raise HTTPException(404, {"error": f"no scene '{scn}'", "hint": ""})

    @app.get("/api/series/{sid}/bundle")
    def bundle(sid: str, episode: str | None = None, scene: str | None = None):
        sess(sid)
        try:
            return {"bundle": render.compile_bundle(store, sid, episode, scene), "rev": store.rev(sid)}
        except StoreError as e:
            raise _err(e)

    @app.get("/api/library")
    def library():
        from . import vocab as V
        return {"actions": V.builtin_actions(), "stances": V.builtin()["stances"], "emotions": V.builtin()["emotions"],
                "vocab": {"backgrounds": V.BACKGROUNDS, "times": V.TIMES, "props": V.PROPS, "fx": V.FX_KINDS, "weapons": V.WEAPONS,
                          "hair": V.HAIR, "outfits": V.OUTFITS, "builds": V.BUILDS, "joints": V.JOINTS, "eases": V.EASES}}

    @app.get("/api/series/{sid}/lint/{scn}")
    def lint(sid: str, scn: str):
        sess(sid)
        from . import check
        try:
            return {"findings": check.check_scene(store, sid, scn)}
        except StoreError as e:
            raise _err(e)

    # ------------------------------------------------------------------ write
    @app.post("/api/series/{sid}/ops")
    def run_ops(sid: str, req: OpsRequest):
        s = sess(sid, req.episode)
        res = s.run([(o.name, o.args) for o in req.ops], src=req.src, label=req.label)
        return {"results": [{"name": n, "ok": ok, "message": m} for n, ok, m in res], "rev": store.rev(sid)}

    @app.post("/api/series/{sid}/undo")
    def undo(sid: str):
        sess(sid)
        try:
            return {"undone": store.undo(sid), "rev": store.rev(sid)}
        except StoreError as e:
            raise _err(e)

    @app.post("/api/series/{sid}/redo")
    def redo(sid: str):
        sess(sid)
        try:
            return {"redone": store.redo(sid), "rev": store.rev(sid)}
        except StoreError as e:
            raise _err(e)

    @app.get("/api/series/{sid}/history")
    def history(sid: str):
        sess(sid)
        return {"turns": store.history(sid)}

    @app.get("/api/series/{sid}/snapshots")
    def snaps(sid: str):
        sess(sid)
        return {"snapshots": store.snapshots(sid)}

    @app.post("/api/series/{sid}/snapshots")
    def snap(sid: str, body: dict):
        sess(sid)
        return {"id": store.snapshot(sid, str(body.get("name") or time.strftime("snapshot %Y-%m-%d %H:%M")))}

    @app.post("/api/series/{sid}/snapshots/{ref}/restore")
    def restore(sid: str, ref: str):
        sess(sid)
        try:
            return {"rev": store.restore(sid, ref)}
        except StoreError as e:
            raise _err(e)

    # ------------------------------------------------------------------ recordings (browser canvas capture -> mp4 on disk)
    @app.post("/api/recordings")
    async def save_recording(request: Request, name: str = "recording"):
        data = await request.body()
        if len(data) < 1000:
            raise HTTPException(400, {"error": "the recording is empty", "hint": "record for at least a second before stopping"})
        base = _safe(name, "recording") + time.strftime("-%Y%m%d-%H%M%S")
        webm = exports / f"{base}.webm"
        webm.write_bytes(data)
        ff = render.find_ffmpeg()
        if not ff:
            return {"file": webm.name, "url": f"/exports/{webm.name}", "mp4": False,
                    "note": "ffmpeg is not installed, so the recording was saved as WebM (winget install Gyan.FFmpeg to get MP4)"}
        mp4 = exports / f"{base}.mp4"
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                            "-c:a", "aac", "-movflags", "+faststart", str(mp4)], capture_output=True, text=True)
        if r.returncode != 0:
            raise HTTPException(500, {"error": "mp4 conversion failed", "hint": r.stderr.strip()[-300:] + " (the WebM was kept: " + webm.name + ")"})
        webm.unlink(missing_ok=True)
        return {"file": mp4.name, "url": f"/exports/{mp4.name}", "mp4": True, "path": str(mp4)}

    @app.post("/api/audio")
    async def save_audio(request: Request, name: str = "voice", ext: str = "webm"):
        """Voice-actor recordings (made in the studio with the microphone) are stored under the workspace audio/ folder."""
        data = await request.body()
        if len(data) < 500:
            raise HTTPException(400, {"error": "the recording is empty", "hint": "hold the record button while speaking"})
        ext = ext if ext in ("webm", "ogg", "wav", "mp3", "m4a") else "webm"
        fname = f"{_safe(name, 'voice')}-{time.strftime('%Y%m%d-%H%M%S')}.{ext}"
        (audio_dir / fname).write_bytes(data)
        return {"file": fname, "url": f"/audio/{fname}"}

    @app.get("/api/recordings")
    def list_recordings():
        files = sorted((p for p in exports.iterdir() if p.suffix in (".mp4", ".webm")), key=lambda p: p.stat().st_mtime, reverse=True)
        return {"recordings": [{"file": p.name, "url": f"/exports/{p.name}", "mb": round(p.stat().st_size / 1e6, 2)} for p in files[:50]]}

    # ------------------------------------------------------------------ events
    @app.get("/api/events")
    async def events():
        q = hub.subscribe()

        async def gen():
            yield "retry: 1000\n\n"
            try:
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), 15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(ev)}\n\n"
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ static
    app.mount("/engine", StaticFiles(directory=str(REPO / "engine_js")), name="engine")
    app.mount("/exports", StaticFiles(directory=str(exports)), name="exports")
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")
    if STUDIO_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(STUDIO_DIST / "assets")), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = STUDIO_DIST / path
            return FileResponse(f if path and f.is_file() else STUDIO_DIST / "index.html")
    else:
        @app.get("/")
        def no_studio():
            return JSONResponse({"studio": "not built", "hint": "cd studio && npm install && npm run build"})
    return app
