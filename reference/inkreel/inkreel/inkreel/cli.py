"""Inkreel terminal: type what you want animated; watch it appear in the live preview."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    import readline  # noqa: F401  (line editing + history)
except Exception:  # pragma: no cover
    pass

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from . import __version__, ops
from .demo import demo_ops
from .director import DEFAULT_MODEL, Director, DirectorError
from .server import Hub, start_server
from .state import Project

ROOT = Path(__file__).resolve().parent.parent
ACCENT = "#e8a23c"
TEAL = "#2fb5a0"
console = Console(highlight=False)

HELP = f"""[bold]Just type what you want.[/bold] Examples:
  [{TEAL}]make a 2D beach duel at dusk, Kabi with a big blade vs Ogun with a staff, 12 seconds[/]
  [{TEAL}]make the second hit a knockdown and push the camera in[/]
  [{TEAL}]research how smear frames and impact frames are used in anime fights, then apply it[/]
  [{TEAL}]add a scene where Ogun explains why he betrayed the village, night, campfire[/]

[bold]Commands[/bold]
  /play [scene]        play in the preview (all scenes, or one)
  /export [name.mp4]   render a video file  (options: --scene ID  --fps 24  --scale 1)
  /still <seconds>     save one frame as PNG  (options: --scene ID)
  /status              what is in the project right now
  /scenes              list scenes
  /research <topic>    web research, saved to project notes
  /undo  /redo         step back/forward through director edits
  /demo                add a built-in demo duel (works without an API key)
  /model [name]        show or change the AI model
  /think on|off        extended thinking for harder choreography
  /clear               forget the chat history (project stays)
  /open                open the preview in your browser
  /quit"""


def banner(project, url, director):
    t = Table.grid(padding=(0, 2))
    t.add_row("[bold]project[/]", f"{escape(project.data['meta']['title'])}  [dim]{escape(str(project.path))}[/]")
    t.add_row("[bold]preview[/]", f"[underline]{url}[/]")
    key = "[green]ready[/]" if director.available else "[yellow]no ANTHROPIC_API_KEY (demo/export still work)[/]"
    t.add_row("[bold]director[/]", f"{escape(director.model)}  {key}")
    console.print(Panel(t, title=f"[bold {ACCENT}]INKREEL[/] [dim]v{__version__}[/]", border_style=ACCENT, padding=(1, 2)))
    console.print("[dim]Type what you want animated, or /help.[/]\n")


def tokens(line):
    import shlex
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()


def opt(args, name, default=None):
    if f"--{name}" in args:
        i = args.index(f"--{name}")
        if i + 1 < len(args):
            v = args[i + 1]
            del args[i:i + 2]
            return v
    return default


def ensure_node_deps():
    rd = ROOT / "render"
    if (rd / "node_modules" / "@napi-rs").exists():
        return True
    if not shutil.which("node") or not shutil.which("npm"):
        console.print("[red]Exporting needs Node.js (https://nodejs.org) and ffmpeg. Install them, then try again.[/]")
        return False
    console.print("[dim]First export: installing the renderer (npm install, one time)...[/]")
    r = subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund"], cwd=rd)
    return r.returncode == 0


def run_render(project, out, scene=None, fps=None, scale=1.0, still=None):
    if not ensure_node_deps():
        return False
    cmd = ["node", str(ROOT / "render" / "render.js"), str(project.path), str(out)]
    if scene:
        cmd += ["--scene", scene]
    if fps:
        cmd += ["--fps", str(fps)]
    if scale != 1.0:
        cmd += ["--scale", str(scale)]
    if still is not None:
        cmd += ["--still", str(still)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT / "render")
    if still is not None:
        o = p.communicate()[0]
        ok = p.returncode == 0
        console.print(f"[green]saved {out}[/]" if ok else f"[red]render failed:[/] {escape(o.strip())}")
        return ok
    prog = Progress(TextColumn("[bold]rendering"), BarColumn(), TextColumn("{task.completed}/{task.total} frames"), TimeRemainingColumn(), console=console)
    task = None
    tail = []
    with prog:
        for line in p.stdout:
            m = re.match(r"frame (\d+)/(\d+)", line)
            if m:
                if task is None:
                    task = prog.add_task("r", total=int(m.group(2)))
                prog.update(task, completed=int(m.group(1)))
            else:
                tail.append(line.strip())
    p.wait()
    if p.returncode == 0:
        size = Path(out).stat().st_size / 1e6
        console.print(f"[green]saved[/] {out}  [dim]({size:.1f} MB)[/]")
        return True
    console.print("[red]render failed[/] " + escape(" ".join(tail[-3:])))
    return False


class App:
    def __init__(self, project, director, hub, url):
        self.project, self.director, self.hub, self.url = project, director, hub, url
        self.streaming = False
        director.on_text = self.on_text
        director.on_op = self.on_op
        director.on_search = self.on_search

    # --- director callbacks
    def on_text(self, s):
        if not self.streaming:
            console.print(f"[bold {ACCENT}]director[/] ", end="")
            self.streaming = True
        console.print(escape(s), end="", soft_wrap=True)

    def _endstream(self):
        if self.streaming:
            console.print()
            self.streaming = False

    def on_op(self, name, args, ok, msg):
        self._endstream()
        if ok:
            warn = "WARNING" in msg
            console.print(f"  [{'yellow' if warn else 'green'}]{'!' if warn else '+'}[/] [dim]{escape(name)}[/] {escape(msg)}")
            self.hub.broadcast({"type": "log", "text": msg, "warn": warn})
        else:
            console.print(f"  [red]x[/] [dim]{escape(name)}[/] [red]{escape(msg)}[/]")
            self.hub.broadcast({"type": "log", "text": f"{name}: {msg}", "warn": True})

    def on_search(self, q):
        self._endstream()
        console.print(f"  [{TEAL}]search[/] {escape(q)}")
        self.hub.broadcast({"type": "log", "text": f"searching the web: {q}"})

    # --- commands
    def cmd(self, line):
        parts = tokens(line)
        c, args = parts[0].lower(), parts[1:]
        if c in ("/quit", "/exit", "/q"):
            return False
        if c in ("/help", "/h", "/?"):
            console.print(HELP)
        elif c == "/status":
            console.print(escape(ops.describe(self.project.data)))
        elif c == "/scenes":
            t = Table(show_header=True, header_style="bold")
            for h in ("#", "id", "name", "look", "length"):
                t.add_column(h)
            for i, s in enumerate(self.project.data["scenes"], 1):
                t.add_row(str(i), s["id"], s["name"], f"{s['background']['preset']}/{s['background'].get('time', 'day')}", f"{ops.scene_duration(s):.1f}s")
            console.print(t)
        elif c == "/play":
            self.hub.broadcast({"type": "cmd", "action": "play", "scene": args[0] if args else None})
            console.print(f"[dim]playing in the preview ({self.hub.count} window(s) connected)[/]")
        elif c == "/open":
            webbrowser.open(self.url)
        elif c == "/undo":
            console.print("undone" if self.project.undo() else "[dim]nothing to undo[/]")
        elif c == "/redo":
            console.print("redone" if self.project.redo() else "[dim]nothing to redo[/]")
        elif c == "/demo":
            res = self.project.run_ops(demo_ops())
            bad = [m for ok, m in res if not ok]
            console.print(f"demo added ({len(res) - len(bad)} edits). Press play in the preview, or /export.")
            for m in bad:
                console.print(f"[red]{escape(m)}[/]")
            self.hub.broadcast({"type": "touched", "scene": "demo_duel"})
        elif c == "/model":
            if args:
                self.director.model = args[0]
            console.print(f"model: {self.director.model}")
        elif c == "/think":
            if args:
                self.director.think = args[0].lower() in ("on", "1", "true", "yes")
            console.print(f"extended thinking: {'on' if self.director.think else 'off'}")
        elif c == "/clear":
            self.director.reset_memory()
            console.print("chat memory cleared (the project is untouched)")
        elif c == "/export":
            scene, fps, scale = opt(args, "scene"), opt(args, "fps"), opt(args, "scale", "1")
            name = args[0] if args else f"{self.project.root.name}{'-' + scene if scene else ''}.mp4"
            out = Path(name) if Path(name).is_absolute() else self.project.root / "exports" / name
            if not self.project.data["scenes"]:
                console.print("[yellow]nothing to export yet[/]")
            else:
                run_render(self.project, out, scene=scene, fps=fps, scale=float(scale))
        elif c == "/still":
            scene = opt(args, "scene")
            t = float(args[0]) if args else 1.0
            out = self.project.root / "exports" / f"still-{t:g}.png"
            run_render(self.project, out, scene=scene, still=t)
        elif c == "/research":
            if not args:
                console.print("usage: /research <topic>")
            else:
                self.talk("Use web search to research this: " + " ".join(args) + ". Save what you learn with note_research, then tell me in a few lines how it should "
                          "shape the animation. Do not build or change scenes yet unless the topic clearly asks for it.")
        else:
            console.print(f"[yellow]unknown command {escape(c)}[/]. Try /help")
        return True

    def talk(self, text):
        if not self.director.available:
            console.print("[yellow]No ANTHROPIC_API_KEY found, so I cannot reach the director.[/] Set it and restart:\n"
                          "  export ANTHROPIC_API_KEY=sk-ant-...\n[dim]Meanwhile /demo, /play and /export all work.[/]")
            return
        self.hub.broadcast({"type": "busy", "on": True})
        try:
            self.director.run(text)
            self._endstream()
        except DirectorError as e:
            self._endstream()
            console.print(f"[red]{escape(str(e))}[/]")
        except KeyboardInterrupt:
            self._endstream()
            console.print("[yellow]interrupted (edits so far are kept; /undo reverts them)[/]")
        finally:
            self.hub.broadcast({"type": "busy", "on": False})
        console.print()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inkreel", description="Terminal-driven 2D animation studio")
    ap.add_argument("project", nargs="?", default="my-animation", help="project folder (created if missing)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--think", action="store_true", help="enable extended thinking")
    ap.add_argument("--no-search", action="store_true", help="disable web research")
    a = ap.parse_args(argv)
    if a.no_search:
        os.environ["INKREEL_NO_SEARCH"] = "1"

    project = Project(Path(a.project))
    hub = Hub()
    project.listeners.append(hub.broadcast)
    server, port = start_server(project, hub, a.port, log=lambda m: console.print(f"[dim]{escape(m)}[/]"))
    url = f"http://127.0.0.1:{port}"
    director = Director(project, model=a.model, think=a.think)
    banner(project, url, director)
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    app = App(project, director, hub, url)
    try:
        while True:
            try:
                line = console.input(f"[bold {ACCENT}]ink >[/] ").strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                console.print("[dim](use /quit to exit)[/]")
                continue
            if not line:
                continue
            if line.startswith("/"):
                if not app.cmd(line):
                    break
            else:
                app.talk(line)
    finally:
        server.should_exit = True
    console.print("[dim]saved. bye.[/]")


if __name__ == "__main__":
    main()
