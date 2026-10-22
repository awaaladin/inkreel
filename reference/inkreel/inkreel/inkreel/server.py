"""Local preview server: serves the web player and streams live project updates (SSE)."""
from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

WEB = Path(__file__).resolve().parent.parent / "web"


class Hub:
    """Thread-safe fan-out of events to SSE clients."""

    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = asyncio.Queue()
        with self.lock:
            self.clients.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients = [(l, x) for l, x in self.clients if x is not q]

    def broadcast(self, ev):
        with self.lock:
            cl = list(self.clients)
        for loop, q in cl:
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except RuntimeError:
                pass

    @property
    def count(self):
        return len(self.clients)


def create_app(project, hub, log=print):
    app = FastAPI(title="Inkreel")

    @app.middleware("http")
    async def nocache(request, call_next):
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    app.mount("/web", StaticFiles(directory=str(WEB)), name="web")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/project")
    def get_project():
        with project.lock:
            return JSONResponse({"version": project.version, "project": project.data})

    @app.get("/api/events")
    async def events():
        q = hub.subscribe()

        async def gen():
            yield "retry: 1000\n\n"
            yield f"data: {json.dumps({'type': 'project', 'version': project.version})}\n\n"
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

    @app.post("/api/upload")
    async def upload(request: Request, name: str = "recording.webm"):
        data = await request.body()
        safe = "".join(c for c in name if c.isalnum() or c in "._-") or "recording.webm"
        out = project.root / "exports" / safe
        out.write_bytes(data)
        msg = f"saved {out.relative_to(project.root)} ({len(data) // 1024} KB)"
        if safe.endswith(".webm") and shutil.which("ffmpeg"):
            mp4 = out.with_suffix(".mp4")

            def conv():
                r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                    "-crf", "18", str(mp4)], capture_output=True)
                hub.broadcast({"type": "log", "text": f"converted to {mp4.name}" if r.returncode == 0 else "mp4 conversion failed"})
                log(f"recording saved: {mp4 if r.returncode == 0 else out}")
            threading.Thread(target=conv, daemon=True).start()
        else:
            log(f"recording saved: {out}")
        hub.broadcast({"type": "log", "text": msg})
        return {"ok": True, "path": str(out)}

    return app


def free_port(start):
    for p in range(start, start + 30):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("no free port found")


def start_server(project, hub, port=8765, log=print):
    import uvicorn

    port = free_port(port)
    config = uvicorn.Config(create_app(project, hub, log), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return server, port
