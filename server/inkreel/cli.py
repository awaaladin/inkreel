"""inkreel CLI: scripted commands plus an interactive REPL with a live studio."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import threading
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from . import ops as O
from . import render, sample, timing
from .session import Session
from .store import Store, StoreError

REPO = Path(__file__).resolve().parents[2]
ACCENT, TEAL = "#e8a23c", "#2fb5a0"
console = Console(highlight=False)

HELP = f"""[bold]Just type what you want[/bold] (needs ANTHROPIC_API_KEY), or use commands:
  /series [id]          list or switch series         /episode [id]   list or switch episode
  /scene [id]           list or switch scene          /cast           characters in this series
  /op <name> <json>     run one op directly           /undo /redo     step through history
  /history              recent turns                  /snapshot [name]  /snapshots  /diff <a> [b]  /restore <ref>
  /still <scene> <t>    save a PNG                    /export [--scene id] [--episode id] [--fps N] [--scale S]
  /play                 play in the studio            /lint [scene]   check a scene
  /model [name]  /cost  /help  /quit"""


def default_workspace() -> Path:
    return Path(os.environ.get("INKREEL_WORKSPACE") or (REPO / "workspaces" / "default"))


def open_store(a) -> Store:
    return Store(Path(a.workspace) if a.workspace else default_workspace())


# --------------------------------------------------------------------------- rendering helpers
def run_export(store: Store, sid: str, eid=None, scene=None, fps=None, scale=1.0, name=None) -> Path | None:
    try:
        b = render.compile_bundle(store, sid, eid, scene)
    except StoreError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return None
    out = store.root / "exports" / (name or "-".join(x for x in (sid, eid, scene) if x) + ".mp4")
    prog = Progress(TextColumn("[bold]rendering"), BarColumn(), TextColumn("{task.completed}/{task.total} frames"), TimeRemainingColumn(), console=console)
    task = None
    try:
        with prog:
            def cb(i, n):
                nonlocal task
                if task is None:
                    task = prog.add_task("r", total=n)
                prog.update(task, completed=i)
            render.default_backend().video(b, out, fps=fps, scale=scale, progress=cb)
    except render.RenderError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return None
    console.print(f"[green]saved[/] {out} [dim]({out.stat().st_size / 1e6:.1f} MB)[/]")
    return out


def run_still(store: Store, sid: str, scene: str, t: float, scale=1.0, out: str | None = None) -> Path | None:
    try:
        b = render.compile_bundle(store, sid, None, scene)
        p = Path(out) if out else store.root / "exports" / f"{sid}-{scene}-{t:g}.png"
        render.default_backend().still(b, t, p, scale)
    except (StoreError, render.RenderError) as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return None
    console.print(f"[green]saved[/] {p}")
    return p


# --------------------------------------------------------------------------- REPL
class Repl:
    def __init__(self, store: Store, sid: str, url: str | None = None, hub=None):
        self.store, self.sid, self.url, self.hub = store, sid, url, hub
        self.sess = Session(store, sid)
        self.director = None

    @property
    def eid(self):
        return self.sess.eid

    def prompt(self):
        return f"[bold {ACCENT}]{self.sid}{'/' + self.eid if self.eid else ''} >[/] "

    def ep_ids(self):
        return self.store.reader().read(f"series/{self.sid}/series.json")["episodes"]

    def scene_ids(self, eid=None):
        tx = self.store.reader()
        out = []
        for e in ([eid] if eid else self.ep_ids()):
            out += tx.read(f"series/{self.sid}/episodes/{e}/episode.json")["scenes"]
        return out

    def talk(self, text):
        try:
            from .director import Director  # Phase 2
        except ImportError:
            console.print("[yellow]The AI director is not installed yet in this build.[/] Use /op or /help.")
            return
        if self.director is None:
            self.director = Director(self.store, self.sid, on_text=lambda s: console.print(escape(s), end=""),
                                     on_op=self.on_op)
        try:
            self.director.focus_episode = self.eid
            self.director.run(text)
            console.print()
        except Exception as e:  # DirectorError etc: message already says how to fix
            console.print(f"[red]{escape(str(e))}[/]")

    def on_op(self, name, args, ok, msg):
        warn = "WARNING" in msg
        console.print(f"  [{'red' if not ok else 'yellow' if warn else 'green'}]{'x' if not ok else '!' if warn else '+'}[/] [dim]{escape(name)}[/] {escape(msg)}")

    def cmd(self, line: str) -> bool:
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        c, args = parts[0].lower(), parts[1:]
        s, sid = self.store, self.sid
        if c in ("/quit", "/exit", "/q"):
            return False
        if c in ("/help", "/h", "/?"):
            console.print(HELP)
        elif c == "/series":
            if args:
                self.sid = args[0]
                self.sess = Session(s, self.sid)
            console.print(", ".join(f"[bold]{x}[/]" if x == self.sid else x for x in s.list_series()))
        elif c == "/episode":
            if args:
                if args[0] not in self.ep_ids():
                    console.print(f"[red]no episode '{escape(args[0])}'[/] have: {self.ep_ids()}")
                else:
                    self.sess.eid = args[0]
            tx = s.reader()
            t = Table(show_header=True, header_style="bold")
            for h in ("id", "title", "scenes", "length"):
                t.add_column(h)
            for e in self.ep_ids():
                ep = tx.read(f"series/{self.sid}/episodes/{e}/episode.json")
                dur = sum(timing.scene_duration(tx.read(f"series/{self.sid}/episodes/{e}/scenes/{x}.json")) for x in ep["scenes"])
                t.add_row(("> " if e == self.eid else "  ") + e, ep["title"], str(len(ep["scenes"])), f"{dur:.1f}s")
            console.print(t)
        elif c == "/scene":
            tx = s.reader()
            t = Table(show_header=True, header_style="bold")
            for h in ("episode", "id", "name", "look", "cast", "length"):
                t.add_column(h)
            for e in self.ep_ids():
                for x in tx.read(f"series/{self.sid}/episodes/{e}/episode.json")["scenes"]:
                    sc = tx.read(f"series/{self.sid}/episodes/{e}/scenes/{x}.json")
                    t.add_row(e, x, sc.get("name", ""), f"{sc['background']['preset']}/{sc['background'].get('time', 'day')}", ",".join(sc["actors"]), f"{timing.scene_duration(sc):.1f}s")
            console.print(t)
        elif c == "/cast":
            for cid, ch in __import__("inkreel.render", fromlist=["x"]).compile_bundle(s, sid)["characters"].items():
                console.print(f"  [bold]{cid}[/] {escape(str(ch.get('name', '')))} {ch.get('height')}px {ch.get('weapon', 'none')}")
        elif c == "/op":
            if len(args) < 1:
                console.print("usage: /op <name> <json args>")
            else:
                try:
                    a = json.loads(" ".join(args[1:]) or "{}")
                except json.JSONDecodeError as e:
                    console.print(f"[red]bad JSON: {escape(str(e))}[/]")
                    return True
                for n, ok, m in self.sess.run([(args[0], a)], src="user", label=f"/op {args[0]}"):
                    self.on_op(n, a, ok, m)
        elif c == "/undo":
            try:
                r = s.undo(sid)
                console.print(f"undone: {escape(r['label'])}" if r else "[dim]nothing to undo[/]")
            except StoreError as e:
                console.print(f"[red]{escape(str(e))}[/]")
        elif c == "/redo":
            try:
                r = s.redo(sid)
                console.print(f"redone: {escape(r['label'])}" if r else "[dim]nothing to redo[/]")
            except StoreError as e:
                console.print(f"[red]{escape(str(e))}[/]")
        elif c == "/history":
            for h in s.history(sid, 15):
                console.print(f"  {h['id']:>4} [{h['state']}] {h['src']:<6} {escape(h['label'])} ({h['ops']} ops{', %d failed' % h['failed'] if h['failed'] else ''})")
        elif c == "/snapshot":
            console.print(f"snapshot {s.snapshot(sid, ' '.join(args) or 'snapshot')} saved")
        elif c == "/snapshots":
            for x in s.snapshots(sid):
                console.print(f"  {x['id']:>3} {escape(x['name'])}")
        elif c == "/restore":
            try:
                s.restore(sid, args[0])
                console.print("restored (undo with /undo)")
            except (StoreError, IndexError) as e:
                console.print(f"[red]{escape(str(e) or 'usage: /restore <snapshot id or name>')}[/]")
        elif c == "/diff":
            try:
                d = s.diff_snapshots(sid, args[0], args[1] if len(args) > 1 else None)
            except (StoreError, IndexError) as e:
                console.print(f"[red]{escape(str(e) or 'usage: /diff <a> [b]')}[/]")
                return True
            console.print(f"added {len(d['added'])}, removed {len(d['removed'])}, changed {len(d['changed'])}")
            for scn, sd in d["scenes"].items():
                console.print(f"  {scn}: +{len(sd['added'])} -{len(sd['removed'])} ~{len(sd['changed'])}")
        elif c == "/still":
            if len(args) < 2:
                console.print("usage: /still <scene> <t seconds>")
            else:
                run_still(s, sid, args[0], float(args[1]))
        elif c == "/export":
            scene, ep = _opt(args, "scene"), _opt(args, "episode") or (None if _opt_peek(args, "scene") else self.eid)
            run_export(s, sid, ep, scene, fps=float(_opt(args, "fps") or 0) or None, scale=float(_opt(args, "scale") or 1))
        elif c == "/play":
            if self.hub:
                self.hub.broadcast({"type": "cmd", "action": "play", "scene": args[0] if args else None})
                console.print("[dim]playing in the studio[/]")
            else:
                console.print("[dim]no studio attached[/]")
        elif c == "/lint":
            try:
                from .check import check_scene
            except ImportError:
                console.print("[yellow]lint arrives with the Phase 2 build[/]")
                return True
            for scn in ([args[0]] if args else self.scene_ids(self.eid)):
                for f in check_scene(s, sid, scn):
                    console.print(f"  [{'red' if f['severity'] == 'error' else 'yellow'}]{f['severity']}[/] {scn} t={f.get('t', '-')}: {escape(f['message'])}")
        elif c == "/model":
            if self.director is None and args:
                os.environ["INKREEL_MODEL"] = args[0]
            console.print(f"model: {os.environ.get('INKREEL_MODEL', 'claude-sonnet-5-5')}")
        elif c == "/cost":
            console.print(self.director.cost_line() if self.director else "no director turns yet")
        else:
            console.print(f"[yellow]unknown command {escape(c)}[/]. Try /help")
        return True


def _opt(args, name):
    if f"--{name}" in args:
        i = args.index(f"--{name}")
        if i + 1 < len(args):
            v = args[i + 1]
            del args[i:i + 2]
            return v
    return None


def _opt_peek(args, name):
    return f"--{name}" in args


# --------------------------------------------------------------------------- commands
def cmd_new(a):
    s = open_store(a)
    sid = s.create_series(a.series, a.title)
    console.print(f"[green]created series[/] {sid} in {s.root}")


def cmd_build_sample(a):
    s = open_store(a)
    sample.build(s)
    console.print(f"[green]sample series built[/] ibeno_tides (6 scenes) in {s.root}")


def cmd_still(a):
    s = open_store(a)
    return 0 if run_still(s, a.series, a.scene, float(a.t), a.scale, a.out) else 1


def cmd_export(a):
    s = open_store(a)
    return 0 if run_export(s, a.series, a.episode, a.scene, a.fps, a.scale, a.name) else 1


def cmd_schema(a):
    from . import model as M
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, m in M.MODELS.items():
        (out / f"{name}.schema.json").write_text(json.dumps(m.model_json_schema(by_alias=True), indent=1), encoding="utf-8")
    console.print(f"wrote {len(M.MODELS)} schemas to {out}")


def cmd_serve(a):
    import uvicorn
    from .api import create_app
    s = open_store(a)
    uvicorn.run(create_app(s), host=a.host, port=a.port, log_level="warning")


def cmd_run(a):
    """Batch mode: run a script of /commands, `op name {json}` lines and (with a key) free-text prompts."""
    s = open_store(a)
    repl = Repl(s, a.series)
    fails = 0
    for n, raw in enumerate(Path(a.script).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("op "):
            line = "/op " + line[3:]
        if line.startswith("/"):
            console.print(f"[dim]{n}:[/] {escape(line)}")
            repl.cmd(line)
        else:
            repl.talk(line)
    return 1 if fails else 0


def cmd_open(a):
    import uvicorn
    from .api import Hub, create_app
    s = open_store(a)
    sid = a.series or (s.list_series() or [None])[0]
    if not sid:
        console.print("[yellow]no series yet.[/] Create one: inkreel new <name>   or the sample: inkreel build-sample")
        return 1
    hub = Hub()
    app = create_app(s, hub)
    port = a.port
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/?series={sid}"
    t = Table.grid(padding=(0, 2))
    t.add_row("[bold]workspace[/]", str(s.root))
    t.add_row("[bold]studio[/]", f"[underline]{url}[/]")
    t.add_row("[bold]director[/]", ("[green]ready[/]" if os.environ.get("ANTHROPIC_API_KEY") else "[yellow]no ANTHROPIC_API_KEY (commands still work)[/]"))
    console.print(Panel(t, title=f"[bold {ACCENT}]INKREEL[/]", border_style=ACCENT, padding=(1, 2)))
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    repl = Repl(s, sid, url, hub)
    try:
        while True:
            try:
                line = console.input(repl.prompt()).strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                console.print("[dim](use /quit to exit)[/]")
                continue
            if not line:
                continue
            if line.startswith("/"):
                if not repl.cmd(line):
                    break
            else:
                repl.talk(line)
    finally:
        server.should_exit = True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inkreel", description="Terminal-driven 2D animation studio for whole series")
    ap.add_argument("--workspace", "-w", default=None, help="workspace folder (default: $INKREEL_WORKSPACE or ./workspaces/default)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new", help="create a series")
    p.add_argument("series")
    p.add_argument("--title")
    p.set_defaults(fn=cmd_new)
    p = sp.add_parser("build-sample", help="build the Ibeno Tides sample series")
    p.set_defaults(fn=cmd_build_sample)
    p = sp.add_parser("open", help="open the live studio and the REPL")
    p.add_argument("series", nargs="?")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_open)
    p = sp.add_parser("serve", help="API + studio server only")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_serve)
    p = sp.add_parser("still", help="render one frame")
    p.add_argument("series")
    p.add_argument("scene")
    p.add_argument("t")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_still)
    p = sp.add_parser("export", help="render mp4")
    p.add_argument("series")
    p.add_argument("--episode")
    p.add_argument("--scene")
    p.add_argument("--fps", type=float)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--name")
    p.set_defaults(fn=cmd_export)
    p = sp.add_parser("run", help="run a script file of /commands and ops")
    p.add_argument("series")
    p.add_argument("script")
    p.set_defaults(fn=cmd_run)
    p = sp.add_parser("schema", help="export JSON Schemas from the Pydantic models")
    p.add_argument("--out", default=str(REPO / "schemas"))
    p.set_defaults(fn=cmd_schema)
    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except StoreError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
