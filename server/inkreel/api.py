"""FastAPI app: REST + SSE for the studio, CLI and tests. Serves the studio build and the engine files."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ops as O
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


class ExportRequest(BaseModel):
    episode: str | None = None
    scene: str | None = None
    fps: float | None = None
    scale: float = 1.0
    name: str | None = None


def _err(e: Exception) -> HTTPException:
    code = 404 if "no series" in str(e) or "no scene" in str(e) or "no episode" in str(e) else 400
    return HTTPException(code, {"error": str(e), "hint": getattr(e, "hint", "")})


def create_app(store: Store, hub: Hub | None = None) -> FastAPI:
    hub = hub or Hub()
    store.listeners.append(hub.broadcast)
    app = FastAPI(title="Inkreel")
    app.state.store, app.state.hub = store, hub
    backend = render.default_backend()

    @app.middleware("http")
    async def nocache(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/api"):
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
        actions = {f[:-5]: tx.read(f"series/{sid}/libraries/actions/{f}") for f in tx.list(f"series/{sid}/libraries/actions")}
        eps = []
        for eid in s["episodes"]:
            ep = tx.read(f"series/{sid}/episodes/{eid}/episode.json")
            scenes = []
            for scn in ep["scenes"]:
                sc = tx.read(f"series/{sid}/episodes/{eid}/scenes/{scn}.json")
                scenes.append({"id": scn, "name": sc.get("name", scn), "duration": timing.scene_duration(sc),
                               "background": sc["background"], "cast": list(sc["actors"])})
            eps.append({**ep, "scene_info": scenes, "duration": sum(x["duration"] for x in scenes)})
        return {"series": s, "style": tx.read(f"series/{sid}/style.json"), "characters": chars, "custom_actions": actions,
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
            r = store.undo(sid)
        except StoreError as e:
            raise _err(e)
        return {"undone": r, "rev": store.rev(sid)}

    @app.post("/api/series/{sid}/redo")
    def redo(sid: str):
        sess(sid)
        try:
            r = store.redo(sid)
        except StoreError as e:
            raise _err(e)
        return {"redone": r, "rev": store.rev(sid)}

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

    @app.get("/api/series/{sid}/snapshots/{a}/diff")
    def diff(sid: str, a: str, b: str | None = None):
        sess(sid)
        try:
            return store.diff_snapshots(sid, a, b)
        except StoreError as e:
            raise _err(e)

    # ------------------------------------------------------------------ render
    @app.get("/api/series/{sid}/still.png")
    def still(sid: str, scene: str, t: float = 0.0, scale: float = 0.5, episode: str | None = None):
        sess(sid)
        try:
            b = render.compile_bundle(store, sid, episode, scene)
            out = store.root / ".inkreel" / "cache" / f"{sid}-{scene}-{store.rev(sid)}-{t:.2f}-{scale}.png"
            if not out.exists():
                backend.still(b, t, out, scale)
            return FileResponse(out, media_type="image/png")
        except (StoreError, render.RenderError) as e:
            raise _err(e)

    def _run_job(job_id: int, sid: str, req: ExportRequest):
        def upd(**kw):
            sets = ", ".join(f"{k}=?" for k in kw)
            store.db.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*kw.values(), job_id))
            store.db.commit()
            hub.broadcast({"type": "job", "id": job_id, **kw})
        try:
            upd(state="running")
            b = render.compile_bundle(store, sid, req.episode, req.scene)
            name = req.name or "-".join(x for x in (sid, req.episode, req.scene) if x) + ".mp4"
            out = store.root / "exports" / name
            backend.video(b, out, fps=req.fps, scale=req.scale, progress=lambda i, n: upd(progress=i / max(1, n)))
            upd(state="done", progress=1.0, out=str(out))
        except Exception as e:
            upd(state="error", error=str(e))

    @app.post("/api/series/{sid}/export")
    def export(sid: str, req: ExportRequest):
        sess(sid)
        with store.lock:
            cur = store.db.execute("INSERT INTO jobs(series,kind,spec,state,ts) VALUES(?,?,?,?,?)", (sid, "export", req.model_dump_json(), "queued", time.time()))
            store.db.commit()
        threading.Thread(target=_run_job, args=(cur.lastrowid, sid, req), daemon=True).start()
        return {"job": cur.lastrowid}

    @app.get("/api/jobs")
    def jobs():
        rows = store.db.execute("SELECT id,series,kind,state,progress,out,error FROM jobs ORDER BY id DESC LIMIT 50").fetchall()
        return {"jobs": [dict(zip(("id", "series", "kind", "state", "progress", "out", "error"), r)) for r in rows]}

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
    app.mount("/libraries", StaticFiles(directory=str(REPO / "libraries")), name="libraries")
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
